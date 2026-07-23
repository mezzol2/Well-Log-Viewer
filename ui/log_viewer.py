"""
Multi-track log viewer widget.

Renders each curve in its own vertical track sharing a common depth
(Y) axis, inverted so depth increases downward - this is the
standard convention geologists/petrophysicists expect (vs. a single
overlaid chart, which is how a non-domain dev might default to
plotting it).
"""

import numpy as np
import pyqtgraph as pg
from PySide6.QtWidgets import (
    QWidget, QHBoxLayout, QLabel, QVBoxLayout, QScrollArea, QSizePolicy
)
from PySide6.QtGui import QFontMetrics
from PySide6.QtCore import Qt

# Typical display ranges/colors for common curve mnemonics.
# A real tool would pull this from a curve-display config (OSDU has
# no built-in concept of "how to plot a curve" - that's app-level).
#
# "range" is (left_edge, right_edge) as the petrophysicist reads the
# track. left > right means the scale runs backwards - NPHI is plotted
# 0.45 -> -0.15 so it overlays RHOB for gas crossover. That has to be
# done with invertX(): pyqtgraph normalizes setXRange(hi, lo) to
# (lo, hi) and silently draws it forwards.
CURVE_DISPLAY = {
    "GR":   {"range": (0, 200),   "color": "g", "log_x": False},
    "RHOB": {"range": (1.8, 3.0), "color": "r", "log_x": False},
    "NPHI": {"range": (0.45, -0.15), "color": "b", "log_x": False},  # reversed, standard convention
    "RT":   {"range": (0.2, 2000), "color": "k", "log_x": True},
}


class _TrackHeader(QLabel):
    """Track caption that elides instead of demanding its full width.

    pyqtgraph's own setTitle() is deliberately not used: its LabelItem
    forces a minimum width on the PlotItem layout, so a long caption
    (e.g. "NPHI (v/v_decimal)") makes the ViewBox wider than the track,
    pushing most of the curve outside the visible area. A plain QLabel
    with an Ignored size policy lets the track shrink freely.
    """

    def __init__(self, text, parent=None):
        super().__init__(parent)
        self._full_text = text
        self.setToolTip(text)
        self.setAlignment(Qt.AlignCenter)
        self.setStyleSheet("font-weight: bold; padding: 2px;")
        self.setSizePolicy(QSizePolicy.Ignored, QSizePolicy.Fixed)
        self._apply_elide()

    def resizeEvent(self, event):
        super().resizeEvent(event)
        self._apply_elide()

    def _apply_elide(self):
        fm = QFontMetrics(self.font())
        self.setText(fm.elidedText(self._full_text, Qt.ElideRight,
                                   max(0, self.width() - 4)))


class LogTrackWidget(QWidget):
    """A single track (one curve) plotted against depth, with a caption
    above it. Composed of a header label + PlotWidget rather than being
    a PlotWidget itself - see _TrackHeader for why."""

    def __init__(self, curve, parent=None):
        super().__init__(parent)

        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(0)

        caption = f"{curve.mnemonic} ({curve.unit})" if curve.unit else curve.mnemonic
        self.header = _TrackHeader(caption)
        if curve.description:
            self.header.setToolTip(f"{caption}\n{curve.description}")
        layout.addWidget(self.header)

        self.plot = pg.PlotWidget()
        self.plot.setBackground("w")
        self.plot.showGrid(x=True, y=True, alpha=0.3)
        layout.addWidget(self.plot, stretch=1)

        display = CURVE_DISPLAY.get(curve.mnemonic,
                                    {"range": None, "color": "b", "log_x": False})
        finite = np.isfinite(curve.values)
        pen = pg.mkPen(display["color"], width=1.2)

        if display["log_x"]:
            self.plot.setLogMode(x=True, y=False)
            # avoid log(0) issues; keep NaNs as gaps
            vals = curve.values.copy()
            vals[finite & (vals <= 0)] = 0.01
            self.plot.plot(vals, curve.depth, pen=pen, connect="finite")
        else:
            self.plot.plot(curve.values, curve.depth, pen=pen, connect="finite")

        if display["range"]:
            left, right = display["range"]
            reversed_scale = left > right
            lo, hi = (right, left) if reversed_scale else (left, right)
            if display["log_x"]:
                self.plot.setXRange(np.log10(lo), np.log10(hi), padding=0)
            else:
                self.plot.setXRange(lo, hi, padding=0)
            if reversed_scale:
                self.plot.getViewBox().invertX(True)

        # Depth increases downward
        self.plot.invertY(True)
        self.plot.setLabel("left", "Depth", units="m")
        self.plot.getAxis("left").setWidth(55)

    def setYLink(self, other):
        """Link this track's depth axis to another LogTrackWidget's."""
        self.plot.setYLink(other.plot)


class MultiTrackLogViewer(QWidget):
    """Lays out one LogTrackWidget per curve, side by side, with a
    shared/linked depth axis so scrolling/zooming one scrolls all.

    Which curves appear is decided by the caller (the CurveSelector),
    not capped here - every curve the user checks is drawn. To keep many
    tracks usable rather than compressed into slivers, each track has a
    minimum width and the whole strip scrolls horizontally when they
    don't all fit.
    """

    # Legacy default for callers that hand over a whole log (e.g. tests):
    # how many of the (canonical-sorted) curves to show without a selector.
    MAX_TRACKS = 8
    TRACK_MIN_WIDTH = 150

    def __init__(self, parent=None):
        super().__init__(parent)
        outer = QVBoxLayout(self)
        outer.setContentsMargins(0, 0, 0, 0)

        # Horizontal scroll: with widgetResizable, few tracks stretch to
        # fill the viewport; many tracks stay at TRACK_MIN_WIDTH and the
        # strip scrolls instead of squeezing every track to a sliver.
        self._scroll = QScrollArea()
        self._scroll.setWidgetResizable(True)
        self._scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarAsNeeded)
        self._scroll.setVerticalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
        outer.addWidget(self._scroll)

        self._container = QWidget()
        self.layout = QHBoxLayout(self._container)
        self.layout.setContentsMargins(4, 4, 4, 4)
        self.layout.setSpacing(2)
        self._scroll.setWidget(self._container)

        self._tracks = []
        self._placeholder = None

    def clear(self):
        for t in self._tracks:
            t.setParent(None)
            t.deleteLater()
        self._tracks = []
        if self._placeholder is not None:
            self._placeholder.setParent(None)
            self._placeholder.deleteLater()
            self._placeholder = None

    def _show_placeholder(self, text):
        self.clear()
        self._placeholder = QLabel(text)
        self._placeholder.setAlignment(Qt.AlignCenter)
        self.layout.addWidget(self._placeholder)

    def display_curves(self, curves):
        """Render exactly the given curves, one track each."""
        self.clear()
        if not curves:
            self._show_placeholder("Select one or more curves to display.")
            return

        first_track = None
        for curve in curves:
            track = LogTrackWidget(curve)
            track.setMinimumWidth(self.TRACK_MIN_WIDTH)
            if first_track is None:
                first_track = track
            else:
                track.setYLink(first_track)  # linked depth scrolling/zoom
            self._tracks.append(track)
            self.layout.addWidget(track)

    def display_well_log(self, well_log):
        """Convenience: show a whole log's first MAX_TRACKS curves."""
        if well_log is None or not well_log.curves:
            self._show_placeholder("No log data available for this wellbore.")
            return
        self.display_curves(well_log.curves[: self.MAX_TRACKS])
