# -*- coding: utf-8 -*-
import os
import sys
import glob

from PyQt5.QtWidgets import (
    QMainWindow, QWidget, QVBoxLayout, QHBoxLayout, QTableWidget,
    QTableWidgetItem, QToolBar, QAction, QFileDialog, QMessageBox,
    QProgressBar, QLabel, QStatusBar, QDialog, QListWidget, QListWidgetItem,
    QPushButton, QLineEdit, QFormLayout, QScrollArea, QInputDialog, QComboBox,
    QAbstractItemView, QHeaderView
)
from PyQt5.QtGui import QIcon, QPixmap, QColor
from PyQt5.QtCore import Qt, QThread, pyqtSignal, QSize

sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from core.classifier import DefectClassifier, OK_LABEL, NG_LABEL
from core.filename_parser import parse_filename, max_token_count
from core.excel_export import export_to_excel
from core import settings as settings_mod

IMAGE_EXTS = (".jpg", ".jpeg", ".png", ".bmp", ".tif", ".tiff")

COL_THUMB = 0
COL_FILENAME = 1
COL_JUDGE = 2
COL_CODE = 3
COL_CONF = 4
FIXED_COL_COUNT = 5  # 위 5개 컬럼 다음부터 파일명 분리 토큰 컬럼


def list_images_recursive(folder):
    files = []
    for ext in IMAGE_EXTS:
        files.extend(glob.glob(os.path.join(folder, "**", f"*{ext}"), recursive=True))
        files.extend(glob.glob(os.path.join(folder, "**", f"*{ext.upper()}"), recursive=True))
    return sorted(set(files))


# ----------------------------------------------------------------------
class TrainWorker(QThread):
    progress = pyqtSignal(int, int, str)
    done = pyqtSignal(dict)
    error = pyqtSignal(str)

    def __init__(self, classifier: DefectClassifier, root_dir, good_folder_name):
        super().__init__()
        self.classifier = classifier
        self.root_dir = root_dir
        self.good_folder_name = good_folder_name

    def run(self):
        try:
            report = self.classifier.train(
                self.root_dir, self.good_folder_name,
                progress_callback=lambda c, t, m: self.progress.emit(c, t, m)
            )
            self.done.emit(report)
        except Exception as e:
            self.error.emit(str(e))


class InspectWorker(QThread):
    progress = pyqtSignal(int, int, str)
    row_ready = pyqtSignal(dict)
    finished_all = pyqtSignal(int)
    error = pyqtSignal(str)

    def __init__(self, classifier: DefectClassifier, folder, recursive=True):
        super().__init__()
        self.classifier = classifier
        self.folder = folder
        self.recursive = recursive

    def run(self):
        try:
            files = list_images_recursive(self.folder) if self.recursive else sorted(
                glob.glob(os.path.join(self.folder, "*.*"))
            )
            files = [f for f in files if f.lower().endswith(IMAGE_EXTS)]
            total = len(files)
            if total == 0:
                self.error.emit("선택한 폴더에 이미지 파일이 없습니다.")
                return
            for i, path in enumerate(files):
                try:
                    result = self.classifier.predict(path)
                except Exception as e:
                    result = {"label": "오류", "defect_code": str(e), "confidence": 0, "need_review": True}
                tokens = parse_filename(path)
                self.row_ready.emit({
                    "path": path,
                    "filename": os.path.basename(path),
                    "label": result["label"],
                    "defect_code": result["defect_code"],
                    "confidence": result["confidence"],
                    "need_review": result["need_review"],
                    "tokens": tokens,
                })
                self.progress.emit(i + 1, total, os.path.basename(path))
            self.finished_all.emit(total)
        except Exception as e:
            self.error.emit(str(e))


# ----------------------------------------------------------------------
class ColumnSelectDialog(QDialog):
    """화면에 표시할 컬럼을 체크박스로 선택하는 대화상자."""

    def __init__(self, headers, visible_flags, parent=None):
        super().__init__(parent)
        self.setWindowTitle("표시할 컬럼 선택")
        self.resize(320, 420)
        layout = QVBoxLayout(self)
        layout.addWidget(QLabel("검사 결과 화면 및 엑셀 내보내기에 포함할 컬럼을 선택하세요."))

        self.list_widget = QListWidget()
        for idx, name in enumerate(headers):
            item = QListWidgetItem(name)
            item.setFlags(item.flags() | Qt.ItemIsUserCheckable)
            item.setCheckState(Qt.Checked if visible_flags[idx] else Qt.Unchecked)
            self.list_widget.addItem(item)
        layout.addWidget(self.list_widget)

        btn_row = QHBoxLayout()
        all_btn = QPushButton("전체 선택")
        none_btn = QPushButton("전체 해제")
        ok_btn = QPushButton("적용")
        all_btn.clicked.connect(lambda: self._set_all(Qt.Checked))
        none_btn.clicked.connect(lambda: self._set_all(Qt.Unchecked))
        ok_btn.clicked.connect(self.accept)
        btn_row.addWidget(all_btn)
        btn_row.addWidget(none_btn)
        btn_row.addStretch()
        btn_row.addWidget(ok_btn)
        layout.addLayout(btn_row)

    def _set_all(self, state):
        for i in range(self.list_widget.count()):
            self.list_widget.item(i).setCheckState(state)

    def get_checked(self):
        return [self.list_widget.item(i).checkState() == Qt.Checked
                for i in range(self.list_widget.count())]


class HeaderEditDialog(QDialog):
    """모든 컬럼의 제목을 한 번에 편집하는 대화상자."""

    def __init__(self, headers, parent=None):
        super().__init__(parent)
        self.setWindowTitle("컬럼 제목 편집")
        self.resize(360, 480)
        outer = QVBoxLayout(self)
        outer.addWidget(QLabel("각 컬럼의 제목을 자유롭게 입력하세요 (예: LOT번호, 설비명 등)."))

        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        inner = QWidget()
        form = QFormLayout(inner)
        self.edits = []
        for idx, name in enumerate(headers):
            edit = QLineEdit(name)
            form.addRow(f"컬럼 {idx + 1}", edit)
            self.edits.append(edit)
        scroll.setWidget(inner)
        outer.addWidget(scroll)

        ok_btn = QPushButton("적용")
        ok_btn.clicked.connect(self.accept)
        outer.addWidget(ok_btn)

    def get_headers(self):
        return [e.text().strip() or f"항목{i+1}" for i, e in enumerate(self.edits)]


# ----------------------------------------------------------------------
class MainWindow(QMainWindow):
    def __init__(self):
        super().__init__()
        self.setWindowTitle("TFT LCD 불량 자동 분석 프로그램")
        self.resize(1400, 800)

        self.classifier = DefectClassifier()
        self.app_settings = settings_mod.load_settings()
        self.current_headers = []   # 전체 컬럼 헤더(고정4 + 동적 토큰컬럼)
        self.rows_data = []         # 내보내기를 위한 원본 데이터 저장

        self._build_ui()
        self._restore_model_if_any()

    # ------------------------------------------------------------------
    def _build_ui(self):
        toolbar = QToolBar("메인 툴바")
        toolbar.setIconSize(QSize(20, 20))
        self.addToolBar(toolbar)

        act_train = QAction("① 학습 폴더 선택/학습", self)
        act_train.triggered.connect(self.on_train)
        toolbar.addAction(act_train)

        act_load_model = QAction("모델 불러오기", self)
        act_load_model.triggered.connect(self.on_load_model)
        toolbar.addAction(act_load_model)

        act_save_model = QAction("모델 저장", self)
        act_save_model.triggered.connect(self.on_save_model)
        toolbar.addAction(act_save_model)

        toolbar.addSeparator()

        act_inspect = QAction("② 검사 폴더 선택/분석", self)
        act_inspect.triggered.connect(self.on_inspect)
        toolbar.addAction(act_inspect)

        toolbar.addSeparator()

        act_headers = QAction("컬럼 제목 편집", self)
        act_headers.triggered.connect(self.on_edit_headers)
        toolbar.addAction(act_headers)

        act_columns = QAction("표시 컬럼 선택", self)
        act_columns.triggered.connect(self.on_select_columns)
        toolbar.addAction(act_columns)

        toolbar.addSeparator()

        act_export = QAction("엑셀로 내보내기", self)
        act_export.triggered.connect(self.on_export_excel)
        toolbar.addAction(act_export)

        # 테이블
        self.table = QTableWidget()
        self.table.setEditTriggers(QAbstractItemView.NoEditTriggers)
        self.table.setSelectionBehavior(QAbstractItemView.SelectRows)
        self.table.horizontalHeader().sectionDoubleClicked.connect(self.on_header_double_click)
        self.table.cellDoubleClicked.connect(self.on_cell_double_click)
        self.table.verticalHeader().setVisible(False)

        central = QWidget()
        v = QVBoxLayout(central)
        v.addWidget(self.table)
        self.setCentralWidget(central)

        # 상태바
        self.status = QStatusBar()
        self.setStatusBar(self.status)
        self.progress_bar = QProgressBar()
        self.progress_bar.setMaximumWidth(300)
        self.progress_bar.setVisible(False)
        self.status.addPermanentWidget(self.progress_bar)
        self.model_status_label = QLabel("모델: 로드되지 않음")
        self.status.addWidget(self.model_status_label)

        self._init_table_headers(extra_token_count=5)

    # ------------------------------------------------------------------
    def _init_table_headers(self, extra_token_count):
        base = ["썸네일", "원본파일명", "판정", "불량코드", "신뢰도(%)"]
        tokens = [self.app_settings["column_headers"].get(f"col_{FIXED_COL_COUNT+i}", f"항목{i+1}")
                  for i in range(extra_token_count)]
        headers = base + tokens
        self.current_headers = headers
        self.table.setColumnCount(len(headers))
        self.table.setHorizontalHeaderLabels(headers)
        self.table.setColumnWidth(COL_THUMB, 90)
        self.table.horizontalHeader().setSectionResizeMode(COL_FILENAME, QHeaderView.Interactive)
        self._apply_visibility_from_settings()

    def _apply_visibility_from_settings(self):
        vis = self.app_settings.get("visible_columns", {})
        for c in range(self.table.columnCount()):
            key = f"col_{c}"
            if key in vis:
                self.table.setColumnHidden(c, not vis[key])

    def _ensure_token_columns(self, needed_count):
        current_extra = self.table.columnCount() - FIXED_COL_COUNT
        if needed_count <= current_extra:
            return
        add_n = needed_count - current_extra
        new_total = self.table.columnCount() + add_n
        self.table.setColumnCount(new_total)
        for i in range(add_n):
            col_idx = current_extra + i
            default_name = self.app_settings["column_headers"].get(
                f"col_{FIXED_COL_COUNT+col_idx}", f"항목{col_idx+1}")
            item = QTableWidgetItem(default_name)
            self.table.setHorizontalHeaderItem(FIXED_COL_COUNT + col_idx, item)
            self.current_headers.append(default_name)

    # ------------------------------------------------------------------
    # 학습
    def on_train(self):
        root_dir = QFileDialog.getExistingDirectory(
            self, "학습 폴더 선택 (하위에 '양품' 폴더와 불량코드별 폴더가 있어야 합니다)")
        if not root_dir:
            return
        subfolders = [f for f in os.listdir(root_dir) if os.path.isdir(os.path.join(root_dir, f))]
        if not subfolders:
            QMessageBox.warning(self, "오류", "선택한 폴더 안에 하위 폴더가 없습니다.")
            return

        good_name, ok = QInputDialog.getItem(
            self, "양품 폴더 지정", "다음 중 '양품' 이미지가 들어있는 폴더를 선택하세요:",
            subfolders, 0, False)
        if not ok:
            return

        self.progress_bar.setVisible(True)
        self.progress_bar.setValue(0)
        self.status.showMessage("학습 준비 중...")

        self.train_worker = TrainWorker(self.classifier, root_dir, good_name)
        self.train_worker.progress.connect(self._on_progress)
        self.train_worker.done.connect(self._on_train_done)
        self.train_worker.error.connect(self._on_error)
        self.train_worker.start()

        self.app_settings["last_train_dir"] = root_dir
        self.app_settings["good_folder_name"] = good_name
        settings_mod.save_settings(self.app_settings)

    def _on_progress(self, cur, total, msg):
        self.progress_bar.setMaximum(total)
        self.progress_bar.setValue(cur)
        self.status.showMessage(f"({cur}/{total}) {msg}")

    def _on_train_done(self, report):
        self.progress_bar.setVisible(False)
        self.status.showMessage("학습 완료", 5000)
        self.model_status_label.setText(
            f"모델: 학습 완료 (불량코드 {len(report.get('불량코드 목록', []))}종)")
        lines = "\n".join(f"{k}: {v}" for k, v in report.items())
        QMessageBox.information(self, "학습 결과", lines)

        # 새로 학습된 불량코드 목록을 설정에 저장
        self.app_settings["defect_codes"] = report.get("불량코드 목록", [])
        settings_mod.save_settings(self.app_settings)

        save_path, _ = QFileDialog.getSaveFileName(
            self, "학습된 모델 저장", "tft_model.joblib", "Model Files (*.joblib)")
        if save_path:
            self.classifier.save(save_path)
            self.app_settings["last_model_path"] = save_path
            settings_mod.save_settings(self.app_settings)

    def _on_error(self, msg):
        self.progress_bar.setVisible(False)
        QMessageBox.critical(self, "오류", msg)
        self.status.showMessage("오류 발생", 5000)

    # ------------------------------------------------------------------
    def on_load_model(self):
        path, _ = QFileDialog.getOpenFileName(self, "모델 불러오기", "", "Model Files (*.joblib)")
        if not path:
            return
        try:
            self.classifier.load(path)
            self.model_status_label.setText(f"모델: {os.path.basename(path)} 로드됨")
            self.app_settings["last_model_path"] = path
            self.app_settings["defect_codes"] = self.classifier.defect_codes
            settings_mod.save_settings(self.app_settings)
            QMessageBox.information(self, "완료", "모델을 불러왔습니다.")
        except Exception as e:
            QMessageBox.critical(self, "오류", f"모델을 불러올 수 없습니다: {e}")

    def on_save_model(self):
        if self.classifier.bin_clf is None:
            QMessageBox.warning(self, "알림", "먼저 모델을 학습하거나 불러와주세요.")
            return
        path, _ = QFileDialog.getSaveFileName(self, "모델 저장", "tft_model.joblib", "Model Files (*.joblib)")
        if path:
            self.classifier.save(path)
            QMessageBox.information(self, "완료", "모델을 저장했습니다.")

    def _restore_model_if_any(self):
        path = self.app_settings.get("last_model_path", "")
        if path and os.path.exists(path):
            try:
                self.classifier.load(path)
                self.model_status_label.setText(f"모델: {os.path.basename(path)} 로드됨 (자동복원)")
            except Exception:
                pass

    # ------------------------------------------------------------------
    # 검사
    def on_inspect(self):
        if self.classifier.bin_clf is None:
            QMessageBox.warning(self, "알림", "먼저 모델을 학습하거나 불러와주세요.")
            return
        folder = QFileDialog.getExistingDirectory(self, "검사할 이미지 폴더 선택")
        if not folder:
            return

        self.table.setRowCount(0)
        self.rows_data = []

        # 폴더 내 파일명 최대 토큰 수만큼 컬럼 자동 확장
        files = list_images_recursive(folder)
        files = [f for f in files if f.lower().endswith(IMAGE_EXTS)]
        if not files:
            QMessageBox.warning(self, "알림", "이미지가 없습니다.")
            return
        needed = max_token_count(files)
        self._ensure_token_columns(needed)

        self.progress_bar.setVisible(True)
        self.progress_bar.setValue(0)

        self.inspect_worker = InspectWorker(self.classifier, folder, recursive=True)
        self.inspect_worker.progress.connect(self._on_progress)
        self.inspect_worker.row_ready.connect(self._on_row_ready)
        self.inspect_worker.finished_all.connect(self._on_inspect_finished)
        self.inspect_worker.error.connect(self._on_error)
        self.inspect_worker.start()

        self.app_settings["last_inspect_dir"] = folder
        settings_mod.save_settings(self.app_settings)

    def _on_row_ready(self, data):
        row = self.table.rowCount()
        self.table.insertRow(row)

        # 썸네일
        thumb_item = QTableWidgetItem()
        pixmap = QPixmap(data["path"])
        if not pixmap.isNull():
            thumb_item.setIcon(QIcon(pixmap.scaled(80, 80, Qt.KeepAspectRatio, Qt.SmoothTransformation)))
        thumb_item.setData(Qt.UserRole, data["path"])
        thumb_item.setFlags(thumb_item.flags() & ~Qt.ItemIsEditable)
        self.table.setItem(row, COL_THUMB, thumb_item)
        self.table.setRowHeight(row, 84)

        self.table.setItem(row, COL_FILENAME, QTableWidgetItem(data["filename"]))

        judge_item = QTableWidgetItem(data["label"])
        if data["label"] == NG_LABEL:
            judge_item.setBackground(QColor(255, 205, 205))
        elif data["label"] == OK_LABEL:
            judge_item.setBackground(QColor(205, 255, 210))
        self.table.setItem(row, COL_JUDGE, judge_item)

        code_item = QTableWidgetItem(str(data["defect_code"]))
        self.table.setItem(row, COL_CODE, code_item)

        conf_text = f"{data['confidence']}" + (" (재검토)" if data["need_review"] else "")
        conf_item = QTableWidgetItem(conf_text)
        if data["need_review"]:
            conf_item.setBackground(QColor(255, 235, 156))
        self.table.setItem(row, COL_CONF, conf_item)

        for i, tok in enumerate(data["tokens"]):
            col = FIXED_COL_COUNT + i
            if col < self.table.columnCount():
                self.table.setItem(row, col, QTableWidgetItem(tok))

        self.rows_data.append(data)

    def _on_inspect_finished(self, total):
        self.progress_bar.setVisible(False)
        self.status.showMessage(f"검사 완료: 총 {total}건", 6000)

    # ------------------------------------------------------------------
    # 컬럼 제목/표시 관리
    def on_header_double_click(self, index):
        current = self.table.horizontalHeaderItem(index).text()
        new_name, ok = QInputDialog.getText(self, "컬럼 제목 변경", "새 컬럼 제목:", text=current)
        if ok and new_name.strip():
            self.table.horizontalHeaderItem(index).setText(new_name.strip())
            self.current_headers[index] = new_name.strip()
            self.app_settings["column_headers"][f"col_{index}"] = new_name.strip()
            settings_mod.save_settings(self.app_settings)

    def on_edit_headers(self):
        headers = [self.table.horizontalHeaderItem(c).text() for c in range(self.table.columnCount())]
        dlg = HeaderEditDialog(headers, self)
        if dlg.exec_() == QDialog.Accepted:
            new_headers = dlg.get_headers()
            for c, name in enumerate(new_headers):
                self.table.horizontalHeaderItem(c).setText(name)
                self.app_settings["column_headers"][f"col_{c}"] = name
            self.current_headers = new_headers
            settings_mod.save_settings(self.app_settings)

    def on_select_columns(self):
        headers = [self.table.horizontalHeaderItem(c).text() for c in range(self.table.columnCount())]
        visible = [not self.table.isColumnHidden(c) for c in range(self.table.columnCount())]
        dlg = ColumnSelectDialog(headers, visible, self)
        if dlg.exec_() == QDialog.Accepted:
            checked = dlg.get_checked()
            for c, is_visible in enumerate(checked):
                self.table.setColumnHidden(c, not is_visible)
                self.app_settings["visible_columns"][f"col_{c}"] = is_visible
            settings_mod.save_settings(self.app_settings)

    def on_cell_double_click(self, row, col):
        # 불량코드 셀을 더블클릭하면 수동으로 코드 변경 가능
        if col != COL_CODE:
            return
        judge = self.table.item(row, COL_JUDGE).text()
        if judge != NG_LABEL:
            return
        codes = self.classifier.defect_codes or self.app_settings.get("defect_codes", [])
        if not codes:
            return
        current = self.table.item(row, COL_CODE).text()
        code, ok = QInputDialog.getItem(self, "불량코드 수동 변경", "불량코드 선택:", codes,
                                         codes.index(current) if current in codes else 0, False)
        if ok:
            self.table.item(row, COL_CODE).setText(code)
            if row < len(self.rows_data):
                self.rows_data[row]["defect_code"] = code

    # ------------------------------------------------------------------
    # 엑셀 내보내기 (화면에 보이는 컬럼만)
    def on_export_excel(self):
        if self.table.rowCount() == 0:
            QMessageBox.warning(self, "알림", "내보낼 데이터가 없습니다. 먼저 검사를 실행하세요.")
            return

        visible_cols = [c for c in range(self.table.columnCount()) if not self.table.isColumnHidden(c)]
        headers = [self.table.horizontalHeaderItem(c).text() for c in visible_cols]

        image_col_pos = visible_cols.index(COL_THUMB) if COL_THUMB in visible_cols else None

        rows = []
        for r in range(self.table.rowCount()):
            row_vals = []
            for c in visible_cols:
                item = self.table.item(r, c)
                if c == COL_THUMB:
                    row_vals.append(item.data(Qt.UserRole) if item else "")
                else:
                    row_vals.append(item.text() if item else "")
            rows.append(row_vals)

        save_path, _ = QFileDialog.getSaveFileName(
            self, "엑셀로 저장", "불량판정결과.xlsx", "Excel Files (*.xlsx)")
        if not save_path:
            return
        try:
            export_to_excel(headers, rows, save_path, image_col_index=image_col_pos, embed_thumbnails=True)
            QMessageBox.information(self, "완료", f"엑셀 파일로 저장했습니다:\n{save_path}")
        except Exception as e:
            QMessageBox.critical(self, "오류", f"엑셀 저장 중 오류:\n{e}")
