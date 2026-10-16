"""Venv + dependency sync for Rustix Python.

Creates (or repairs) a venv and installs requirements with uv, falling back
to pip. A hash of the inputs is stored in the venv, so restarts with no
dependency changes skip the install entirely.
"""

import argparse
import hashlib
import platform
import shutil
import subprocess
import sys
from pathlib import Path

MARKER = ".rustix-deps"
BASE_PY = getattr(sys, "_base_executable", None) or sys.executable
PY_TAG = f"{platform.python_implementation()}-{sys.version_info.major}.{sys.version_info.minor}"


def _say(log, msg):
    log(f"\033[38;5;208m[rustix]\033[0m {msg}")


def _run(cmd, cwd, log):
    proc = subprocess.Popen(cmd, cwd=cwd, stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True)
    for line in proc.stdout:
        log(line.rstrip("\n"))
    return proc.wait()


def ensure_venv(project: Path, venv: Path, req: str = "requirements.txt", extra: str = "", log=print) -> Path:
    """Make sure `venv` exists for this Python and has `req` + `extra` installed. Returns its python."""
    py = venv / "bin" / "python"
    tag_file = venv / ".rustix-python"
    if py.exists() and (not tag_file.exists() or tag_file.read_text().strip() != PY_TAG):
        _say(log, f"Python changed ({tag_file.read_text().strip() if tag_file.exists() else '?'} -> {PY_TAG}), rebuilding venv")
        shutil.rmtree(venv, ignore_errors=True)
    if not py.exists():
        _say(log, f"Creating venv ({PY_TAG})")
        if _run(["uv", "venv", "--seed", "--quiet", "--python", BASE_PY, str(venv)], project, log) != 0:
            shutil.rmtree(venv, ignore_errors=True)
            if _run([BASE_PY, "-m", "venv", str(venv)], project, log) != 0:
                raise RuntimeError("could not create venv")
        tag_file.write_text(PY_TAG)

    req_path = project / req if req else None
    has_req = bool(req_path and req_path.is_file())
    packages = extra.split()
    if not has_req and not packages:
        return py

    h = hashlib.sha256(PY_TAG.encode())
    if has_req:
        h.update(req_path.read_bytes())
    h.update(" ".join(packages).encode())
    digest = h.hexdigest()
    marker = venv / MARKER
    if marker.exists() and marker.read_text().strip() == digest:
        _say(log, "Dependencies up to date")
        return py

    args = (["-r", str(req_path)] if has_req else []) + packages
    _say(log, f"Installing dependencies ({req if has_req else 'extra packages only'})")
    rc = _run(["uv", "pip", "install", "--python", str(py), *args], project, log)
    if rc != 0:
        _say(log, "uv failed, retrying with pip")
        rc = _run([str(py), "-m", "pip", "install", "--disable-pip-version-check", *args], project, log)
    if rc != 0:
        raise RuntimeError("dependency install failed")
    marker.write_text(digest)
    _say(log, "Dependencies installed")
    return py


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--dir", required=True)
    ap.add_argument("--venv", required=True)
    ap.add_argument("--req", default="requirements.txt")
    ap.add_argument("--extra", default="")
    a = ap.parse_args()
    try:
        ensure_venv(Path(a.dir), Path(a.venv), a.req, a.extra)
    except RuntimeError as e:
        _say(print, str(e))
        sys.exit(1)


if __name__ == "__main__":
    main()
