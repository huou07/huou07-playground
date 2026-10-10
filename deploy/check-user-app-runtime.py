#!/usr/bin/env python3
"""Exercise fresh database and gateway containers on disposable local resources."""

from __future__ import annotations

import pathlib
import secrets
import shutil
import socket
import subprocess
import sys
import time
import urllib.error
import urllib.request


HOME = pathlib.Path("/home/huou07")
LITELLM_IMAGE = "ghcr.io/berriai/litellm:v1.104.2"
POSTGRES_IMAGE = "docker.io/library/postgres:16"
OMNIROUTE_IMAGE = "docker.io/diegosouzapw/omniroute:3.8.51"
REDIS_IMAGE = "docker.io/library/redis:8.6.5-alpine"


class Stage:
    def __init__(self) -> None:
        self.tag = "h07-check-" + secrets.token_hex(5)
        self.pods: list[str] = []
        self.volumes: list[str] = []
        self.containers: list[str] = []
        self.config_files = (
            HOME / ".config/litellm/postgres.env",
            HOME / ".config/litellm/litellm.env",
            HOME / ".config/omniroute/omniroute.env",
        )

    def run(self, label: str, args: list[str], *, check: bool = True) -> subprocess.CompletedProcess[str]:
        result = subprocess.run(args, text=True, capture_output=True, check=False)
        if check and result.returncode:
            raise RuntimeError(f"{label} failed (exit {result.returncode}); details are withheld to protect credentials.")
        return result

    def create_pod(self, suffix: str, ports: list[tuple[int, int]]) -> str:
        name = self.tag + "-" + suffix
        args = ["podman", "pod", "create", "--name", name]
        for host_port, container_port in ports:
            args.extend(("--publish", f"127.0.0.1:{host_port}:{container_port}"))
        self.run("temporary Podman pod creation", args)
        self.pods.append(name)
        return name

    def volume(self, suffix: str) -> str:
        name = self.tag + "-" + suffix
        self.run("temporary Podman volume creation", ["podman", "volume", "create", name])
        self.volumes.append(name)
        return name

    def container(self, suffix: str, args: list[str], label: str) -> str:
        name = self.tag + "-" + suffix
        self.containers.append(name)
        self.run(label, ["podman", "run", "-d", "--name", name, *args])
        return name

    def wait_http(self, label: str, url: str, *, html: bool = False, timeout: int = 240) -> None:
        deadline = time.monotonic() + timeout
        while time.monotonic() < deadline:
            try:
                with urllib.request.urlopen(url, timeout=3) as response:
                    body = response.read(4096).lower()
                    if response.status == 200 and (not html or b"<html" in body or b"<!doctype html" in body):
                        print(f"{label} passed.")
                        return
            except (OSError, urllib.error.URLError, urllib.error.HTTPError, TimeoutError):
                time.sleep(2)
        self.print_sanitized_logs()
        raise RuntimeError(f"{label} did not become ready on its temporary port.")

    def wait_postgres(self, name: str, timeout: int = 120) -> None:
        deadline = time.monotonic() + timeout
        while time.monotonic() < deadline:
            if self.run("PostgreSQL readiness probe", [
                "podman", "exec", name, "pg_isready", "-U", "litellm", "-d", "litellm",
            ], check=False).returncode == 0:
                return
            time.sleep(2)
        raise RuntimeError("Temporary PostgreSQL did not become ready.")

    def print_sanitized_logs(self) -> None:
        secrets_to_hide: set[str] = set()
        for path in self.config_files:
            if path.is_file():
                for line in path.read_text().splitlines():
                    if "=" in line:
                        value = line.split("=", 1)[1]
                        if len(value) >= 4:
                            secrets_to_hide.add(value)
        for name in self.containers:
            result = self.run("container log inspection", ["podman", "logs", "--tail", "40", name], check=False)
            text = result.stdout + result.stderr
            for secret in secrets_to_hide:
                text = text.replace(secret, "[REDACTED]")
            for line in text.splitlines():
                if any(word in line.lower() for word in ("error", "fatal", "failed", "exception")):
                    print(line[:240], file=sys.stderr)

    def check_ports(self, ports: tuple[int, ...]) -> None:
        for port in ports:
            with socket.socket() as sock:
                sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
                try:
                    sock.bind(("127.0.0.1", port))
                except OSError as exc:
                    raise RuntimeError(f"Temporary acceptance port {port} is already in use.") from exc

    def run_all(self) -> None:
        self.check_ports((14000, 22128, 22129, 22132))
        litellm_pod = self.create_pod("litellm", [(14000, 4000)])
        pg_volume = self.volume("pgdata")
        postgres = self.container("postgres", [
            "--pod", litellm_pod,
            "--env-file", str(self.config_files[0]),
            "-v", f"{pg_volume}:/var/lib/postgresql/data",
            POSTGRES_IMAGE,
        ], "temporary PostgreSQL start")
        self.wait_postgres(postgres)
        print("Fresh PostgreSQL passed.")

        litellm = self.container("litellm", [
            "--pod", litellm_pod,
            "--env-file", str(self.config_files[1]),
            "-v", f"{HOME}/.config/litellm/config.yaml:/app/config.yaml:ro",
            LITELLM_IMAGE, "--config", "/app/config.yaml",
        ], "temporary LiteLLM start")
        self.wait_http("LiteLLM readiness", "http://127.0.0.1:14000/health/readiness")
        self.wait_http("LiteLLM admin UI", "http://127.0.0.1:14000/ui", html=True)

        self.run("PostgreSQL persistence probe", [
            "podman", "exec", postgres, "psql", "-U", "litellm", "-d", "litellm",
            "-v", "ON_ERROR_STOP=1", "-c",
            "CREATE TABLE readiness_probe (value text); INSERT INTO readiness_probe VALUES ('persistent');",
        ])
        self.run("temporary PostgreSQL restart", ["podman", "restart", postgres])
        self.wait_postgres(postgres)
        row = self.run("PostgreSQL persistence verification", [
            "podman", "exec", postgres, "psql", "-U", "litellm", "-d", "litellm",
            "-At", "-c", "SELECT value FROM readiness_probe",
        ]).stdout.strip()
        if row != "persistent":
            raise RuntimeError("Temporary PostgreSQL data did not persist across restart.")
        self.wait_http("LiteLLM recovery", "http://127.0.0.1:14000/health/readiness", timeout=60)
        print("PostgreSQL data persisted across restart.")

        omni_pod = self.create_pod("omniroute", [(22128, 20128), (22129, 20129), (22132, 20132)])
        redis_volume = self.volume("redisdata")
        redis = self.container("redis", [
            "--pod", omni_pod,
            "-v", f"{redis_volume}:/data",
            REDIS_IMAGE, "redis-server", "--save", "60", "1", "--loglevel", "warning",
        ], "temporary Redis start")
        if self.run("Redis readiness", ["podman", "exec", redis, "redis-cli", "ping"]).stdout.strip() != "PONG":
            raise RuntimeError("Temporary Redis did not become ready.")
        self.run("Redis persistence probe", ["podman", "exec", redis, "redis-cli", "set", "readiness-probe", "persistent"])
        self.run("Redis persistence save", ["podman", "exec", redis, "redis-cli", "save"])
        self.run("temporary Redis restart", ["podman", "restart", redis])
        if self.run("Redis persistence verification", ["podman", "exec", redis, "redis-cli", "get", "readiness-probe"]).stdout.strip() != "persistent":
            raise RuntimeError("Temporary Redis data did not persist across restart.")
        print("Redis data persisted across restart.")

        app_volume = self.volume("omni-data")
        omniroute = self.container("omniroute", [
            "--pod", omni_pod,
            "--env-file", str(self.config_files[2]),
            "-v", f"{app_volume}:/app/data",
            OMNIROUTE_IMAGE,
        ], "temporary OmniRoute start")
        self.wait_http("OmniRoute health", "http://127.0.0.1:22128/healthz")
        self.wait_http("OmniRoute dashboard", "http://127.0.0.1:22128/", html=True)
        probe = "require('node:fs').writeFileSync('/app/data/.playground-readiness', 'persistent')"
        self.run("OmniRoute data write", ["podman", "exec", omniroute, "node", "-e", probe])
        self.run("temporary OmniRoute restart", ["podman", "restart", omniroute])
        self.wait_http("OmniRoute recovery", "http://127.0.0.1:22128/healthz", timeout=60)
        value = self.run("OmniRoute data verification", [
            "podman", "exec", omniroute, "node", "-e",
            "process.stdout.write(require('node:fs').readFileSync('/app/data/.playground-readiness', 'utf8'))",
        ]).stdout
        if value != "persistent":
            raise RuntimeError("OmniRoute data volume did not persist across restart.")
        self.run("OmniRoute probe cleanup", [
            "podman", "exec", omniroute, "node", "-e",
            "require('node:fs').unlinkSync('/app/data/.playground-readiness')",
        ])
        print("OmniRoute data persisted across restart.")
        print("No model inference was requested.")

    def cleanup(self) -> None:
        failed = False
        for name in reversed(self.pods):
            exists = self.run("temporary pod existence check", ["podman", "pod", "exists", name], check=False)
            if exists.returncode == 0:
                result = self.run("temporary pod cleanup", ["podman", "pod", "rm", "--force", name], check=False)
                failed |= result.returncode != 0
            elif exists.returncode != 1:
                failed = True
        for name in reversed(self.containers):
            exists = self.run("temporary container existence check", ["podman", "container", "exists", name], check=False)
            if exists.returncode == 0:
                result = self.run("temporary container cleanup", ["podman", "rm", "--force", name], check=False)
                failed |= result.returncode != 0
            elif exists.returncode != 1:
                failed = True
        for name in reversed(self.volumes):
            exists = self.run("temporary volume existence check", ["podman", "volume", "exists", name], check=False)
            if exists.returncode == 0:
                result = self.run("temporary volume cleanup", ["podman", "volume", "rm", name], check=False)
                failed |= result.returncode != 0
            elif exists.returncode != 1:
                failed = True
        if failed:
            raise RuntimeError("A named temporary staging resource could not be removed; inspect only resources prefixed " + self.tag)


def main() -> int:
    stage = Stage()
    try:
        stage.run_all()
        return 0
    except (OSError, RuntimeError, subprocess.SubprocessError) as exc:
        stage.print_sanitized_logs()
        print(f"Fresh application staging failed: {exc}", file=sys.stderr)
        return 1
    finally:
        try:
            stage.cleanup()
            print("Temporary staging containers, pods, and volumes removed.")
        except RuntimeError as exc:
            print(str(exc), file=sys.stderr)
            raise SystemExit(1) from exc


if __name__ == "__main__":
    raise SystemExit(main())
