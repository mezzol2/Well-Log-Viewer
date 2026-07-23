"""
Main window: a well/wellbore tree on the left (grouped by field),
multi-track log viewer on the right.

All data access goes through OSDUClient - this window never touches
mock_data directly, which is the point of the abstraction.
"""

from PySide6.QtWidgets import (
    QMainWindow, QTreeWidget, QTreeWidgetItem, QSplitter, QWidget,
    QVBoxLayout, QLabel, QStatusBar
)
from PySide6.QtCore import Qt

from client_interfaces.base import OSDUClient
from ui.log_viewer import MultiTrackLogViewer
from ui.curve_selector import CurveSelector


class MainWindow(QMainWindow):
    def __init__(self, client: OSDUClient):
        super().__init__()
        self.client = client
        self.setWindowTitle("OSDU Well Log Viewer (mock data)")
        self.resize(1200, 750)

        # The log currently loaded in the viewer, so header text can be
        # recomputed when the curve selection changes.
        self._current_wellbore = None
        self._current_log = None

        splitter = QSplitter(Qt.Horizontal)

        # --- Left panel: well/wellbore tree ---
        self.tree = QTreeWidget()
        self.tree.setHeaderLabels(["Wells / Wellbores"])
        self.tree.setMinimumWidth(240)
        self.tree.setMaximumWidth(420)
        self.tree.itemClicked.connect(self._on_tree_item_clicked)

        # --- Middle panel: curve picker ---
        self.curve_selector = CurveSelector()
        self.curve_selector.setMinimumWidth(200)
        self.curve_selector.setMaximumWidth(360)
        self.curve_selector.selectionChanged.connect(self._on_curve_selection_changed)

        # --- Right panel: log viewer + header ---
        right_panel = QWidget()
        right_layout = QVBoxLayout(right_panel)
        right_layout.setContentsMargins(0, 0, 0, 0)

        self.header_label = QLabel("Select a wellbore to view its log data.")
        self.header_label.setStyleSheet("padding: 6px; font-weight: bold;")
        right_layout.addWidget(self.header_label)

        self.log_viewer = MultiTrackLogViewer()
        right_layout.addWidget(self.log_viewer, stretch=1)

        splitter.addWidget(self.tree)
        splitter.addWidget(self.curve_selector)
        splitter.addWidget(right_panel)
        splitter.setStretchFactor(2, 1)

        self.setCentralWidget(splitter)
        self.setStatusBar(QStatusBar())

        self._populate_tree()

    def _populate_tree(self):
        wells = self.client.search_wells()
        fields = {}
        for well in wells:
            fields.setdefault(well.field_name, []).append(well)

        for field_name, field_wells in fields.items():
            field_item = QTreeWidgetItem([field_name])
            field_item.setFlags(field_item.flags() & ~Qt.ItemIsSelectable)
            self.tree.addTopLevelItem(field_item)

            for well in field_wells:
                well_item = QTreeWidgetItem([well.name])
                well_item.setData(0, Qt.UserRole, ("well", well))
                field_item.addChild(well_item)

                for wb in self.client.get_wellbores_for_well(well.id):
                    wb_item = QTreeWidgetItem([wb.name])
                    wb_item.setData(0, Qt.UserRole, ("wellbore", wb))
                    well_item.addChild(wb_item)

            field_item.setExpanded(True)

    def _on_tree_item_clicked(self, item: QTreeWidgetItem, column: int):
        data = item.data(0, Qt.UserRole)
        if not data:
            return
        kind, obj = data
        if kind != "wellbore":
            return

        well_log = self.client.get_well_log(obj.id)
        self._current_wellbore = obj
        self._current_log = well_log

        if well_log and well_log.curves:
            # Populating the selector emits selectionChanged, which draws
            # the default curve set and updates the header.
            self.curve_selector.set_curves(well_log.curves)
            self.statusBar().showMessage(f"Loaded log for {obj.id}", 4000)
        else:
            self.curve_selector.clear()
            self.log_viewer.display_well_log(well_log)
            self.header_label.setText(f"{obj.name} — no log data")

    def _on_curve_selection_changed(self, curves):
        self.log_viewer.display_curves(curves)
        self._update_header(len(curves))

    def _update_header(self, shown_count):
        obj, log = self._current_wellbore, self._current_log
        if obj is None or log is None:
            return
        self.header_label.setText(
            f"{obj.name}  —  {log.top_depth:.0f}–{log.bottom_depth:.0f} m MD  "
            f"(showing {shown_count} of {len(log.curves)} curves)"
        )
