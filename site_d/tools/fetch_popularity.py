"""요리별 네이버 월간 검색량(PC+모바일)을 받아 site_d/popularity.json 에 저장한다. 사이트의 '많이 찾는 요리'가 이 파일을 쓴다.

네이버 검색광고 키 3개(NAVER_AD_*)가 .env 에 있어야 한다(내 PC: Naver_keys_input.bat 로 입력). 무료 API이고 5개씩 묶어 7번쯤 호출한다.
한 달에 한 번쯤 실행한 뒤 site_d/build.py 로 다시 빌드한다. 실시간 순위가 아니라 월간 검색량 순위다.
실행: venv/Scripts/python.exe site_d/tools/fetch_popularity.py
"""
from __future__ import annotations

import json
import sys
import time
from datetime import datetime, timedelta, timezone
from pathlib import Path

HERE = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(HERE))
sys.path.insert(0, str(HERE.parent))

from recipes_data import RECIPES  # noqa: E402
from search_demand import _naver_ad_volumes, naver_ad_configured  # noqa: E402

# 사람들이 실제로 검색하는 이름이 레시피 이름과 다른 경우 대체 검색어
SEARCH_NAME = {
    "tuna-kimchi-stew": "참치김치찌개", "egg-ramen": "계란라면", "spam-egg-rice": "스팸계란덮밥", "ham-fried-rice": "햄볶음밥",
    "soy-egg-rice": "간장계란밥", "tuna-mayo-bowl": "참치마요덮밥", "stir-fried-potato": "감자볶음", "potato-pancake": "감자전",
}


def main() -> None:
    if not naver_ad_configured():
        raise SystemExit("네이버 검색광고 키(NAVER_AD_*)가 .env 에 없습니다. Naver_keys_input.bat 로 먼저 입력하세요.")
    names = {r["slug"]: SEARCH_NAME.get(r["slug"], r["name"]).replace(" ", "") for r in RECIPES}
    volumes = {}
    items = list(names.items())
    for i in range(0, len(items), 5):
        chunk = items[i:i + 5]
        got = _naver_ad_volumes([n for _, n in chunk])
        for slug, name in chunk:
            volumes[slug] = int(got.get(name, 0) or 0)
        time.sleep(0.6)
    kst = datetime.now(timezone(timedelta(hours=9)))
    (HERE / "popularity.json").write_text(
        json.dumps({"updated": kst.strftime("%Y-%m-%d"), "source": "네이버 검색광고 키워드 도구 월간 검색량(PC+모바일)", "volumes": volumes}, ensure_ascii=False, indent=1),
        encoding="utf-8",
    )
    top = sorted(volumes.items(), key=lambda t: -t[1])[:10]
    print("상위 10개:", ", ".join(f"{s}({v:,})" for s, v in top))
    print("검색량 0(제외됨):", sum(1 for v in volumes.values() if not v), "개")


if __name__ == "__main__":
    main()
