# -*- coding: utf-8 -*-
"""
TFT LCD 이미지 특징 추출기

정밀도를 위해 다음 정보를 함께 사용한다.
1) 전역 밝기/대비 통계
2) 전역 히스토그램 (조도 얼룩/암점/휘점 등 전반적 이상 감지)
3) 그리드 블록별 평균/표준편차 (국부적 결함: 스크래치, 이물, Mura 등 위치성 결함 감지)
4) 라플라시안 분산 (초점/미세 결함으로 인한 선예도 변화)
5) Canny 엣지 밀도 (스크래치·크랙 등 엣지성 결함)
6) 블록별 엣지 밀도 분산 (국부적 엣지 이상 = 결함 위치가 특정 영역에 몰릴 때 강하게 반응)

이미지 크기는 512x512로 정규화하여 특징 벡터 차원을 고정한다.
"""
import cv2
import numpy as np

IMG_SIZE = 512
GRID = 8  # 8x8 = 64 블록


def _read_image_gray(image_path):
    # 한글 경로 등을 위해 imdecode 사용
    with open(image_path, "rb") as f:
        data = np.frombuffer(f.read(), dtype=np.uint8)
    img = cv2.imdecode(data, cv2.IMREAD_COLOR)
    if img is None:
        raise ValueError(f"이미지를 읽을 수 없습니다: {image_path}")
    gray = cv2.cvtColor(img, cv2.COLOR_BGR2GRAY)
    return img, gray


def extract_features(image_path):
    """이미지 경로를 받아 고정 길이의 numpy 특징 벡터를 반환한다."""
    _, gray = _read_image_gray(image_path)
    gray = cv2.resize(gray, (IMG_SIZE, IMG_SIZE), interpolation=cv2.INTER_AREA)

    feats = []

    # 1) 전역 통계
    feats.append(float(np.mean(gray)))
    feats.append(float(np.std(gray)))

    # 2) 전역 히스토그램 (32 bin, 정규화)
    hist = cv2.calcHist([gray], [0], None, [32], [0, 256]).flatten()
    hist = hist / (hist.sum() + 1e-6)
    feats.extend(hist.tolist())

    # 3) 그리드 블록 평균/표준편차
    step = IMG_SIZE // GRID
    for i in range(GRID):
        for j in range(GRID):
            block = gray[i * step:(i + 1) * step, j * step:(j + 1) * step]
            feats.append(float(np.mean(block)))
            feats.append(float(np.std(block)))

    # 4) 라플라시안 분산 (선예도/미세결함)
    lap = cv2.Laplacian(gray, cv2.CV_64F)
    feats.append(float(lap.var()))

    # 5) Canny 엣지 밀도
    edges = cv2.Canny(gray, 50, 150)
    edge_density = float(np.count_nonzero(edges)) / edges.size
    feats.append(edge_density)

    # 6) 블록별 엣지 밀도의 표준편차 (국부적 엣지 이상 감지)
    block_edge_densities = []
    for i in range(GRID):
        for j in range(GRID):
            block = edges[i * step:(i + 1) * step, j * step:(j + 1) * step]
            block_edge_densities.append(np.count_nonzero(block) / block.size)
    feats.append(float(np.std(block_edge_densities)))
    feats.append(float(np.max(block_edge_densities)))

    return np.array(feats, dtype=np.float32)
