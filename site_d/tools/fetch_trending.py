"""'오늘 많이 찾은 요리'를 만든다: 네이버 데이터랩(검색어 트렌드)의 일별 검색 지수로 요리 33개의 최근 하루 검색량을 추정해 site_d/trending.json 에 저장한다.

데이터랩은 한 번에 5개 키워드 그룹까지만 비교하고 지수(0~100)가 요청 안에서만 상대적이다. 그래서 모든 요청에 같은 기준 키워드(떡볶이)를 넣고,
기준 키워드의 일별 지수로 나눈 뒤 기준 키워드의 월간 검색량(site_d/popularity.json, 네이버 검색광고)을 하루치로 환산해 곱한다 -> 요리별 하루 검색량 추정.
가장 최근 데이터는 '어제'다(오늘 자료는 하루가 끝나야 나온다). 하루 수치는 추정치이고 순위를 정하는 데만 쓴다.

필요: .env 의 NAVER_CLIENT_ID, NAVER_CLIENT_SECRET (developers.naver.com 에서 앱을 만들고 '검색어 트렌드(데이터랩)' API를 선택). 무료, 하루 25,000회 한도.
실행: venv/Scripts/python.exe site_d/tools/fetch_trending.py
"""
from __future__ import annotations

import json
import os
import sys
import time
from datetime import datetime, timedelta, timezone
from pathlib import Path

import requests

HERE = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(HERE))
sys.path.insert(0, str(HERE.parent))

import config  # noqa: E402,F401  (.env 를 환경변수로 불러온다)
from recipes_data import RECIPES  # noqa: E402

URL = "https://openapi.naver.com/v1/datalab/search"
ANCHOR_SLUG = "tteokbokki"
SEARCH_NAME = {
    "tuna-kimchi-stew": "참치김치찌개", "egg-ramen": "계란라면", "ham-fried-rice": "햄볶음밥",
}
KST = timezone(timedelta(hours=9))


class NotConfigured(Exception):
    pass


def keys() -> tuple:
    # 데이터랩 전용 키(NAVER_DATALAB_ID/SECRET)를 먼저 보고, 없으면 예전 이름(NAVER_CLIENT_ID/SECRET)을 쓴다
    cid = (os.environ.get("NAVER_DATALAB_ID") or os.environ.get("NAVER_CLIENT_ID") or "").strip()
    sec = (os.environ.get("NAVER_DATALAB_SECRET") or os.environ.get("NAVER_CLIENT_SECRET") or "").strip()
    if not cid or not sec:
        raise NotConfigured("NAVER_DATALAB_ID / NAVER_DATALAB_SECRET 이 .env 에 없습니다 (바탕화면 'Naver 데이터랩 키 입력' 으로 입력).")
    return cid, sec


def query(cid: str, sec: str, names: list, start: str, end: str) -> dict:
    """키워드 그룹(최대 5)의 일별 지수를 받아 {이름: {날짜: 지수}} 로 돌려준다."""
    body = {"startDate": start, "endDate": end, "timeUnit": "date", "keywordGroups": [{"groupName": n, "keywords": [n]} for n in names]}
    r = requests.post(URL, headers={"X-Naver-Client-Id": cid, "X-Naver-Client-Secret": sec, "Content-Type": "application/json"}, data=json.dumps(body), timeout=30)
    if r.status_code in (401, 403):
        raise RuntimeError(f"데이터랩 인증 실패(HTTP {r.status_code}): 앱에 '검색어 트렌드' API가 선택돼 있는지, ID/Secret 이 맞는지 확인하세요. {r.text[:120]}")
    if r.status_code != 200:
        raise RuntimeError(f"데이터랩 조회 실패(HTTP {r.status_code}): {r.text[:160]}")
    return {g["title"]: {p["period"]: float(p["ratio"]) for p in g.get("data", [])} for g in r.json().get("results", [])}


def build() -> dict:
    cid, sec = keys()
    end_d = (datetime.now(KST) - timedelta(days=1)).date()
    start, end = (end_d - timedelta(days=6)).isoformat(), end_d.isoformat()
    names = {r["slug"]: SEARCH_NAME.get(r["slug"], r["name"]).replace(" ", "") for r in RECIPES}
    anchor = names[ANCHOR_SLUG]
    pop_path = HERE / "popularity.json"
    monthly = json.loads(pop_path.read_text(encoding="utf-8")).get("volumes", {}).get(ANCHOR_SLUG) if pop_path.exists() else None
    anchor_daily = (monthly / 30.0) if monthly else 100.0   # 월간 검색량이 없으면 상대 점수(기준=100)로 둔다

    series = {}   # 이름 -> {날짜: 기준으로 환산한 하루 검색량}
    others = [(s, n) for s, n in names.items() if s != ANCHOR_SLUG]
    for i in range(0, len(others), 4):
        chunk = others[i:i + 4]
        got = query(cid, sec, [anchor] + [n for _, n in chunk], start, end)
        a = got.get(anchor, {})
        for slug, n in chunk:
            d = got.get(n, {})
            series[slug] = {day: anchor_daily * d[day] / a[day] for day in d if a.get(day, 0) > 0}
        series.setdefault(ANCHOR_SLUG, {day: anchor_daily for day in a if a.get(day, 0) > 0})
        time.sleep(0.4)

    last_day = max((day for s in series.values() for day in s), default=None)
    if not last_day:
        raise RuntimeError("데이터랩에서 일별 데이터를 받지 못했습니다.")
    rows = []
    for slug, s in series.items():
        if last_day not in s:
            continue
        week = [v for v in s.values()]
        avg7 = sum(week) / len(week) if week else 0
        rows.append({"slug": slug, "est": round(s[last_day]), "avg7": round(avg7), "up": round(s[last_day] / avg7, 2) if avg7 else 0})
    rows.sort(key=lambda r: -r["est"])
    return {
        "updated": datetime.now(KST).strftime("%Y-%m-%d %H:%M"),
        "date": last_day,
        "source": "네이버 데이터랩 검색어 트렌드(일별 지수)로 추정한 하루 검색량",
        "items": rows,
    }


def main() -> None:
    try:
        data = build()
    except NotConfigured as exc:
        raise SystemExit(str(exc))
    (HERE / "trending.json").write_text(json.dumps(data, ensure_ascii=False, indent=1), encoding="utf-8")
    nm = {r["slug"]: r["name"] for r in RECIPES}
    print(f"{data['date']} 기준 상위 8:", ", ".join(f"{nm[r['slug']]}({r['est']:,}, 주간평균 대비 x{r['up']})" for r in data["items"][:8]))


if __name__ == "__main__":
    main()
