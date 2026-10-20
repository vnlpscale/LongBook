from __future__ import annotations

import importlib.metadata
import platform
import shutil
import subprocess
import sys

from .config import data_directory


def diagnose() -> dict:
    packages = {}
    for name in ["gradio", "httpx", "huggingface-hub", "torch", "transformers", "accelerate", "bitsandbytes"]:
        try:
            packages[name] = importlib.metadata.version(name)
        except importlib.metadata.PackageNotFoundError:
            packages[name] = "not installed"
    gpu = "nvidia-smi not found (this does not rule out other accelerators)"
    if shutil.which("nvidia-smi"):
        try:
            result = subprocess.run(["nvidia-smi", "--query-gpu=name,memory.total,driver_version",
                                     "--format=csv,noheader"], capture_output=True, text=True,
                                    timeout=5, check=True)
            gpu = result.stdout.strip()
        except (subprocess.SubprocessError, OSError):
            gpu = "nvidia-smi failed"
    return {"python": sys.version.split()[0], "os": platform.system(),
            "architecture": platform.machine(), "packages": packages, "gpu": gpu,
            "data_directory": str(data_directory()),
            "scope": "UI / personal harness. Real LongBook inference requires separate validation."}
