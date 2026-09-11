# -*- coding: utf-8 -*-
"""
프로그램 설정(작업자 지정 컬럼 제목, 불량코드 목록, 마지막 모델 경로 등)을
JSON 파일로 저장/로드한다. exe로 패키징했을 때도 실행 파일 옆에 저장되도록
사용자 홈 디렉토리 하위에 저장한다.
"""
import os
import json
import sys

APP_DIR_NAME = "TFT_LCD_Inspector"


def _config_dir():
    if sys.platform.startswith("win"):
        base = os.environ.get("APPDATA", os.path.expanduser("~"))
    else:
        base = os.path.expanduser("~/.config")
    path = os.path.join(base, APP_DIR_NAME)
    os.makedirs(path, exist_ok=True)
    return path


def _config_path():
    return os.path.join(_config_dir(), "settings.json")


DEFAULT_SETTINGS = {
    "column_headers": {},      # {"col_3": "LOT번호", ...} 컬럼 위치별 사용자 지정 제목
    "visible_columns": {},     # {"col_3": true/false, ...}
    "defect_codes": [],        # 사용자가 등록한 불량코드 목록
    "good_folder_name": "양품",
    "last_model_path": "",
    "last_train_dir": "",
    "last_inspect_dir": "",
    "confidence_threshold": 60,
}


def load_settings():
    path = _config_path()
    if os.path.exists(path):
        try:
            with open(path, "r", encoding="utf-8") as f:
                data = json.load(f)
            merged = dict(DEFAULT_SETTINGS)
            merged.update(data)
            return merged
        except Exception:
            return dict(DEFAULT_SETTINGS)
    return dict(DEFAULT_SETTINGS)


def save_settings(settings: dict):
    path = _config_path()
    with open(path, "w", encoding="utf-8") as f:
        json.dump(settings, f, ensure_ascii=False, indent=2)
