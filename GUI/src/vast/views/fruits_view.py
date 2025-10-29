# views/fruits_view.py
from __future__ import annotations
from typing import Optional, Tuple, Dict, List
from PyQt6.QtCore import Qt, pyqtSignal # type: ignore
from PyQt6.QtWidgets import ( # type: ignore
    QWidget, QVBoxLayout, QHBoxLayout, QLabel, QPushButton, QComboBox,
    QTableWidget, QTableWidgetItem, QAbstractItemView, QDoubleSpinBox,
    QMessageBox, QHeaderView, 
)

from dashboard_api import DashboardApi


class FruitsView(QWidget):
    """
    Thresholds editor per ( task, label).
    Replaces the previous 'client thresholds' view.
    """
    thresholdsSaved = pyqtSignal(dict)  # {( task, label): threshold}

    def __init__(self, api: DashboardApi, parent=None):
        super().__init__(parent)
        self.api = api

        # --- Layout scaffolding ---
        root = QVBoxLayout(self)
        root.setSpacing(10)

        title = QLabel("Fruits — Task Thresholds (per task/label)")
        title.setStyleSheet("font-size: 18px; font-weight: 600;")
        root.addWidget(title)

        # Action buttons
        btns = QHBoxLayout()
        self.btn_add = QPushButton("Add row")
        self.btn_delete = QPushButton("Delete selected")
        self.btn_save = QPushButton("Save all")
        btns.addWidget(self.btn_add)
        btns.addWidget(self.btn_delete)
        btns.addStretch(1)
        btns.addWidget(self.btn_save)
        root.addLayout(btns)

        # Table: 4 columns
       
        # 0: Task (editable text)
        # 1: Label (editable text, optional; empty string means default bucket)
        # 2: Threshold (0..1) as spinbox
        # 3: Updated By (editable text, optional)
        self.tbl = QTableWidget(0, 4, self)
        self.tbl.setHorizontalHeaderLabels([
             "Task", "Label (optional)", "Threshold (0..1)", "Updated By"
        ])
        self.tbl.horizontalHeader().setStretchLastSection(True)
        self.tbl.horizontalHeader().setSectionResizeMode(
            QHeaderView.ResizeMode.Interactive
        )
        self.tbl.setSelectionBehavior(QAbstractItemView.SelectionBehavior.SelectRows)
        self.tbl.setSelectionMode(QAbstractItemView.SelectionMode.SingleSelection)
        self.tbl.setEditTriggers(
            QAbstractItemView.EditTrigger.DoubleClicked
            | QAbstractItemView.EditTrigger.SelectedClicked
            | QAbstractItemView.EditTrigger.EditKeyPressed
        )
        root.addWidget(self.tbl)

        # Status line
        self.lbl_status = QLabel("Add rows and click Save.")
        self.lbl_status.setStyleSheet("color:#555;")
        root.addWidget(self.lbl_status)

        # Signals
        self.btn_add.clicked.connect(self.add_row)
        self.btn_delete.clicked.connect(self.delete_selected)
        self.btn_save.clicked.connect(self.save_all)

        # Start with an empty demo row
        self.add_row()

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

       
        # Task
        cmb = QComboBox(self.tbl)
        TASK_OPTIONS = ["ripeness", "disease", "size", "color"]
        cmb.addItems(TASK_OPTIONS)
        if task in TASK_OPTIONS:
            cmb.setCurrentText(task)
        else:
            cmb.setCurrentIndex(0)
        self.tbl.setCellWidget(r, 0, cmb)
        # Label (optional)
        self._set_text_cell(r, 1, label)

        # Threshold spinbox
        spn = QDoubleSpinBox(self.tbl)
        spn.setRange(0.0, 1.0)
        spn.setSingleStep(0.01)
        spn.setDecimals(2)
        spn.setValue(float(threshold))
        self.tbl.setCellWidget(r, 2, spn)

        # Updated By
        self._set_text_cell(r, 3, updated_by)

        self.lbl_status.setText("Row added.")

    def delete_selected(self):
        sel = self.tbl.selectionModel().selectedRows()
        if not sel:
            self.lbl_status.setText("No row selected.")
            return
        for m in sel:
            self.tbl.removeRow(m.row())
        self.lbl_status.setText("Row deleted.")

    # -------- Helpers --------
    def _set_text_cell(self, row: int, col: int, text: str):
        item = QTableWidgetItem(text or "")
        # Editable text item
        item.setFlags(item.flags() | Qt.ItemFlag.ItemIsEditable)
        self.tbl.setItem(row, col, item)

    def _read_row(self, r: int) -> Tuple[ str, str, float, str]:

        # Task
        cmb = self.tbl.cellWidget(r, 0)
        if isinstance(cmb, QComboBox):
            task = cmb.currentText()
        else:
            task = ""


        # Label (optional; empty string is allowed)
        label_item = self.tbl.item(r, 1)
        label = (label_item.text().strip() if label_item else "")

        # Threshold
        spn = self.tbl.cellWidget(r, 2)
        threshold = float(spn.value()) if isinstance(spn, QDoubleSpinBox) else 0.0

        # Updated By
        updated_item = self.tbl.item(r, 3)
        updated_by = (updated_item.text().strip() if updated_item else "")

        return  task, label, threshold, updated_by

    def _validate(self) -> Tuple[bool, str]:
        """
        Rules:
        - Task: required
        - Label: optional (dedup still enforced using the triple)
        - Threshold: 0..1
        - No duplicate (mission_id, task, label)
        - At least one row
        """
        seen = set()
        for r in range(self.tbl.rowCount()):
            t, l, thr, _ = self._read_row(r)
            if not t:
                return False, f"Row {r+1}: Task is empty."
            if not (0.0 <= thr <= 1.0):
                return False, f"Row {r+1}: Threshold must be between 0 and 1."

            key = (t, l or "")
            if key in seen:
                return False, (
                    f"Row {r+1}: Duplicate ( task, label) = "
                    f"( {t}, {l or '∅'})."
                )
            seen.add(key)

        if self.tbl.rowCount() == 0:
            return False, "No rows to save."

        return True, ""

    # -------- Save --------
    def save_all(self):
        ok, msg = self._validate()
        if not ok:
            QMessageBox.warning(self, "Validation error", msg)
            self.lbl_status.setStyleSheet("color:#b00020;")
            self.lbl_status.setText(msg)
            return

        # Build mapping: {( task, label): threshold}
        mapping: Dict[Tuple[ str, str], float] = {}
        updated_by_for_row: Dict[Tuple[ str, str], str] = {}

        for r in range(self.tbl.rowCount()):
            t, l, thr, updated_by = self._read_row(r)
            key = ( t, l or "")
            mapping[key] = thr
            updated_by_for_row[key] = updated_by or "gui"

        # Disable buttons during save
        self.btn_save.setEnabled(False)
        self.btn_add.setEnabled(False)
        self.btn_delete.setEnabled(False)

        def _normalize_fail_list(fail_raw) -> List[Tuple[str, str]]:
            """
            Normalize to list of (key, reason) as strings for message box.
            """
            pairs: List[Tuple[str, str]] = []
            for item in fail_raw or []:
                # expected formats can vary; keep it defensive
                if isinstance(item, (list, tuple)) and len(item) >= 1:
                    key = str(item[0])
                    reason = str(item[1]) if len(item) > 1 else "unknown"
                elif isinstance(item, dict):
                    # try generic fields
                    key = (
                        item.get("key")
                        or item.get("id")
                        or f"{item.get('task')},{item.get('label','')}"
                    )
                    reason = str(item.get("reason") or item.get("detail") or "unknown")
                else:
                    key = str(item)
                    reason = "unknown"
                pairs.append((key, reason))
            return pairs

        try:
            # Flatten mapping into the API’s expected structure
            # API helper that we assume exists (as agreed earlier):
            # bulk_set_task_thresholds_labeled(mapping, updated_by="gui")
            # If your API expects a list of dicts, it should convert internally.
            # To respect per-row updated_by, we send the majority value,
            # and rely on server-side to accept it. Alternatively, expose a
            # dedicated bulk that accepts per-row updated_by list.
            report = self.api.bulk_set_task_thresholds_labeled(mapping, updated_by="gui")

            ok_keys = set(report.get("ok", []))  # may contain tuples or strings per API
            fail_pairs = _normalize_fail_list(report.get("fail", []))

            total = len(mapping)
            failed = len(fail_pairs)
            succeeded = len(ok_keys) if ok_keys else (total - failed)

            if failed == 0:
                self.lbl_status.setStyleSheet("color:#0a7d00;")
                self.lbl_status.setText(f"Saved {succeeded}/{total} thresholds ✓")
                QMessageBox.information(self, "Saved", f"All {total} thresholds saved successfully.")
                # Emit a normalized dict for listeners
                self.thresholdsSaved.emit({k: v for k, v in mapping.items()})
            else:
                self.lbl_status.setStyleSheet("color:#cc7a00;")
                # Show first 10 failures neatly
                lines = "\n".join(f"- {k}: {reason}" for k, reason in fail_pairs[:10])
                more = "" if failed <= 10 else f"\n(+{failed-10} more...)"
                self.lbl_status.setText(f"Partial save: {succeeded}/{total} saved, {failed} failed.")
                QMessageBox.warning(self, "Partial save", f"Saved {succeeded}/{total}.\nFailed:\n{lines}{more}")

        except Exception as e:
            import traceback
            traceback.print_exc()
            QMessageBox.critical(self, "Error", f"Failed to save thresholds:\n{type(e).__name__}: {e}")

        finally:
            self.btn_save.setEnabled(True)
            self.btn_add.setEnabled(True)
            self.btn_delete.setEnabled(True)
