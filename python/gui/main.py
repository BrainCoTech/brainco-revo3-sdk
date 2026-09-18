#!/usr/bin/env python3
"""
BC Revo3 SDK GUI - Modern Control Interface
Supports Revo3 protocols and device types

Usage:
    python main.py                                # Auto-detect
    python main.py --revo3-modbus                 # Only detect Revo3 Modbus
"""

import argparse
import json
import logging
import signal
import sys
from pathlib import Path

# Suppress pyqtgraph disconnect warnings (PySide6 compatibility issue)
import warnings
warnings.filterwarnings("ignore", message="Failed to disconnect.*", category=RuntimeWarning)

# Add parent directory to path
sys.path.insert(0, str(Path(__file__).parent.parent))

from gui.runtime_support import (
    environment_report,
    export_support_bundle,
    install_exception_logging,
    prepare_logging,
)


def main(argv=None):
    """Main entry point"""
    # Parse command-line arguments
    parser = argparse.ArgumentParser(description="BC Revo3 SDK GUI")
    parser.add_argument("--check", action="store_true", help="Check GUI dependencies without opening devices")
    parser.add_argument("--diagnostics", type=Path, help="Export an offline environment ZIP and exit")
    parser.add_argument("--revo3-modbus", action="store_true",
                        help="Only detect Revo3 Modbus devices (hides other protocols)")
    parser.add_argument("--mock", nargs="?", const="revo3-touch", default=None,
                        help="Run in Revo3 mock mode for UI testing")
    parser.add_argument("--canfd", nargs="?", const="", default=None,
                        help="Start in CANFD mode, optionally specifying the adapter port name")
    args = parser.parse_args(argv)
    if args.diagnostics:
        try:
            print(export_support_bundle(args.diagnostics))
            return 0
        except OSError as error:
            print(f"Cannot export diagnostics: {error}", file=sys.stderr)
            return 1
    report = environment_report(check_imports=True)
    missing = [name for name, entry in report["packages"].items() if not entry["import_ok"]]
    if args.check:
        print(json.dumps(report, indent=2))
        return 1 if missing else 0
    if missing:
        print(json.dumps(report, indent=2), file=sys.stderr)
        print("From the repository or extracted example bundle root, install GUI dependencies with:\n"
              "python -m pip install './python[gui]'",
              file=sys.stderr)
        return 1
    try:
        log_directory = prepare_logging()
        import logger as example_logger
    except OSError as error:
        print(f"Cannot initialize GUI logs: {error}. Set REVO3_LOG_DIR to a writable directory.", file=sys.stderr)
        return 1
    install_exception_logging()
    try:
        return run_gui(args, report, log_directory)
    except Exception:
        logging.getLogger().exception("GUI startup failed")
        print(f"GUI startup failed. Logs: {example_logger.log_filename}", file=sys.stderr)
        return 1


def run_gui(args, report, log_directory):
    from PySide6.QtWidgets import QApplication
    from PySide6.QtCore import Qt
    from gui.main_window import MainWindow
    # Enable high DPI scaling
    QApplication.setHighDpiScaleFactorRoundingPolicy(
        Qt.HighDpiScaleFactorRoundingPolicy.PassThrough
    )
    
    app = QApplication(sys.argv)
    app.setApplicationName("BC Revo3 SDK")
    app.setOrganizationName("BrainCo")
    app.setApplicationVersion(report["packages"]["bc-revo3-sdk"]["version"] or "unknown")
    logging.getLogger().info("GUI started; log directory: %s", log_directory)
    
    # Handle Ctrl+C gracefully
    signal.signal(signal.SIGINT, signal.SIG_DFL)
    
    # Dynamic dark/light theme stylesheet application
    from gui.styles import is_dark_mode, get_theme_stylesheet
    is_dark = is_dark_mode()
    app.setStyleSheet(get_theme_stylesheet(is_dark))
    
    # Create and show main window
    window = MainWindow(
        revo3_modbus=args.revo3_modbus,
        mock_type=args.mock,
        canfd=args.canfd,
    )
    window.show()
    
    return app.exec()


if __name__ == "__main__":
    sys.exit(main())
