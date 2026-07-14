"""Touch Sensor Shared Components

Common chart widgets, constants, and utilities used across all touch sensor panels:
- PressureTouchPanel (Modulus/Pressure)
- ForceTouchPanel (ArrayPressure/Force-Torque)
- TouchPanelRevo3 (Revo3 Tactile Arrays)
"""

import asyncio
import numpy as np
from typing import Optional
from PySide6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QGroupBox,
    QPushButton, QLabel, QCheckBox, QGridLayout, QTabWidget,
    QFrame, QProgressBar, QComboBox, QScrollArea
)
from PySide6.QtCore import Qt, QTimer

from .styles import COLORS, is_dark_mode
from common_imports import logger, run_async


try:
    import pyqtgraph as pg
    HAS_PYQTGRAPH = True
except ImportError:
    pg = None  # type: ignore
    HAS_PYQTGRAPH = False


# =============================================================================
# Shared Chart Widgets
# =============================================================================

class SummaryChart(QWidget):
    """Real-time multi-line chart for summary data (force, pressure, etc.)"""

    def __init__(self, title: str = "Summary", y_range: tuple = (0, 5000),
                 sensor_names: list = None, sensor_colors: list = None,
                 y_label: str = "mN"):
        super().__init__()
        self.title = title
        self.y_range = y_range
        self.sensor_names = sensor_names or []
        self.sensor_colors = sensor_colors or []
        self.sensor_count = len(self.sensor_names)
        self.y_label = y_label
        self.curves = []
        self.data = [[] for _ in range(self.sensor_count)]
        self.max_points = 200
        self._setup_ui()

    def _setup_ui(self):
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)

        if HAS_PYQTGRAPH and pg is not None:
            self.plot = pg.PlotWidget()
            self.plot.setBackground('#1a1a2e')
            self.plot.showGrid(x=True, y=True, alpha=0.3)
            self.plot.setYRange(self.y_range[0], self.y_range[1])
            self.plot.setXRange(0, self.max_points)
            self.plot.setTitle(self.title, color='w', size='10pt')
            self.plot.setLabel('bottom', 'samples', color='w')
            self.plot.setLabel('left', self.y_label, color='w')

            self.plot.addLegend(offset=(-10, 10))

            for i, (name, color) in enumerate(zip(self.sensor_names, self.sensor_colors)):
                pen = pg.mkPen(color=color, width=2)
                curve = self.plot.plot([], [], pen=pen, name=name)
                self.curves.append(curve)
            layout.addWidget(self.plot)
        else:
            layout.addWidget(QLabel("pyqtgraph not installed"))

    def add_data(self, values: list):
        """Add data for all sensors"""
        for i, val in enumerate(values[:self.sensor_count]):
            self.data[i].append(val)
            if len(self.data[i]) > self.max_points:
                self.data[i].pop(0)
        self._update_curves()

    def _update_curves(self):
        if not HAS_PYQTGRAPH:
            return
        for i, curve in enumerate(self.curves):
            if self.data[i]:
                curve.setData(list(range(len(self.data[i]))), self.data[i])

    def clear(self):
        self.data = [[] for _ in range(self.sensor_count)]
        self._update_curves()

    def set_sensor_visible(self, sensor_idx: int, visible: bool):
        """Show/hide a sensor curve"""
        if HAS_PYQTGRAPH and sensor_idx < len(self.curves):
            self.curves[sensor_idx].setVisible(visible)


class HeatmapChart(QWidget):
    """2D heatmap chart for pressure/tactile array data with pyqtgraph ImageItem"""

    def __init__(self, module_name: str, point_count: int, color: tuple,
                 rows: int, cols: int, coord_map: list = None):
        super().__init__()
        self.module_name = module_name
        self.point_count = point_count
        self.color = color
        self.rows = rows
        self.cols = cols
        self.coord_map = coord_map  # list of (row, col) tuples, or None for divmod fallback
        self.current_values = [0] * point_count
        self.value_unit = "force"
        self.current_max_limit = 500.0
        self.current_stats_max_limit = None
        self._setup_ui()

    def _get_coords(self, i: int):
        """Get (row, col) for point index i, using coord_map if available"""
        if self.coord_map and i < len(self.coord_map):
            return self.coord_map[i]
        return divmod(i, self.cols)

    def _setup_ui(self):
        layout = QVBoxLayout(self)
        layout.setContentsMargins(4, 4, 4, 4)
        layout.setSpacing(4)

        # -- Header: module name + stats --
        header_frame = QFrame()
        header_frame.setStyleSheet("background-color: #1a1a2e; border-radius: 6px; padding: 4px 8px;")
        header = QHBoxLayout(header_frame)
        header.setContentsMargins(8, 4, 8, 4)
        r, g, b = self.color
        name_label = QLabel(f"🔥 {self.module_name} ({self.point_count} pts)")
        name_label.setStyleSheet(
            "font-size: 16px; font-weight: bold; color: #ffeb3b;"
        )
        header.addWidget(name_label)
        header.addStretch()
        self.stats_label = QLabel("max: 0.0  avg: 0.0 mN  |  sum: 0.00 N  |  cnt: 0/0")
        self.stats_label.setStyleSheet(
            "font-size: 14px; font-family: 'Courier New'; color: #eee;"
        )
        header.addWidget(self.stats_label)
        layout.addWidget(header_frame)

        # -- Body: heatmap --
        if HAS_PYQTGRAPH and pg is not None:
            self.plot_widget = pg.PlotWidget()
            self.plot_widget.setBackground('#1a1a2e')
            self.plot_widget.hideAxis('bottom')
            self.plot_widget.hideAxis('left')
            self.plot_widget.getViewBox().invertY(True)

            # Colormap: black -> blue -> cyan -> yellow -> red
            positions = [0.0, 0.25, 0.5, 0.75, 1.0]
            colors_rgb = [
                (0, 0, 0),
                (0, 0, 180),
                (0, 200, 200),
                (220, 220, 0),
                (255, 50, 0),
            ]
            self.cmap = pg.ColorMap(positions, colors_rgb)
            self.lut = self.cmap.getLookupTable(nPts=256)
            self.disabled_cmap = pg.ColorMap([0.0, 1.0], [(35, 35, 45), (35, 35, 45)])
            self.disabled_lut = self.disabled_cmap.getLookupTable(nPts=256)

            self.img_item = pg.ImageItem()
            self.img_item.setLookupTable(self.lut)
            self.plot_widget.addItem(self.img_item)

            # Initialize 2D grid with zeros instead of nan (nan breaks pyqtgraph ImageItem)
            self._data_2d = np.zeros((self.rows, self.cols), dtype=np.float64)
            valid_coords = set()
            for i in range(self.point_count):
                r_idx, c_idx = self._get_coords(i)
                if r_idx < self.rows and c_idx < self.cols:
                    valid_coords.add((r_idx, c_idx))
                    
            # Explicitly draw empty placeholders for missing sensors
            for r in range(self.rows):
                for c in range(self.cols):
                    if (r, c) not in valid_coords:
                        # Draw a distinct dark dotted/dashed box to indicate 'No Sensor Layout Hole'
                        rect = pg.QtWidgets.QGraphicsRectItem(c, r, 1, 1)
                        rect.setPen(pg.mkPen('#3a3a5a', width=1, style=Qt.DashLine))
                        rect.setBrush(pg.mkBrush(20, 20, 30, 200))
                        self.plot_widget.addItem(rect)

            self.img_item.setImage(self._data_2d.T, levels=(0, 500))

            # Text overlays
            self.text_items = []
            for i in range(self.point_count):
                r_idx, c_idx = self._get_coords(i)
                if r_idx < self.rows and c_idx < self.cols:
                    txt = pg.TextItem(str(i + 1), color='w', anchor=(0.5, 0.5))
                    txt.setFont(pg.QtGui.QFont('Courier New', 11))
                    txt.setPos(c_idx + 0.5, r_idx + 0.5)
                    self.plot_widget.addItem(txt)
                    self.text_items.append(txt)

            # Colorbar
            self.bar_item = None
            try:
                bar_item = pg.ColorBarItem(
                    values=(0, 500), colorMap=self.cmap,
                    interactive=False, width=15,
                )
                bar_item.setImageItem(self.img_item, insert_in=self.plot_widget.plotItem)
                self.bar_item = bar_item
            except Exception:
                pass

            layout.addWidget(self.plot_widget, 1)
        else:
            layout.addWidget(QLabel("pyqtgraph required"), 1)

    def _update_stats_label(self):
        n_total = len(self.current_values) if self.current_values else 1
        total = sum(self.current_values)
        avg = total / n_total
        max_val = max(self.current_values) if self.current_values else 0
        active_vals = [v for v in self.current_values if v > 0]
        active_count = len(active_vals)

        if self.value_unit == "force":
            if self.current_stats_max_limit is not None:
                sum_limit = self.current_stats_max_limit * self.point_count
                self.stats_label.setText(
                    f"max: {max_val:.0f}  avg: {avg:.0f}/{self.current_stats_max_limit:.0f} mN  |  "
                    f"sum: {total / 1000.0:.1f}/{sum_limit / 1000.0:.1f} N  |  cnt: {active_count}/{n_total}"
                )
            else:
                self.stats_label.setText(
                    f"max: {max_val:.0f}  avg: {avg:.0f} mN  |  "
                    f"sum: {total / 1000.0:.1f} N  |  cnt: {active_count}/{n_total}"
                )
        else:
            if self.current_stats_max_limit is not None:
                avg_text = f"{avg:.0f}/{self.current_stats_max_limit:.0f}"
            else:
                avg_text = f"{avg:.0f}"
            self.stats_label.setText(
                f"max: {max_val:.0f}  avg: {avg_text} (ADC)  |  "
                f"sum: {total:.0f}  |  cnt: {active_count}/{n_total}"
            )

    def set_value_unit(self, value_unit: str, max_limit: float = None, stats_max_limit: float = None):
        self.value_unit = value_unit
        if max_limit is not None:
            self.current_max_limit = max_limit
        self.current_stats_max_limit = stats_max_limit
        self._update_stats_label()

    def add_data(
        self,
        values: list,
        is_enabled: bool = True,
        max_limit: float = 500.0,
        value_unit: str = "force",
        stats_max_limit: float = None,
    ):
        """Update heatmap with new values"""
        self.value_unit = value_unit
        self.current_max_limit = max_limit
        self.current_stats_max_limit = stats_max_limit
        if not is_enabled:
            if HAS_PYQTGRAPH:
                self.img_item.setLookupTable(self.disabled_lut)
                self._data_2d.fill(0.0)
                self.img_item.setImage(self._data_2d.T, levels=(0, 100))
                for txt in self.text_items:
                    txt.setText("OFF")
                    txt.setColor('#666666')
            self.stats_label.setText("Disabled")
            return

        n = min(len(values), self.point_count)
        self.current_values = list(values[:n]) + [0] * max(0, self.point_count - n)

        for i in range(self.point_count):
            r_idx, c_idx = self._get_coords(i)
            if r_idx < self.rows and c_idx < self.cols:
                self._data_2d[r_idx, c_idx] = float(self.current_values[i])

        valid = [v for v in self.current_values if v > 0]
        max_val = max(valid) if valid else 100
        level_max = max(100, max_val * 1.2)

        if HAS_PYQTGRAPH:
            self.img_item.setLookupTable(self.lut)
            self.img_item.setImage(self._data_2d.T, levels=(0, max_limit))
            if hasattr(self, "bar_item") and self.bar_item is not None:
                try:
                    self.bar_item.setLevels((0, max_limit))
                except Exception:
                    pass

            for i, txt in enumerate(self.text_items):
                val = self.current_values[i]
                txt.setText(f"{val:.1f}" if isinstance(val, float) else str(val))
                if val > max_limit * 0.5:
                    txt.setColor('k')
                else:
                    txt.setColor('w')

        self._update_stats_label()

    def clear(self):
        self.current_values = [0] * self.point_count
        for i in range(self.point_count):
            r_idx, c_idx = self._get_coords(i)
            if r_idx < self.rows and c_idx < self.cols:
                self._data_2d[r_idx, c_idx] = 0.0
        if HAS_PYQTGRAPH:
            self.img_item.setLookupTable(self.lut)
            self.img_item.setImage(self._data_2d.T, levels=(0, 500))
            if hasattr(self, "bar_item") and self.bar_item is not None:
                try:
                    self.bar_item.setLevels((0, 500))
                except Exception:
                    pass
            for txt in self.text_items:
                txt.setText("0")
                txt.setColor('w')
        self.stats_label.setText("max: 0.0  avg: 0.0 mN  |  sum: 0.00 N  |  cnt: 0/0")


def build_status_cards(parent_layout, sensor_names, sensor_colors, is_compact=False):
    """Build sensor status cards with progress bars and value labels.

    Returns: (sensor_cards, sensor_bars, sensor_labels)
    """
    title = QLabel("📊 Sensor Status")
    title.setStyleSheet("font-weight: bold; font-size: 12px;")
    parent_layout.addWidget(title)

    sensor_cards = []
    sensor_bars = []
    sensor_labels = []

    scroll = QScrollArea()
    scroll.setWidgetResizable(True)
    scroll.setStyleSheet("QScrollArea { border: none; background: transparent; }")

    cards_widget = QWidget()
    cards_layout = QVBoxLayout(cards_widget)
    cards_layout.setContentsMargins(0, 0, 0, 0)
    cards_layout.setSpacing(2 if is_compact else 4)

    is_dark = is_dark_mode()
    bg_card = COLORS['bg_card'] if is_dark else "#ffffff"
    border_color = "#34495e" if is_dark else "#dee2e6"
    text_muted = COLORS['text_secondary'] if is_dark else "#2c3e50"
    bg_bar = "#2a2a3e" if is_dark else "#e9ecef"
    border_bar = "#444" if is_dark else "#cfd4d9"

    for i, (name, color) in enumerate(zip(sensor_names, sensor_colors)):
        # If light mode, darken the color to guarantee enough contrast on white background
        r, g, b = color
        if not is_dark:
            if r > 200 and g > 200 and b < 150:
                # Yellow -> Dark Gold/Orange-Brown
                display_color = (180, 130, 0)
            elif r > 200 and g < 150 and b > 200:
                # Magenta -> Dark Purple
                display_color = (160, 30, 160)
            elif r < 150 and g > 200 and b > 200:
                # Cyan -> Dark Cyan/Teal
                display_color = (0, 140, 140)
            elif r > 200 and g < 150 and b < 150:
                # Red -> Deep Red
                display_color = (200, 40, 40)
            elif r < 150 and g > 200 and b < 150:
                # Green -> Deep Green
                display_color = (30, 150, 30)
            elif r < 150 and g < 150 and b > 200:
                # Blue -> Deep Blue
                display_color = (30, 80, 200)
            else:
                display_color = (int(r * 0.7), int(g * 0.7), int(b * 0.7))
        else:
            display_color = color

        card = QFrame()
        card.setStyleSheet(f"""
            QFrame {{
                background-color: {bg_card};
                border: 1px solid {border_color};
                border-left: 4px solid rgb{display_color};
                border-radius: 4px;
                padding: 2px;
            }}
        """)
        card_layout = QHBoxLayout(card)
        card_layout.setContentsMargins(6, 2, 6, 2)
        card_layout.setSpacing(6)

        name_label = QLabel(name)
        name_label.setFixedWidth(80 if is_compact else 50)
        name_label.setStyleSheet(f"color: rgb{display_color}; font-weight: bold; font-size: 13px;")
        card_layout.addWidget(name_label)

        bar = QProgressBar()
        bar.setRange(0, 5000)
        bar.setValue(0)
        bar.setTextVisible(False)
        bar.setFixedHeight(14 if is_compact else 16)
        dr, dg, db = display_color
        bar.setStyleSheet(f"""
            QProgressBar {{
                border: 1px solid {border_bar};
                border-radius: 3px;
                background-color: {bg_bar};
            }}
            QProgressBar::chunk {{
                background-color: rgb({dr}, {dg}, {db});
                border-radius: 2px;
            }}
        """)
        card_layout.addWidget(bar, 1)
        sensor_bars.append(bar)

        val_label = QLabel("0")
        val_label.setFixedWidth(220)
        val_label.setAlignment(Qt.AlignRight)
        val_label.setStyleSheet(f"""
            QLabel {{
                font-family: 'Courier New';
                font-size: 12px;
                font-weight: bold;
                color: {text_muted};
            }}
        """)
        card_layout.addWidget(val_label)
        sensor_labels.append(val_label)

        cards_layout.addWidget(card)
        sensor_cards.append(card)

    scroll.setWidget(cards_widget)
    parent_layout.addWidget(scroll, 1)

    return sensor_cards, sensor_bars, sensor_labels
