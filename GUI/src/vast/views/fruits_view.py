# views/fruits_view.py
from __future__ import annotations
from typing import Optional, Tuple, Dict, List
from PyQt6.QtCore import Qt, pyqtSignal
from PyQt6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QLabel, QPushButton, QComboBox,
    QTableWidget, QTableWidgetItem, QAbstractItemView, QDoubleSpinBox,
    QMessageBox, QHeaderView, QDialog, QLineEdit, QFrame
)

from dashboard_api import DashboardApi


# ---------- thresholds ----------
class ThresholdsEditorDialog(QDialog):
    thresholdsSaved = pyqtSignal(dict)  # {(task,label): threshold}

    TASK_OPTIONS = ["ripeness", "disease", "size", "color"]

    def __init__(self, api: DashboardApi, parent: QWidget | None = None):
        super().__init__(parent)
        self.api = api
        self.setWindowTitle("Fruits — Task Thresholds")
        self.setModal(True)
        self.resize(820, 560)

        
        self.setStyleSheet("""

QLineEdit#search {
    padding: 10px 12px; border: 1px solid #e8dccc; border-radius: 10px; background: #ffffff;
}


/* ====== status====== */
QLabel#status { color: #6b7280; }
QLabel.status-ok   { color: #17803a; }  
QLabel.status-warn { color: #b25a00; } 
QLabel.status-err  { color: #cc0022; }  


QPushButton, QToolButton {
    padding: 10px 16px; border-radius: 12px; color: white; border: none; font-weight: 700;
}
QPushButton:disabled { background: #c8c8c8; color: #f5f5f5; }

/* Add (🍌) */
QPushButton#btn_add {
    background: qlineargradient(x1:0,y1:0,x2:1,y2:0, stop:0 #f8e27a, stop:1 #d8c94a);
    color: #3a3a00;
}
QPushButton#btn_add:hover { background: qlineargradient(x1:0,y1:0,x2:1,y2:0, stop:0 #ffef87, stop:1 #e3d65a); }

/* Delete (🍒) */
QPushButton#btn_delete {
    background: qlineargradient(x1:0,y1:0,x2:1,y2:0, stop:0 #ff6a7a, stop:1 #e03d4f);
}
QPushButton#btn_delete:hover { background: qlineargradient(x1:0,y1:0,x2:1,y2:0, stop:0 #ff7f8d, stop:1 #ea5666); }

/* Save (🥝) */
QPushButton#btn_save {
    background: qlineargradient(x1:0,y1:0,x2:1,y2:0, stop:0 #4bd27c, stop:1 #2fb765);
}
QPushButton#btn_save:hover { background: qlineargradient(x1:0,y1:0,x2:1,y2:0, stop:0 #5fe08b, stop:1 #3fcb75); }

/* Close (🫐) */
QPushButton#btn_close {
    background: qlineargradient(x1:0,y1:0,x2:1,y2:0, stop:0 #6a7bff, stop:1 #4757e6);
}
QPushButton#btn_close:hover { background: qlineargradient(x1:0,y1:0,x2:1,y2:0, stop:0 #7d8bff, stop:1 #5b6cf0); }
""")

        root = QVBoxLayout(self)
        root.setSpacing(12)

        # Title
        title = QLabel("Fruits — Task Thresholds (per task/label)")
        title.setObjectName("title")
        root.addWidget(title)

        # Toolbar: search + actions
        toolbar = QFrame()
        toolbar.setObjectName("toolbar")
        tl = QHBoxLayout(toolbar)
        tl.setContentsMargins(12, 12, 12, 12)
        tl.setSpacing(8)

        self.txt_search = QLineEdit(placeholderText="Search by task or label…")
        self.txt_search.setObjectName("search")

        self.btn_add = QPushButton("🍌 Add row")
        self.btn_delete = QPushButton("🍒 Delete selected")
        self.btn_save = QPushButton("🥝 Save all")

        self.btn_add.setObjectName("btn_add")
        self.btn_delete.setObjectName("btn_delete")
        self.btn_save.setObjectName("btn_save")

        tl.addWidget(self.txt_search, 1)
        tl.addStretch(0)
        tl.addWidget(self.btn_add)
        tl.addWidget(self.btn_delete)
        tl.addWidget(self.btn_save)

        root.addWidget(toolbar)

        # Table
        self.tbl = QTableWidget(0, 4, self)
        self.tbl.setAlternatingRowColors(True)
        self.tbl.setHorizontalHeaderLabels([
            "Task", "Label (optional)", "Threshold (0..1)", "Updated By"
        ])
        hdr = self.tbl.horizontalHeader()
        hdr.setStretchLastSection(True)
        hdr.setSectionResizeMode(QHeaderView.ResizeMode.Interactive)
        self.tbl.setSelectionBehavior(QAbstractItemView.SelectionBehavior.SelectRows)
        self.tbl.setSelectionMode(QAbstractItemView.SelectionMode.SingleSelection)
        self.tbl.setEditTriggers(
            QAbstractItemView.EditTrigger.DoubleClicked
            | QAbstractItemView.EditTrigger.SelectedClicked
            | QAbstractItemView.EditTrigger.EditKeyPressed
        )
     
        self.tbl.verticalHeader().setDefaultSectionSize(36)   

        root.addWidget(self.tbl, 1)

        # Status + Close
        bottom = QHBoxLayout()
        self.lbl_status = QLabel("Add rows and click Save.")
        self.lbl_status.setObjectName("status")
        bottom.addWidget(self.lbl_status)
        bottom.addStretch(1)
        self.btn_close = QPushButton("🫐 Close")
        self.btn_close.setObjectName("btn_close")
        bottom.addWidget(self.btn_close)
        root.addLayout(bottom)

        # Signals
        self.btn_add.clicked.connect(self.add_row)
        self.btn_delete.clicked.connect(self.delete_selected)
        self.btn_save.clicked.connect(self.save_all)
        self.btn_close.clicked.connect(self.accept)
        self.txt_search.textChanged.connect(self._apply_filter)

        # Start with one empty row
        self.add_row()

    def load_rows(self, rows: List[Tuple[str, str, float, str]]):
        
        self.tbl.setRowCount(0)
        for t, l, thr, upd in rows:
            self.add_row(t, l, thr, upd)
        self.lbl_status.setText(f"Loaded {len(rows)} rows.")

    # -------- Row ops --------
    def add_row(
        self,
        task: str = "",
        label: str = "",
        threshold: float = 0.5,
        updated_by: str = "gui"
    ):
        r = self.tbl.rowCount()
        self.tbl.insertRow(r)

        # Task (combobox)
        cmb = QComboBox(self.tbl)
        cmb.addItems(self.TASK_OPTIONS)
        if task in self.TASK_OPTIONS:
            cmb.setCurrentText(task)
        self.tbl.setCellWidget(r, 0, cmb)

        # Label (editable)
        self._set_text_cell(r, 1, label)

        # Threshold (spinbox)
        spn = QDoubleSpinBox(self.tbl)
        spn.setRange(0.0, 1.0)
        spn.setSingleStep(0.01)
        spn.setDecimals(2)
        spn.setValue(float(threshold))
        spn.setAlignment(Qt.AlignmentFlag.AlignRight)  
        self.tbl.setCellWidget(r, 2, spn)

        # Updated By
        self._set_text_cell(r, 3, updated_by or "gui")

        self.lbl_status.setText("Row added.")

    def delete_selected(self):
        sel = self.tbl.selectionModel().selectedRows()
        if not sel:
            self._set_status("No row selected.", "warn")
            return
        for m in sel:
            self.tbl.removeRow(m.row())
        self._set_status("Row deleted.", "ok")

    # -------- Helpers --------
    def _set_text_cell(self, row: int, col: int, text: str):
        item = QTableWidgetItem(text or "")
        item.setFlags(item.flags() | Qt.ItemFlag.ItemIsEditable)
        self.tbl.setItem(row, col, item)

    def _read_row(self, r: int) -> Tuple[str, str, float, str]:
        # Task
        cmb = self.tbl.cellWidget(r, 0)
        task = cmb.currentText() if isinstance(cmb, QComboBox) else ""

        # Label (optional)
        label_item = self.tbl.item(r, 1)
        label = (label_item.text().strip() if label_item else "")

        # Threshold
        spn = self.tbl.cellWidget(r, 2)
        threshold = float(spn.value()) if isinstance(spn, QDoubleSpinBox) else 0.0

        # Updated By
        updated_item = self.tbl.item(r, 3)
        updated_by = (updated_item.text().strip() if updated_item else "")

        return task, label, threshold, updated_by

    def _apply_filter(self):
        q = self.txt_search.text().strip().lower()
        for r in range(self.tbl.rowCount()):
            t, l, _, _ = self._read_row(r)
            show = (q in t.lower()) or (q in (l or "").lower()) or (q == "")
            self.tbl.setRowHidden(r, not show)

    def _set_status(self, text: str, level: str = "info"):
        # level: ok|warn|err|info
        self.lbl_status.setText(text)
        for cls in ["status-ok", "status-warn", "status-err"]:
            self.lbl_status.setProperty("class", "")
        if level == "ok":
            self.lbl_status.setProperty("class", "status-ok")
        elif level == "warn":
            self.lbl_status.setProperty("class", "status-warn")
        elif level == "err":
            self.lbl_status.setProperty("class", "status-err")
        self.lbl_status.style().unpolish(self.lbl_status)
        self.lbl_status.style().polish(self.lbl_status)

    def _validate(self) -> Tuple[bool, str, List[int]]:
        """
        Rules:
        - Task: required
        - Label: optional (dedup by (task,label))
        - Threshold: 0..1
        - No duplicate (task, label)
        - At least one row
        Returns: (ok, msg, bad_rows_indices)
        """
        seen = set()
        bad_rows = []

        for r in range(self.tbl.rowCount()):
            t, l, thr, _ = self._read_row(r)
            if not t:
                bad_rows.append(r)
                return False, f"Row {r+1}: Task is empty.", bad_rows
            if not (0.0 <= thr <= 1.0):
                bad_rows.append(r)
                return False, f"Row {r+1}: Threshold must be between 0 and 1.", bad_rows

            key = (t, l or "")
            if key in seen:
                bad_rows.append(r)
                return False, f"Row {r+1}: Duplicate (task,label)=({t},{l or '∅'}).", bad_rows
            seen.add(key)

        if self.tbl.rowCount() == 0:
            return False, "No rows to save.", []

        return True, "", []

    # -------- Save --------
    def save_all(self):
        ok, msg, bad_rows = self._validate()
       
        if not ok:
            if bad_rows:
                self.tbl.selectRow(bad_rows[0])
            QMessageBox.warning(self, "Validation error", msg)
            self._set_status(msg, "err")
            return

        # Build mapping: {(task,label): threshold}
        mapping: Dict[Tuple[str, str], float] = {}
        for r in range(self.tbl.rowCount()):
            t, l, thr, _ = self._read_row(r)
            key = (t, l or "")
            mapping[key] = thr

        # Disable buttons during save
        self.btn_save.setEnabled(False)
        self.btn_add.setEnabled(False)
        self.btn_delete.setEnabled(False)

        def _normalize_ok_set(ok_raw) -> set[tuple[str, str]]:
            ok: set[tuple[str, str]] = set()
            for item in ok_raw or []:
                if isinstance(item, (list, tuple)):
                    ok.add((str(item[0]) if len(item)>0 else "", str(item[1]) if len(item)>1 else ""))
            return ok

        def _normalize_fail_list(fail_raw):
            pairs = []
            for item in fail_raw or []:
                if isinstance(item, (list, tuple)) and len(item) >= 1:
                    key = item[0]
                    reason = item[1] if len(item) > 1 else "unknown"
                    if isinstance(key, (list, tuple)) and len(key) >= 1:
                        key_str = f"{key[0]},{key[1] if len(key)>1 else ''}"
                    else:
                        key_str = str(key)
                    pairs.append((key_str, str(reason)))
                else:
                    pairs.append((str(item), "unknown"))
            return pairs

        try:
            report = self.api.bulk_set_task_thresholds_labeled(mapping, updated_by="gui")
            ok_keys = _normalize_ok_set(report.get("ok", []))
            fail_pairs = _normalize_fail_list(report.get("fail", []))

            total = len(mapping)
            failed = len(fail_pairs)
            succeeded = len(ok_keys) if ok_keys else (total - failed)

            if failed == 0:
                self._set_status(f"Saved {succeeded}/{total} thresholds ✓", "ok")
                QMessageBox.information(self, "Saved", f"All {total} thresholds saved successfully.")
                self.thresholdsSaved.emit({k: v for k, v in mapping.items()})
            else:
                lines = "\n".join(f"- {k}: {reason}" for k, reason in fail_pairs[:10])
                more = "" if failed <= 10 else f"\n(+{failed-10} more...)"
                self._set_status(f"Partial save: {succeeded}/{total} saved, {failed} failed.", "warn")
                QMessageBox.warning(self, "Partial save", f"Saved {succeeded}/{total}.\nFailed:\n{lines}{more}")

        except Exception as e:
            import traceback
            traceback.print_exc()
            QMessageBox.critical(self, "Error", f"Failed to save thresholds:\n{type(e).__name__}: {e}")
            self._set_status("Failed to save thresholds.", "err")
        finally:
            self.btn_save.setEnabled(True)
            self.btn_add.setEnabled(True)
            self.btn_delete.setEnabled(True)



class FruitsView(QWidget):
    thresholdsSaved = pyqtSignal(dict)  # {(task,label): threshold}

    def __init__(self, api: DashboardApi, parent=None):
        super().__init__(parent)
        self.api = api

        root = QVBoxLayout(self)
        root.setSpacing(10)

        title = QLabel("Fruits")
        title.setStyleSheet("font-size: 22px; font-weight: 700;")
        root.addWidget(title)

        
        row = QHBoxLayout()
        lbl = QLabel("Manage task thresholds per task/label.")
        self.btn_open_editor = QPushButton("Change thresholds…")
        row.addWidget(lbl, 1)
        row.addStretch(0)
        row.addWidget(self.btn_open_editor)
        root.addLayout(row)

        line = QFrame()
        line.setFrameShape(QFrame.Shape.HLine)
        line.setStyleSheet("color:#e5e7eb;")
        root.addWidget(line)

        
        self.lbl_status = QLabel("Click “Change thresholds…” to edit.")
        self.lbl_status.setStyleSheet("color:#555;")
        root.addWidget(self.lbl_status)

     
        self.btn_open_editor.clicked.connect(self.open_thresholds_dialog)

    def open_thresholds_dialog(self):
        dlg = ThresholdsEditorDialog(self.api, self)
       
        # rows = self.api.get_current_thresholds() -> List[Tuple[str,str,float,str]]
        # dlg.load_rows(rows)

        dlg.thresholdsSaved.connect(self.thresholdsSaved.emit)
        dlg.exec()  # modal
        self.lbl_status.setText("Threshold editor closed.")
