"""Touch Sensor Shared Components

Common chart widgets, constants, and utilities used across all touch sensor panels:
- mt_* piezoresistive array panels
- hp_* fingertip force/torque panels
- TouchPanelRevo3 (Revo3 Tactile Arrays)
"""

import asyncio
import logging
import math
import numpy as np
from typing import Optional
from PySide6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QGroupBox,
    QPushButton, QLabel, QCheckBox, QGridLayout, QTabWidget,
    QFrame, QProgressBar, QComboBox, QScrollArea, QSizePolicy
)
from PySide6.QtCore import Qt, QTimer, QPointF, QRectF
from PySide6.QtGui import QPainter, QPen, QBrush, QColor, QFont

from .styles import COLORS, is_dark_mode

logger = logging.getLogger("revo3.vision_touch")

# The hp_* product specification defines a 30 N Fz measurement range and a
# 0.05 Nm Mx/My measurement range. Fx/Fy and Fn remain dynamically scaled.
HP_FORCE_DISPLAY_BASELINE_MN = 30000.0
HP_TORQUE_DISPLAY_BASELINE_NM = 0.05


def run_async(coro_or_factory):
    """Run a low-frequency async GUI action in a dedicated event loop."""
    loop = asyncio.new_event_loop()
    asyncio.set_event_loop(loop)
    try:
        coroutine = coro_or_factory() if callable(coro_or_factory) else coro_or_factory
        return loop.run_until_complete(coroutine)
    finally:
        loop.close()
        asyncio.set_event_loop(None)


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
        all_vals = []
        for i, curve in enumerate(self.curves):
            if self.data[i]:
                curve.setData(list(range(len(self.data[i]))), self.data[i])
                all_vals.extend(self.data[i][-50:])
        if all_vals and hasattr(self, "plot"):
            cur_min = min(all_vals)
            cur_max = max(all_vals)
            target_min = min(self.y_range[0], cur_min)
            target_max = max(self.y_range[1], cur_max * 1.15)
            margin = max(abs(target_max - target_min) * 0.08, 10.0)
            y_low = max(0.0, target_min - margin) if self.y_range[0] >= 0 and cur_min >= 0 else (target_min - margin)
            self.plot.setYRange(y_low, target_max + margin)

    def clear(self):
        self.data = [[] for _ in range(self.sensor_count)]
        self._update_curves()

    def set_y_axis(self, y_range: tuple, y_label: str):
        self.y_range = y_range
        self.y_label = y_label
        if HAS_PYQTGRAPH and hasattr(self, "plot"):
            self.plot.setYRange(y_range[0], y_range[1])
            self.plot.setLabel('left', y_label, color='w')

    def set_sensor_visible(self, sensor_idx: int, visible: bool):
        """Show/hide a sensor curve"""
        if HAS_PYQTGRAPH and sensor_idx < len(self.curves):
            self.curves[sensor_idx].setVisible(visible)


class HeatmapChart(QWidget):
    """2D heatmap chart for pressure/tactile array data with pyqtgraph ImageItem"""

    def __init__(self, module_name: str, point_count: int, color: tuple,
                 rows: int, cols: int, coord_map: list = None,
                 cell_aspect: float = 1.0):
        super().__init__()
        self.module_name = module_name
        self.point_count = point_count
        self.color = color
        self.rows = rows
        self.cols = cols
        self.coord_map = coord_map  # list of (row, col) tuples, or None for divmod fallback
        self.cell_aspect = cell_aspect
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
        name_label = QLabel(
            f"🔥 {self.module_name}  |  {self.point_count} channels  |  "
            f"{self.rows}×{self.cols} grid"
        )
        name_label.setStyleSheet(
            "font-size: 16px; font-weight: bold; color: #ffeb3b;"
        )
        header.addWidget(name_label)
        header.addStretch()
        self.stats_label = QLabel(
            f"peak: 0 mN  |  mean: 0 mN  |  total: 0 mN  |  "
            f"active: 0/{self.point_count}"
        )
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
            self.plot_widget.getViewBox().setAspectLocked(False)
            self.plot_widget.getViewBox().setRange(xRange=(0, self.cols), yRange=(0, self.rows), padding=0.02)
            self.plot_widget.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Expanding)
            self.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Expanding)

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
                    txt.setFont(pg.QtGui.QFont('Courier New', 13, pg.QtGui.QFont.Bold))
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
                self._update_colorbar_unit()
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
                peak_text = f"{max_val:.0f}/{self.current_stats_max_limit:.0f} mN"
            else:
                peak_text = f"{max_val:.0f} mN"
            self.stats_label.setText(
                f"peak: {peak_text}  |  mean: {avg:.0f} mN  |  "
                f"total: {total:.0f} mN  |  active: {active_count}/{n_total}"
            )
        else:
            unit_label = "Raw" if self.value_unit == "raw" else "ADC"
            peak_text = f"{max_val:.0f}"
            if self.current_stats_max_limit is not None:
                peak_text += f"/{self.current_stats_max_limit:.0f}"
            self.stats_label.setText(
                f"peak: {peak_text} {unit_label}  |  mean: {avg:.0f} {unit_label}  |  "
                f"total: {total:.0f} counts  |  active: {active_count}/{n_total}"
            )

    def _update_colorbar_unit(self):
        if not hasattr(self, "bar_item") or self.bar_item is None:
            return
        axis = getattr(self.bar_item, "axis", None)
        if axis is not None:
            unit_label = {
                "force": "mN",
                "raw": "Raw",
            }.get(self.value_unit, "ADC")
            axis.setLabel(text=unit_label)

    def set_value_unit(self, value_unit: str, max_limit: float = None, stats_max_limit: float = None):
        unit_changed = value_unit != self.value_unit
        self.value_unit = value_unit
        if max_limit is not None:
            self.current_max_limit = max_limit
        self.current_stats_max_limit = stats_max_limit
        if HAS_PYQTGRAPH and hasattr(self, "bar_item") and self.bar_item is not None:
            try:
                self.bar_item.setLevels((0, self.current_max_limit))
            except Exception:
                pass
        self._update_colorbar_unit()
        if unit_changed:
            self.clear()
        else:
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
        self._update_colorbar_unit()
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
                if isinstance(val, (int, float)) and abs(val - round(val)) < 0.05:
                    txt.setText(str(int(round(val))))
                else:
                    txt.setText(f"{val:.1f}")
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
            self.img_item.setImage(self._data_2d.T, levels=(0, self.current_max_limit))
            if hasattr(self, "bar_item") and self.bar_item is not None:
                try:
                    self.bar_item.setLevels((0, self.current_max_limit))
                except Exception:
                    pass
        self._update_stats_label()
    def update_data(self, values, is_enabled=True, max_limit=500.0, value_unit="force", stats_max_limit=None):
        """Update heatmap data (alias for add_data)"""
        self.add_data(values, is_enabled=is_enabled, max_limit=max_limit, value_unit=value_unit, stats_max_limit=stats_max_limit)

    def update_heatmap(self, values, is_enabled=True, max_limit=500.0, value_unit="force", stats_max_limit=None):
        """Update heatmap data (alias for add_data)"""
        self.add_data(values, is_enabled=is_enabled, max_limit=max_limit, value_unit=value_unit, stats_max_limit=stats_max_limit)


def build_status_cards(parent_layout, sensor_names, sensor_colors, is_compact=False):
    """Build sensor status cards with progress bars and value labels.

    Returns: (sensor_cards, sensor_bars, sensor_labels)
    """
    title = QLabel("Sensor Status")
    title.setStyleSheet("font-weight: bold; font-size: 12px;")
    parent_layout.addWidget(title)

    sensor_cards = []
    sensor_bars = []
    sensor_labels = []

    scroll = QScrollArea()
    scroll.setWidgetResizable(True)
    scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
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
        name_label.setFixedWidth(120 if is_compact else 95)
        name_label.setStyleSheet(
            f"color: rgb{display_color}; font-weight: bold; "
            f"font-size: {11 if is_compact else 13}px;"
        )
        card_layout.addWidget(name_label)

        bar = QProgressBar()
        bar.setRange(0, 5000)
        bar.setValue(0)
        bar.setTextVisible(False)
        bar.setFixedHeight(14 if is_compact else 16)
        if is_compact:
            bar.setMinimumWidth(45)
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
        if is_compact:
            val_label.setMinimumWidth(105)
            val_label.setMaximumWidth(125)
        else:
            val_label.setFixedWidth(220)
        val_label.setAlignment(Qt.AlignRight)
        val_label.setStyleSheet(f"""
            QLabel {{
                font-family: 'Courier New';
                font-size: {10 if is_compact else 12}px;
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


# =============================================================================
# 2D Force / Torque Compass Widget (矢量罗盘)
# =============================================================================

class ForceCompassWidget(QWidget):
    """2D Vector Compass Dial Widget for displaying 2D Force (Fx, Fy) and Torque (Mx, My).

    Features:
    - Polar dial with concentric range rings and X/Y crosshair axes (+Fx, -Fx, +Fy, -Fy)
    - Dynamic glowing vector arrow showing (Fx, Fy) direction and magnitude |Fxy|
    - Center force point indicator and torque arc
    """

    def __init__(
        self,
        title: str = "2D Force Vector",
        max_force: float = 20.0,
        force_unit: str = "mN",
    ):
        super().__init__()
        self.title_text = title
        self.force_unit = force_unit
        self.min_force = max(float(max_force), 0.01)
        self.max_force = self.min_force
        self.fx = 0.0
        self.fy = 0.0
        self.fz = 0.0
        self.mx = 0.0
        self.my = 0.0
        self.fn = 0.0
        self.setMinimumSize(180, 180)

    def set_values(self, fx: float, fy: float, fz: float = 0.0, mx: float = 0.0, my: float = 0.0, fn: float = 0.0):
        self.fx = fx
        self.fy = fy
        self.fz = fz
        self.mx = mx
        self.my = my
        self.fn = fn

        # Keep the vector within the dial while retaining some headroom.
        f_mag = math.hypot(fx, fy)
        if math.isfinite(f_mag):
            if f_mag > self.max_force * 0.9:
                self.max_force = max(f_mag * 1.3, self.min_force)
            elif f_mag < self.max_force * 0.2 and self.max_force > self.min_force:
                self.max_force = max(self.max_force * 0.8, self.min_force)

        self.update()

    def paintEvent(self, event):
        painter = QPainter(self)
        painter.setRenderHint(QPainter.Antialiasing)

        w = self.width()
        h = self.height()
        cx = w / 2.0
        cy = h / 2.0
        radius = min(w, h) / 2.0 - 18.0

        # Background circle
        painter.setBrush(QBrush(QColor("#0f172a")))
        painter.setPen(QPen(QColor("#334155"), 1.5))
        painter.drawEllipse(int(cx - radius), int(cy - radius), int(radius * 2), int(radius * 2))

        # Concentric range rings (0.5 max, 1.0 max)
        ring_pen = QPen(QColor("#1e293b"), 1, Qt.DashLine)
        painter.setPen(ring_pen)
        painter.setBrush(Qt.NoBrush)
        painter.drawEllipse(int(cx - radius * 0.5), int(cy - radius * 0.5), int(radius), int(radius))

        # Crosshair axes (+Fx Right, -Fx Left, +Fy Up, -Fy Down)
        axis_pen = QPen(QColor("#475569"), 1)
        painter.setPen(axis_pen)
        painter.drawLine(int(cx - radius), int(cy), int(cx + radius), int(cy))
        painter.drawLine(int(cx), int(cy - radius), int(cx), int(cy + radius))

        # Axis Labels
        font = QFont("Menlo", 9, QFont.Bold)
        painter.setFont(font)
        painter.setPen(QColor("#38bdf8"))  # Light Blue Fx
        painter.drawText(int(cx + radius - 22), int(cy - 4), "+Fx")
        painter.drawText(int(cx - radius + 4), int(cy - 4), "-Fx")

        painter.setPen(QColor("#4ade80"))  # Light Green Fy
        painter.drawText(int(cx - 10), int(cy - radius + 12), "+Fy")
        painter.drawText(int(cx - 10), int(cy + radius - 4), "-Fy")

        # Compass Title & Scale
        painter.setPen(QColor("#94a3b8"))
        painter.setFont(QFont("Menlo", 8))
        painter.drawText(
            int(cx - radius + 4),
            int(cy + radius - 4),
            f"Max:{self.max_force:.0f}{self.force_unit}",
        )

        # Vector Arrow (Fx -> Right (+X), Fy -> Up (-Y in screen coords))
        scale = radius / self.max_force if self.max_force > 0 else 1.0
        vx = self.fx * scale
        vy = -self.fy * scale  # Invert Y for screen coordinates (screen Y goes down)

        # Leave room for the arrow-head node even if the input is non-finite or
        # the auto-scale state has not caught up with an abrupt value change.
        vector_length = math.hypot(vx, vy)
        max_vector_length = max(radius - 6.0, 0.0)
        if math.isfinite(vector_length) and vector_length > max_vector_length > 0.0:
            clip_ratio = max_vector_length / vector_length
            vx *= clip_ratio
            vy *= clip_ratio
        elif not math.isfinite(vector_length):
            vx = 0.0
            vy = 0.0

        target_x = cx + vx
        target_y = cy + vy

        # Vector magnitude
        f_mag = math.hypot(self.fx, self.fy)

        if f_mag > 0.01:
            # Draw glowing vector line
            arrow_pen = QPen(QColor("#f59e0b"), 2.5)  # Amber vector line
            painter.setPen(arrow_pen)
            painter.drawLine(int(cx), int(cy), int(target_x), int(target_y))

            # Draw vector head node
            painter.setBrush(QBrush(QColor("#ef4444") if f_mag > self.max_force * 0.8 else QColor("#f59e0b")))
            painter.setPen(QPen(QColor("#ffffff"), 1.5))
            painter.drawEllipse(int(target_x - 5), int(target_y - 5), 10, 10)

        # ── 3D Normal Force (Fz Press Depth) Circle ──
        # Fz represents vertical pressing into the fingertip (typically negative for inward pressure)
        fz_mag = abs(self.fz)
        if fz_mag > 0.05:
            # Scale center press circle based on Fz magnitude (max 30px radius)
            force_to_n = 0.001 if self.force_unit == "mN" else 1.0
            fz_n = fz_mag * force_to_n
            fz_r = min(max(fz_n * 1.2, 4.0), 30.0)
            fz_color = QColor(244, 67, 54, 160) if fz_n > 50.0 else QColor(56, 189, 248, 140)
            painter.setBrush(QBrush(fz_color))
            painter.setPen(QPen(QColor("#60a5fa"), 1))
            painter.drawEllipse(int(cx - fz_r), int(cy - fz_r), int(fz_r * 2), int(fz_r * 2))

        # Center dot
        painter.setBrush(QBrush(QColor("#38bdf8")))
        painter.setPen(Qt.NoPen)
        painter.drawEllipse(int(cx - 3), int(cy - 3), 6, 6)

        # Vector Magnitude & Fz HUD Text
        painter.setFont(QFont("Menlo", 8 if w < 220 else 9, QFont.Bold))
        hud_y = max(0, int(cy - radius - 16))
        hud_height = max(14, int(cy - radius + 12) - hud_y)
        painter.setPen(QColor("#f59e0b"))
        painter.drawText(
            4,
            hud_y,
            max(1, int(w / 2) - 6),
            hud_height,
            Qt.AlignLeft | Qt.AlignVCenter,
            f"|Fxy|:{f_mag:.0f}{self.force_unit}",
        )
        painter.setPen(QColor("#60a5fa"))
        painter.drawText(
            int(w / 2) + 2,
            hud_y,
            max(1, int(w / 2) - 6),
            hud_height,
            Qt.AlignRight | Qt.AlignVCenter,
            f"Fz:{self.fz:+.0f}{self.force_unit}",
        )


# =============================================================================
# hp_* Fingertip Module Card Widget
# =============================================================================

class HpForceTorqueModuleCard(QGroupBox):
    """Card widget for displaying one hp_* 6D force/torque fingertip module.

    Layout:
    - Top: Status + Sensor + prominent Zero button
    - Middle: 2D Force Compass Dial + 6D Time-Series Chart (side-by-side)
    - Metrics: Fx/Fy/Fz/Mx/My/Fn instrument-style value labels
    - Bottom: 48-point film heatmap (compact)
    """

    FT_CHANNELS = [
        ("fx", "Fx", (255, 80, 80), "mN"),
        ("fy", "Fy", (80, 255, 80), "mN"),
        ("fz", "Fz", (80, 140, 255), "mN"),
        ("mx", "Mx", (0, 220, 220), "Nm"),
        ("my", "My", (220, 80, 220), "Nm"),
        ("resultant_force_mn", "Fn", (255, 200, 50), "mN"),
    ]
    MAX_CHART_POINTS = 200

    def __init__(self, name: str, module_idx: int, universal_id: int, color: tuple, on_zero_cb=None):
        super().__init__()
        self.module_name = name
        self.module_idx = module_idx
        self.universal_id = universal_id
        self.color = color
        self.on_zero_cb = on_zero_cb
        self._chart_data = {ch[0]: [] for ch in self.FT_CHANNELS}
        self._chart_curves = []

        self.setTitle(f"🖐️ {name} (hp_* Mod {module_idx} / TouchID {universal_id})")
        self._setup_ui()

    def _setup_ui(self):
        layout = QVBoxLayout(self)
        layout.setContentsMargins(8, 8, 8, 8)
        layout.setSpacing(6)

        # ── Top Status Row ──
        top_row = QHBoxLayout()
        top_row.setSpacing(12)

        self.status_lbl = QLabel("Status: --")
        self.status_lbl.setStyleSheet("font-weight: bold; color: #888; font-size: 12px;")
        top_row.addWidget(self.status_lbl)

        self.sensor_lbl = QLabel("Sensor: --")
        self.sensor_lbl.setStyleSheet("font-weight: bold; color: #888; font-size: 12px;")
        top_row.addWidget(self.sensor_lbl)

        top_row.addStretch()

        if self.on_zero_cb:
            zero_btn = QPushButton("🎯  当前指尖清零")
            zero_btn.setToolTip(
                f"仅校准当前 HP 指尖模块：{self.module_name}"
            )
            zero_btn.setFixedHeight(34)
            zero_btn.setMinimumWidth(150)
            zero_btn.setStyleSheet("""
                QPushButton {
                    background: qlineargradient(x1:0, y1:0, x2:1, y2:0,
                        stop:0 #e65100, stop:1 #ff6d00);
                    color: white;
                    border: 1px solid #ff9100;
                    border-radius: 6px;
                    font-size: 13px;
                    font-weight: bold;
                    padding: 4px 16px;
                    letter-spacing: 1px;
                }
                QPushButton:hover {
                    background: qlineargradient(x1:0, y1:0, x2:1, y2:0,
                        stop:0 #ff6d00, stop:1 #ff9100);
                }
                QPushButton:pressed {
                    background: qlineargradient(x1:0, y1:0, x2:1, y2:0,
                        stop:0 #bf360c, stop:1 #e65100);
                }
            """)
            zero_btn.clicked.connect(lambda: self.on_zero_cb(self.module_idx))
            top_row.addWidget(zero_btn)

        layout.addLayout(top_row)

        # ── Visual Row: 2D Compass Dial (罗盘) + 6D Time-Series Chart (Side by Side) ──
        vis_row = QHBoxLayout()
        vis_row.setSpacing(8)

        # 2D Compass Dial
        self.compass = ForceCompassWidget(
            title=f"{self.module_name} Force Compass",
            max_force=HP_FORCE_DISPLAY_BASELINE_MN,
        )
        vis_row.addWidget(self.compass, 1)

        # Force and torque use separate axes because mN and Nm differ by
        # several orders of magnitude at their specified measurement ranges.
        if HAS_PYQTGRAPH and pg is not None:
            history_widget = QWidget()
            history_layout = QVBoxLayout(history_widget)
            history_layout.setContentsMargins(0, 0, 0, 0)
            history_layout.setSpacing(4)

            self.ft_plot = pg.PlotWidget()
            self.ft_plot.setBackground('#0f172a')
            self.ft_plot.showGrid(x=True, y=True, alpha=0.2)
            self.ft_plot.setYRange(
                -HP_FORCE_DISPLAY_BASELINE_MN,
                HP_FORCE_DISPLAY_BASELINE_MN,
            )
            self.ft_plot.setXRange(0, self.MAX_CHART_POINTS)
            self.ft_plot.setTitle("Force History", color='#94a3b8', size='9pt')
            self.ft_plot.setLabel('bottom', 'samples', color='#64748b')
            self.ft_plot.setLabel('left', 'mN', color='#64748b')
            self.ft_plot.addLegend(offset=(-10, 10), labelTextSize='9pt')

            self.torque_plot = pg.PlotWidget()
            self.torque_plot.setBackground('#0f172a')
            self.torque_plot.showGrid(x=True, y=True, alpha=0.2)
            self.torque_plot.setYRange(
                -HP_TORQUE_DISPLAY_BASELINE_NM,
                HP_TORQUE_DISPLAY_BASELINE_NM,
            )
            self.torque_plot.setXRange(0, self.MAX_CHART_POINTS)
            self.torque_plot.setTitle("Torque History", color='#94a3b8', size='9pt')
            self.torque_plot.setLabel('bottom', 'samples', color='#64748b')
            self.torque_plot.setLabel('left', 'Nm', color='#64748b')
            self.torque_plot.addLegend(offset=(-10, 10), labelTextSize='9pt')

            for key, label, color_rgb, unit in self.FT_CHANNELS:
                pen = pg.mkPen(color=color_rgb, width=2)
                target_plot = self.torque_plot if key in ("mx", "my") else self.ft_plot
                curve = target_plot.plot([], [], pen=pen, name=f"{label} ({unit})")
                self._chart_curves.append((key, curve))

            self.ft_plot.setMinimumHeight(120)
            self.torque_plot.setMinimumHeight(120)
            history_layout.addWidget(self.ft_plot, 1)
            history_layout.addWidget(self.torque_plot, 1)
            vis_row.addWidget(history_widget, 2)
        else:
            self.ft_plot = None
            self.torque_plot = None
            vis_row.addWidget(QLabel("pyqtgraph not installed — chart unavailable"))

        layout.addLayout(vis_row)

        # ── Metrics Row (Compact Instrument-Style Labels) ──
        grid = QGridLayout()
        grid.setContentsMargins(0, 0, 0, 0)
        grid.setSpacing(4)

        card_bg = "#1e293b"
        card_border = "#334155"
        lbl_style = f"background-color: {card_bg}; border: 1px solid {card_border}; border-radius: 4px; padding: 4px 8px; font-family: 'Menlo', 'Consolas', 'Courier New', monospace; font-size: 12px; font-weight: bold; color: #e2e8f0;"
        fn_style = f"background-color: {card_bg}; border: 1px solid #d97706; border-radius: 4px; padding: 4px 8px; font-family: 'Menlo', 'Consolas', 'Courier New', monospace; font-size: 12px; font-weight: bold; color: #fbbf24;"

        self.fx_lbl = QLabel("Fx: +0 mN")
        self.fy_lbl = QLabel("Fy: +0 mN")
        self.fz_lbl = QLabel("Fz: +0 mN")
        self.mx_lbl = QLabel("Mx: +0.0000 Nm")
        self.my_lbl = QLabel("My: +0.0000 Nm")
        self.fn_lbl = QLabel("Fn: +0 mN")

        for lbl in (self.fx_lbl, self.fy_lbl, self.fz_lbl, self.mx_lbl, self.my_lbl):
            lbl.setStyleSheet(lbl_style)
        self.fn_lbl.setStyleSheet(fn_style)

        grid.addWidget(self.fx_lbl, 0, 0)
        grid.addWidget(self.fy_lbl, 0, 1)
        grid.addWidget(self.fz_lbl, 0, 2)
        grid.addWidget(self.mx_lbl, 0, 3)
        grid.addWidget(self.my_lbl, 0, 4)
        grid.addWidget(self.fn_lbl, 0, 5)
        layout.addLayout(grid)

        # ── 48-Point Film Heatmap ──
        self.heatmap = HeatmapChart(
            module_name=f"{self.module_name} (48-Point Tactile Array)",
            point_count=48,
            color=self.color,
            rows=6,
            cols=8
        )
        self.heatmap.setMinimumHeight(240)
        layout.addWidget(self.heatmap, 2)

    def update_payload(self, mod_payload):
        """Update status, metrics, compass, chart, and heatmap from an hp_* payload."""
        if not mod_payload:
            return

        # -- Status --
        status = getattr(mod_payload, "status", 0)
        sensor_st = getattr(mod_payload, "sensor_status", 0)

        status_map = {
            1: ("Status: Ready(1)", "#4caf50"),
            0: ("Status: WarmingUp(0)", "#ff9800"),
        }
        text, color = status_map.get(status, (f"Status: Offline({status})", "#f44336"))
        self.status_lbl.setText(text)
        self.status_lbl.setStyleSheet(f"font-weight: bold; color: {color}; font-size: 12px;")

        sensor_text = "Sensor: Normal(0)" if sensor_st == 0 else f"Sensor: Fault({sensor_st})"
        sensor_color = "#4caf50" if sensor_st == 0 else "#f44336"
        self.sensor_lbl.setText(sensor_text)
        self.sensor_lbl.setStyleSheet(f"font-weight: bold; color: {sensor_color}; font-size: 12px;")

        # -- Metrics --
        fx = getattr(mod_payload, "fx", 0.0)
        fy = getattr(mod_payload, "fy", 0.0)
        fz = getattr(mod_payload, "fz", 0.0)
        mx_nm = getattr(mod_payload, "mx", 0.0)
        my_nm = getattr(mod_payload, "my", 0.0)
        fn = getattr(mod_payload, "resultant_force_mn", 0.0)

        self.fx_lbl.setText(f"Fx: {fx:+.1f} mN")
        self.fy_lbl.setText(f"Fy: {fy:+.1f} mN")
        self.fz_lbl.setText(f"Fz: {fz:+.1f} mN")
        self.mx_lbl.setText(f"Mx: {mx_nm:+.4f} Nm")
        self.my_lbl.setText(f"My: {my_nm:+.4f} Nm")
        self.fn_lbl.setText(f"Fn: {fn:+.1f} mN")

        # -- 2D Force Compass Update --
        self.compass.set_values(fx, fy, fz, mx_nm, my_nm, fn)

        # -- 6D Chart Update --
        values = {
            "fx": fx,
            "fy": fy,
            "fz": fz,
            "mx": mx_nm,
            "my": my_nm,
            "resultant_force_mn": fn,
        }
        for key in self._chart_data:
            self._chart_data[key].append(values.get(key, 0.0))
            if len(self._chart_data[key]) > self.MAX_CHART_POINTS:
                self._chart_data[key].pop(0)

        if self.ft_plot is not None:
            for key, curve in self._chart_curves:
                d = self._chart_data[key]
                if d:
                    curve.setData(list(range(len(d))), d)

            force_vals = [
                value
                for key in ("fx", "fy", "fz", "resultant_force_mn")
                for value in self._chart_data[key][-50:]
            ]
            if force_vals:
                force_abs = max(
                    HP_FORCE_DISPLAY_BASELINE_MN,
                    max(abs(value) for value in force_vals) * 1.1,
                )
                self.ft_plot.setYRange(-force_abs, force_abs)

            torque_vals = [
                value
                for key in ("mx", "my")
                for value in self._chart_data[key][-50:]
            ]
            if torque_vals and self.torque_plot is not None:
                torque_abs = max(
                    HP_TORQUE_DISPLAY_BASELINE_NM,
                    max(abs(value) for value in torque_vals) * 1.1,
                )
                self.torque_plot.setYRange(-torque_abs, torque_abs)

        # -- Heatmap --
        points = getattr(mod_payload, "points", [])
        if points:
            self.heatmap.update_heatmap(
                list(points), value_unit="raw", max_limit=255.0
            )

    def clear_chart(self):
        """Clear 6D time-series chart history and reset compass dial."""
        for key in self._chart_data:
            self._chart_data[key].clear()
        if self.ft_plot is not None:
            for key, curve in self._chart_curves:
                curve.setData([], [])
        self.compass.set_values(0.0, 0.0, 0.0, 0.0, 0.0, 0.0)
