import sys
import os
import sqlite3
import io
from datetime import datetime

from PyQt6.QtWidgets import (
    QApplication, QWidget, QLabel, QPushButton, QLineEdit, QVBoxLayout,
    QHBoxLayout, QTabWidget, QTableWidget, QTableWidgetItem, QMessageBox,
    QComboBox, QDialog, QDialogButtonBox
)
from PyQt6.QtGui import QPixmap, QImage
from PyQt6.QtCore import Qt, QTimer

import qrcode
import cv2
from pyzbar.pyzbar import decode

DB_NAME = "reagents.db"

# ------------------- DB 初期化 -------------------

def init_db():
    conn = sqlite3.connect(DB_NAME)
    c = conn.cursor()
    c.execute("""CREATE TABLE IF NOT EXISTS reagents (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    name TEXT,
                    code TEXT UNIQUE,
                    location TEXT,
                    qr_image BLOB
                 )""")
    c.execute("""CREATE TABLE IF NOT EXISTS usage_history (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    reagent_code TEXT,
                    user TEXT,
                    used_date TEXT
                 )""")
    conn.commit()
    conn.close()


def generate_code():
    today = datetime.now().strftime("%Y%m%d")
    conn = sqlite3.connect(DB_NAME)
    c = conn.cursor()
    c.execute("SELECT COUNT(*) FROM reagents WHERE code LIKE ?", (f"{today}%",))
    count = c.fetchone()[0] + 1
    conn.close()
    return f"{today}-{count:03d}"

# ------------------- QR カメラダイアログ -------------------


class QRCameraDialog(QDialog):
    """ライブプレビューしながら1枚だけQRコードを読むダイアログ"""

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWindowTitle("QRコード読み取り (Esc でキャンセル)")
        self.resize(640, 480)
        self.label = QLabel(alignment=Qt.AlignmentFlag.AlignCenter)

        lay = QVBoxLayout(self)
        lay.addWidget(self.label)

        self.cap = cv2.VideoCapture(0, cv2.CAP_DSHOW)
        if not self.cap.isOpened():
            raise RuntimeError("カメラを開けませんでした")

        self.qr_payload = None

        self.timer = QTimer(self)
        self.timer.timeout.connect(self.next_frame)
        self.timer.start(30)

    def next_frame(self):
        ok, frame = self.cap.read()
        if not ok:
            return
        rgb = cv2.cvtColor(frame, cv2.COLOR_BGR2RGB)
        h, w, ch = rgb.shape
        qimg = QImage(rgb.data, w, h, ch * w, QImage.Format.Format_RGB888)
        self.label.setPixmap(QPixmap.fromImage(qimg).scaled(
            self.label.size(), Qt.AspectRatioMode.KeepAspectRatio, Qt.TransformationMode.SmoothTransformation))

        decoded = decode(frame)
        if decoded:
            self.qr_payload = decoded[0].data.decode("utf-8")
            self.accept()

    def keyPressEvent(self, e):
        if e.key() == Qt.Key.Key_Escape:
            self.reject()
        else:
            super().keyPressEvent(e)

    def closeEvent(self, e):
        if self.cap.isOpened():
            self.cap.release()
        self.timer.stop()
        super().closeEvent(e)

# ------------------- メインウィジェット -------------------


class ReagentManager(QWidget):
    def __init__(self):
        super().__init__()
        self.setWindowTitle("Reagent QR Manager")
        self.resize(800, 600)

        self.current_code = None
        self.current_qr_bytes = None

        self.tabs = QTabWidget()
        self.register_tab = QWidget()
        self.history_tab = QWidget()

        self.tabs.addTab(self.register_tab, "原料登録")
        self.tabs.addTab(self.history_tab, "使用履歴検索")

        main_layout = QVBoxLayout(self)
        main_layout.addWidget(self.tabs)

        self._setup_register_tab()
        self._setup_history_tab()

    # ------------------- Register Tab -------------------

    def _setup_register_tab(self):
        name_lbl = QLabel("原料名:")
        self.name_edit = QLineEdit()

        loc_lbl = QLabel("保管場所:")
        self.loc_combo = QComboBox()
        self.loc_combo.addItems(["冷蔵庫", "冷凍庫", "常温棚"])

        self.code_lbl = QLabel("管理番号: -")
        self.qr_display = QLabel(alignment=Qt.AlignmentFlag.AlignCenter)
        self.qr_display.setFixedSize(200, 200)

        gen_btn = QPushButton("QR生成")
        gen_btn.clicked.connect(self.generate_qr)

        save_btn = QPushButton("登録")
        save_btn.clicked.connect(self.save_reagent)

        lay = QVBoxLayout(self.register_tab)
        form1 = QHBoxLayout()
        form1.addWidget(name_lbl)
        form1.addWidget(self.name_edit)
        lay.addLayout(form1)

        form2 = QHBoxLayout()
        form2.addWidget(loc_lbl)
        form2.addWidget(self.loc_combo)
        lay.addLayout(form2)

        lay.addWidget(self.code_lbl)
        lay.addWidget(self.qr_display)
        btns = QHBoxLayout()
        btns.addWidget(gen_btn)
        btns.addWidget(save_btn)
        lay.addLayout(btns)
        lay.addStretch()

    def generate_qr(self):
        self.current_code = generate_code()
        self.code_lbl.setText(f"管理番号: {self.current_code}")

        qr = qrcode.QRCode(box_size=4, border=2)
        qr.add_data(f"管理番号:{self.current_code}")
        qr.make(fit=True)
        img = qr.make_image(fill_color="black", back_color="white").convert("RGB")

        buf = io.BytesIO()
        img.save(buf, format="PNG")
        self.current_qr_bytes = buf.getvalue()

        qimg = QImage.fromData(self.current_qr_bytes)
        pix = QPixmap.fromImage(qimg)
        self.qr_display.setPixmap(pix.scaled(self.qr_display.size(), Qt.AspectRatioMode.KeepAspectRatio,
                                             Qt.TransformationMode.SmoothTransformation))

    def save_reagent(self):
        name = self.name_edit.text().strip()
        location = self.loc_combo.currentText()
        if not name or not self.current_code:
            QMessageBox.warning(self, "入力不足", "原料名とQR生成を完了してください。")
            return
        conn = sqlite3.connect(DB_NAME)
        c = conn.cursor()
        try:
            c.execute("INSERT INTO reagents (name, code, location, qr_image) VALUES (?,?,?,?)",
                      (name, self.current_code, location, self.current_qr_bytes))
            conn.commit()
            QMessageBox.information(self, "登録完了", "登録が完了しました。")
            self.name_edit.clear()
            self.code_lbl.setText("管理番号: -")
            self.qr_display.clear()
            self.current_code = None
            self.current_qr_bytes = None
        except sqlite3.IntegrityError:
            QMessageBox.warning(self, "重複", "この管理番号は既に存在します。")
        finally:
            conn.close()

    # ------------------- History Tab -------------------

    def _setup_history_tab(self):
        search_lbl = QLabel("管理番号:")
        self.search_edit = QLineEdit()
        search_btn = QPushButton("検索")
        search_btn.clicked.connect(lambda: self.search_history_by_code(self.search_edit.text().strip()))

        qr_btn = QPushButton("QRコードから検索")
        qr_btn.clicked.connect(self.search_by_qr)

        top = QHBoxLayout()
        top.addWidget(search_lbl)
        top.addWidget(self.search_edit)
        top.addWidget(search_btn)
        top.addWidget(qr_btn)

        self.table = QTableWidget(0, 4)
        self.table.setHorizontalHeaderLabels(["id", "管理番号", "使用者", "使用日"])

        lay = QVBoxLayout(self.history_tab)
        lay.addLayout(top)
        lay.addWidget(self.table)
        lay.addStretch()

        self.populate_history_table()

    def populate_history_table(self, code=None):
        """履歴テーブルを（フィルタ付きで）再描画"""
        conn = sqlite3.connect(DB_NAME)
        c = conn.cursor()
        if code:
            c.execute(
                "SELECT id, reagent_code, user, used_date "
                "FROM usage_history WHERE reagent_code=? "
                "ORDER BY used_date DESC",
                (code,)
            )
        else:
            c.execute(
                "SELECT id, reagent_code, user, used_date "
                "FROM usage_history ORDER BY used_date DESC"
            )
        rows = c.fetchall()
        conn.close()

        self.table.setRowCount(len(rows))
        for r, row in enumerate(rows):
            for c_idx, val in enumerate(row):
                self.table.setItem(r, c_idx, QTableWidgetItem(str(val)))

    def search_history_by_code(self, code):
        code = code.strip()
        if not code:
            QMessageBox.warning(self, "入力不足", "管理番号を入力してください。")
            return
        self.populate_history_table(code)

        def search_by_qr(self):
        """カメラプレビューを表示し、QR が1枚読み取れたら履歴検索に反映"""
        try:
            dlg = QRCameraDialog(self)
        except RuntimeError as err:
            QMessageBox.warning(self, "カメラエラー", str(err))
            return

        if dlg.exec() == QDialog.DialogCode.Accepted and dlg.qr_payload:
            payload = dlg.qr_payload or ""
            for line in payload.split("
"):
                if line.startswith("管理番号"):
                    code = line.split(":", 1)[-1].strip()
                    self.search_history_by_code(code)
                    return
            QMessageBox.information(self, "QR読取", "管理番号を含む QR ではありませんでした。")

    # ------------------- アプリ起動 -------------------

# ------------------- アプリ起動 -------------------

if __name__ == "__main__":
    init_db()
    app = QApplication(sys.argv)
    win = ReagentManager()
    win.show()
    sys.exit(app.exec())
