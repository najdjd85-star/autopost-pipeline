"""검색 수요 데이터(자동완성·서치콘솔·네이버 검색량)를 지금 갱신하고 요약을 보여 준다(서버 데몬이 매일 자동으로도 실행).

실행 예:
  venv/bin/python scripts/run_search_demand.py            # 오래된 것만 갱신
  venv/bin/python scripts/run_search_demand.py --force    # 전부 새로 모음(시드 수 x 약 1초)
  venv/bin/python scripts/run_search_demand.py --show A   # 사이트 A 시드의 수요 가중치와 서치콘솔 상위 검색어 보기
"""
from __future__ import annotations

import argparse
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import search_demand as sd
from trend_scraper import SITE_SEED_KEYWORDS

parser = argparse.ArgumentParser()
parser.add_argument("--force", action="store_true")
parser.add_argument("--show", metavar="SITE", help="A/B/C 중 하나")
parser.add_argument("--probe", metavar="KEYWORD", help="네이버 검색광고 키워드 도구 응답을 그대로 출력(점검용, 키는 출력되지 않음)")
args = parser.parse_args()

if args.probe:
    hints = [h.strip() for h in args.probe.split(",") if h.strip()][:5]
    print("원본 응답:", sd._naver_ad_raw(hints))
    parsed = sd._naver_ad_volumes(hints)
    print("해석 결과:", {k: parsed.get(k.replace(" ", "")) for k in hints}, "/ 전체 항목 수", len(parsed))
elif args.show:
    site = args.show.upper()
    print(f"[Site {site}] 네이버 검색광고 키: {'있음' if sd.naver_ad_configured() else '없음(자동완성·서치콘솔만 사용)'}")
    ranked = sorted(SITE_SEED_KEYWORDS.get(site, []), key=lambda k: -sd.demand_weight(site, k))
    for kw in ranked:
        entry = sd._fresh_keyword_entry(kw)
        print(f"  가중치 {sd.demand_weight(site, kw):4.2f}  {kw:24} 자동완성 {len(entry.get('suggest', [])):2}개  검색량 {entry.get('volume')}")
    print("서치콘솔 상위 검색어:")
    for r in sorted(sd._gsc_rows(site), key=lambda r: -r["impressions"])[:10]:
        print(f"  노출 {r['impressions']:4} 클릭 {r['clicks']:3} 순위 {r['position']:5}  {r['query']}")
else:
    print("갱신 결과:", sd.run_daily(force=args.force))
