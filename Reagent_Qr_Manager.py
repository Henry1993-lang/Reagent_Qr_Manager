import sys
import os
import sqlite3
from datetime import datetime
from PyQt6.QtWidgets import (
    QApplication, QWidget, QLabel, QPushButton, QLineEdit, QVBoxLayout, QHBoxLayout,
    QFileDialog, QMessageBox, QListWidget, QComboBox, QTabWidget, QTableWidget,
    QTableWidgetItem, QDialog, QDialogButtonBox, QCalendarWidget, QInputDialog
)
from PyQt6.QtGui import QPixmap
from PyQt6.QtCore import Qt
import qrcode
import cv2
from pyzbar.pyzbar import decode
from PyQt6.QtWidgets import QInputDialog


DB_NAME = "reagents.db"

# ------------------- Database Setup -------------------
def init_db():
    conn = sqlite3.connect(DB_NAME)
    c = conn.cursor()
    c.execute('''CREATE TABLE IF NOT EXISTS reagents (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    name TEXT,
                    code TEXT UNIQUE,
                    location TEXT,
                    qr_path TEXT)''')
    c.execute('''CREATE TABLE IF NOT EXISTS usage_history (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    reagent_code TEXT,
                    user TEXT,
                    used_date TEXT,
                    FOREIGN KEY(reagent_code) REFERENCES reagents(code))''')
    c.execute('''CREATE TABLE IF NOT EXISTS users (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    name TEXT UNIQUE)''')
    conn.commit()
    conn.close()

# ------------------- Helper Functions -------------------
def generate_code():
    today = datetime.now().strftime("%Y%m%d")
    conn = sqlite3.connect(DB_NAME)
    c = conn.cursor()
    c.execute("SELECT COUNT(*) FROM reagents WHERE code LIKE ?", (f"REAG-{today}-%",))
    count = c.fetchone()[0] + 1
    conn.close()
    return f"REAG-{today}-{count:03}"

# ------------------- Main Window -------------------
class ReagentManager(QWidget):
    def __init__(self):
        super().__init__()
        self.setWindowTitle("有機合成原料 管理システム")
        self.resize(800, 600)
        self.tabs = QTabWidget()

        self.init_register_tab()
        self.init_usage_tab()
        self.init_history_tab()

        layout = QVBoxLayout()
        layout.addWidget(self.tabs)
        self.setLayout(layout)

    # Register Tab
    def init_register_tab(self):
        tab = QWidget()
        layout = QVBoxLayout()

        self.name_input = QLineEdit()
        self.code_label = QLabel(generate_code())
        self.location_input = QComboBox()
        self.location_input.addItems(["冷蔵庫", "冷凍庫"])
        self.qr_label = QLabel("QRコードがここに表示されます")
        self.qr_label.setAlignment(Qt.AlignmentFlag.AlignCenter)

        save_btn = QPushButton("QRコード生成＆保存")
        save_btn.clicked.connect(self.generate_and_save_qr)

        layout.addWidget(QLabel("原料名:"))
        layout.addWidget(self.name_input)
        layout.addWidget(QLabel("管理番号:"))
        layout.addWidget(self.code_label)
        layout.addWidget(QLabel("保管場所:"))
        layout.addWidget(self.location_input)
        layout.addWidget(self.qr_label)
        layout.addWidget(save_btn)
        tab.setLayout(layout)

        self.tabs.addTab(tab, "原料登録")

    # Usage Tab
    def init_usage_tab(self):
        tab = QWidget()
        layout = QVBoxLayout()

        self.reagent_name_select = QComboBox()
        self.refresh_reagent_names()

        self.user_select = QComboBox()
        self.user_select.setEditable(True)
        self.refresh_user_list()

        usage_btn = QPushButton("使用登録")
        usage_btn.clicked.connect(self.save_usage)

        self.calendar = QCalendarWidget()
        self.calendar.setGridVisible(True)

        layout.addWidget(QLabel("原料名:"))
        layout.addWidget(self.reagent_name_select)
        layout.addWidget(QLabel("使用者:"))
        layout.addWidget(self.user_select)
        layout.addWidget(QLabel("使用日:"))
        layout.addWidget(self.calendar)
        layout.addWidget(usage_btn)
        tab.setLayout(layout)

        self.tabs.addTab(tab, "使用記録登録")

    # History Tab
    def init_history_tab(self):
        tab = QWidget()
        layout = QVBoxLayout()

        self.search_input = QLineEdit()
        search_btn = QPushButton("検索（原料名）")
        search_btn.clicked.connect(self.search_history_by_name)
        scan_btn = QPushButton("QRコードから検索")
        scan_btn.clicked.connect(self.search_by_qr)
        self.history_table = QTableWidget(0, 3)
        self.history_table.setHorizontalHeaderLabels(["原料名", "使用者", "使用日"])

        layout.addWidget(self.search_input)
        layout.addWidget(search_btn)
        layout.addWidget(scan_btn)
        layout.addWidget(self.history_table)
        tab.setLayout(layout)

        self.tabs.addTab(tab, "使用履歴表示")

    def generate_and_save_qr(self):
        name = self.name_input.text()
        code = self.code_label.text()
        location = self.location_input.currentText()
        if not name:
            QMessageBox.warning(self, "入力エラー", "原料名を入力してください。")
            return
        text = f"原料名: {name}\n管理番号: {code}\n保管場所: {location}"
        qr = qrcode.make(text)

        filepath, _ = QFileDialog.getSaveFileName(self, "QRコードの保存", f"{code}.png", "PNG Files (*.png)")
        if filepath:
            qr.save(filepath)
            self.qr_label.setPixmap(QPixmap(filepath).scaled(200, 200, Qt.AspectRatioMode.KeepAspectRatio))
            conn = sqlite3.connect(DB_NAME)
            c = conn.cursor()
            try:
                c.execute("INSERT INTO reagents (name, code, location, qr_path) VALUES (?, ?, ?, ?)",
                          (name, code, location, filepath))
                conn.commit()
                QMessageBox.information(self, "保存完了", "登録が完了しました。")
                self.code_label.setText(generate_code())
                self.refresh_reagent_names()
            except sqlite3.IntegrityError:
                QMessageBox.warning(self, "保存エラー", "管理番号が重複しています。")
            finally:
                conn.close()

    def save_usage(self):
        name = self.reagent_name_select.currentText()
        user = self.user_select.currentText()
        date = self.calendar.selectedDate().toString("yyyy-MM-dd")
        conn = sqlite3.connect(DB_NAME)
        c = conn.cursor()
        c.execute("SELECT code FROM reagents WHERE name=?", (name,))
        result = c.fetchone()
        if not result:
            QMessageBox.warning(self, "原料エラー", "指定された原料名は登録されていません。")
            return
        code = result[0]
        try:
            c.execute("INSERT INTO usage_history (reagent_code, user, used_date) VALUES (?, ?, ?)", (code, user, date))
            c.execute("INSERT OR IGNORE INTO users (name) VALUES (?)", (user,))
            conn.commit()
            QMessageBox.information(self, "保存完了", "使用履歴を登録しました。")
        finally:
            conn.close()
            self.refresh_user_list()

    def refresh_reagent_names(self):
        self.reagent_name_select.clear()
        conn = sqlite3.connect(DB_NAME)
        c = conn.cursor()
        c.execute("SELECT name FROM reagents")
        self.reagent_name_select.addItems([row[0] for row in c.fetchall()])
        conn.close()

    def refresh_user_list(self):
        self.user_select.clear()
        conn = sqlite3.connect(DB_NAME)
        c = conn.cursor()
        c.execute("SELECT name FROM users")
        self.user_select.addItems([row[0] for row in c.fetchall()])
        conn.close()

    def search_history_by_name(self):
        keyword = self.search_input.text()
        conn = sqlite3.connect(DB_NAME)
        c = conn.cursor()
        c.execute('''SELECT r.name, u.user, u.used_date FROM usage_history u
                     JOIN reagents r ON u.reagent_code = r.code
                     WHERE r.name LIKE ?''', (f"%{keyword}%",))
        results = c.fetchall()
        self.populate_history_table(results)
        conn.close()

    def search_by_qr(self):
        cap = cv2.VideoCapture(0)
        ret, frame = cap.read()
        cap.release()
        if not ret:
            QMessageBox.warning(self, "エラー", "カメラから画像を取得できませんでした。")
            return
        decoded = decode(frame)
        for obj in decoded:
            data = obj.data.decode("utf-8")
            for line in data.split('\n'):
                if line.startswith("管理番号"):
                    code = line.split(":")[-1].strip()
                    self.search_history_by_code(code)
                    return

    def search_history_by_code(self, code):
        conn = sqlite3.connect(DB_NAME)
        c = conn.cursor()
        c.execute("SELECT r.name, u.user, u.used_date FROM usage_history u JOIN reagents r ON u.reagent_code = r.code WHERE u.reagent_code=?", (code,))
        results = c.fetchall()
        self.populate_history_table(results)
        conn.close()

    def populate_history_table(self, rows):
        self.history_table.setRowCount(0)
        for row in rows:
            row_pos = self.history_table.rowCount()
            self.history_table.insertRow(row_pos)
            for col, val in enumerate(row):
                self.history_table.setItem(row_pos, col, QTableWidgetItem(val))

if __name__ == '__main__':
    init_db()
    app = QApplication(sys.argv)
    win = ReagentManager()
    win.show()
    sys.exit(app.exec())
