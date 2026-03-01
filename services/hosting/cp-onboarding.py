# File: onboarding.py

import subprocess
import sys
import os

# === Config ===
BASE_DIR = os.path.dirname(os.path.abspath(__file__))
ADD_USER_SCRIPT = os.path.join(BASE_DIR, "f:/my-servers/services/backend/django/hosting/auth/users/add-cp-user.py")
CREATE_SITE_SCRIPT = os.path.join(BASE_DIR, "f:/my-servers/services/backend/django/hosting/resource/websites/create-default-website.py")

def run_script(script_path, args):
    try:
        print(f"🚀 Running script: {os.path.basename(script_path)} {' '.join(args)}")
        result = subprocess.run(
            ["python3", script_path] + args,
            cwd=os.path.dirname(script_path),
            capture_output=True,
            text=True
        )

        print(result.stdout)
        if result.returncode != 0:
            print(f"🔥 Script failed: {script_path}")
            print(result.stderr)
            return False

        print(f"✅ Script completed: {script_path}")
        return True

    except Exception as e:
        print(f"❌ Error running script {script_path}: {e}")
        return False


def main(username, email, domain):
    print(f"🔐 Onboarding user: {username} ({email}) with domain: {domain}")

    # Step 1: Add CyberPanel user
    if not run_script(ADD_USER_SCRIPT, [username, email, domain]):
        print("❌ Failed during user creation.")
        return

    # Step 2: Create default website (✅ FIXED: pass 3 args)
    if not run_script(CREATE_SITE_SCRIPT, [username, email, domain]):
        print("❌ Failed during website creation.")
        return

    print("🏁 Onboarding process completed successfully.")


if __name__ == "__main__":
    if len(sys.argv) != 4:
        print("Usage: python onboarding.py <username> <email> <domain>")
        sys.exit(1)

    _, username, email, domain = sys.argv
    main(username, email, domain)
