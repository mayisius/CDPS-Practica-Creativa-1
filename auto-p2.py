#!/usr/bin/env python3

import os
import sys
import subprocess
import shutil
import json
import logging


def init_logging(debug_enabled):
    """
    RQ7: Inicializa el logger. Si debug=true en el JSON,
    el nivel será DEBUG; si no, será INFO.
    """
    log = logging.getLogger("auto-p2")
    log.setLevel(logging.DEBUG if debug_enabled else logging.INFO)

    handler = logging.StreamHandler()
    formatter = logging.Formatter("%(asctime)s - %(levelname)s - %(message)s",
                                  "%Y-%m-%d %H:%M:%S")
    handler.setFormatter(formatter)

    # evitar añadir múltiples handlers si init_logging() se llama 2 veces
    if not log.handlers:
        log.addHandler(handler)

    return log


from lib_auto_p2 import VM, Red

# ---------------------------
# Constantes (RQ1)
# ---------------------------

BASE_IMAGE = "cdps-vm-base-pc1.qcow2"      # Debe estar en el directorio (RQ1)
XML_TEMPLATE = "plantilla-vm-pc1.xml"      # Debe estar en el directorio (RQ1)


# ---------------------------
# Configuración (RQ3)
# ---------------------------

def load_config():
    """
    RQ3 + RQ7:
    Lee auto-p2.json, valida num_servers y obtiene 'debug'.
    NO inicializa logging (eso lo hace main()).
    Devuelve el diccionario completo.
    """

    config_file = "auto-p2.json"

    if not os.path.exists(config_file):
        logging.getLogger("auto-p2").error(
            f"ERROR (RQ3): No se encuentra el fichero de configuración '{config_file}'."
        )
        sys.exit(1)

    try:
        with open(config_file, "r") as f:
            config = json.load(f)
    except json.JSONDecodeError as e:
        logging.getLogger("auto-p2").error(
            f"ERROR (RQ3): El fichero '{config_file}' no contiene JSON válido."
        )
        logging.getLogger("auto-p2").error(f"Detalle: {e}")
        sys.exit(1)

    # Validación de num_servers
    if "num_servers" not in config:
        logging.getLogger("auto-p2").error(
            "ERROR (RQ3): Falta el campo 'num_servers' en auto-p2.json."
        )
        sys.exit(1)

    num_servers = config["num_servers"]

    if not isinstance(num_servers, int):
        logging.getLogger("auto-p2").error(
            "ERROR (RQ3): 'num_servers' debe ser un número entero."
        )
        sys.exit(1)

    if not (1 <= num_servers <= 5):
        logging.getLogger("auto-p2").error(
            "ERROR (RQ3): 'num_servers' debe estar entre 1 y 5."
        )
        sys.exit(1)

    # Validar debug
    debug = config.get("debug", False)
    if not isinstance(debug, bool):
        logging.getLogger("auto-p2").error(
            "ERROR (RQ7): El campo 'debug' debe ser true/false."
        )
        sys.exit(1)

    # Mensaje informativo (ya con logger global configurado por main)
    log = logging.getLogger("auto-p2")
    log.info(f"Configuración cargada (RQ3/RQ7): num_servers={num_servers}, debug={debug}")

    return config

# ---------------------------
# Creación de imágenes qcow2 (RQ5)
# ---------------------------

def create_images(num_servers):
    """
    RQ5:
    Crea las imágenes de las VMs como ficheros de diferencias (qcow2)
    respecto de la imagen base, dentro del directorio 'images/'.

    Crea:
    - lb.qcow2  (balanceador)
    - c1.qcow2  (cliente)
    - s1.qcow2 ... sN.qcow2 (servidores web, N=num_servers)
    """
    os.makedirs("images", exist_ok=True)

    vm_names = ["lb", "c1"]
    for i in range(1, num_servers + 1):
        vm_names.append(f"s{i}")

    print(f"Creando imágenes qcow2 de diferencias para: {', '.join(vm_names)}")

    base_image_path = os.path.abspath(BASE_IMAGE)

    for name in vm_names:
        image_path = os.path.join("images", f"{name}.qcow2")

        if os.path.exists(image_path):
            print(f"  [AVISO] La imagen {image_path} ya existe. Se omite su creación.")
            continue

        cmd = [
            "qemu-img",
            "create",
            "-f", "qcow2",
            "-F", "qcow2",
            "-b", base_image_path,
            image_path
        ]

        print(f"  [CMD] {' '.join(cmd)}")
        ret = subprocess.call(cmd)

        if ret != 0:
            print(f"  [ERROR] Falló la creación de la imagen {image_path}")
        else:
            print(f"  [OK] Imagen creada: {image_path}")


def configure_vm_hostname(vm_name, hostname):
    """
    RQ4: Configura el hostname de la VM usando virt-customize.
    """
    image_path = os.path.join("images", f"{vm_name}.qcow2")
    print(f"Configurando hostname de {vm_name} -> {hostname}")
    cmd = ["sudo", "virt-customize", "-a", image_path, "--hostname", hostname]
    ret = subprocess.call(cmd)
    if ret != 0:
        print(f"[ERROR] Falló la configuración de hostname para {vm_name}")


def configure_vm_interfaces(vm_name, content):
    """
    RQ4: Escribe /etc/network/interfaces dentro de la imagen
    usando virt-copy-in.

    'content' es el contenido completo del fichero.
    """
    image_path = os.path.join("images", f"{vm_name}.qcow2")
    tmp_path = "/tmp/interfaces"   # nombre fijo para que dentro sea 'interfaces'

    print(f"Configurando /etc/network/interfaces de {vm_name}")

    # 1) Crear fichero temporal en el host con nombre 'interfaces'
    with open(tmp_path, "w") as f:
        f.write(content)

    # 2) Copiarlo dentro de la imagen, al directorio correcto
    #    Resultado dentro de la VM: /etc/network/interfaces
    cmd = ["sudo", "virt-copy-in", "-a", image_path, tmp_path, "/etc/network"]
    ret = subprocess.call(cmd)
    if ret != 0:
        print(f"[ERROR] Falló la configuración de interfaces para {vm_name}")
    else:
        print(f"[OK] Configuración de red aplicada a {vm_name}")

    # 3) Borrar el temporal del host
    try:
        os.remove(tmp_path)
    except FileNotFoundError:
        pass


def configure_lb_router():
    """
    RQ4: Activa el reenvío de IP en el balanceador para que funcione como router.
    Edita /etc/sysctl.conf en la imagen de lb usando virt-edit.
    """
    image_path = os.path.join("images", "lb.qcow2")
    print("Activando ip_forward en lb (RQ4)...")

    cmd = [
        "sudo", "virt-edit",
        "-a", image_path,
        "/etc/sysctl.conf",
        "-e", "s/#net.ipv4.ip_forward=1/net.ipv4.ip_forward=1/"
    ]
    ret = subprocess.call(cmd)
    if ret != 0:
        print("[ERROR] Falló la activación de ip_forward en lb")
    else:
        print("[OK] ip_forward activado en lb")


def configure_all_vms(num_servers):
    """
    RQ4:
    - Configura hostname y red de lb, c1 y s1..sN.
    - Configura lb para que actúe como router (ip_forward).

    Direccionamiento según escenario PC1:
      RED1: 192.168.1.0/26
        lb-eth0  -> 192.168.1.1
        c1-eth0  -> 192.168.1.11
      RED2: 192.168.1.64/26
        lb-eth1  -> 192.168.1.65
        s1-eth0  -> 192.168.1.101
        s2-eth0  -> 192.168.1.102
        s3-eth0  -> 192.168.1.103
        (y si hay más: s4=192.168.1.104, s5=192.168.1.105)
    """

    print("Configurando hostname y red en las VMs (RQ4)...")

    # -------- LB --------
    lb_ifaces = """auto lo
iface lo inet loopback

auto eth0
iface eth0 inet static
  address 192.168.1.1
  netmask 255.255.255.192

auto eth1
iface eth1 inet static
  address 192.168.1.65
  netmask 255.255.255.192
"""

    configure_vm_hostname("lb", "lb")
    configure_vm_interfaces("lb", lb_ifaces)
    configure_lb_router()

    # -------- c1 --------
    c1_ifaces = """auto lo
iface lo inet loopback

auto eth0
iface eth0 inet static
  address 192.168.1.11
  netmask 255.255.255.192
  gateway 192.168.1.1
  dns-nameservers 8.8.8.8
"""

    configure_vm_hostname("c1", "c1")
    configure_vm_interfaces("c1", c1_ifaces)

    # -------- servidores s1..sN --------
    for i in range(1, num_servers + 1):
        # s1 -> 101, s2 -> 102, etc.
        ip_last_octet = 100 + i
        ip_addr = f"192.168.1.{ip_last_octet}"

        s_ifaces = f"""auto lo
iface lo inet loopback

auto eth0
iface eth0 inet static
  address {ip_addr}
  netmask 255.255.255.192
  gateway 192.168.1.65
  dns-nameservers 8.8.8.8
"""

        vm_name = f"s{i}"
        configure_vm_hostname(vm_name, vm_name)
        configure_vm_interfaces(vm_name, s_ifaces)

    print("Configuración de RQ4 aplicada a todas las VMs.\n")


# ---------------------------
# Comprobación de entorno (RQ1)
# ---------------------------

def check_environment(orden):
    """
    Comprueba que el directorio cumple RQ1:
    - Existen la imagen base y la plantilla XML.
    - Si la orden es 'define', no debe haber restos de ejecuciones previas
      (otros .qcow2 y .xml en el directorio principal).
    """

    print("Comprobando entorno (RQ1)...")

    if not os.path.exists(BASE_IMAGE):
        print(f"ERROR (RQ1): No se encuentra la imagen base '{BASE_IMAGE}'.")
        print("Asegúrate de que está en el directorio actual antes de ejecutar el script.")
        sys.exit(1)
    else:
        print(f"Imagen base encontrada: {BASE_IMAGE}")

    if not os.path.exists(XML_TEMPLATE):
        print(f"ERROR (RQ1): No se encuentra la plantilla XML '{XML_TEMPLATE}'.")
        print("Debe estar en el directorio de trabajo.")
        sys.exit(1)
    else:
        print(f"Plantilla XML encontrada: {XML_TEMPLATE}")

    if orden == "define":
        for file in os.listdir("."):
            if file.endswith(".qcow2") and file != BASE_IMAGE:
                print(f"ERROR (RQ1): Se encontró un fichero qcow2 inesperado: {file}")
                print("El directorio debe estar limpio antes de 'define'.")
                sys.exit(1)

        for file in os.listdir("."):
            if file.endswith(".xml") and file != XML_TEMPLATE:
                print(f"ERROR (RQ1): Se encontró un fichero XML inesperado: {file}")
                print("El directorio debe estar limpio antes de 'define'.")
                sys.exit(1)

    print("Entorno correcto. RQ1 cumplido.\n")


# ---------------------------
# Órdenes principales (RQ2, RQ3, RQ5, RQ8, RQ9)
# ---------------------------

def define():
    """
    RQ2 + RQ3 + RQ5 + RQ8 + RQ9:
    - Lee la configuración (num_servers) de auto-p2.json (RQ3)
    - Crea las imágenes qcow2 de diferencias (RQ5)
    - Crea las redes OVS LAN1 y LAN2 (RQ9)
    - Genera los XML y define las VMs con virsh (RQ8)
    """
    print("Ejecutando 'define' (RQ2).")

    config = load_config()
    num_servers = config["num_servers"]

    print(f"Usando num_servers = {num_servers} (RQ3).")

    create_images(num_servers)

    # RQ4: configurar hostname, red e ip_forward en las VMs
    configure_all_vms(num_servers)

    # RQ9: redes OVS
    print("Creando redes virtuales OVS (RQ9)...")
    lan1 = Red("LAN1")
    lan2 = Red("LAN2")
    lan1.create_net()
    lan2.create_net()

    # RQ8: generar XMLs y definir VMs
    def img(name):
        return os.path.join("images", f"{name}.qcow2")

    vms_def = []

    vms_def.append({
        "name": "lb",
        "image": img("lb"),
        "interfaces": [
            {"bridge": "LAN1"},
            {"bridge": "LAN2"},
        ],
    })

    vms_def.append({
        "name": "c1",
        "image": img("c1"),
        "interfaces": [
            {"bridge": "LAN1"},
        ],
    })

    for i in range(1, num_servers + 1):
        vms_def.append({
            "name": f"s{i}",
            "image": img(f"s{i}"),
            "interfaces": [
                {"bridge": "LAN2"},
            ],
        })

    os.makedirs("xmls", exist_ok=True)

    print("Generando XMLs y definiendo VMs (RQ8)...")

    for vm_info in vms_def:
        vm = VM(vm_info["name"])
        vm.define_vm(
            template_xml_path=XML_TEMPLATE,
            image_path=vm_info["image"],
            interfaces=vm_info["interfaces"],
            xml_dir="xmls",
        )


def start():
    """
    RQ2 + RQ8:
    - Arranca las VMs usando los métodos de la clase VM.
    - Abre las consolas en terminales separados.
    """

    print("Ejecutando 'start' (RQ2).")

    config = load_config()
    num_servers = config["num_servers"]

    vm_names = ["lb", "c1"] + [f"s{i}" for i in range(1, num_servers + 1)]
    vms = [VM(name) for name in vm_names]

    print("\nArrancando máquinas virtuales...")
    for vm in vms:
        vm.start_vm()

    print("\nAbriendo consolas en terminales separados...")
    for vm in vms:
        vm.show_console_vm()

    print("\nTodas las máquinas arrancadas y consolas abiertas.\n")


def stop():
    """
    RQ2 + RQ8:
    - Detiene las VMs de forma ordenada usando VM.stop_vm()
    """
    print("Ejecutando 'stop' (RQ2).")

    config = load_config()
    num_servers = config["num_servers"]

    vm_names = ["lb", "c1"] + [f"s{i}" for i in range(1, num_servers + 1)]
    vms = [VM(name) for name in vm_names]

    print("Deteniendo máquinas virtuales (virsh shutdown)...")
    for vm in vms:
        vm.stop_vm()

    print("stop completado.\n")


def undefine():
    """
    RQ2 + RQ8 (+ RQ9 parcialmente):
    - Elimina las VMs con VM.undefine_vm()
    - Borra los ficheros generados (images/, xmls/)
    - Elimina las redes OVS LAN1 y LAN2
    """
    print("Ejecutando 'undefine' (RQ2).")

    config = load_config()
    num_servers = config["num_servers"]

    vm_names = ["lb", "c1"] + [f"s{i}" for i in range(1, num_servers + 1)]
    vms = [VM(name) for name in vm_names]

    print("Eliminando VMs (virsh undefine)...")
    for vm in vms:
        vm.undefine_vm()

    print("Borrando ficheros generados (images/, xmls/)...")
    shutil.rmtree("images", ignore_errors=True)
    shutil.rmtree("xmls", ignore_errors=True)

    print("Eliminando redes virtuales OVS (RQ9)...")
    lan1 = Red("LAN1")
    lan2 = Red("LAN2")
    lan1.destroy_net()
    lan2.destroy_net()

    print("Escenario liberado (undefine completado).")



# ---------------------------
# Main (RQ2)
# ---------------------------

def main():
    # ========== RQ7: Leer config y activar logging ==========
    if not os.path.exists("auto-p2.json"):
        print("ERROR (RQ3): No se encuentra auto-p2.json")
        sys.exit(1)

    # Primero cargamos la configuración SIN logger activo
    raw_config = load_config()

    # Ahora activamos logging según debug
    log = init_logging(raw_config.get("debug", False))

    # ========== RQ2: validar orden ==========
    if len(sys.argv) < 2:
        log.error("Debes indicar una orden: define | start | stop | undefine")
        sys.exit(1)

    orden = sys.argv[1]

    if orden not in ("define", "start", "stop", "undefine"):
        log.error(f"Orden no válida: {orden}")
        log.info("Órdenes válidas: define | start | stop | undefine")
        sys.exit(1)

    log.info(f"Orden recibida (RQ2): {orden}")

    # ========== RQ1: comprobar entorno ==========
    check_environment(orden)

    # ========== Ejecutar comando ==========
    if orden == "define":
        define()
    elif orden == "start":
        start()
    elif orden == "stop":
        stop()
    elif orden == "undefine":
        undefine()

if __name__ == "__main__":
    main()
 