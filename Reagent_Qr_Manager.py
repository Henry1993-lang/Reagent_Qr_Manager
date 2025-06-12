"""
Reagent_Qr_Manager.py — self‑contained, executable PyQt6 app
* 原料登録（QR 生成 & DB 保存）
* 使用履歴検索（管理番号入力 or QR カメラ読取）
SQLite3 + PyInstaller 対応（--collect-all pyzbar / --collect-binaries cv2）
"""

from __future__ import annotations

import io
import os
import sqlite3
import sys
from datetime import datetime

import cv2
import qrcode
from PyQt6.QtCore import Qt, QTimer
from PyQt6.QtGui import QImage, QPixmap
from PyQt6.QtWidgets import (
    QApplication,
    QComboBox,
    QDialog,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QMessageBox,
    QPushButton,
    QTabWidget,
    QTableWidget,
    QTableWidgetItem,
    QVBoxLayout,
    QWidget,
)
from pyzbar.pyzbar import decode

DB_NAME = "reagents.db"

# ------------------- DB utils -------------------

def init_db() -> None:
    conn = sqlite3.connect(DB_NAME)
    cur = conn.cursor()
    cur.execute(
        """CREATE TABLE IF NOT EXISTS reagents (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            name TEXT,
            code TEXT UNIQUE,
            location TEXT,
            qr_image BLOB)"""
    )
    cur.execute(
        """CREATE TABLE IF NOT EXISTS usage_history (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            reagent_code TEXT,
            user TEXT,
            used_date TEXT)"""
    )
    conn.commit()
    conn.close()


def generate_code() -> str:
    today = datetime.now().strftime("%Y%m%d")
    conn = sqlite3.connect(DB_NAME)
    cur = conn.cursor()
    cur.execute("SELECT COUNT(*) FROM reagents WHERE code LIKE ?", (f"{today}%",))
    count = cur.fetchone()[0] + 1
    conn.close()
    return f"{today}-{count:03d}"

# ------------------- Camera dialog -------------------


class QRCameraDialog(QDialog):
    """Show live camera; auto‑close when 1 QR detected."""

    def __init__(self, parent: QWidget | None = None):
        super().__init__(parent)
        self.setWindowTitle("QR 読み取り (Esc でキャンセル)")
        self.resize(640, 480)

        self.label = QLabel(alignment=Qt.AlignmentFlag.AlignCenter)
        lay = QVBoxLayout(self)
        lay.addWidget(self.label)

        self.cap = cv2.VideoCapture(0, cv2.CAP_DSHOW)
        if not self.cap.isOpened():
            raise RuntimeError("カメラを開けませんでした")

        self.qr_payload: str | None = None
        self.timer = QTimer(self, interval=30)
        self.timer.timeout.connect(self._next)
        self.timer.start()

    def _next(self) -> None:
        ret, frame = self.cap.read()
        if not ret:
            return
        rgb = cv2.cvtColor(frame, cv2.COLOR_BGR2RGB)
        h, w, ch = rgb.shape
        qimg = QImage(rgb.data, w, h, ch * w, QImage.Format.Format_RGB888)
        self.label.setPixmap(QPixmap.fromImage(qimg).scaled(self.label.size(), Qt.AspectRatioMode.KeepAspectRatio))

        dec = decode(frame)
        if dec:
            self.qr_payload = dec[0].data.decode()
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

# ------------------- Main widget -------------------


class ReagentManager(QWidget):
    def __init__(self):
        super().__init__()
        self.setWindowTitle("Reagent QR Manager")
        self.resize(900, 600)

        self.current_code: str | None = None
        self.current_qr: bytes | None = None

        self.tabs = QTabWidget()
        self.register_tab = QWidget()
        self.history_tab = QWidget()
        self.tabs.addTab(self.register_tab, "原料登録")
        self.tabs.addTab(self.history_tab, "履歴検索")

        root = QVBoxLayout(self)
        root.addWidget(self.tabs)

        self._setup_register_tab()
        self._setup_history_tab()

    # ----- Register tab -----
    def _setup_register_tab(self) -> None:
        name_lbl = QLabel("原料名:")
        self.name_edit = QLineEdit()

        loc_lbl = QLabel("保管場所:")
        self.loc_combo = QComboBox()
        self.loc_combo.addItems(["冷蔵庫", "冷凍庫", "常温棚"])

        self.code_lbl = QLabel("管理番号: -")
        self.qr_preview = QLabel(alignment=Qt.AlignmentFlag.AlignCenter)
        self.qr_preview.setFixedSize(200, 200)

        gen_btn = QPushButton("QR生成", clicked=self.generate_qr)
        save_btn = QPushButton("登録", clicked=self.save_reagent)

        lay = QVBoxLayout(self.register_tab)
        f1 = QHBoxLayout(); f1.addWidget(name_lbl); f1.addWidget(self.name_edit)
        f2 = QHBoxLayout(); f2.addWidget(loc_lbl); f2.addWidget(self.loc_combo)
        btns = QHBoxLayout(); btns.addWidget(gen_btn); btns.addWidget(save_btn)
        for w in (f1, f2): lay.addLayout(w)
        lay.addWidget(self.code_lbl)
        lay.addWidget(self.qr_preview)
        lay.addLayout(btns); lay.addStretch()

    def generate_qr(self) -> None:
        self.current_code = generate_code()
        self.code_lbl.setText(f"管理番号: {self.current_code}")
        qr = qrcode.make(f"管理番号:{self.current_code}")
        buf = io.BytesIO(); qr.save(buf, format="PNG")
        self.current_qr = buf.getvalue()
        pix = QPixmap.fromImage(QImage.fromData(self.current_qr))
        self.qr_preview.setPixmap(pix.scaled(self.qr_preview.size(), Qt.AspectRatioMode.KeepAspectRatio))

    def save_reagent(self) -> None:
        name = self.name_edit.text().strip()
        if not name or not self.current_code:
            QMessageBox.warning(self, "入力不足", "原料名を入力し QR を生成してください。")
            return
        conn = sqlite3.connect(DB_NAME)
        cur = conn.cursor()
        try:
            cur.execute(
                "INSERT INTO reagents (name, code, location, qr_image) VALUES (?,?,?,?)",
                (name, self.current_code, self.loc_combo.currentText(), self.current_qr),
            )
            conn.commit()
            QMessageBox.information(self, "登録完了", "原料を登録しました。")
            # reset
            self.name_edit.clear(); self.code_lbl.setText("管理番号: -"); self.qr_preview.clear()
            self.current_code = None; self.current_qr = None
        except sqlite3.IntegrityError:
            QMessageBox.warning(self, "重複", "同じ管理番号が存在します。")
        finally:
            conn.close()

    # ----- History tab -----
    def _setup_history_tab(self) -> None:
        self.search_edit = QLineEdit()
        search_btn = QPushButton("検索", clicked=lambda: self.search_history_by_code(self.search_edit.text()))
        qr_btn = QPushButton("QRコードから検索", clicked=self.search_by_qr)

        top = QHBoxLayout(); top.addWidget(QLabel("管理番号:")); top.addWidget(self.search_edit); top.addWidget(search_btn); top.addWidget(qr_btn)
        self.table = QTableWidget(0, 4)
        self.table.setHorizontalHeaderLabels(["id", "管理番号", "使用者", "使用日"])

        lay = QVBoxLayout(self.history_tab); lay.addLayout(top); lay.addWidget(self.table)
        self.populate_history_table()

    def populate_history_table(self, code: str | None = None) -> None:
        conn = sqlite3.connect(DB_NAME)
        cur = conn.cursor()
        if code:
            cur.execute("SELECT id, reagent_code, user, used_date FROM usage_history WHERE reagent_code=? ORDER BY used_date DESC", (code,))
        else:
            cur.execute("SELECT id, reagent_code, user, used_date FROM usage_history ORDER BY used_date DESC")
        rows = cur.fetchall(); conn.close()
        self.table.setRowCount(len(rows))
        for r, row in enumerate(rows):
            for c, val in enumerate(row):
                self.table.setItem(r, c, QTableWidgetItem(str(val)))

    def search_history_by_code(self, code: str) -> None:
        self.populate_history_table(code.strip())

    def search_by_qr(self) -> None:
        """Open camera dialog, read 1 QR, then filter history."""
        try:
            dlg = QRCameraDialog(self)
        except RuntimeError as e:
            QMessageBox.warning(self, "カメラエラー", str(e))
            return

        if dlg.exec() == QDialog.DialogCode.Accepted and dlg.qr_payload:
            for line in dlg.qr_payload.splitlines():
                if line.startswith("管理番号"):
                    self.search_history_by_code(line.split(":", 1)[-1].strip())
                    return
            QMessageBox.information(self, "QR読取", "管理番号を含む QR ではありませんでした。")

# ------------------- main -------------------

if __name__ == "__main__":
    init_db()

    app = QApplication(sys.argv)
    win = ReagentManager()
    win.show()

    sys.exit(app.exec())
