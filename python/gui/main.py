#!/usr/bin/env python3
"""
BC Revo3 SDK GUI - Modern Control Interface
Supports Revo3 protocols and device types

Usage:
    python main.py                                # Auto-detect
    python main.py --revo3-modbus                 # Only detect Revo3 Modbus
"""

import argparse
import signal
import sys
from pathlib import Path

# Suppress pyqtgraph disconnect warnings (PySide6 compatibility issue)
import warnings
warnings.filterwarnings("ignore", message="Failed to disconnect.*", category=RuntimeWarning)

# Add parent directory to path
sys.path.insert(0, str(Path(__file__).parent.parent))

from PySide6.QtWidgets import QApplication
from PySide6.QtCore import Qt

from gui.main_window import MainWindow


def main():
    """Main entry point"""
    # Parse command-line arguments
    parser = argparse.ArgumentParser(description="BC Revo3 SDK GUI")
    parser.add_argument("--revo3-modbus", action="store_true",
                        help="Only detect Revo3 Modbus devices (hides other protocols)")
    parser.add_argument("--mock", nargs="?", const="revo3-touch", default=None,
                        help="Run in Revo3 mock mode for UI testing")
    args = parser.parse_args()



    # Enable high DPI scaling
    QApplication.setHighDpiScaleFactorRoundingPolicy(
        Qt.HighDpiScaleFactorRoundingPolicy.PassThrough
    )
    
    app = QApplication(sys.argv)
    app.setApplicationName("BC Revo3 SDK")
    app.setOrganizationName("BrainCo")
    app.setApplicationVersion("1.0.0")
    
    # Handle Ctrl+C gracefully
    signal.signal(signal.SIGINT, signal.SIG_DFL)
    
    # Dark theme has compatibility issues on macOS, use system default
    # app.setStyleSheet(DARK_THEME)
    
    # Create and show main window
    window = MainWindow(revo3_modbus=args.revo3_modbus, mock_type=args.mock)
    window.show()
    
    sys.exit(app.exec())


if __name__ == "__main__":
    main()
