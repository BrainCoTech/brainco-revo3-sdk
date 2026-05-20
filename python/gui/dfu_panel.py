"""Revo3 DFU panel with legacy GUI shape."""

import asyncio
import inspect
import os
import sys
from pathlib import Path
from typing import Optional, TYPE_CHECKING

from PySide6.QtCore import QObject, QThread, Signal, QSettings
from PySide6.QtWidgets import (
    QFileDialog,
    QGroupBox,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QMessageBox,
    QProgressBar,
    QPushButton,
    QVBoxLayout,
    QWidget,
)

from .i18n import tr

sys.path.insert(0, str(Path(__file__).parent.parent))
from common_imports import sdk

if TYPE_CHECKING:
    from .shared_data import SharedDataManager


class DfuWorker(QObject):
    progress = Signal(int)
    state_changed = Signal(str)
    finished = Signal(bool, str)

    def __init__(self, device, slave_id: int, firmware_path: str):
        super().__init__()
        self.device = device
        self.slave_id = slave_id
        self.firmware_path = firmware_path

    def run(self):
        loop = None
        try:
            loop = asyncio.new_event_loop()
            asyncio.set_event_loop(loop)
            loop.run_until_complete(self._run_dfu())
            self.finished.emit(True, "")
        except Exception as e:
            import traceback

            traceback.print_exc()
            self.finished.emit(False, str(e))
        finally:
            if loop is not None:
                loop.close()

    async def _run_dfu(self):
        self.state_changed.emit("Starting")
        # Wait for 0.5s to allow the RS-485 bus to settle and data collector to fully exit
        await asyncio.sleep(0.5)

        def on_state(slave_id, state):
            state_map = {
                0: "dfu_state_idle",
                1: "dfu_state_starting",
                2: "dfu_state_started",
                3: "dfu_state_transferring",
                4: "dfu_state_completed",
                5: "dfu_state_aborted"
            }
            state_key = state_map.get(state, "dfu_state_unknown")
            state_text = tr(state_key).replace("{state}", str(state))
            self.state_changed.emit(f"{tr('dfu_state_prefix')}{state_text}")
            
        def on_progress(slave_id, p):
            self.progress.emit(int(p * 100))

        result = self.device.revo3_start_dfu(
            self.slave_id, 
            self.firmware_path, 
            5,
            on_state,
            on_progress
        )
        if asyncio.isfuture(result) or inspect.isawaitable(result):
            await result
        self.progress.emit(100)
        self.state_changed.emit("Completed")


class DfuPanel(QWidget):
    dfu_started = Signal()
    dfu_finished = Signal(bool)

    def __init__(self):
        super().__init__()
        self.shared_data: Optional["SharedDataManager"] = None
        self._dfu_thread = None
        self._dfu_worker = None
        self._setup_ui()

    @property
    def device(self):
        return self.shared_data.device if self.shared_data else None

    @property
    def slave_id(self):
        return self.shared_data.slave_id if self.shared_data else 1

    @property
    def device_info(self):
        return self.shared_data.device_info if self.shared_data else None

    def _setup_ui(self):
        layout = QVBoxLayout(self)
        warning = QGroupBox()
        warning_layout = QVBoxLayout(warning)
        self.warning_title_label = QLabel(tr("dfu_warning_title"))
        self.warning_title_label.setStyleSheet("font-weight: bold; color: #856404;")
        self.warning_text_label = QLabel(f"{tr('dfu_warning_1')}\n{tr('dfu_warning_2')}\n{tr('dfu_warning_3')}")
        self.warning_text_label.setWordWrap(True)
        
        self.version_note_label = QLabel(tr("note_modbus_ota_requires_0_0_4"))
        self.version_note_label.setStyleSheet("color: #666666; font-style: italic;")
        self.version_note_label.setWordWrap(True)
        
        warning_layout.addWidget(self.warning_title_label)
        warning_layout.addWidget(self.warning_text_label)
        warning_layout.addWidget(self.version_note_label)
        layout.addWidget(warning)

        self.device_group = QGroupBox(tr("device_info"))
        dev_layout = QHBoxLayout(self.device_group)
        self.device_type_label = QLabel(tr("device_type") + ": --")
        self.firmware_version_label = QLabel(tr("current_firmware") + ": --")
        dev_layout.addWidget(self.device_type_label)
        dev_layout.addWidget(self.firmware_version_label)
        dev_layout.addStretch()
        layout.addWidget(self.device_group)

        self.file_group = QGroupBox(tr("firmware_file"))
        file_layout = QHBoxLayout(self.file_group)
        self.file_path_edit = QLineEdit()
        self.settings = QSettings("BrainCo", "Revo3SDK")
        last_path = self.settings.value("dfu_last_path", "")
        if isinstance(last_path, str) and last_path:
            self.file_path_edit.setText(last_path)
            
        self.browse_btn = QPushButton(tr("btn_browse"))
        self.browse_btn.clicked.connect(self._browse)
        file_layout.addWidget(self.file_path_edit, 1)
        file_layout.addWidget(self.browse_btn)
        layout.addWidget(self.file_group)

        self.progress_bar = QProgressBar()
        self.progress_bar.setTextVisible(True)
        self.progress_bar.setFormat("%p%")
        self.progress_bar.setStyleSheet("""
            QProgressBar {
                border: 1px solid #cfd4d9;
                border-radius: 4px;
                text-align: center;
                background-color: #f8f9fa;
            }
            QProgressBar::chunk {
                background-color: #5D9CEC;
            }
        """)
        layout.addWidget(self.progress_bar)
        self.status_label = QLabel(tr("dfu_state_idle"))
        layout.addWidget(self.status_label)

        buttons = QHBoxLayout()
        self.start_btn = QPushButton(tr("btn_start_upgrade"))
        self.start_btn.clicked.connect(self._start_dfu)
        buttons.addWidget(self.start_btn)
        buttons.addStretch()
        layout.addLayout(buttons)
        layout.addStretch()

    def _browse(self):
        last_dir = self.settings.value("dfu_last_dir", "")
        if not isinstance(last_dir, str):
            last_dir = ""
        path, _ = QFileDialog.getOpenFileName(self, tr("firmware_file"), last_dir, "Firmware (*.bin *.ota);;All (*)")
        if path:
            self.file_path_edit.setText(path)
            self.settings.setValue("dfu_last_path", path)
            self.settings.setValue("dfu_last_dir", os.path.dirname(path))

    def set_device(self, device, slave_id, device_info, shared_data=None):
        self.shared_data = shared_data
        if device_info:
            self.device_type_label.setText(f"{tr('device_type')}: {device_info.hardware_type}")
            self.firmware_version_label.setText(f"{tr('current_firmware')}: {device_info.firmware_version}")

    def clear_device(self):
        self.shared_data = None
        self.device_type_label.setText(tr("device_type") + ": --")
        self.firmware_version_label.setText(tr("current_firmware") + ": --")

    def _start_dfu(self):
        if not self.device:
            QMessageBox.warning(self, tr("warning"), tr("error_no_device"))
            return
        firmware_path = self.file_path_edit.text().strip()
        if not firmware_path or not os.path.exists(firmware_path):
            QMessageBox.warning(self, tr("warning"), tr("dfu_select_file"))
            return
            
        self.settings.setValue("dfu_last_path", firmware_path)
        self.settings.setValue("dfu_last_dir", os.path.dirname(firmware_path))
        
        self.dfu_started.emit()
        self.start_btn.setEnabled(False)
        self.progress_bar.setValue(0)
        self._dfu_thread = QThread()
        self._dfu_worker = DfuWorker(self.device, self.slave_id, firmware_path)
        self._dfu_worker.moveToThread(self._dfu_thread)
        self._dfu_thread.started.connect(self._dfu_worker.run)
        self._dfu_worker.progress.connect(self.progress_bar.setValue)
        self._dfu_worker.state_changed.connect(self.status_label.setText)
        self._dfu_worker.finished.connect(self._on_finished)
        self._dfu_worker.finished.connect(self._dfu_thread.quit)
        self._dfu_thread.start()

    def _on_finished(self, success, message):
        self.start_btn.setEnabled(True)
        self.dfu_finished.emit(success)
        if success:
            QMessageBox.information(self, tr("success"), tr("dfu_completed"))
        else:
            QMessageBox.critical(self, tr("error"), message)

    def update_texts(self):
        self.warning_title_label.setText(tr("dfu_warning_title"))
        self.warning_text_label.setText(f"{tr('dfu_warning_1')}\n{tr('dfu_warning_2')}\n{tr('dfu_warning_3')}")
        self.device_group.setTitle(tr("device_info"))
        
        if self.device_info:
            self.device_type_label.setText(f"{tr('device_type')}: {self.device_info.hardware_type}")
            self.firmware_version_label.setText(f"{tr('current_firmware')}: {self.device_info.firmware_version}")
        else:
            self.device_type_label.setText(tr("device_type") + ": --")
            self.firmware_version_label.setText(tr("current_firmware") + ": --")
            
        if hasattr(self, 'file_group'):
            self.file_group.setTitle(tr("firmware_file"))
            
        self.browse_btn.setText(tr("btn_browse"))
        self.start_btn.setText(tr("btn_start_upgrade"))
