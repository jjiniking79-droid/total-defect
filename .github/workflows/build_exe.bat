@echo off
REM ========================================================
REM TFT LCD 불량 자동 분석 프로그램 - exe 빌드 스크립트
REM Windows PC에서 실행하세요 (Python 3.10~3.11 권장)
REM ========================================================

echo [1/3] 가상환경 생성...
python -m venv venv
call venv\Scripts\activate.bat

echo [2/3] 패키지 설치...
pip install --upgrade pip
pip install -r requirements.txt

echo [3/3] exe 빌드...
pyinstaller --noconfirm --onefile --windowed ^
  --name TFT_LCD_Inspector ^
  --collect-all sklearn ^
  --collect-all cv2 ^
  main.py

echo.
echo 완료! dist\TFT_LCD_Inspector.exe 파일을 확인하세요.
pause
