#!/usr/bin/env python3
"""Scoped broker acceptance using an isolated helper and synthetic owner data.

Explicit Linux root invocation:
  broker.py /absolute/path/to/h07p-server --disposable-fixture

Uses existing owner/service/worker UIDs, creates no account, changes no production
policy/ACL/service, and disables helper relays and managed-unit operations.
Owner decisions use the fixture admin socket as root; this does not test PAM/HTTP.
"""
import json
import os
from pathlib import Path
import pwd
import shutil
import socket
import sqlite3
import subprocess
import sys
import tempfile
import time


def rpc(path, message):
    with socket.socket(socket.AF_UNIX) as connection:
        connection.settimeout(40)
        connection.connect(str(path))
        connection.sendall((json.dumps(message) + "\n").encode())
        line = connection.makefile("rb").readline(4 * 1024 * 1024)
        if not line.endswith(b"\n"):
            raise AssertionError("Missing or oversized fixture broker response")
        return json.loads(line)


WORKER_CLIENT = (
    "import json,socket,sys;"
    "s=socket.socket(socket.AF_UNIX);s.settimeout(40);s.connect(sys.argv[1]);"
    "s.sendall((sys.argv[2]+'\\n').encode());"
    "line=s.makefile('rb').readline(4194304);"
    "assert line.endswith(b'\\n');"
    "sys.stdout.buffer.write(line)"
)


def main():
    if (sys.platform != "linux" or os.geteuid() != 0
            or sys.argv[2:] != ["--disposable-fixture"]):
        raise SystemExit("Run on an authorized disposable Linux fixture as root with --disposable-fixture")
    binary = str(Path(sys.argv[1]).resolve())
    owner = pwd.getpwnam("huou07")
    service = pwd.getpwnam("huou07-playground")
    workers = ["dsh-worker", "codex-worker", "opencode-worker"]
    for worker in workers:
        pwd.getpwnam(worker)
    root = Path(tempfile.mkdtemp(prefix="h07p-broker-", dir="/var/tmp"))
    root.chmod(0o755)
    control = root / "control"
    control.mkdir(mode=0o700)
    data = root / "data"
    data.mkdir(mode=0o700)
    os.chown(data, owner.pw_uid, owner.pw_gid)
    workspace = data / "workspace"
    workspace.mkdir(mode=0o700)
    os.chown(workspace, owner.pw_uid, owner.pw_gid)
    nas = root / "nas"
    nas.mkdir(mode=0o700)
    os.chown(nas, service.pw_uid, service.pw_gid)
    admin = root / "run/admin.sock"
    broker_socket = root / "run/broker.sock"
    policy = {"revision": 0, "enforced_revision": 0, "preset": "balance",
              "workspace": str(workspace), "rules": []}
    process = None
    checks = 0

    def check(condition, description):
        nonlocal checks
        if not condition:
            raise AssertionError(description)
        checks += 1

    def save_policy():
        temporary = control / ".fixture-policy"
        temporary.write_text(json.dumps(policy))
        temporary.replace(control / "policy.json")

    def fixture_file(name, content=b"synthetic fixture"):
        path = data / name
        if isinstance(content, str):
            content = content.encode()
        path.write_bytes(content)
        os.chown(path, owner.pw_uid, owner.pw_gid)
        path.chmod(0o600)
        return path

    def worker_rpc(worker, message):
        result = subprocess.run(
            ["runuser", "-u", worker, "--", "python3", "-c", WORKER_CLIENT,
             str(broker_socket), json.dumps(message)],
            check=True, capture_output=True, timeout=45,
        )
        return json.loads(result.stdout)

    def request(operation, target, content=None, worker=workers[0], **extra):
        message = dict(op="request", operation=operation, path=str(target), **extra)
        if content is not None:
            message["content"] = content
        return worker_rpc(worker, message)

    def approve(response, allow=True):
        check(response["ok"], "synthetic operation request accepted")
        identifier = response["data"]["id"]
        decision = rpc(admin, dict(op="approve", id=identifier, allow=allow))
        check(decision["ok"], "fixture owner decides request")
        return identifier

    def redeem(identifier, worker=workers[0], **extra):
        return worker_rpc(worker, dict(op="redeem", id=identifier, **extra))

    try:
        # Exercise migration from the original nine-column read-only schema.
        with sqlite3.connect(control / "policy.db") as connection:
            connection.executescript(
                "CREATE TABLE approvals(id TEXT PRIMARY KEY,worker TEXT,path TEXT,"
                "operation TEXT,revision INTEGER,expires INTEGER,state TEXT,dev INTEGER,ino INTEGER);"
                "INSERT INTO approvals VALUES('legacy','dsh-worker','/not-opened','read',"
                "0,9999999999,'approved',1,1);"
            )
        save_policy()
        env = dict(os.environ, H07P_CONTROL_DIR=str(control),
                   H07P_HELPER_SOCKET=str(admin), H07P_NAS_DIR=str(nas),
                   H07P_MANAGED_UNITS="", H07P_RELAYS="false")
        with open(root / "helper.log", "wb") as log:
            process = subprocess.Popen([binary, "helper"], env=env, stdout=log, stderr=log)
        for _ in range(100):
            if admin.exists() and broker_socket.exists():
                break
            if process.poll() is not None:
                raise AssertionError("Fixture helper exited before socket readiness")
            time.sleep(.05)
        check(admin.exists() and broker_socket.exists(), "isolated fixture sockets ready")
        with sqlite3.connect(control / "policy.db") as connection:
            check(connection.execute("SELECT state FROM approvals WHERE id='legacy'").fetchone()[0]
                  == "invalidated", "migration invalidates unbound legacy approval")

        original = fixture_file("ordinary.txt", "original synthetic text")
        check(not rpc(broker_socket, dict(op="request", operation="read", path=str(original)))["ok"],
              "root cannot forge a recognized worker principal on broker socket")
        check(not request("execute", original)["ok"], "broker execute explicitly unsupported")
        check(not request("read", "/etc/passwd")["ok"], "administration denied before reading")
        check(not request("read", "/home/huou07/.codex/never-open-this-fixture")["ok"],
              "native credential boundary denied without inspecting owner files")
        private = nas / "fixture.txt"
        private.write_text("synthetic NAS content")
        os.chown(private, service.pw_uid, service.pw_gid)
        check(not request("read", private)["ok"], "NAS cannot be brokered")

        pending = request("read", original, uid=pwd.getpwnam(workers[1]).pw_uid)
        check(pending["ok"], "kernel UID overrides caller-supplied UID")
        check(not redeem(pending["data"]["id"])["ok"], "pending approval is denial")
        identifier = approve(pending)
        check(not redeem(identifier, worker=workers[1])["ok"], "approval bound to requesting worker")
        read = redeem(identifier)
        check(read["ok"] and read["data"]["data"] == "original synthetic text",
              "approved one-file read returns matching content")
        check(not redeem(identifier)["ok"], "approved read is single-use")
        binary_file = fixture_file("binary.bin", b"\x00\xff\x01")
        binary_read = redeem(approve(request("read", binary_file)))
        check(binary_read["ok"] and binary_read["data"]["encoding"] == "hex"
              and bytes.fromhex(binary_read["data"]["data"]) == b"\x00\xff\x01",
              "binary read preserves bytes with explicit encoding")
        large = fixture_file("large.bin", b"x" * (1024 * 1024 + 1))
        check(not request("read", large)["ok"], "read exceeds one-MiB budget rejected")

        secret = "synthetic-approved-write-never-in-status"
        identifier = approve(request("write", original, secret))
        status = rpc(admin, {"op": "status"})
        check(status["ok"] and secret not in json.dumps(status),
              "owner status never exposes write payload")
        written = redeem(identifier, content="forged-redeem-payload")
        check(written["ok"] and original.read_text() == secret,
              "write replays the exact approved payload, ignoring redemption substitution")
        check(not redeem(identifier)["ok"], "write cannot replay")
        check(not request("write", original, "x" * (64 * 1024 + 1))["ok"],
              "write exceeds 64-KiB budget rejected")

        created = data / "created.txt"
        identifier = approve(request("create", created, "approved new file"))
        check(not created.exists(), "pending create has no filesystem effect")
        check(redeem(identifier, content="forged create")["ok"]
              and created.read_text() == "approved new file",
              "create uses exact approved content")
        check(not request("create", created, "overwrite")["ok"],
              "create never authorizes implicit overwrite")
        collision = data / "collision.txt"
        identifier = approve(request("create", collision, "must not replace"))
        collision.write_text("preserved collision")
        os.chown(collision, owner.pw_uid, owner.pw_gid)
        check(not redeem(identifier)["ok"] and collision.read_text() == "preserved collision",
              "create collision preserves replacement")
        parent_swap = data / "parent-swap"
        parent_swap.mkdir(mode=0o700)
        os.chown(parent_swap, owner.pw_uid, owner.pw_gid)
        identifier = approve(request("create", parent_swap / "new.txt", "must not enter replacement"))
        parent_swap.rename(data / "old-parent")
        parent_swap.mkdir(mode=0o700)
        os.chown(parent_swap, owner.pw_uid, owner.pw_gid)
        check(not redeem(identifier)["ok"] and not (parent_swap / "new.txt").exists(),
              "create is bound to original parent identity")

        listing = redeem(approve(request("list", data)))
        check(listing["ok"] and any(entry["name"] == "ordinary.txt"
                                   for entry in listing["data"]["entries"]),
              "approved directory listing returns bounded metadata")
        check(len(listing["data"]["entries"]) <= 500, "listing is bounded")
        blocked = fixture_file("blocked.txt", "must stay private")
        policy["rules"] = [dict(action="block", worker="*", target=str(blocked),
                                recursive=False, operations=["list", "read", "write",
                                                             "create", "delete", "execute"])]
        save_policy()
        check(not request("read", blocked)["ok"], "Block wins over explicit approval request")
        listing = redeem(approve(request("list", data)))
        check(listing["ok"] and not any(entry["name"] == "blocked.txt"
                                       for entry in listing["data"]["entries"]),
              "listing suppresses blocked descendants")
        policy["rules"] = []
        save_policy()

        replace_target = fixture_file("replace.txt", "original target")
        identifier = approve(request("write", replace_target, "must not overwrite replacement"))
        replacement = fixture_file("replacement.txt", "replacement preserved")
        replacement.replace(replace_target)
        check(not redeem(identifier)["ok"] and replace_target.read_text() == "replacement preserved",
              "inode substitution cannot redirect approved write")
        identifier = approve(request("delete", replace_target))
        replacement = fixture_file("replacement2.txt", "delete replacement preserved")
        replacement.replace(replace_target)
        check(not redeem(identifier)["ok"] and replace_target.read_text() == "delete replacement preserved",
              "inode substitution cannot redirect approved deletion")
        deleting = fixture_file("deleting.txt", "explicit delete fixture")
        identifier = approve(request("delete", deleting))
        check(deleting.exists(), "pending deletion has no filesystem effect")
        check(redeem(identifier)["ok"] and not deleting.exists(),
              "approved deletion removes exactly the approved file")
        check(not redeem(identifier)["ok"], "deletion cannot replay")

        alias = data / "alias.txt"
        alias.symlink_to(original)
        check(not request("read", alias)["ok"], "symlink aliases rejected")
        alias.unlink()
        hardlink = data / "hardlink.txt"
        os.link(original, hardlink)
        check(not request("write", original, "unsafe alias write")["ok"],
              "hardlink aliases rejected")
        hardlink.unlink()
        identifier = approve(request("read", original))
        with sqlite3.connect(control / "policy.db") as connection:
            connection.execute("UPDATE approvals SET expires=?1 WHERE id=?2",
                               (int(time.time()) - 1, identifier))
        check(not redeem(identifier)["ok"], "expired approval denied")
        identifier = approve(request("read", original))
        policy["revision"] += 1
        policy["enforced_revision"] = policy["revision"]
        save_policy()
        check(not redeem(identifier)["ok"], "policy revision change invalidates approval")
        policy["preset"] = "strict"
        save_policy()
        check(not request("read", original)["ok"], "strict forbids outside-workspace approval")
        inside = workspace / "inside.txt"
        inside.write_text("strict workspace fixture")
        os.chown(inside, owner.pw_uid, owner.pw_gid)
        check(redeem(approve(request("read", inside)))["ok"],
              "strict still permits scoped approval within workspace")
        print(json.dumps({"checks": checks, "result": "passed",
                          "runtime": "Linux synthetic helper/real worker UIDs",
                          "production_services_changed": False,
                          "pam_http_tested": False}))
    finally:
        if process is not None:
            process.terminate()
            try:
                process.wait(timeout=10)
            except subprocess.TimeoutExpired:
                process.kill()
                process.wait()
        shutil.rmtree(root)


if __name__ == "__main__":
    main()
