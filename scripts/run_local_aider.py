#!/usr/bin/env python3
"""Launch the pinned local Aider/Ollama setup inside AutoCage."""

from __future__ import annotations

import argparse
import hashlib
import json
import os
from pathlib import Path
import subprocess
import time
import urllib.request

OLLAMA = Path("/usr/bin/ollama")
AIDER = Path("/usr/local/venvs/aider/bin/aider")
MODEL = "ollama_chat/qwen2.5-coder:3b"
MODEL_DIR = Path("/usr/local/share/ollama/models")
MANIFEST = MODEL_DIR / "manifests/registry.ollama.ai/library/qwen2.5-coder/3b"
MODEL_BLOB = MODEL_DIR / "blobs/sha256-4a188102020e9c9530b687fd6400f775c45e90a0d7baafe65bd0a36963fbb7ba"
MODEL_SIZE = 1_929_903_072
EDITABLE_FILES = ("src/calculator.py", "config/settings.json")
EXPECTED_AIDER_VERSION = "0.86.2"
EXPECTED_OLLAMA_VERSION = "0.40.4"
EXPECTED_MANIFEST_SHA256 = "ce40a49b0aa2b3b607d26a603e0f2db06a256cecbc9cca7adf893ae11a80275a"


def workspace_input(value: str) -> str:
    path = Path(value)
    if path.is_absolute() or ".." in path.parts or not path.parts:
        raise ValueError("input must be workspace-relative")
    root = Path.cwd().resolve(strict=True)
    result = (root / path).resolve(strict=True)
    result.relative_to(root)
    if not result.is_file():
        raise ValueError("input must name a regular file")
    return result.relative_to(root).as_posix()


def verify_local_install() -> tuple[str, str]:
    if not OLLAMA.is_file() or not os.access(OLLAMA, os.X_OK):
        raise RuntimeError("Ollama missing at /usr/bin/ollama; no network fallback is used")
    if not AIDER.is_file() or not os.access(AIDER, os.X_OK):
        raise RuntimeError("Aider missing at /usr/local/venvs/aider/bin/aider")
    version_env = {"HOME": "/tmp", "PATH": "/usr/local/venvs/aider/bin:/usr/bin:/bin"}
    aider = subprocess.run([str(AIDER), "--version"], env=version_env,
                           capture_output=True, text=True, timeout=10, check=False)
    if aider.returncode != 0 or EXPECTED_AIDER_VERSION not in aider.stdout + aider.stderr:
        raise RuntimeError("Aider version does not match the validated 0.86.2 setup")
    ollama = subprocess.run([str(OLLAMA), "--version"], env=version_env,
                            capture_output=True, text=True, timeout=10, check=False)
    if ollama.returncode != 0 or EXPECTED_OLLAMA_VERSION not in ollama.stdout + ollama.stderr:
        raise RuntimeError("Ollama version does not match the validated 0.40.4 setup")
    if not MANIFEST.is_file():
        raise RuntimeError("Qwen2.5-Coder model manifest missing; no model will be downloaded")
    manifest_bytes = MANIFEST.read_bytes()
    manifest_hash = hashlib.sha256(manifest_bytes).hexdigest()
    if manifest_hash != EXPECTED_MANIFEST_SHA256:
        raise RuntimeError("local Qwen2.5-Coder manifest does not match the pinned identity")
    manifest = json.loads(manifest_bytes)
    for item in [manifest.get("config"), *manifest.get("layers", [])]:
        if not isinstance(item, dict) or not isinstance(item.get("digest"), str):
            raise RuntimeError("local model manifest contains an invalid layer identity")
        blob = MODEL_DIR / "blobs" / item["digest"].replace(":", "-")
        if not blob.is_file() or blob.stat().st_size != item.get("size"):
            raise RuntimeError("a pinned local Ollama model blob is missing or has the wrong size")
    if not MODEL_BLOB.is_file() or MODEL_BLOB.stat().st_size != MODEL_SIZE:
        raise RuntimeError("pinned Qwen2.5-Coder model blob is missing or has the wrong size")
    return manifest_hash, aider.stdout.strip() or EXPECTED_AIDER_VERSION


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--task", required=True)
    parser.add_argument("--input", required=True)
    args = parser.parse_args()

    os.umask(0o077)
    input_path = workspace_input(args.input)
    manifest_hash, aider_version = verify_local_install()
    home = Path("/tmp/autocage-aider-home")
    home.mkdir(mode=0o700, parents=True, exist_ok=True)
    settings = Path("/tmp/autocage-aider-model-settings.yml")
    settings.write_text("- name: " + MODEL + "\n  extra_params:\n    num_ctx: 8192\n", encoding="utf-8")
    env = {
        "HOME": str(home), "TMPDIR": "/tmp",
        "PATH": "/usr/local/venvs/aider/bin:/usr/bin:/bin",
        "LANG": "C.UTF-8", "TERM": "dumb", "NO_COLOR": "1",
        "PYTHONDONTWRITEBYTECODE": "1", "PYTHONNOUSERSITE": "1",
        "OLLAMA_HOST": "127.0.0.1:11434",
        "OLLAMA_MODELS": str(MODEL_DIR),
        "OLLAMA_CONTEXT_LENGTH": "8192", "OLLAMA_KEEP_ALIVE": "5m",
        "OLLAMA_API_BASE": "http://127.0.0.1:11434",
    }
    log_fd = os.open("/tmp/autocage-playground-ollama.log",
                     os.O_WRONLY | os.O_CREAT | os.O_TRUNC, 0o600)
    log = os.fdopen(log_fd, "wb")
    server = subprocess.Popen([str(OLLAMA), "serve"], env=env,
                              stdin=subprocess.DEVNULL, stdout=log,
                              stderr=subprocess.STDOUT)
    try:
        started = time.monotonic()
        deadline = started + 60
        while time.monotonic() < deadline:
            if server.poll() is not None:
                raise RuntimeError(f"Ollama exited before readiness ({server.returncode})")
            try:
                with urllib.request.urlopen("http://127.0.0.1:11434/api/tags", timeout=1) as response:
                    if response.status == 200:
                        break
            except OSError:
                time.sleep(0.25)
        else:
            raise TimeoutError("Ollama did not become ready on sandbox loopback")

        command = [
            str(AIDER), "--model", MODEL, "--model-settings-file", str(settings),
            "--no-git", "--no-analytics", "--yes-always", "--map-tokens", "0",
            "--no-pretty", "--input-history-file", "/tmp/autocage-aider-input-history",
            "--chat-history-file", "/tmp/autocage-aider-chat-history.md",
            "--read", input_path, "--message", args.task, *EDITABLE_FILES,
        ]
        run_started = time.monotonic()
        result = subprocess.run(command, env=env, check=False)
        metrics = {
            "agent": "Aider",
            "aider_version": aider_version,
            "ollama_version": EXPECTED_OLLAMA_VERSION,
            "model": "qwen2.5-coder:3b",
            "model_manifest_sha256": manifest_hash,
            "server_ready_millis": int((time.monotonic() - started) * 1000),
            "agent_elapsed_millis": int((time.monotonic() - run_started) * 1000),
            "network_mode": "private AutoCage namespace, sandbox loopback only",
        }
        print("AUTOCAGE_LOCAL_AGENT_METRICS=" + json.dumps(metrics, sort_keys=True), flush=True)
        return result.returncode
    finally:
        if server.poll() is None:
            server.terminate()
            try:
                server.wait(timeout=10)
            except subprocess.TimeoutExpired:
                server.kill()
                server.wait(timeout=5)
        log.close()


if __name__ == "__main__":
    raise SystemExit(main())
