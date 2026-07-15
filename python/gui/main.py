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
    parser.add_argument("--touch-vendor", choices=["matrix", "pressure"], default=None,
                        help="Manually specify touch vendor (matrix or pressure) to override auto-detection")
    parser.add_argument("--canfd", nargs="?", const="", default=None,
                        help="Start in CANFD mode, optionally specifying the adapter port name")
    parser.add_argument("--vts-force-model-dir", default=None,
                        help="Parent directory for VTS force models: {dir}/{SN}/{SN}.onnx.enc")
    parser.add_argument("--vts-force-model-mode", choices=["none", "auto", "required"], default="none",
                        help="VTS force model loading mode: none=fast init, auto=load when present, required=skip sensors without models")
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
    
    # Dynamic dark/light theme stylesheet application
    from gui.styles import is_dark_mode, get_theme_stylesheet
    is_dark = is_dark_mode()
    app.setStyleSheet(get_theme_stylesheet(is_dark))
    
    # Create and show main window
    window = MainWindow(
        revo3_modbus=args.revo3_modbus,
        mock_type=args.mock,
        touch_vendor=args.touch_vendor,
        vts_force_model_dir=args.vts_force_model_dir,
        vts_force_model_mode=args.vts_force_model_mode,
        canfd=args.canfd,
    )
    window.show()
    
    sys.exit(app.exec())


if __name__ == "__main__":
    main()
