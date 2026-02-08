import os
import subprocess
import logging
import shutil
from lxml import etree

log = logging.getLogger("auto-p2")


class VM:
    def __init__(self, name):
        self.name = name
        log.debug(f"init VM {self.name}")

    def define_vm(self, template_xml_path, image_path, interfaces, xml_dir="xmls"):
        """
        Crea el XML de la VM a partir de una plantilla y la define con virsh.

        - template_xml_path: ruta a plantilla-vm-pc1.xml
        - image_path: ruta al qcow2 de esta VM (p.ej. images/s1.qcow2)
        - interfaces: lista de diccionarios, ej.:
              [{"bridge": "LAN1"}, {"bridge": "LAN2"}]
        - xml_dir: directorio donde guardar los XML (por defecto 'xmls')
        """

        log.debug(f"Definiendo VM {self.name} con imagen {image_path}")

        os.makedirs(xml_dir, exist_ok=True)

        tree = etree.parse(template_xml_path)
        root = tree.getroot()

        # <name>
        name_elem = root.find("name")
        if name_elem is not None:
            name_elem.text = self.name
        else:
            log.error("No se encontró el elemento <name> en la plantilla XML.")

        # Disco principal -> ruta absoluta a la imagen qcow2
        disk_source = root.find(".//devices/disk[@device='disk']/source")
        if disk_source is not None:
            abs_image_path = os.path.abspath(image_path)
            disk_source.set("file", abs_image_path)
        else:
            log.error("No se encontró el disco principal en la plantilla XML.")

        # ---- Interfaces de red ----
        # En lugar de reutilizar solo las interfaces que haya en la plantilla,
        # borramos todas las existentes y creamos nuevas según la lista
        # 'interfaces' que nos pasa auto-p2.py.
        devices = root.find("devices")
        if devices is None:
            log.error("No se encontró el nodo <devices> en la plantilla XML.")
        else:
            # 1) Borrar todas las interfaces actuales
            for old_if in devices.findall("interface"):
                devices.remove(old_if)

            # 2) Crear una interfaz por cada entrada en 'interfaces'
            for iface_cfg in interfaces:
                bridge_name = iface_cfg.get("bridge", "LAN1")

                iface_el = etree.SubElement(devices, "interface")
                iface_el.set("type", "bridge")

                src_el = etree.SubElement(iface_el, "source")
                src_el.set("bridge", bridge_name)

                model_el = etree.SubElement(iface_el, "model")
                model_el.set("type", "virtio")

                vport_el = etree.SubElement(iface_el, "virtualport")
                vport_el.set("type", "openvswitch")


        xml_path = os.path.join(xml_dir, f"{self.name}.xml")
        tree.write(xml_path, pretty_print=True)
        log.debug(f"XML generado para {self.name}: {xml_path}")

        cmd = ["sudo", "virsh", "define", xml_path]
        log.debug("Ejecutando: " + " ".join(cmd))
        ret = subprocess.call(cmd)

        if ret != 0:
            print(f"[ERROR] Falló 'virsh define' para {self.name}")
        else:
            print(f"[OK] VM definida: {self.name} (XML: {xml_path})")

    # --------- Métodos que pide RQ8 ---------

    def start_vm(self):
        """Arranca la VM usando virsh start."""
        cmd = ["sudo", "virsh", "start", self.name]
        log.debug("Ejecutando: " + " ".join(cmd))
        ret = subprocess.call(cmd)
        if ret != 0:
            print(f"[ERROR] No se pudo arrancar la VM {self.name}")
        else:
            print(f"[OK] VM arrancada: {self.name}")

    def show_console_vm(self):
        """
        Abre la consola de la VM en un terminal nuevo.
        Usa xterm si existe; si no, gnome-terminal.
        """
        use_xterm = shutil.which("xterm") is not None
        if use_xterm:
            cmd = f'xterm -e "sudo virsh console {self.name}" &'
        else:
            cmd = f'gnome-terminal -- bash -c "sudo virsh console {self.name}" &'

        log.debug("Ejecutando: " + cmd)
        subprocess.call(cmd, shell=True)

    def stop_vm(self):
        """Apaga la VM ordenadamente con virsh shutdown."""
        cmd = ["sudo", "virsh", "shutdown", self.name]
        log.debug("Ejecutando: " + " ".join(cmd))
        ret = subprocess.call(cmd)
        if ret != 0:
            print(f"[AVISO] No se pudo apagar la VM {self.name} (puede que ya esté apagada).")
        else:
            print(f"[OK] Orden de apagado enviada a {self.name}.")

    def undefine_vm(self):
        """Libera la definición de la VM con virsh undefine."""
        cmd = ["sudo", "virsh", "undefine", self.name]
        log.debug("Ejecutando: " + " ".join(cmd))
        ret = subprocess.call(cmd)
        if ret != 0:
            print(f"[AVISO] No se pudo undefinear la VM {self.name}.")
        else:
            print(f"[OK] VM undefineada: {self.name}")


class Red:
    def __init__(self, name):
        self.name = name
        log.debug(f"init Red {self.name}")

    def create_net(self):
        """
        Crea un bridge OVS con nombre 'self.name' usando ovs-vsctl.
        Equivalente a: sudo ovs-vsctl add-br <nombre>
        """
        cmd = ["sudo", "ovs-vsctl", "add-br", self.name]
        log.debug("Ejecutando: " + " ".join(cmd))
        ret = subprocess.call(cmd)

        if ret != 0:
            print(f"[ERROR] Falló la creación de la red {self.name}")
        else:
            print(f"[OK] Red creada: {self.name}")

    def destroy_net(self):
        """
        Elimina el bridge OVS con nombre 'self.name'.
        Equivalente a: sudo ovs-vsctl del-br <nombre>
        """
        cmd = ["sudo", "ovs-vsctl", "del-br", self.name]
        log.debug("Ejecutando: " + " ".join(cmd))
        ret = subprocess.call(cmd)

        if ret != 0:
            print(f"[ERROR] Falló el borrado de la red {self.name}")
        else:
            print(f"[OK] Red eliminada: {self.name}")
