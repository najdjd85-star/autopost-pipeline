"""서버에서 쿠팡 링크 은행을 제대로 읽는지 점검한다(쿠팡 API는 호출하지 않는다, 비용 0).

실행: venv/bin/python scripts/check_link_bank.py
"""
from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import coupang_link_bank as bank_mod

bank = bank_mod.load_remote_bank()
if not bank:
    print("[ERR] 링크 은행을 읽지 못했습니다 (WP 인증/네트워크 확인)")
    sys.exit(1)

total = sum(len(v) for v in bank.get("sites", {}).values())
print(f"[OK ] 링크 은행 읽기 성공: 생성 {bank.get('generated_at')} / 항목 {total}개 / 사용 한도 {bank.get('max_age_days')}일")

for site, keyword in (("B", "공기청정기 렌탈"), ("B", "eSIM 개통"), ("A", "청년월세 지원"), ("C", "연말정산 환급")):
    product = bank_mod.pick_product(site, keyword)
    shown = f"{product['name'][:30]} | {product['url'][:40]}..." if product else "없음 (홈 링크로 대체됨)"
    print(f"  Site {site} '{keyword}' -> {shown}")
