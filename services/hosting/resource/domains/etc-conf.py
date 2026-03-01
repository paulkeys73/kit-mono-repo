import sys
import os
import ctypes
import subprocess
import socket
import time

HOSTS_FILE = r"C:\Windows\System32\drivers\etc\hosts"
IP = sys.argv[2] if len(sys.argv) >= 3 else None
DOMAIN = sys.argv[1] if len(sys.argv) >= 3 else None

def log(msg):
    print(f"[{time.strftime('%Y-%m-%d %H:%M:%S')}] {msg}", flush=True)

def is_admin():
    try:
        return ctypes.windll.shell32.IsUserAnAdmin()
    except Exception as e:
        log(f"Error checking admin status: {e}")
        return False

def entry_exists(domain):
    log(f"Checking if entry exists for domain: {domain}")
    with open(HOSTS_FILE, "r") as f:
        for line in f:
            if domain in line and not line.strip().startswith("#"):
                log(f"Entry already exists:\n    {line.strip()}")
                return True
    log("No existing entry found.")
    return False

def add_entry(domain, ip):
    line = f"{ip}    {domain}\n"
    log(f"Adding entry: {line.strip()}")
    with open(HOSTS_FILE, "a") as f:
        f.write(line)
    log(f"Entry added: {ip} -> {domain}")

def verify_entry(domain):
    log("Verifying entry exists after writing...")
    with open(HOSTS_FILE, "r") as f:
        lines = [line.strip() for line in f if domain in line and not line.strip().startswith("#")]
    if lines:
        log(f"Verified entry in hosts file:\n    {lines[0]}")
        return True
    else:
        log("Entry not found in hosts file after writing. Something went wrong.")
        return False

def test_dns_resolution(domain):
    log(f"Testing DNS resolution for {domain}...")
    try:
        resolved_ip = socket.gethostbyname(domain)
        log(f"Domain {domain} resolves to {resolved_ip}")
        if resolved_ip == IP:
            log("✅ DNS resolution test passed!")
            return True
        else:
            log(f"⚠️ Warning: Resolved IP ({resolved_ip}) does not match expected IP ({IP}).")
            return False
    except Exception as e:
        log(f"❌ DNS resolution test failed: {e}")
        return False

def list_all_custom_hosts_entries():
    log("Listing all non-commented hosts file entries:")
    with open(HOSTS_FILE, "r") as f:
        lines = [line.strip() for line in f if line.strip() and not line.strip().startswith("#")]
    if not lines:
        log("No entries found in hosts file.")
        return
    for line in lines:
        parts = line.split()
        if len(parts) >= 2:
            ip, domain = parts[0], parts[1]
            log(f"  {domain} -> {ip}")
    log("End of hosts file entries.")

def run_as_admin_and_wait():
    log("Script not running as admin — relaunching with admin rights now...")

    python_exe = sys.executable
    script_path = os.path.abspath(sys.argv[0])
    script_args = sys.argv[1:]

    # Construct command line for python script
    cmd_parts = [python_exe, script_path] + script_args
    cmd_line = subprocess.list2cmdline(cmd_parts)

    # Full command with ping and pause after script runs
    full_cmd = f'{cmd_line} && echo. && echo Pinging {DOMAIN}... && ping {DOMAIN} && pause'

    # PowerShell expects -ArgumentList to be an array of strings
    # so build a properly quoted array: @('/k', 'full_cmd')
    # Need to double quote full_cmd inside PowerShell to preserve spaces & special chars

    # Escape inner double quotes by doubling them for PowerShell
    full_cmd_escaped = full_cmd.replace('"', '""')

    ps_command = (
        f'Start-Process cmd.exe -ArgumentList @("/k", "{full_cmd_escaped}") -Verb RunAs'
    )

    log(f"Launching PowerShell command to elevate:\n{ps_command}")

    subprocess.run(["powershell", "-Command", ps_command], check=True)

    sys.exit(0)


if __name__ == "__main__":
    log(f"Script started for domain: {DOMAIN}, IP: {IP}")

    if not is_admin():
        run_as_admin_and_wait()

    log("Running with admin privileges confirmed.")

    if not os.access(HOSTS_FILE, os.W_OK):
        log(f"Permission denied: Cannot write to {HOSTS_FILE} even after elevation. Aborting.")
        sys.exit(1)

    if not entry_exists(DOMAIN):
        add_entry(DOMAIN, IP)
        if verify_entry(DOMAIN):
            test_dns_resolution(DOMAIN)
        else:
            log("Hosts entry verification failed.")
    else:
        log("No changes made; entry already exists.")
        test_dns_resolution(DOMAIN)

    list_all_custom_hosts_entries()

    log("Script completed. You can close this window when ready.")
    time.sleep(10)
