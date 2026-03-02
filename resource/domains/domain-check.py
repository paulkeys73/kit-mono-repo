import os
import sys
import subprocess
import time

sys.stdout.reconfigure(encoding="utf-8")

DEFAULT_IP = "192.168.42.80"

# --- Helpers ---
def run_script(script, args=[]):
    full_path = os.path.abspath(script)
    cmd = ["python", full_path] + args
    print(f"\n[⚙️] Running: {' '.join(cmd)}")

    result = subprocess.run(cmd, capture_output=True, encoding="utf-8", errors="replace")
    
    if result.stdout.strip():
        print(result.stdout.strip())
    if result.stderr.strip():
        print("[❗] STDERR:\n", result.stderr.strip())

    return result


def domain_in_output(output, domain):
    return domain.lower() in output.lower()

def get_user_child_domains(owner):
    result = subprocess.run(
        ["python", os.path.abspath("user-child-domain-list.py"), owner],
        capture_output=True,
        text=True
    )
    if result.returncode != 0:
        print(f"[❌] Error fetching child domains for user '{owner}'")
        print(result.stderr)
        sys.exit(1)
    return result.stdout

def wait_for_subdomain(full_domain, owner, retries=5, delay=2):
    print("\n⏳ Waiting for subdomain to be registered...")
    for attempt in range(1, retries + 1):
        print(f"🔁 Attempt {attempt} of {retries}...")
        output = get_user_child_domains(owner)
        if domain_in_output(output, full_domain):
            print(f"[✅] Subdomain '{full_domain}' verified in attempt {attempt}.")
            return True
        time.sleep(delay)
    print(f"[⚠️] Subdomain '{full_domain}' still not listed after {retries} attempts.")
    return False

def trigger_etc_config(domain, ip=DEFAULT_IP):
    print(f"\n🛠️ Triggering etc-conf.py for domain: {domain} with IP: {ip}")
    result = run_script("etc-conf.py", [domain, ip])
    if result.returncode == 0:
        print(f"[✅] etc-conf.py completed for {domain}")
    else:
        print(f"[❌] etc-conf.py failed for {domain}. Please check permissions or logs.")

# --- Main Workflow ---
def main():
    if len(sys.argv) < 3:
        print("Usage: python domain-check.py <parent_domain> <subdomain> [package] [owner]")
        sys.exit(1)

    parent_domain = sys.argv[1]
    subdomain = sys.argv[2]
    package = sys.argv[3] if len(sys.argv) > 3 else "Default"
    owner = sys.argv[4] if len(sys.argv) > 4 else subdomain

    full_domain = f"{subdomain}.{parent_domain}"

    print("\n🚀 Starting domain workflow...")

    # Pre-validation listings
    run_script("../websites/list-website.py")
    run_script("../websites/user-website-list.py", [owner])
    run_script("list-child-domain.py")
    run_script("user-child-domain-list.py", [owner])

    # Check if subdomain already exists
    print(f"\n🔍 Checking if subdomain '{full_domain}' already exists...")
    existing = domain_in_output(get_user_child_domains(owner), full_domain)

    if existing:
        print(f"[✅] Subdomain '{full_domain}' already exists. No action needed.")
    else:
        print(f"[➕] Subdomain '{full_domain}' not found. Creating...")
        creation = run_script("add-subdomain.py", [parent_domain, subdomain, package, owner])
        if creation.returncode != 0:
            print("[❌] Subdomain creation failed. Exiting.")
            sys.exit(1)

        # Retry to allow CyberPanel to register the new domain
        if not wait_for_subdomain(full_domain, owner):
            print(f"[⚠️] Subdomain '{full_domain}' was created but not yet visible. Please verify in CyberPanel.")

        # Trigger etc-conf after successful creation
        trigger_etc_config(full_domain, DEFAULT_IP)

    # Final verification listings
    print("\n🔁 Final verification listings:")
    run_script("user-child-domain-list.py", [owner])
    run_script("../websites/user-website-list.py", [owner])

    print(f"\n✅ Domain provisioning completed: {full_domain}")

if __name__ == "__main__":
    main()
