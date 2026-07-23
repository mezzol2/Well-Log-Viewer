"""
Curve selector: a checkable list of the curves available in the current
well log, letting the user choose which ones the multi-track viewer draws.

Real LAS files (and OSDU WellLog records) can carry dozens or hundreds of
curves - the Volve LFP composite has 170. Showing them all at once is
unreadable, and a fixed "first N" cap silently hides the interesting ones
when a file's useful curves don't happen to sort first (e.g. an
interpretation product with no raw GR/RHOB). Letting the user pick is how
commercial log viewers (Techlog, Petrel) handle this, and it keeps the UI
honest: every curve in the log is visible in the list, checked or not.
"""

import html

import numpy as np
from PySide6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QListWidget, QListWidgetItem,
    QLabel, QPushButton, QTextEdit, QSplitter,
)
from PySide6.QtCore import Qt, Signal


# Descriptions that carry no information. Volve's LFP export writes "v1"
# as the description of all 170 curves; treating that as a real caption
# would just be noise, so the panel says so instead of parroting it.
_JUNK_DESCRIPTIONS = {"", "v1", "unknown", "none", "n/a", "-"}


def _curve_details_html(curve) -> str:
    """Human-readable context for one curve: what the file said about it,
    plus statistics derived from the samples (useful precisely because
    real files so often have missing or junk descriptions)."""
    esc = html.escape
    rows = []

    def row(label, value):
        rows.append(
            f"<tr><td style='padding-right:8px; color:#666;'>{esc(label)}</td>"
            f"<td>{value}</td></tr>"
        )

    row("Curve", f"<b>{esc(curve.mnemonic)}</b>")
    # Surface the alias-table rename so the user can audit the guess.
    original = getattr(curve, "original_mnemonic", "") or ""
    if original and original.upper() != curve.mnemonic.upper():
        row("In file", f"{esc(original)} <i>(renamed by alias table)</i>")
    row("Unit", esc(curve.unit) if curve.unit else "<i>none</i>")

    descr = (curve.description or "").strip()
    if descr.lower() in _JUNK_DESCRIPTIONS:
        row("Description", "<i>none recorded in file</i>"
            + (f" (file says &quot;{esc(descr)}&quot;)" if descr else ""))
    else:
        row("Description", esc(descr))

    source = (getattr(curve, "source_info", "") or "").strip()
    if source:
        row("Source", f"<span style='font-size:11px;'>{esc(source)}</span>")

    values = np.asarray(curve.values, dtype=float)
    finite = np.isfinite(values)
    n_total, n_finite = values.size, int(finite.sum())
    pct = (100.0 * n_finite / n_total) if n_total else 0.0
    row("Coverage", f"{n_finite:,} / {n_total:,} samples ({pct:.1f}%)")

    if n_finite:
        v = values[finite]
        d = np.asarray(curve.depth, dtype=float)[finite]
        row("Depth", f"{d.min():.1f} – {d.max():.1f} m MD")
        row("Range", f"{v.min():.4g} &nbsp;/&nbsp; {np.median(v):.4g} "
                     f"&nbsp;/&nbsp; {v.max():.4g} "
                     f"<span style='color:#666;'>(min/med/max)</span>")
    else:
        row("Values", "<i>all null</i>")

    return "<table style='font-size:12px;'>" + "".join(rows) + "</table>"


class CurveSelector(QWidget):
    # Emitted with the list of currently-checked LogCurve objects,
    # in the log's original curve order.
    selectionChanged = Signal(list)

    # How many curves to check by default when a new log is loaded.
    # Curves arrive canonical-sorted (GR/RHOB/NPHI/RT first), so the
    # default lands on the most useful ones when they're present.
    DEFAULT_CHECKED = 8

    def __init__(self, parent=None):
        super().__init__(parent)
        self._curves = []
        # Guard against a signal storm while (un)checking many items at once.
        self._suppress = False

        layout = QVBoxLayout(self)
        layout.setContentsMargins(4, 4, 4, 4)

        self._title = QLabel("Curves")
        self._title.setStyleSheet("font-weight: bold;")
        layout.addWidget(self._title)

        btn_row = QHBoxLayout()
        self.all_btn = QPushButton("All")
        self.none_btn = QPushButton("None")
        self.all_btn.clicked.connect(lambda: self._set_all(True))
        self.none_btn.clicked.connect(lambda: self._set_all(False))
        btn_row.addWidget(self.all_btn)
        btn_row.addWidget(self.none_btn)
        btn_row.addStretch(1)
        layout.addLayout(btn_row)

        # List on top, details for the highlighted curve underneath. The
        # details track the *highlighted* row (single click or arrow keys)
        # rather than needing a double-click, so browsing curves to find
        # the right one is a single gesture.
        split = QSplitter(Qt.Vertical)

        self.list = QListWidget()
        self.list.itemChanged.connect(self._on_item_changed)
        self.list.currentItemChanged.connect(self._on_current_item_changed)
        split.addWidget(self.list)

        self.details = QTextEdit()
        self.details.setReadOnly(True)
        self.details.setPlaceholderText("Select a curve to see its description.")
        split.addWidget(self.details)

        split.setStretchFactor(0, 3)
        split.setStretchFactor(1, 2)
        layout.addWidget(split, stretch=1)

    def set_curves(self, curves):
        """Populate from a new log; check the first DEFAULT_CHECKED curves.

        Emits selectionChanged once at the end so the viewer draws the
        default set immediately.
        """
        self._curves = list(curves)
        self._suppress = True
        self.list.clear()
        for i, c in enumerate(self._curves):
            label = c.mnemonic + (f"  ({c.unit})" if c.unit else "")
            item = QListWidgetItem(label)
            item.setFlags(item.flags() | Qt.ItemIsUserCheckable)
            item.setCheckState(Qt.Checked if i < self.DEFAULT_CHECKED else Qt.Unchecked)
            item.setData(Qt.UserRole, i)
            if c.description:
                item.setToolTip(c.description)
            self.list.addItem(item)
        self._suppress = False
        self._title.setText(f"Curves ({len(self._curves)})")
        if self._curves:
            self.list.setCurrentRow(0)   # show details for something immediately
        self._emit()

    def clear(self):
        self._curves = []
        self._suppress = True
        self.list.clear()
        self._suppress = False
        self._title.setText("Curves")
        self.details.clear()

    def _set_all(self, checked):
        state = Qt.Checked if checked else Qt.Unchecked
        self._suppress = True
        for row in range(self.list.count()):
            self.list.item(row).setCheckState(state)
        self._suppress = False
        self._emit()

    def _on_item_changed(self, _item):
        if not self._suppress:
            self._emit()

    def _on_current_item_changed(self, current, _previous):
        if current is None:
            self.details.clear()
            return
        index = current.data(Qt.UserRole)
        if index is None or index >= len(self._curves):
            self.details.clear()
            return
        self.details.setHtml(_curve_details_html(self._curves[index]))

    def _emit(self):
        selected = [
            self._curves[self.list.item(r).data(Qt.UserRole)]
            for r in range(self.list.count())
            if self.list.item(r).checkState() == Qt.Checked
        ]
        self.selectionChanged.emit(selected)
