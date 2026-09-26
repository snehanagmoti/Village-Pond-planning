"""Install the built, same-origin app under user-owned Supervisor on a lab host.

Run from an unpacked release containing dist/, web.py and a Supervisor wheel.
Usage: python install_lab_service.py --backend /path/to/backend --python /path/to/venv/bin/python
Does not modify other services or require root privileges.
"""

import argparse
import json
import os
from pathlib import Path
import shutil
import signal
import socket
import subprocess
import time
import zipfile


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--backend", required=True, type=Path)
    parser.add_argument("--python", required=True, type=Path)
    parser.add_argument("--port", type=int, default=8000)
    parser.add_argument("--additional-ports", default="")
    args = parser.parse_args()
    backend, python = args.backend.resolve(), args.python.absolute()
    release = Path(__file__).resolve().parent
    runtime = Path.home() / ".local" / "share" / "pond-service"
    runtime.mkdir(parents=True, exist_ok=True, mode=0o700)
    dependencies = runtime / "packages"
    dependencies.mkdir(exist_ok=True)
    for wheel in release.glob("supervisor-*.whl"):
        with zipfile.ZipFile(wheel) as package:
            package.extractall(dependencies)
    shutil.copy2(release / "web.py", backend / "web.py")
    shutil.copy2(release / "lab_server.py", backend / "lab_server.py")
    environment = {
        **os.environ,
        "APP_ENV": "demo", "ENABLE_API_DOCS": "true", "HISTORY_ENABLED": "false",
        "TRUSTED_HOSTS": "localhost,127.0.0.1,10.1.75.53,172.17.0.38,172.17.0.39,testserver",
        "CORS_ORIGINS": "http://10.1.75.53,http://localhost:18080",
        "GEOCODING_USER_AGENT": "VillagePondPlanning/2.1 (+https://github.com/snehanagmoti/Village-Pond-planning)",
        "APPROVED_RUNOFF_COEFFICIENT": "0.30",
        "APPROVED_RUNOFF_COEFFICIENT_SOURCE": "Course demo scenario C=0.30",
        "ELEVATION_FALLBACK_ENABLED": "true", "RAINFALL_FALLBACK_ENABLED": "true",
        "FRONTEND_DIST": str(release / "dist"),
        "PYTHONPATH": str(dependencies),
        "POND_HTTP_PORTS": ",".join(filter(None, [str(args.port), args.additional_ports])),
    }
    subprocess.run([str(python), "-c", "from web import create_app; create_app(); print('application validated')"], cwd=backend, env=environment, check=True)
    config = runtime / "supervisord.conf"
    settings = {key: value for key, value in environment.items() if key not in os.environ or os.environ.get(key) != value}
    # Always keep explicit runtime settings in the supervisor config.
    for key in ("APP_ENV", "ENABLE_API_DOCS", "HISTORY_ENABLED", "TRUSTED_HOSTS", "CORS_ORIGINS", "GEOCODING_USER_AGENT", "APPROVED_RUNOFF_COEFFICIENT", "APPROVED_RUNOFF_COEFFICIENT_SOURCE", "ELEVATION_FALLBACK_ENABLED", "RAINFALL_FALLBACK_ENABLED", "FRONTEND_DIST", "PYTHONPATH"):
        settings[key] = environment[key]
    settings["POND_HTTP_PORTS"] = environment["POND_HTTP_PORTS"]
    env_config = ",".join(f'{key}="{value}"' for key, value in settings.items())
    content = f"""[unix_http_server]
file={runtime}/supervisor.sock
chmod=0700
[supervisord]
logfile={runtime}/supervisord.log
logfile_maxbytes=5MB
logfile_backups=2
pidfile={runtime}/supervisord.pid
childlogdir={runtime}
[rpcinterface:supervisor]
supervisor.rpcinterface_factory=supervisor.rpcinterface:make_main_rpcinterface
[supervisorctl]
serverurl=unix://{runtime}/supervisor.sock
[program:pond-web]
directory={backend}
command={python} -m lab_server
environment={env_config}
autostart=true
autorestart=true
startsecs=3
startretries=10
stopasgroup=true
killasgroup=true
stdout_logfile={runtime}/web.log
stdout_logfile_maxbytes=10MB
stdout_logfile_backups=2
redirect_stderr=true
"""
    ctl = [str(python), "-m", "supervisor.supervisorctl", "-c", str(config)]
    if config.exists() and (runtime / "supervisor.sock").exists():
        subprocess.run(ctl + ["shutdown"], env=environment, check=True)
        for _ in range(20):
            if not (runtime / "supervisor.sock").exists():
                break
            time.sleep(0.5)
    # Stop only the prior pond Uvicorn process, verified by its working directory.
    for entry in Path("/proc").iterdir():
        if not entry.name.isdigit():
            continue
        try:
            command = (entry / "cmdline").read_bytes().split(b"\0")
            if b"uvicorn" in command and b"main:app" in command and (entry / "cwd").resolve() == backend:
                os.kill(int(entry.name), signal.SIGTERM)
        except (PermissionError, FileNotFoundError, ProcessLookupError):
            pass
    for _ in range(30):
        with socket.socket() as probe:
            if probe.connect_ex(("127.0.0.1", args.port)) != 0:
                break
        time.sleep(0.5)
    else:
        raise RuntimeError(f"Port {args.port} remains occupied; other services were not stopped")
    config.write_text(content)
    subprocess.run([str(python), "-m", "supervisor.supervisord", "-c", str(config)], env=environment, check=True)
    time.sleep(4)
    subprocess.run(ctl + ["status"], env=environment, check=True)
    (runtime / "deployment.json").write_text(json.dumps({"backend": str(backend), "python": str(python), "frontend": str(release / "dist"), "port": args.port}, indent=2))
    print("Deployment complete; supervisor restarts crashes and survives SSH logout.")
    print("Container reboot requires starting supervisord again; no system init is available.")


if __name__ == "__main__":
    main()
