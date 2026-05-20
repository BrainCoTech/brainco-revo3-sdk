"""Revo3-only timing test panel using the legacy chart worker."""

from .timing_test_revo3_worker import (
    REVO3_SINGLE_FINGER_OPTIONS,
    REVO3_SINGLE_JOINT_OPTIONS,
    TimingTestRevo3Worker,
)

try:
    from PySide6.QtCore import QThread
    from PySide6.QtWidgets import (
        QButtonGroup,
        QComboBox,
        QDoubleSpinBox,
        QGroupBox,
        QHBoxLayout,
        QLabel,
        QPushButton,
        QRadioButton,
        QSpinBox,
        QTextEdit,
        QVBoxLayout,
        QWidget,
    )
except ImportError:
    raise


class TimingTestPanel(QWidget):
    def __init__(self):
        super().__init__()
        self.shared_data = None
        self.worker = None
        self._thread = None
        self.is_running = False
        self._setup_ui()

    @property
    def device(self):
        return self.shared_data.device if self.shared_data else None

    @property
    def slave_id(self):
        return self.shared_data.slave_id if self.shared_data else 1

    def _setup_ui(self):
        layout = QVBoxLayout(self)
        mode_group = QGroupBox("Timing Test")
        mode_layout = QHBoxLayout(mode_group)
        self.mode_group = QButtonGroup(self)
        self.single_joint_radio = QRadioButton("Single Joint")
        self.single_joint_radio.setChecked(True)
        self.single_finger_radio = QRadioButton("Single Finger")
        self.all_fingers_radio = QRadioButton("All Fingers")
        for i, btn in enumerate([self.single_joint_radio, self.single_finger_radio, self.all_fingers_radio]):
            self.mode_group.addButton(btn, i)
            mode_layout.addWidget(btn)
        self.target_combo = QComboBox()
        for name, idx in REVO3_SINGLE_JOINT_OPTIONS:
            self.target_combo.addItem(name, idx)
        mode_layout.addWidget(self.target_combo)
        self.cycles_spin = QSpinBox()
        self.cycles_spin.setRange(1, 100)
        self.cycles_spin.setValue(5)
        mode_layout.addWidget(QLabel("Cycles"))
        mode_layout.addWidget(self.cycles_spin)
        self.kp_spin = QDoubleSpinBox()
        self.kp_spin.setRange(0.0, 50.0)
        self.kp_spin.setValue(5.0)
        self.kd_spin = QDoubleSpinBox()
        self.kd_spin.setRange(0.0, 10.0)
        self.kd_spin.setValue(0.5)
        mode_layout.addWidget(QLabel("Kp"))
        mode_layout.addWidget(self.kp_spin)
        mode_layout.addWidget(QLabel("Kd"))
        mode_layout.addWidget(self.kd_spin)
        self.start_btn = QPushButton("Start")
        self.start_btn.clicked.connect(self._start)
        self.stop_btn = QPushButton("Stop")
        self.stop_btn.clicked.connect(self._stop)
        self.stop_btn.setEnabled(False)
        mode_layout.addWidget(self.start_btn)
        mode_layout.addWidget(self.stop_btn)
        mode_layout.addStretch()
        layout.addWidget(mode_group)
        self.log = QTextEdit()
        self.log.setReadOnly(True)
        layout.addWidget(self.log, 1)
        self.single_joint_radio.toggled.connect(self._update_targets)
        self.single_finger_radio.toggled.connect(self._update_targets)

    def _update_targets(self):
        self.target_combo.clear()
        options = REVO3_SINGLE_FINGER_OPTIONS if self.single_finger_radio.isChecked() else REVO3_SINGLE_JOINT_OPTIONS
        for name, idx in options:
            self.target_combo.addItem(name, idx)

    def set_device(self, device, slave_id, device_info, shared_data=None):
        self.shared_data = shared_data
        self.start_btn.setEnabled(shared_data is not None)

    def clear_device(self):
        self._stop()
        self.shared_data = None
        self.start_btn.setEnabled(False)

    def _start(self):
        if not self.shared_data or not self.device:
            return
        self._thread = QThread()
        test_mode = "single_joint" if self.single_joint_radio.isChecked() else "single_finger"
        if self.all_fingers_radio.isChecked():
            test_mode = "all_fingers"
        self.worker = TimingTestRevo3Worker(
            self.device,
            self.slave_id,
            self.cycles_spin.value(),
            2,
            test_mode,
            self.target_combo.currentData(),
            self.shared_data,
            "MIT",
            "Sine",
            self.kp_spin.value(),
            self.kd_spin.value(),
        )
        self.worker.moveToThread(self._thread)
        self._thread.started.connect(self.worker.run)
        if hasattr(self.worker, "log_message"):
            self.worker.log_message.connect(self.log.append)
        if hasattr(self.worker, "finished"):
            self.worker.finished.connect(self._on_finished)
            self.worker.finished.connect(self._thread.quit)
        self._thread.start()
        self.start_btn.setEnabled(False)
        self.stop_btn.setEnabled(True)

    def _stop(self):
        if self.worker and hasattr(self.worker, "stop"):
            self.worker.stop()
        self.stop_btn.setEnabled(False)

    def _on_finished(self, *args):
        self.start_btn.setEnabled(self.shared_data is not None)
        self.stop_btn.setEnabled(False)
        self.log.append("Timing test finished")

    def update_texts(self):
        pass
