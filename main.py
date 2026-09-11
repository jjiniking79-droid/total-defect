# -*- coding: utf-8 -*-
"""
TFT LCD 불량 자동 분석 프로그램
실행: python main.py
exe 빌드: build_exe.bat 참고 (Windows에서 PyInstaller 필요)
"""
import sys
from PyQt5.QtWidgets import QApplication
from ui.main_window import MainWindow


def main():
    app = QApplication(sys.argv)
    app.setStyle("Fusion")
    win = MainWindow()
    win.show()
    sys.exit(app.exec_())


if __name__ == "__main__":
    main()
