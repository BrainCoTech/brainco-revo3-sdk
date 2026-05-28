"""Revo3 data collection panel, matching the legacy GUI workflow."""

import time
from datetime import datetime
from pathlib import Path
from typing import Optional, TYPE_CHECKING

from PySide6.QtCore import QObject, QThread, Signal
from PySide6.QtWidgets import (
    QCheckBox,
    QFileDialog,
    QGroupBox,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QProgressBar,
    QPushButton,
    QSpinBox,
    QTextEdit,
    QVBoxLayout,
    QWidget,
)

from .constants import REVO3_MOTOR_COUNT
from .i18n import tr

if TYPE_CHECKING:
    from .shared_data import SharedDataManager


class CollectorWorker(QObject):
    progress = Signal(int, int, float)
    log_message = Signal(str)
    finished = Signal(bool, str)

    def __init__(self, shared_data, save_path, duration, freq, collect_motor, collect_touch):
        super().__init__()
        self.shared_data = shared_data
        self.save_path = save_path
        self.duration = duration
        self.freq = freq
        self.collect_motor = collect_motor
        self.collect_touch = collect_touch
        self.is_running = True

    def stop(self):
        self.is_running = False

    def run(self):
        try:
            save_dir = Path(self.save_path)
            save_dir.mkdir(parents=True, exist_ok=True)
            filename = save_dir / f"revo3_data_{datetime.now().strftime('%Y%m%d_%H%M%S')}.csv"
            self.log_message.emit(f"Saving to: {filename}")

            motor_freq = max(1, self.freq)
            touch_freq = min(20, motor_freq) if self.collect_touch else 0
            self.shared_data.stop()
            self.shared_data.start(motor_freq, touch_freq)

            start_time = time.time()
            total_samples = self.duration * motor_freq
            while self.is_running and time.time() - start_time < self.duration:
                current_count = self.shared_data.revo3_motor_buffer.len() if self.shared_data.revo3_motor_buffer else 0
                self.progress.emit(current_count, total_samples, time.time() - start_time)
                time.sleep(0.5)

            self.shared_data.stop()
            self._write_csv(filename)
            final_count = self.shared_data.revo3_motor_buffer.len() if self.shared_data.revo3_motor_buffer else 0
            self.finished.emit(True, f"Collection completed, {final_count} records")
        except Exception as e:
            import traceback

            traceback.print_exc()
            self.finished.emit(False, f"Collection failed: {e}")

    def _write_csv(self, filename):
        motor_data = self.shared_data.revo3_motor_buffer.pop_all() if self.shared_data.revo3_motor_buffer else []
        touch_data = self.shared_data.revo3_touch_buffer.pop_all() if self.shared_data.revo3_touch_buffer else []
        with open(filename, "w", encoding="utf-8") as f:
            headers = ["index"]
            if self.collect_motor:
                for prefix in ("status", "pos", "vel", "cur", "err"):
                    headers.extend(f"{prefix}_{i}" for i in range(REVO3_MOTOR_COUNT))
            if self.collect_touch:
                headers.extend(f"touch_summary_{i}" for i in range(42))
            f.write(",".join(headers) + "\n")

            for idx, motor in enumerate(motor_data):
                row = [str(idx)]
                if self.collect_motor:
                    values = [
                        list(getattr(motor, "statuses", []) or []),
                        list(getattr(motor, "positions", []) or []),
                        list(getattr(motor, "velocities", []) or []),
                        list(getattr(motor, "currents", []) or []),
                        list(getattr(motor, "errors", []) or []),
                    ]
                    for arr in values:
                        row.extend(str(arr[i] if i < len(arr) else 0) for i in range(REVO3_MOTOR_COUNT))
                if self.collect_touch:
                    if touch_data:
                        t_idx = min(idx * len(touch_data) // max(1, len(motor_data)), len(touch_data) - 1)
                        summary = list(getattr(touch_data[t_idx], "summary", []) or [])
                    else:
                        summary = []
                    row.extend(str(summary[i] if i < len(summary) else 0) for i in range(42))
                f.write(",".join(row) + "\n")
        self.log_message.emit(f"CSV write completed: {len(motor_data)} rows")


class DataCollectorPanel(QWidget):
    def __init__(self):
        super().__init__()
        self.shared_data: Optional["SharedDataManager"] = None
        self.worker = None
        self.thread = None
        self._setup_ui()

    def _setup_ui(self):
        layout = QVBoxLayout(self)
        config_group = QGroupBox(tr("data_collection"))
        config_layout = QVBoxLayout(config_group)

        row1 = QHBoxLayout()
        self.duration_label = QLabel(tr("duration_sec") + ":")
        row1.addWidget(self.duration_label)
        self.duration_spin = QSpinBox()
        self.duration_spin.setRange(1, 3600)
        self.duration_spin.setValue(10)
        row1.addWidget(self.duration_spin)
        self.freq_label = QLabel(tr("frequency") + ":")
        row1.addWidget(self.freq_label)
        self.freq_spin = QSpinBox()
        self.freq_spin.setRange(1, 2000)
        self.freq_spin.setValue(100)
        row1.addWidget(self.freq_spin)
        row1.addStretch()
        config_layout.addLayout(row1)

        row2 = QHBoxLayout()
        self.motor_check = QCheckBox(tr("motor_data"))
        self.motor_check.setChecked(True)
        self.touch_check = QCheckBox(tr("touch_data"))
        row2.addWidget(self.motor_check)
        row2.addWidget(self.touch_check)
        row2.addStretch()
        config_layout.addLayout(row2)

        row3 = QHBoxLayout()
        self.path_edit = QLineEdit(str(Path.home() / "revo3_data"))
        self.browse_btn = QPushButton(tr("btn_browse"))
        self.browse_btn.clicked.connect(self._browse)
        row3.addWidget(QLabel(tr("save_path") + ":"))
        row3.addWidget(self.path_edit, 1)
        row3.addWidget(self.browse_btn)
        config_layout.addLayout(row3)
        layout.addWidget(config_group)

        button_layout = QHBoxLayout()
        self.start_btn = QPushButton(tr("btn_start_collection"))
        self.start_btn.clicked.connect(self._start_collection)
        self.stop_btn = QPushButton(tr("btn_stop_collection"))
        self.stop_btn.clicked.connect(self._stop_collection)
        self.stop_btn.setEnabled(False)
        button_layout.addWidget(self.start_btn)
        button_layout.addWidget(self.stop_btn)
        button_layout.addStretch()
        layout.addLayout(button_layout)

        self.progress_bar = QProgressBar()
        layout.addWidget(self.progress_bar)
        self.log_text = QTextEdit()
        self.log_text.setReadOnly(True)
        layout.addWidget(self.log_text, 1)

    def _browse(self):
        path = QFileDialog.getExistingDirectory(self, tr("select_directory"), self.path_edit.text())
        if path:
            self.path_edit.setText(path)

    def set_device(self, device, slave_id, device_info, shared_data=None):
        self.shared_data = shared_data
        self.start_btn.setEnabled(shared_data is not None)

    def clear_device(self):
        self._stop_collection()
        self.shared_data = None
        self.start_btn.setEnabled(False)

    def _start_collection(self):
        if not self.shared_data:
            return
        self.thread = QThread()
        self.worker = CollectorWorker(
            self.shared_data,
            self.path_edit.text(),
            self.duration_spin.value(),
            self.freq_spin.value(),
            self.motor_check.isChecked(),
            self.touch_check.isChecked(),
        )
        self.worker.moveToThread(self.thread)
        self.thread.started.connect(self.worker.run)
        self.worker.progress.connect(self._on_progress)
        self.worker.log_message.connect(self._log)
        self.worker.finished.connect(self._on_finished)
        self.worker.finished.connect(self.thread.quit)
        self.thread.start()
        self.start_btn.setEnabled(False)
        self.stop_btn.setEnabled(True)
        self.progress_bar.setValue(0)

    def _stop_collection(self):
        if self.worker:
            self.worker.stop()
        self.stop_btn.setEnabled(False)

    def _on_progress(self, count, total, elapsed):
        self.progress_bar.setValue(min(100, int(count * 100 / max(1, total))))
        self._log(f"Collected {count}/{total} samples, elapsed {elapsed:.1f}s")

    def _on_finished(self, success, message):
        self._log(("OK: " if success else "ERROR: ") + message)
        self.start_btn.setEnabled(self.shared_data is not None)
        self.stop_btn.setEnabled(False)

    def _log(self, message):
        self.log_text.append(message)

    def update_texts(self):
        self.start_btn.setText(tr("btn_start_collection"))
        self.stop_btn.setText(tr("btn_stop_collection"))
        self.browse_btn.setText(tr("btn_browse"))
