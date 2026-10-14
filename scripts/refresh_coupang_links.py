"""[데스크탑(한국 IP)에서 실행] 쿠팡 상품 링크를 만들어 서버가 쓰는 비공개 페이지에 올린다.

서버는 해외 IP라 쿠팡 API가 막히므로, 이 스크립트를 하루 한 번 돌려 링크 은행을 갱신한다.
실행: venv\\Scripts\\python.exe scripts\\refresh_coupang_links.py
종료 코드: 0 = 업로드 성공, 1 = 실패(작업 스케줄러에서 확인용)
"""
from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from coupang_link_bank import refresh_bank
from utils.logger import get_logger

logger = get_logger(__name__)

if __name__ == "__main__":
    result = refresh_bank()
    logger.info("쿠팡 링크 은행 갱신 결과: %s", result)
    sys.exit(0 if result.get("uploaded") else 1)
