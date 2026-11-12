#!/usr/bin/env python3
"""Read-only local health snapshot. No usernames, filenames, tokens or passwords printed."""
from __future__ import annotations

import json
import os
import shutil
import socket
import subprocess
import sys
from pathlib import Path
from urllib.error import HTTPError, URLError
from urllib.request import urlopen

ROOT = Path(__file__).resolve().parents[1]


def emit(name, result):
    print(f"{name:<23} {result}", flush=True)


def run(command, timeout=8):
    try:
        p = subprocess.run(command, capture_output=True, text=True,
                           timeout=timeout, check=False)
        return p.returncode, p.stdout.strip()
    except (OSError, subprocess.TimeoutExpired):
        return -1, ""


def memory():
    values = {}
    try:
        for line in Path("/proc/meminfo").read_text().splitlines():
            name, _, rest = line.partition(":")
            if name in ("MemTotal", "MemAvailable", "SwapTotal", "SwapFree"):
                values[name] = int(rest.strip().split()[0]) / 1024 / 1024
        if len(values) == 4:
            used = values["MemTotal"] - values["MemAvailable"]
            swap_used = values["SwapTotal"] - values["SwapFree"]
            emit("RAM (used/total)", f"{used:.1f} / {values['MemTotal']:.1f} GiB (estimated)")
            emit("Swap (used/total)", f"{swap_used:.1f} / {values['SwapTotal']:.1f} GiB")
            if values["MemAvailable"] < 2:
                emit("RAM WARNING", "available memory below 2 GiB")
    except (OSError, ValueError):
        emit("RAM", "not available")


def http_json(url, timeout=12):
    try:
        with urlopen(url, timeout=timeout) as response:
            return response.status, json.load(response)
    except (URLError, HTTPError, OSError, ValueError, TimeoutError):
        return None, {}


def listener(port):
    try:
        with socket.create_connection(("127.0.0.1", port), timeout=2):
            return True
    except OSError:
        return False


def main():
    print("=== LangChain Lab · local system diagnosis (read only) ===", flush=True)
    emit("Python", sys.version.split()[0])
    emit("OS", "Ubuntu/Linux" if sys.platform.startswith("linux") else sys.platform)
    try:
        load = os.getloadavg()
        emit("CPU cores / load", f"{os.cpu_count() or '?'} / {load[0]:.2f}, {load[1]:.2f}, {load[2]:.2f}")
    except OSError:
        pass
    memory()

    try:
        total, used, free = shutil.disk_usage(ROOT)
        gib = 1024**3
        emit("Project disk (free)", f"{free/gib:.1f} / {total/gib:.1f} GiB")
        if free / total < 0.10:
            emit("DISK WARNING", "less than 10% free")
    except OSError:
        emit("Disk", "unavailable")

    code, result = run(["systemctl", "--user", "is-active", "langchain-lab"])
    emit("FastAPI user service", result if result else "unknown")
    code, result = run(["systemctl", "is-active", "elasticsearch"])
    emit("Elasticsearch service", result if result else "unknown")
    emit("Port 8000 (FastAPI)", "OPEN" if listener(8000) else "CLOSED")
    emit("Port 1234 (LM Studio)", "OPEN" if listener(1234) else "CLOSED")
    emit("Port 9200 (ES)", "OPEN" if listener(9200) else "CLOSED")

    status, health = http_json("http://127.0.0.1:8000/api/documents/health/status", timeout=40)
    if status == 200:
        for key, label in (("elasticsearch", "ES auth via app"), ("embedding", "Embedding test")):
            item = health.get(key, {})
            emit(label, "OK" if item.get("ok") else "ERROR: " + str(item.get("code", "unknown")))
        emit("Document index", str(health.get("document_index", "unknown")))
    else:
        emit("Document health API", "NO RESPONSE (or timeout)")

    status, docs = http_json("http://127.0.0.1:8000/api/documents", timeout=8)
    if status == 200:
        items = docs.get("documents", [])
        counts = {}
        for item in items:
            state = item.get("index_status", "unknown")
            counts[state] = counts.get(state, 0) + 1
        emit("Documents (count)", str(len(items)))
        emit("Document index states", json.dumps(counts, ensure_ascii=False, sort_keys=True))
    else:
        emit("Document list API", "NO RESPONSE")

    # GPU names and aggregate utilization only: never print usernames or GPU processes.
    code, output = run([
        "nvidia-smi",
        "--query-gpu=index,name,memory.total,memory.used,utilization.gpu,temperature.gpu",
        "--format=csv,noheader,nounits"
    ], timeout=9)
    if code == 0 and output:
        print("GPU index, model, MiB total/used, utilization %, temperature C:")
        for line in output.splitlines()[:8]:
            print("  " + line)
    else:
        emit("NVIDIA GPU", "not available or driver/utility not working")

    code, head = run(["git", "-C", str(ROOT), "rev-parse", "--short", "HEAD"])
    emit("Project git commit", head if code == 0 else "unknown")
    code, dirty = run(["git", "-C", str(ROOT), "status", "--porcelain", "--untracked-files=no"])
    emit("Tracked changes", "YES" if dirty else "NO" if code == 0 else "unknown")
    emit("Safety", "No settings or source documents were modified.")
    print("=== end ===")


if __name__ == "__main__":
    main()
