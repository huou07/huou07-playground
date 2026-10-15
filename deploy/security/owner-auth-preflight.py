#!/usr/bin/env python3
"""Owner-run, read-only gate for the dashboard patch. Never prints credentials."""
import os
import pwd
import subprocess


def validate_environment(environment):
    required = [b"OPENCODE_PUBLIC_USERNAME", b"OPENCODE_PUBLIC_PASSWORD",
                b"OPENCODE_BACKEND_USERNAME", b"OPENCODE_BACKEND_PASSWORD"]
    if not all(environment.get(name) for name in required):
        raise RuntimeError("Owner and backend Web logins must already be configured; no changes made.")
    if environment[b"OPENCODE_PUBLIC_PASSWORD"] == environment[b"OPENCODE_BACKEND_PASSWORD"]:
        raise RuntimeError("Owner and worker passwords must differ; no changes made.")


def main():
    if os.geteuid() != 0:
        raise SystemExit("This read-only preflight must be executed by the owner with sudo.")
    result = subprocess.run(["/usr/bin/systemctl", "show", "huou07-playground.service",
                             "-p", "MainPID", "--value"], check=True, capture_output=True, text=True)
    pid = int(result.stdout.strip())
    if pid <= 1 or os.stat(f"/proc/{pid}").st_uid != pwd.getpwnam("huou07-playground").pw_uid:
        raise SystemExit("Dashboard identity check failed; no changes made.")
    with open(f"/proc/{pid}/environ", "rb") as stream:
        environment = dict(entry.split(b"=", 1) for entry in stream.read().split(b"\0") if b"=" in entry)
    try:
        validate_environment(environment)
    except RuntimeError as error:
        raise SystemExit(str(error)) from None
    print("PASS: existing owner login configured and password differs from worker backend; no values disclosed.")


if __name__ == "__main__":
    main()
