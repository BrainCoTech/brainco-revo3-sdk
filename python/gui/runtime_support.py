"""Offline startup checks and bounded diagnostic archives for the GUI."""

import importlib
import importlib.metadata
import json
import logging
import os
import platform
import sys
import tempfile
import threading
import zipfile
from datetime import datetime, timezone
from pathlib import Path


DEPENDENCIES = {
    "bc-revo3-sdk": "bc_revo3_sdk.main_mod",
    "PySide6": "PySide6.QtWidgets",
    "pyqtgraph": "pyqtgraph",
    "numpy": "numpy",
    "pyserial": "serial",
    "colorlog": "colorlog",
    "qasync": "qasync",
}
MAX_LOG_BYTES = 2 * 1024 * 1024


def environment_report(check_imports=False):
    """Collect only runtime information; never enumerate or open devices."""
    packages = {}
    for distribution, module in DEPENDENCIES.items():
        entry = {}
        try:
            entry["version"] = importlib.metadata.version(distribution)
        except importlib.metadata.PackageNotFoundError:
            entry["version"] = None
        if check_imports:
            try:
                importlib.import_module(module)
                entry["import_ok"] = True
            except Exception as error:
                entry.update(import_ok=False, error=f"{type(error).__name__}: {error}")
        packages[distribution] = entry
    return {
        "created_at": datetime.now(timezone.utc).isoformat(),
        "python": platform.python_version(),
        "system": platform.system(),
        "release": platform.release(),
        "machine": platform.machine(),
        "packages": packages,
    }


def gui_log_directory():
    """Resolve writable user storage independently of the working directory."""
    override = os.environ.get("REVO3_LOG_DIR")
    if override:
        return Path(override).expanduser().resolve()
    if sys.platform == "win32":
        base = Path(os.environ.get("LOCALAPPDATA", str(Path.home() / "AppData/Local")))
        return base / "BrainCo/Revo3/logs"
    if sys.platform == "darwin":
        return Path.home() / "Library/Logs/BrainCo/Revo3"
    base = Path(os.environ.get("XDG_STATE_HOME", str(Path.home() / ".local/state")))
    return base / "brainco/revo3/logs"


def prepare_logging():
    directory = gui_log_directory()
    directory.mkdir(parents=True, exist_ok=True)
    os.environ["REVO3_LOG_DIR"] = str(directory)
    return directory


def install_exception_logging():
    """Record uncaught Python and worker errors while preserving default hooks."""
    previous = sys.excepthook
    previous_thread = threading.excepthook

    def exception_hook(kind, value, traceback):
        logging.getLogger().critical("Unhandled GUI exception", exc_info=(kind, value, traceback))
        previous(kind, value, traceback)

    def thread_hook(args):
        logging.getLogger().critical(
            "Unhandled worker exception",
            exc_info=(args.exc_type, args.exc_value, args.exc_traceback),
        )
        previous_thread(args)

    sys.excepthook = exception_hook
    threading.excepthook = thread_hook


def export_support_bundle(destination, snapshot=None, log_paths=()):
    """Atomically export metadata and at most three bounded log tails."""
    destination = Path(destination)
    report = environment_report()
    report["snapshot"] = snapshot or {}
    report["logs"] = []
    payloads = {}
    for index, path in enumerate(list(log_paths)[:3]):
        path = Path(path)
        name = f"logs/session-{index + 1}.log"
        try:
            with path.open("rb") as stream:
                stream.seek(0, os.SEEK_END)
                size = stream.tell()
                stream.seek(max(0, size - MAX_LOG_BYTES))
                payloads[name] = stream.read(MAX_LOG_BYTES)
            report["logs"].append({"file": name, "truncated": size > MAX_LOG_BYTES})
        except OSError as error:
            report["logs"].append({"file": name, "error": type(error).__name__})
    temporary = None
    try:
        with tempfile.NamedTemporaryFile(dir=destination.parent, suffix=".zip", delete=False) as stream:
            temporary = Path(stream.name)
        with zipfile.ZipFile(temporary, "w", zipfile.ZIP_DEFLATED) as archive:
            archive.writestr("report.json", json.dumps(report, indent=2, ensure_ascii=False))
            for name, payload in payloads.items():
                archive.writestr(name, payload)
        os.replace(temporary, destination)
    finally:
        if temporary is not None:
            temporary.unlink(missing_ok=True)
    return destination
