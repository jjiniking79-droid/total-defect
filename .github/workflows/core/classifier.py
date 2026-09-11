# -*- coding: utf-8 -*-
"""
DefectClassifier
-----------------
학습 폴더 구조 (작업자가 준비):

    학습폴더/
        양품/              <- 이 이름(good_folder_name)의 폴더 = 양품(OK) 이미지
            img1.jpg
            img2.jpg
        스크래치/          <- 그 외 폴더명 = 불량 코드 (작업자가 자유롭게 명명)
            img3.jpg
        이물/
            img4.jpg
        ...

동작:
  1) 1차: 양품/불량(OK/NG) 이진 분류 (RandomForest, class_weight='balanced')
  2) 2차: NG로 분류된 경우, 불량코드 다중 분류 (하위폴더명을 그대로 코드로 사용)
     - 불량코드가 1개뿐이면 별도 모델 없이 그 코드를 그대로 부여
  3) 학습 시 holdout(20%)으로 정확도를 검증하여 리포트 반환, 최종 모델은 전체 데이터로 재학습
"""
import os
import glob
import json
import numpy as np
import joblib
from sklearn.ensemble import RandomForestClassifier
from sklearn.model_selection import train_test_split
from sklearn.metrics import accuracy_score, f1_score

from .feature_extractor import extract_features

IMAGE_EXTS = (".jpg", ".jpeg", ".png", ".bmp", ".tif", ".tiff")

OK_LABEL = "양품"
NG_LABEL = "불량"


def _list_images(folder):
    files = []
    for ext in IMAGE_EXTS:
        files.extend(glob.glob(os.path.join(folder, f"*{ext}")))
        files.extend(glob.glob(os.path.join(folder, f"*{ext.upper()}")))
    return sorted(set(files))


class DefectClassifier:
    def __init__(self):
        self.bin_clf = None          # 양품/불량 이진 분류기
        self.code_clf = None         # 불량코드 다중 분류기 (코드가 2개 이상일 때만 존재)
        self.defect_codes = []       # 학습에 사용된 불량코드 목록
        self.single_code = None      # 불량코드가 1개뿐일 때 사용
        self.good_folder_name = OK_LABEL
        self.confidence_threshold = 0.60  # 이 값 미만이면 "재검토 필요" 플래그

    # ------------------------------------------------------------------
    def train(self, root_dir, good_folder_name=OK_LABEL, progress_callback=None):
        """학습 폴더를 읽어 모델을 학습한다. progress_callback(current, total, msg)"""
        self.good_folder_name = good_folder_name
        subfolders = [f for f in sorted(os.listdir(root_dir))
                      if os.path.isdir(os.path.join(root_dir, f))]
        if good_folder_name not in subfolders:
            raise ValueError(
                f"'{good_folder_name}' 폴더를 찾을 수 없습니다. 학습 폴더 안에 "
                f"양품 폴더와 불량코드별 폴더를 만들어 주세요."
            )

        defect_folders = [f for f in subfolders if f != good_folder_name]
        if len(defect_folders) == 0:
            raise ValueError("불량 코드 폴더가 하나도 없습니다. 불량 유형별로 폴더를 나눠주세요.")

        X, y_bin, y_code = [], [], []
        all_files = []
        for f in subfolders:
            imgs = _list_images(os.path.join(root_dir, f))
            for p in imgs:
                all_files.append((p, f))

        total = len(all_files)
        if total < 10:
            raise ValueError("학습 이미지 수가 너무 적습니다 (최소 10장 이상, 양품/불량 각 폴더 권장 20장 이상).")

        for i, (path, folder) in enumerate(all_files):
            try:
                feat = extract_features(path)
            except Exception:
                continue
            X.append(feat)
            if folder == good_folder_name:
                y_bin.append(OK_LABEL)
                y_code.append(None)
            else:
                y_bin.append(NG_LABEL)
                y_code.append(folder)
            if progress_callback:
                progress_callback(i + 1, total, f"특징 추출 중... {os.path.basename(path)}")

        X = np.array(X)
        y_bin = np.array(y_bin)

        # ---- 1) 이진 분류기 학습 + 검증 ----
        Xtr, Xte, ytr, yte = train_test_split(
            X, y_bin, test_size=0.2, random_state=42,
            stratify=y_bin if len(set(y_bin)) > 1 else None
        )
        bin_clf_val = RandomForestClassifier(
            n_estimators=300, class_weight="balanced", random_state=42, n_jobs=-1
        )
        bin_clf_val.fit(Xtr, ytr)
        pred = bin_clf_val.predict(Xte)
        bin_acc = accuracy_score(yte, pred)
        bin_f1 = f1_score(yte, pred, pos_label=NG_LABEL)

        # 최종 모델은 전체 데이터로 재학습
        self.bin_clf = RandomForestClassifier(
            n_estimators=300, class_weight="balanced", random_state=42, n_jobs=-1
        )
        self.bin_clf.fit(X, y_bin)

        # ---- 2) 불량코드 다중 분류기 학습 ----
        ng_idx = [i for i, v in enumerate(y_bin) if v == NG_LABEL]
        X_ng = X[ng_idx]
        y_code_ng = [y_code[i] for i in ng_idx]
        self.defect_codes = sorted(set(y_code_ng))

        code_acc = None
        if len(self.defect_codes) >= 2:
            Xtr2, Xte2, ytr2, yte2 = train_test_split(
                X_ng, y_code_ng, test_size=0.2, random_state=42, stratify=y_code_ng
            )
            code_clf_val = RandomForestClassifier(
                n_estimators=300, random_state=42, n_jobs=-1
            )
            code_clf_val.fit(Xtr2, ytr2)
            code_acc = accuracy_score(yte2, code_clf_val.predict(Xte2))

            self.code_clf = RandomForestClassifier(n_estimators=300, random_state=42, n_jobs=-1)
            self.code_clf.fit(X_ng, y_code_ng)
            self.single_code = None
        else:
            self.code_clf = None
            self.single_code = self.defect_codes[0] if self.defect_codes else None

        report = {
            "총 학습 이미지 수": total,
            "양품/불량 판정 정확도(holdout)": round(bin_acc * 100, 2),
            "불량 F1-score": round(bin_f1, 3),
            "불량코드 판정 정확도(holdout)": round(code_acc * 100, 2) if code_acc is not None else "코드 1종 (분류 불필요)",
            "불량코드 목록": self.defect_codes,
        }
        return report

    # ------------------------------------------------------------------
    def predict(self, image_path):
        """반환: dict(label, defect_code, confidence, need_review)"""
        if self.bin_clf is None:
            raise RuntimeError("모델이 학습/로드되지 않았습니다.")

        feat = extract_features(image_path).reshape(1, -1)
        proba = self.bin_clf.predict_proba(feat)[0]
        classes = list(self.bin_clf.classes_)
        ng_prob = proba[classes.index(NG_LABEL)] if NG_LABEL in classes else 0.0
        label = NG_LABEL if ng_prob >= 0.5 else OK_LABEL
        confidence = ng_prob if label == NG_LABEL else (1 - ng_prob)

        defect_code = None
        if label == NG_LABEL:
            if self.code_clf is not None:
                code_proba = self.code_clf.predict_proba(feat)[0]
                code_classes = list(self.code_clf.classes_)
                best_idx = int(np.argmax(code_proba))
                defect_code = code_classes[best_idx]
                code_conf = code_proba[best_idx]
                confidence = min(confidence, code_conf)
            elif self.single_code is not None:
                defect_code = self.single_code

        need_review = confidence < self.confidence_threshold

        return {
            "label": label,
            "defect_code": defect_code if defect_code else "",
            "confidence": round(float(confidence) * 100, 1),
            "need_review": need_review,
        }

    # ------------------------------------------------------------------
    def save(self, path):
        bundle = {
            "bin_clf": self.bin_clf,
            "code_clf": self.code_clf,
            "defect_codes": self.defect_codes,
            "single_code": self.single_code,
            "good_folder_name": self.good_folder_name,
            "confidence_threshold": self.confidence_threshold,
        }
        joblib.dump(bundle, path)

    def load(self, path):
        bundle = joblib.load(path)
        self.bin_clf = bundle["bin_clf"]
        self.code_clf = bundle["code_clf"]
        self.defect_codes = bundle["defect_codes"]
        self.single_code = bundle["single_code"]
        self.good_folder_name = bundle["good_folder_name"]
        self.confidence_threshold = bundle.get("confidence_threshold", 0.60)
