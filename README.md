# Creative Practice 1 – Automated Infrastructure Deployment (CDPS)

This repository contains **Creative Practice 1** for the course  
**CDPS – Concepts and Design of Digital Systems**.

The project focuses on **automating the creation and management of a virtualized infrastructure scenario** using Python, replicating a realistic load-balanced environment commonly found in data centers and cloud platforms.

The resulting setup is later used as the foundation for scalable application deployments in Creative Practice 2.

---

## Project Overview

The goal of this project is to design a **non-interactive Python automation tool** capable of provisioning, configuring, and managing a complete virtual infrastructure composed of:

- Multiple web servers
- A load balancer acting as a router
- Isolated virtual networks
- Configurable topology and scale

The script automates the full lifecycle of the environment, from creation to teardown, following Infrastructure-as-Code principles.

---

## Key Features

- **Full automation** of virtual machine and network creation
- **Configurable number of backend servers** (1 to 5) via JSON configuration
- **Lifecycle management**: define, start, stop, and destroy the entire scenario
- **Network configuration automation** (hostnames, interfaces, routing)
- **Persistent virtual machines** using QCOW2 differential images
- **Modular design** using a custom Python library for VM and network management
- **Structured logging** using Python’s `logging` module
- **No interactive input** — fully script-driven execution

---

## Technologies & Tools

- **Python 3.9**
- **KVM / libvirt** for virtual machine management
- **Open vSwitch (OVS)** for virtual networking
- **QCOW2** disk images
- **JSON** for configuration
- **Linux system tools** (`virsh`, `virt-customize`, `ovs-vsctl`)

---

## How It Works

The main script (`auto-p2.py`) accepts a command defining the operation to perform:

- `define` – creates virtual machines, networks, and configuration files
- `start` – boots the virtual machines and opens their consoles
- `stop` – gracefully shuts down the virtual machines
- `undefine` – removes all created resources and cleans up the environment

The number of backend servers and debug level are defined in a JSON configuration file.

---

## Repository Structure

