#!/usr/bin/env python
"""Corre recompose entero con una sola orden:  python dev.py

Levanta el backend (FastAPI, 127.0.0.1:8000) y el frontend (Vite, localhost:5173)
a la vez. Ctrl-C baja ambos. Si uno se cae, el otro también.

Requisitos: las deps de Python instaladas (requirements.txt) y, una vez,
`npm install` dentro de web/.
"""
import os
import subprocess
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parent
NPM = "npm.cmd" if os.name == "nt" else "npm"


def main() -> int:
    if not (ROOT / "web" / "node_modules").exists():
        sys.exit("Falta web/node_modules. Corre una vez:  cd web && npm install")

    print("recompose dev — backend :8000  +  frontend :5173")
    print("Abre http://localhost:5173   (Ctrl-C baja ambos)\n")

    backend = subprocess.Popen([sys.executable, "-m", "server"], cwd=ROOT)
    try:
        frontend = subprocess.Popen([NPM, "run", "dev"], cwd=ROOT / "web")
    except FileNotFoundError:
        backend.terminate()
        sys.exit("No encontré npm en el PATH. Instala Node.js y reintenta.")

    procs = [backend, frontend]
    try:
        while all(p.poll() is None for p in procs):
            time.sleep(0.3)
    except KeyboardInterrupt:
        pass
    finally:
        for p in procs:
            if p.poll() is None:
                p.terminate()
        for p in procs:
            try:
                p.wait(timeout=5)
            except subprocess.TimeoutExpired:
                p.kill()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
