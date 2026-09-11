# -*- coding: utf-8 -*-
"""
파일명 파싱 유틸
예: 64N68001AA0_64N67002770_64N6700272AC4_TPTN2603_1011_1221.1429_903.322_F1II_01.jpg
    -> ['64N68001AA0', '64N67002770', '64N6700272AC4', 'TPTN2603', '1011',
        '1221.1429', '903.322', 'F1II', '01']
"""
import os


def parse_filename(filepath: str):
    """파일명(확장자 제외)을 '_' 기준으로 분리하여 리스트로 반환한다."""
    base = os.path.splitext(os.path.basename(filepath))[0]
    if not base:
        return []
    return base.split("_")


def max_token_count(filepaths):
    """여러 파일의 토큰 개수 중 최댓값을 반환 (컬럼 개수 결정용)."""
    m = 0
    for fp in filepaths:
        n = len(parse_filename(fp))
        if n > m:
            m = n
    return m
