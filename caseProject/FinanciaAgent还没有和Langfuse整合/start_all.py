"""Start FastAPI and the Vue development server."""

from __future__ import annotations

import argparse
import os
import shutil
import signal
import socket
import subprocess
import sys
import time
import urllib.error
import urllib.request
from dataclasses import dataclass
from pathlib import Path


PROJECT_ROOT = Path(__file__).resolve().parent
FRONTEND_DIR = PROJECT_ROOT / "frontend"


@dataclass(frozen=True)
class Runtime:
    backend_python: Path
    corepack: Path
    node: Path
    vite_entry: Path


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Start the FinQA FastAPI backend and Vue 3 frontend.",
    )
    parser.add_argument("--backend-host", default="127.0.0.1")
    parser.add_argument("--backend-port", type=int, default=8000)
    parser.add_argument("--frontend-host", default="127.0.0.1")
    parser.add_argument("--frontend-port", type=int, default=5173)
    parser.add_argument(
        "--no-reload",
        action="store_true",
        help="Disable Uvicorn auto-reload.",
    )
    parser.add_argument(
        "--check",
        action="store_true",
        help="Validate dependencies and ports without starting services.",
    )
    return parser.parse_args()


def fail(message: str) -> None:
    raise RuntimeError(message)


def validate_port(port: int, name: str) -> None:
    if not 1 <= port <= 65535:
        fail(f"{name} port must be between 1 and 65535: {port}")


def port_is_open(host: str, port: int) -> bool:
    try:
        with socket.create_connection((host, port), timeout=0.3):
            return True
    except OSError:
        return False


def find_runtime() -> Runtime:
    backend_python = (
        PROJECT_ROOT / ".venv" / "Scripts" / "python.exe"
        if os.name == "nt"
        else PROJECT_ROOT / ".venv" / "bin" / "python"
    )
    if not backend_python.is_file():
        fail(
            f"Backend virtual environment was not found: {backend_python}\n"
            "Create it and install the project dependencies first."
        )

    corepack_name = "corepack.cmd" if os.name == "nt" else "corepack"
    corepack_value = shutil.which(corepack_name) or shutil.which("corepack")
    if not corepack_value:
        fail("Corepack was not found. Install Node.js with Corepack enabled first.")

    if not (FRONTEND_DIR / "package.json").is_file():
        fail(f"Frontend package.json was not found: {FRONTEND_DIR / 'package.json'}")
    if not (FRONTEND_DIR / "node_modules").is_dir():
        fail(
            "Frontend dependencies are not installed. Run:\n"
            f"  cd {FRONTEND_DIR}\n"
            "  corepack yarn install"
        )
    node_name = "node.exe" if os.name == "nt" else "node"
    node_value = shutil.which(node_name) or shutil.which("node")
    if not node_value:
        fail("Node.js was not found in PATH.")
    vite_entry = FRONTEND_DIR / "node_modules" / "vite" / "bin" / "vite.js"
    if not vite_entry.is_file():
        fail(
            f"Vite entry point was not found: {vite_entry}\n"
            "Run 'corepack yarn install' in the frontend directory."
        )
    return Runtime(
        backend_python=backend_python,
        corepack=Path(corepack_value),
        node=Path(node_value),
        vite_entry=vite_entry,
    )


def validate_environment(args: argparse.Namespace) -> Runtime:
    validate_port(args.backend_port, "Backend")
    validate_port(args.frontend_port, "Frontend")
    if args.backend_port == args.frontend_port:
        fail("Backend and frontend ports must be different.")

    runtime = find_runtime()
    occupied = []
    if port_is_open(args.backend_host, args.backend_port):
        occupied.append(f"backend {args.backend_host}:{args.backend_port}")
    if port_is_open(args.frontend_host, args.frontend_port):
        occupied.append(f"frontend {args.frontend_host}:{args.frontend_port}")
    if occupied:
        fail("Port already in use: " + ", ".join(occupied))
    return runtime


def process_options() -> dict:
    if os.name == "nt":
        return {"creationflags": subprocess.CREATE_NEW_PROCESS_GROUP}
    return {"start_new_session": True}


def start_process(command: list[str], cwd: Path, env: dict | None = None) -> subprocess.Popen:
    return subprocess.Popen(
        command,
        cwd=cwd,
        env=env,
        stdin=None,
        stdout=None,
        stderr=None,
        shell=False,
        **process_options(),
    )


def url_is_ready(url: str) -> bool:
    try:
        with urllib.request.urlopen(url, timeout=0.7) as response:
            return 200 <= response.status < 500
    except (OSError, urllib.error.URLError):
        return False


def wait_until_ready(
    backend: subprocess.Popen,
    frontend: subprocess.Popen,
    backend_url: str,
    frontend_url: str,
    timeout: float = 60.0,
) -> bool:
    deadline = time.monotonic() + timeout
    backend_ready = False
    frontend_ready = False
    while time.monotonic() < deadline:
        if backend.poll() is not None or frontend.poll() is not None:
            return False
        backend_ready = backend_ready or url_is_ready(f"{backend_url}/health")
        frontend_ready = frontend_ready or url_is_ready(frontend_url)
        if backend_ready and frontend_ready:
            return True
        time.sleep(0.4)
    return False


def stop_process(process: subprocess.Popen, name: str) -> None:
    if process.poll() is not None:
        return
    print(f"Stopping {name}...")
    try:
        if os.name == "nt":
            process.send_signal(signal.CTRL_BREAK_EVENT)
        else:
            os.killpg(process.pid, signal.SIGTERM)
        process.wait(timeout=6)
        return
    except (OSError, subprocess.TimeoutExpired):
        pass

    process.terminate()
    try:
        process.wait(timeout=3)
    except subprocess.TimeoutExpired:
        process.kill()
        process.wait(timeout=2)


def run(args: argparse.Namespace) -> int:
    runtime = validate_environment(args)
    print("Environment check passed.")
    print(f"  Backend Python: {runtime.backend_python}")
    print(f"  Frontend Corepack: {runtime.corepack}")
    print(f"  Frontend Node: {runtime.node}")
    print(f"  Frontend Vite: {runtime.vite_entry}")
    if args.check:
        return 0

    backend_url = f"http://{args.backend_host}:{args.backend_port}"
    frontend_url = f"http://{args.frontend_host}:{args.frontend_port}"
    backend_command = [
        str(runtime.backend_python),
        "-m",
        "uvicorn",
        "app.main:app",
        "--host",
        args.backend_host,
        "--port",
        str(args.backend_port),
    ]
    if not args.no_reload:
        backend_command.append("--reload")
    frontend_command = [
        str(runtime.node),
        str(runtime.vite_entry),
        "--host",
        args.frontend_host,
        "--port",
        str(args.frontend_port),
    ]

    # 通过子进程环境配置代理与跨域；无需修改用户 .env。
    backend_env = os.environ.copy()
    backend_env["FRONTEND_ORIGIN"] = frontend_url
    frontend_env = os.environ.copy()
    frontend_env["API_TARGET"] = backend_url

    print("Starting FastAPI backend...")
    backend = start_process(backend_command, PROJECT_ROOT, backend_env)
    try:
        print("Starting Vue frontend...")
        frontend = start_process(frontend_command, FRONTEND_DIR, frontend_env)
    except Exception:
        stop_process(backend, "backend")
        raise

    try:
        if not wait_until_ready(
            backend,
            frontend,
            backend_url=backend_url,
            frontend_url=frontend_url,
        ):
            backend_code = backend.poll()
            frontend_code = frontend.poll()
            fail(
                "Services did not become ready within 60 seconds "
                f"(backend={backend_code}, frontend={frontend_code})."
            )

        print("\nFinQA Agent is ready:")
        print(f"  Vue UI:      {frontend_url}")
        print(f"  FastAPI:     {backend_url}")
        print(f"  API docs:    {backend_url}/docs")
        print("  Mode:       Local chat and history (no Langfuse)")
        print("  Press Ctrl+C to stop all services.\n")

        while True:
            backend_code = backend.poll()
            frontend_code = frontend.poll()
            if backend_code is not None:
                print(f"Backend exited with code {backend_code}.")
                return backend_code or 1
            if frontend_code is not None:
                print(f"Frontend exited with code {frontend_code}.")
                return frontend_code or 1
            time.sleep(0.5)
    except KeyboardInterrupt:
        print("\nShutdown requested.")
        return 0
    finally:
        stop_process(frontend, "frontend")
        stop_process(backend, "backend")


def main() -> int:
    try:
        return run(parse_args())
    except RuntimeError as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
