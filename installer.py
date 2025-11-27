import os
import pexpect, sys
import subprocess
import shutil
import requests
from uuid import uuid4
from colorama import Fore, Style


def create_ccd() -> None:
    ccd_dir = "/etc/openvpn/ccd"
    server_conf = "/etc/openvpn/server/server.conf"

    if not os.path.exists(ccd_dir):
        subprocess.run(["mkdir", "-p", ccd_dir], check=True)
        subprocess.run(["chmod", "755", ccd_dir], check=True)

        with open(server_conf, "r") as f:
            lines = f.readlines()

        ccd_line = f"client-config-dir {ccd_dir}\n"
        ccd_exclusive_line = "ccd-exclusive\n"

        if ccd_line not in lines:
            lines.append("\n" + ccd_line)

        if ccd_exclusive_line not in lines:
            lines.append(ccd_exclusive_line)
        with open(server_conf, "w") as f:
            f.writelines(lines)

        subprocess.run(
            ["systemctl", "restart", "openvpn-server@server.service"], check=True
        )


def apply_openvpn_config(tunnel_address: str, protocol: str, ovpn_port: str) -> None:
    """Apply OpenVPN configuration settings"""
    import re

    server_conf = "/etc/openvpn/server/server.conf"
    template_file = "/etc/openvpn/server/client-common.txt"

    try:
        # Determine correct protocol format for server and client
        server_proto = f"{protocol}-server" if protocol == "tcp" else protocol
        client_proto = f"{protocol}-client" if protocol == "tcp" else protocol

        # Update server.conf
        if os.path.exists(server_conf):
            with open(server_conf, "r") as f:
                config = f.read()

            config = re.sub(
                r"^port\s+\d+", f"port {ovpn_port}", config, flags=re.MULTILINE
            )
            config = re.sub(
                r"^proto\s+[\w-]+", f"proto {server_proto}", config, flags=re.MULTILINE
            )

            with open(server_conf, "w") as f:
                f.write(config)

        # Update client-common.txt
        if os.path.exists(template_file):
            with open(template_file, "r") as f:
                template = f.read()

            if tunnel_address and tunnel_address.strip() != "":
                template = re.sub(
                    r"^remote\s+\S+\s+\d+",
                    f"remote {tunnel_address} {ovpn_port}",
                    template,
                    flags=re.MULTILINE,
                )
            else:
                template = re.sub(
                    r"^remote\s+(\S+)\s+\d+",
                    rf"remote \1 {ovpn_port}",
                    template,
                    flags=re.MULTILINE,
                )

            template = re.sub(
                r"^proto\s+[\w-]+",
                f"proto {client_proto}",
                template,
                flags=re.MULTILINE,
            )

            with open(template_file, "w") as f:
                f.write(template)

        # Restart OpenVPN service
        subprocess.run(
            ["systemctl", "restart", "openvpn-server@server.service"], check=True
        )
        print(
            Fore.GREEN
            + f"✓ OpenVPN configured: {protocol}://{tunnel_address}:{ovpn_port}"
            + Style.RESET_ALL
        )

    except Exception as e:
        print(
            Fore.YELLOW
            + f"⚠ Warning: Could not apply OpenVPN config: {e}"
            + Style.RESET_ALL
        )


def install_ovnode():
    if os.path.exists("/etc/openvpn"):
        print("OV-Node is already installed.")
        input("Press Enter to continue...")
        menu()
        return
    try:
        subprocess.run(
            ["wget", "https://git.io/vpn", "-O", "/root/openvpn-install.sh"], check=True
        )  # thanks to Nyr for ovpn installation script <3 https://github.com/Nyr/openvpn-install

        bash = pexpect.spawn(
            "/usr/bin/bash", ["/root/openvpn-install.sh"], encoding="utf-8", timeout=180
        )
        print("Running OV-Node installer...")

        prompts = [
            (r"Which IPv4 address should be used.*:", "1"),
            (r"Protocol.*:", "2"),
            (r"Port.*:", "1194"),
            (r"Select a DNS server for the clients.*:", "1"),
            (r"Enter a name for the first client.*:", "first_client"),
            (r"Press any key to continue...", ""),
        ]

        for pattern, reply in prompts:
            try:
                bash.expect(pattern, timeout=10)
                bash.sendline(reply)
            except pexpect.TIMEOUT:
                pass

        bash.expect(pexpect.EOF, timeout=None)
        bash.close()
        create_ccd()

        # OV-Node configuration prompts
        print()
        print(Fore.CYAN + "=" * 50)
        print("OV-Node Configuration")
        print("=" * 50 + Style.RESET_ALL)
        print()

        shutil.copy(".env.example", ".env")
        example_uuid = str(uuid4())

        # Get server IP automatically
        try:
            import socket

            hostname = socket.gethostname()
            server_ip = socket.gethostbyname(hostname)
        except:
            server_ip = "YOUR_SERVER_IP"

        print(
            Fore.YELLOW
            + "Note: These settings are needed to connect this node to OV-Panel"
            + Style.RESET_ALL
        )
        print()

        TUNNEL_ADDRESS = input(f"Tunnel Address (default: {server_ip}): ").strip()
        if TUNNEL_ADDRESS == "":
            TUNNEL_ADDRESS = server_ip

        PROTOCOL = input("Protocol - tcp or udp (default: udp): ").strip().lower()
        if PROTOCOL not in ["tcp", "udp"]:
            PROTOCOL = "udp"

        OVPN_PORT = input("OpenVPN Port (default: 1194): ").strip()
        if OVPN_PORT == "":
            OVPN_PORT = "1194"

        SERVICE_PORT = input("OV-Node service port (default: 9090): ").strip()
        if SERVICE_PORT == "":
            SERVICE_PORT = "9090"

        API_KEY = input(f"OV-Node API key (default: {example_uuid}): ").strip()
        if API_KEY == "":
            API_KEY = example_uuid

        replacements = {
            "SERVICE_PORT": SERVICE_PORT,
            "API_KEY": API_KEY,
            "TUNNEL_ADDRESS": TUNNEL_ADDRESS,
            "PROTOCOL": PROTOCOL,
            "OVPN_PORT": OVPN_PORT,
        }

        lines = []
        with open(".env", "r") as f:
            for line in f:
                replaced = False
                for key, value in replacements.items():
                    if line.strip().startswith(f"{key}") and ("=" in line):
                        lines.append(f"{key} = {value}\n")
                        replaced = True
                        break
                if not replaced:
                    lines.append(line)

        with open(".env", "w") as f:
            f.writelines(lines)

        # Apply OpenVPN configuration
        apply_openvpn_config(TUNNEL_ADDRESS, PROTOCOL, OVPN_PORT)

        run_ovnode()

        # Display configuration summary
        print()
        print(Fore.GREEN + "=" * 50)
        print("Installation Completed Successfully!")
        print("=" * 50 + Style.RESET_ALL)
        print()
        print(Fore.CYAN + "Node Configuration Details:" + Style.RESET_ALL)
        print(Fore.YELLOW + "-" * 50 + Style.RESET_ALL)
        print(
            f"{Fore.WHITE}Tunnel Address:{Style.RESET_ALL}  {Fore.GREEN}{TUNNEL_ADDRESS}{Style.RESET_ALL}"
        )
        print(
            f"{Fore.WHITE}Protocol:{Style.RESET_ALL}        {Fore.GREEN}{PROTOCOL}{Style.RESET_ALL}"
        )
        print(
            f"{Fore.WHITE}OpenVPN Port:{Style.RESET_ALL}    {Fore.GREEN}{OVPN_PORT}{Style.RESET_ALL}"
        )
        print(
            f"{Fore.WHITE}Service Port:{Style.RESET_ALL}    {Fore.GREEN}{SERVICE_PORT}{Style.RESET_ALL}"
        )
        print(
            f"{Fore.WHITE}API Key:{Style.RESET_ALL}         {Fore.GREEN}{API_KEY}{Style.RESET_ALL}"
        )
        print(Fore.YELLOW + "-" * 50 + Style.RESET_ALL)
        print()
        print(
            Fore.CYAN
            + "⚠ IMPORTANT: Save these details to add this node to OV-Panel!"
            + Style.RESET_ALL
        )
        print()
        input("Press Enter to return to the menu...")
        menu()

    except Exception as e:
        print("Error occurred during installation:", e)
        input("Press Enter to return to the menu...")
        menu()
        return


def update_ovnode():
    if not os.path.exists("/opt/ov-node"):
        print("OV-Node is not installed.")
        input("Press Enter to return to the menu...")
        menu()
        return
    try:
        repo = "https://api.github.com/repos/primeZdev/ov-node/releases/latest"
        install_dir = "/opt/ov-node"
        env_file = os.path.join(install_dir, ".env")
        backup_env = "/tmp/ovnode_env_backup"

        response = requests.get(repo)
        response.raise_for_status()
        release = response.json()

        download_url = release["tarball_url"]
        filename = "/tmp/ov-node-latest.tar.gz"

        print(Fore.YELLOW + f"Downloading {download_url}" + Style.RESET_ALL)
        subprocess.run(["wget", "-O", filename, download_url], check=True)

        if os.path.exists(env_file):
            shutil.copy2(env_file, backup_env)

        if os.path.exists(install_dir):
            shutil.rmtree(install_dir)

        os.makedirs(install_dir, exist_ok=True)

        subprocess.run(
            ["tar", "-xzf", filename, "-C", install_dir, "--strip-components=1"],
            check=True,
        )

        if os.path.exists(backup_env):
            shutil.move(backup_env, env_file)

        print(Fore.YELLOW + "Installing requirements..." + Style.RESET_ALL)
        os.chdir(install_dir)
        subprocess.run(["uv", "sync"], check=True)

        subprocess.run(["systemctl", "restart", "ov-node"], check=True)

        print(Fore.GREEN + "OV-Node updated successfully!" + Style.RESET_ALL)
        input("Press Enter to return to the menu...")
        menu()

    except Exception as e:
        print(Fore.RED + f"Update failed: {e}" + Style.RESET_ALL)


def show_node_info():
    """Display node configuration information"""
    if not os.path.exists("/opt/ov-node/.env"):
        print(
            Fore.RED
            + "OV-Node is not installed or .env file not found."
            + Style.RESET_ALL
        )
        input("Press Enter to return to the menu...")
        menu()
        return

    try:
        # Read .env file
        env_data = {}
        with open("/opt/ov-node/.env", "r") as f:
            for line in f:
                line = line.strip()
                if line and not line.startswith("#") and "=" in line:
                    key, value = line.split("=", 1)
                    env_data[key.strip()] = value.strip()

        # Read OpenVPN config from .env first, then fall back to config files
        ovpn_port = env_data.get("OVPN_PORT", None)
        protocol = env_data.get("PROTOCOL", None)
        tunnel_address = env_data.get("TUNNEL_ADDRESS", None)

        # If not in .env, read from OpenVPN config files
        if ovpn_port is None or protocol is None or tunnel_address is None:
            if os.path.exists("/etc/openvpn/server/server.conf"):
                with open("/etc/openvpn/server/server.conf", "r") as f:
                    for line in f:
                        if line.strip().startswith("port ") and ovpn_port is None:
                            ovpn_port = line.split()[1]
                        elif line.strip().startswith("proto ") and protocol is None:
                            protocol = line.split()[1]

            if tunnel_address is None and os.path.exists(
                "/etc/openvpn/server/client-common.txt"
            ):
                with open("/etc/openvpn/server/client-common.txt", "r") as f:
                    for line in f:
                        if (
                            line.strip().startswith("remote ")
                            and tunnel_address is None
                        ):
                            parts = line.split()
                            if len(parts) >= 2:
                                tunnel_address = parts[1]

        # Set defaults if still not found
        if ovpn_port is None:
            ovpn_port = "1194"
        if protocol is None:
            protocol = "udp"
        if tunnel_address is None:
            tunnel_address = "N/A"

        print()
        print(Fore.CYAN + "=" * 50)
        print("Node Configuration Details")
        print("=" * 50 + Style.RESET_ALL)
        print()
        print(Fore.YELLOW + "-" * 50 + Style.RESET_ALL)
        print(
            f"{Fore.WHITE}Tunnel Address:{Style.RESET_ALL}  {Fore.GREEN}{tunnel_address}{Style.RESET_ALL}"
        )
        print(
            f"{Fore.WHITE}Protocol:{Style.RESET_ALL}        {Fore.GREEN}{protocol}{Style.RESET_ALL}"
        )
        print(
            f"{Fore.WHITE}OpenVPN Port:{Style.RESET_ALL}    {Fore.GREEN}{ovpn_port}{Style.RESET_ALL}"
        )
        print(
            f"{Fore.WHITE}Service Port:{Style.RESET_ALL}    {Fore.GREEN}{env_data.get('SERVICE_PORT', 'N/A')}{Style.RESET_ALL}"
        )
        print(
            f"{Fore.WHITE}API Key:{Style.RESET_ALL}         {Fore.GREEN}{env_data.get('API_KEY', 'N/A')}{Style.RESET_ALL}"
        )
        print(Fore.YELLOW + "-" * 50 + Style.RESET_ALL)
        print()

        # Check service status
        try:
            result = subprocess.run(
                ["systemctl", "is-active", "ov-node"],
                capture_output=True,
                text=True,
                check=False,
            )
            status = result.stdout.strip()
            if status == "active":
                print(
                    f"{Fore.WHITE}Service Status:{Style.RESET_ALL}   {Fore.GREEN}● Running{Style.RESET_ALL}"
                )
            else:
                print(
                    f"{Fore.WHITE}Service Status:{Style.RESET_ALL}   {Fore.RED}● Stopped{Style.RESET_ALL}"
                )
        except:
            print(
                f"{Fore.WHITE}Service Status:{Style.RESET_ALL}   {Fore.YELLOW}● Unknown{Style.RESET_ALL}"
            )

        print()
        input("Press Enter to return to the menu...")
        menu()

    except Exception as e:
        print(Fore.RED + f"Error reading node info: {e}" + Style.RESET_ALL)
        input("Press Enter to return to the menu...")
        menu()
        return


def restart_ovnode():
    if not os.path.exists("/opt/ov-node") and not os.path.exists("/etc/openvpn"):
        print("OV-Node is not installed.")
        input("Press Enter to return to the menu...")
        menu()
        return
    try:
        subprocess.run(["systemctl", "restart", "ov-node"], check=True)
        subprocess.run(["systemctl", "restart", "openvpn-server@server"], check=True)
        print(
            Fore.GREEN + "OV-Node and OpenVPN restarted successfully!" + Style.RESET_ALL
        )
        input("Press Enter to return to the menu...")
        menu()

    except Exception as e:
        print(Fore.RED + f"Restart failed: {e}" + Style.RESET_ALL)
        input("Press Enter to return to the menu...")
        menu()
        return


def uninstall_ovnode():
    if not os.path.exists("/opt/ov-node") and not os.path.exists("/etc/openvpn"):
        print("OV-Node is not installed.")
        input("Press Enter to return to the menu...")
        menu()
        return
    try:
        uninstall = input("Do you want to uninstall OV-Node? (y/n): ")
        if uninstall.lower() != "y":
            print("Uninstallation canceled.")
            menu()
            return

        subprocess.run(["clear"])
        print("Please wait...")
        print(
            Fore.YELLOW + "Stopping and removing OV-Node service..." + Style.RESET_ALL
        )

        # Stop and disable OV-Node service
        deactivate_ovnode()

        # Remove OV-Node directory
        if os.path.exists("/opt/ov-node"):
            print(Fore.YELLOW + "Removing OV-Node files..." + Style.RESET_ALL)
            shutil.rmtree("/opt/ov-node")
            print(Fore.GREEN + "✓ OV-Node files removed" + Style.RESET_ALL)

        # Remove virtual environment
        if os.path.exists("/opt/ov-node_venv"):
            print(Fore.YELLOW + "Removing virtual environment..." + Style.RESET_ALL)
            shutil.rmtree("/opt/ov-node_venv")
            print(Fore.GREEN + "✓ Virtual environment removed" + Style.RESET_ALL)

        # Uninstall OpenVPN if the script exists
        if os.path.exists("/root/openvpn-install.sh"):
            print(Fore.YELLOW + "Uninstalling OpenVPN..." + Style.RESET_ALL)
            try:
                bash = pexpect.spawn(
                    "bash /root/openvpn-install.sh", timeout=300, encoding="utf-8"
                )

                bash.expect("Option:", timeout=30)
                bash.sendline("3")

                bash.expect("Confirm OpenVPN removal", timeout=30)
                bash.sendline("y")

                bash.expect(pexpect.EOF, timeout=60)
                bash.close()
                print(Fore.GREEN + "✓ OpenVPN uninstalled" + Style.RESET_ALL)
            except pexpect.TIMEOUT:
                print(
                    Fore.YELLOW
                    + "⚠ OpenVPN uninstall timeout, removing manually..."
                    + Style.RESET_ALL
                )
            except Exception as e:
                print(
                    Fore.YELLOW
                    + f"⚠ OpenVPN uninstall error: {e}, removing manually..."
                    + Style.RESET_ALL
                )

        # Force remove OpenVPN directories
        if os.path.exists("/etc/openvpn"):
            print(Fore.YELLOW + "Removing OpenVPN configuration..." + Style.RESET_ALL)
            shutil.rmtree("/etc/openvpn")
            print(Fore.GREEN + "✓ OpenVPN configuration removed" + Style.RESET_ALL)

        # Remove OpenVPN install script
        if os.path.exists("/root/openvpn-install.sh"):
            os.remove("/root/openvpn-install.sh")
            print(Fore.GREEN + "✓ OpenVPN install script removed" + Style.RESET_ALL)

        # Remove .env file if exists
        if os.path.exists(".env"):
            os.remove(".env")
            print(Fore.GREEN + "✓ Environment file removed" + Style.RESET_ALL)

        print()
        print(
            Fore.GREEN
            + "OV-Node uninstallation completed successfully!"
            + Style.RESET_ALL
        )
        input("Press Enter to return to the menu...")
        menu()

    except Exception as e:
        print(
            Fore.RED
            + "Error occurred during uninstallation: "
            + str(e)
            + Style.RESET_ALL
        )
        input("Press Enter to return to the menu...")
        menu()
        return


def run_ovnode() -> None:
    """Create and run a systemd service for OV-Node"""
    service_content = """
[Unit]
Description=OV-Node App
After=network.target

[Service]
WorkingDirectory=/opt/ov-node
ExecStart=/opt/ov-node_venv/bin/uv run main.py
Restart=always
RestartSec=5
User=root
Environment="PATH=/opt/ov-node_venv/bin"
Environment="VIRTUAL_ENV=/opt/ov-node_venv"

[Install]
WantedBy=multi-user.target
"""

    with open("/etc/systemd/system/ov-node.service", "w") as f:
        f.write(service_content)

    subprocess.run(["sudo", "systemctl", "daemon-reload"])
    subprocess.run(["sudo", "systemctl", "enable", "ov-node"])
    subprocess.run(["sudo", "systemctl", "start", "ov-node"])


def deactivate_ovnode() -> None:
    """Stop and disable the OV-Node systemd service"""
    try:
        subprocess.run(
            ["sudo", "systemctl", "stop", "ov-node"],
            check=False,
            stderr=subprocess.DEVNULL,
        )
        subprocess.run(
            ["sudo", "systemctl", "disable", "ov-node"],
            check=False,
            stderr=subprocess.DEVNULL,
        )
        if os.path.exists("/etc/systemd/system/ov-node.service"):
            subprocess.run(
                ["rm", "-f", "/etc/systemd/system/ov-node.service"], check=False
            )
        subprocess.run(
            ["sudo", "systemctl", "daemon-reload"],
            check=False,
            stderr=subprocess.DEVNULL,
        )
    except Exception as e:
        print(
            Fore.YELLOW
            + f"⚠ Warning during service deactivation: {e}"
            + Style.RESET_ALL
        )


def menu():
    subprocess.run("clear")
    print(Fore.BLUE + "=" * 34)
    print("Welcome to the OV-Node Installer")
    print("=" * 34 + Style.RESET_ALL)
    print()
    print("Please choose an option:\n")
    print("  1. Install")
    print("  2. Update")
    print("  3. Restart")
    print("  4. Show Node Info")
    print("  5. Uninstall")
    print("  6. Exit")
    print()
    choice = input(Fore.YELLOW + "Enter your choice: " + Style.RESET_ALL)

    if choice == "1":
        install_ovnode()
    elif choice == "2":
        update_ovnode()
    elif choice == "3":
        restart_ovnode()
    elif choice == "4":
        show_node_info()
    elif choice == "5":
        uninstall_ovnode()
    elif choice == "6":
        print(Fore.GREEN + "\nExiting..." + Style.RESET_ALL)
        sys.exit()
    else:
        print(Fore.RED + "\nInvalid choice. Please try again." + Style.RESET_ALL)
        input(Fore.YELLOW + "Press Enter to continue..." + Style.RESET_ALL)
        menu()


if __name__ == "__main__":
    menu()
