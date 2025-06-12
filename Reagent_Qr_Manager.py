import sys
import os
import io
import sqlite3
from datetime import datetime

from PyQt6.QtWidgets import (
    QApplication, QWidget, QLabel, QPushButton, QLineEdit, QVBoxLayout,
    QHBoxLayout, QTabWidget, QTableWidget, QTableWidgetItem, QMessageBox,
    QComboBox, QDialog, QVBoxLayout
)
from PyQt6.QtGui import QPixmap, QImage
from PyQt6.QtCore import Qt, QTimer

import qrcode
import cv2
from pyzbar.pyzbar import decode

DB_NAME = "reagents.db"

# ------------------- DB 初期化 -------------------

def init_db() -> None:
    """SQLite DB がなければテーブルを作成"""
    conn = sqlite3.connect(DB_NAME)
    c = conn.cursor()
    c.execute(
        """CREATE TABLE IF NOT EXISTS reagents (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                name TEXT,
                code TEXT UNIQUE,
                location TEXT,
                qr_image BLOB
        )"""
    )
    c.execute(
        """CREATE TABLE IF NOT EXISTS usage_history (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                reagent_code TEXT,
                user TEXT,
                used_date TEXT
        )"""
    )
    conn.commit()
    conn.close()


def generate_code() -> str:
    """YYYYMMDD-001 形式の連番コードを生成"""
    today = datetime.now().strftime("%Y%m%d")
    conn = sqlite3.connect(DB_NAME)
    c = conn.cursor()
    c.execute("SELECT COUNT(*) FROM reagents WHERE code LIKE ?", (f"{today}%",))
    count = c.fetchone()[0] + 1
    conn.close()
    return f"{today}-{count:03d}"

# ------------------- QR カメラダイアログ -------------------

class QRCameraDialog(QDialog):
    """ライブ映像を表示し、QR を 1 枚読み取ったら閉じるダイアログ"""

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.setWindowTitle("QRコード読み取り (Esc でキャンセル)")
        self.resize(640, 480)

        self.label = QLabel(alignment=Qt.AlignmentFlag.AlignCenter)
        layout = QVBoxLayout(self)
        layout.addWidget(self.label)

        # カメラ初期化
        self.cap = cv2.VideoCapture(0, cv2.CAP_DSHOW)
        if not self.cap.isOpened():
            raise RuntimeError("カメラを開けませんでした")

        self.qr_payload: str | None = None
        self.timer = QTimer(self)
        self.timer.timeout.connect(self._next_frame)
        self.timer.start(30)  # 30 fps

    def _next_frame(self) -> None:
        ret, frame = self.cap.read()
        if not ret:
            return
        rgb = cv2.cvtColor(frame, cv2.COLOR_BGR2RGB)
        h, w, ch = rgb.shape
        qimg = QImage(rgb.data, w, h, ch * w, QImage.Format.Format_RGB888)
        self.label.setPixmap(
            QPixmap.fromImage(qimg).scaled(
                self.label.size(), Qt.AspectRatioMode.KeepAspectRatio, Qt.TransformationMode.SmoothTransformation
            )
        )

        decoded = decode(frame)
        if decoded:
            self.qr_payload = decoded[0].data.decode("utf-8")
            self.accept()

    # Esc キーでキャンセル
    def keyPressEvent(self, event):
        if event.key() == Qt.Key.Key_Escape:
            self.reject()
        else:
            super().keyPressEvent(event)

    def closeEvent(self, event):
        if self.cap.isOpened():
            self.cap.release()
        self.timer.stop()
        super().closeEvent(event)

# ------------------- メインウィジェット -------------------

class ReagentManager(QWidget):
    def __init__(self) -> None:
        super().__init__()
        self.setWindowTitle("Reagent QR Manager")
        self.resize(900, 600)

        self.current_code: str | None = None
        self.current_qr_bytes: bytes | None = None

        # タブ
        self.tabs = QTabWidget()
        self.register_tab = QWidget()
        self.history_tab = QWidget()
        self.tabs.addTab(self.register_tab, "原料登録")
        self.tabs.addTab(self.history_tab, "使用履歴検索")

        main_layout = QVBoxLayout(self)
        main_layout.addWidget(self.tabs)

        self._setup_register_tab()
        self._setup_history_tab()

    # ------- 原料登録タブ -------
    def _setup_register_tab(self) -> None:
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

    def generate_qr(self) -> None:
        """管理番号を生成し、QR をプレビュー"""
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
        self.qr_display.setPixmap(
            pix.scaled(self.qr_display.size(), Qt.AspectRatioMode.KeepAspectRatio, Qt.TransformationMode.SmoothTransformation)
        )

    def save_reagent(self) -> None:
        name = self.name_edit.text().strip()
        location = self.loc_combo.currentText()
        if not name or not self.current_code:
            QMessageBox.warning(self, "入力不足", "原料名の入力と QR 生成をしてください。")
            return

        conn = sqlite3.connect(DB_NAME)
        c = conn.cursor()
        try:
            c.execute(
                "INSERT INTO reagents (name, code, location, qr_image) VALUES (?,?,?,?)",
                (name, self.current_code, location, self.current_qr_bytes),
            )
            conn.commit()
            QMessageBox.information(self, "登録完了", "原料を登録しました。")
            # フォームリセット
            self.name_edit.clear()
            self.code_lbl.setText("管理番号: -")
            self.qr_display.clear()
            self.current_code = None
            self.current_qr_bytes = None
        except sqlite3.IntegrityError:
            QMessageBox.warning(self, "重複", "同じ管理番号が既に存在します。")
        finally:
            conn.close()

    # ------- 履歴検索タブ -------
    def _setup_history_tab(self) -> None:
        search_lbl = QLabel("管理番号:")
        self.search_edit = QLineEdit()
        search_btn = QPushButton("検索")
        search_btn.clicked.connect(lambda: self.search_history_by_code(self.search_edit.text().strip()))

        qr_btn = QPushButton("QRコードから検索")
        qr_btn.clicked.connect(self.search_by_qr)

        top = QHBoxLayout()
        top.addWidget(search_lbl)
        top.addWidget(self.search_edit)
        top.addWidget(search
