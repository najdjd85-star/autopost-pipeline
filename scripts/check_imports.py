"""
전체 모듈 문법/임포트 자가진단 스크립트.

실제 API 키가 하나도 없는 환경에서도 모든 모듈이 예외 없이 import되는지
확인한다 (py_compile로 문법 오류를, 이 스크립트로 임포트 시점 오류를 잡는다).

사용법:
    venv\\Scripts\\python.exe scripts\\check_imports.py
"""
from __future__ import annotations

import importlib
import sys
import traceback
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

MODULES = [
    "constants",
    "config",
    "utils.logger",
    "utils.http",
    "utils.tts",
    "utils.telegram_notify",
    "utils.fonts",
    "utils.captions",
    "smart_affiliate_matcher",
    "wp_client",
    "trend_scraper",
    "keyword_expander",
    "competitor_analyzer",
    "video_trend_analyzer",
    "generator",
    "image_hybrid_engine",
    "video_engine",
    "longform_engine",
    "social_distributor",
    "content_updater",
    "newsletter_system",
    "telegram_bot",
    "main",
]


def main() -> int:
    failures = []
    for name in MODULES:
        try:
            importlib.import_module(name)
            print(f"[OK]   {name}")
        except Exception:  # noqa: BLE001
            print(f"[FAIL] {name}")
            traceback.print_exc()
            failures.append(name)

    print("-" * 60)
    if failures:
        print(f"실패한 모듈 {len(failures)}개: {failures}")
        return 1

    print(f"전체 {len(MODULES)}개 모듈 임포트 성공.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
