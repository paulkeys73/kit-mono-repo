import argparse
import subprocess
import sys
from pathlib import Path


BASE_DIR = Path(__file__).resolve().parent

STEP_ALIASES = {
    "add_user": "auth/users/add-cp-user.py",
    "create_site": "resource/websites/create-default-website.py",
}

DEFAULT_STEPS = ["add_user", "create_site"]


def resolve_step(step: str) -> Path:
    """Resolve step aliases or file paths to an executable script path."""
    candidate = STEP_ALIASES.get(step, step)
    path = Path(candidate)

    if not path.is_absolute():
        path = BASE_DIR / path

    return path.resolve()


def run_step(script: Path, username: str, email: str, domain: str) -> bool:
    if not script.exists():
        print(f"[!] Step script not found: {script}")
        return False

    cmd = [sys.executable, str(script), username, email, domain]
    print(f"[*] Running: {script.name} ({' '.join(cmd[2:])})")

    result = subprocess.run(
        cmd,
        cwd=script.parent,
        text=True,
        capture_output=True,
    )

    if result.stdout:
        print(result.stdout.strip())
    if result.stderr:
        print(result.stderr.strip())

    if result.returncode != 0:
        print(f"[!] Step failed: {script.name} (exit code {result.returncode})")
        return False

    print(f"[+] Step completed: {script.name}")
    return True


def run_onboarding(username: str, email: str, domain: str, steps: list[str], dry_run: bool) -> int:
    resolved = [resolve_step(step) for step in steps]

    print(f"[*] Onboarding user '{username}' with domain '{domain}'")
    print(f"[*] Step order: {', '.join(str(step) for step in steps)}")

    if dry_run:
        for step in resolved:
            print(f"[dry-run] {step}")
        return 0

    for script in resolved:
        if not run_step(script, username, email, domain):
            print("[!] Onboarding aborted.")
            return 1

    print("[+] Onboarding completed successfully.")
    return 0


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Dynamic project entrypoint for CyberPanel onboarding."
    )
    subparsers = parser.add_subparsers(dest="command")

    list_steps = subparsers.add_parser("list-steps", help="List built-in step aliases.")
    list_steps.set_defaults(command="list-steps")

    onboard = subparsers.add_parser("onboard", help="Run onboarding flow.")
    onboard.add_argument("username")
    onboard.add_argument("email")
    onboard.add_argument("domain")
    onboard.add_argument(
        "--steps",
        nargs="+",
        default=DEFAULT_STEPS,
        help=(
            "Step aliases or script paths in execution order. "
            f"Built-ins: {', '.join(STEP_ALIASES.keys())}"
        ),
    )
    onboard.add_argument("--dry-run", action="store_true", help="Show resolved scripts without running.")

    return parser


def main() -> int:
    parser = build_parser()
    args = parser.parse_args()

    if args.command == "list-steps":
        for alias, path in STEP_ALIASES.items():
            print(f"{alias} -> {path}")
        return 0

    if args.command == "onboard":
        return run_onboarding(args.username, args.email, args.domain, args.steps, args.dry_run)

    parser.print_help()
    return 1


if __name__ == "__main__":
    raise SystemExit(main())
