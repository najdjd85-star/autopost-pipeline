"""재료 가격을 KAMIS(농산물유통정보) 소매가격 API에서 받아 site_d/prices_live.json 으로 저장한다(무료, 매일 평일 갱신).

신선식품(채소·과일·곡물·축산물·수산물)만 실시간이다. 가공식품·양념은 prices.py 의 평균가 추정치를 그대로 쓴다.
키가 없으면 아무것도 하지 않고 조용히 끝난다(사이트는 예전 가격으로 계속 만들어진다).

필요한 키(내 PC .env, 바탕화면 'API 키 입력 (아무 이름)' 으로 입력): KAMIS_CERT_KEY, KAMIS_CERT_ID
  - 발급: https://www.kamis.or.kr  회원가입 → Open-API → 이용신청(무료). 인증Key 와 요청자 ID(가입 아이디)를 받는다.
사용:
  venv/Scripts/python.exe -X utf8 site_d/tools/fetch_prices.py            (받아서 prices_live.json 저장)
  venv/Scripts/python.exe -X utf8 site_d/tools/fetch_prices.py --report   (저장 없이 매칭 결과만 보기)
"""
from __future__ import annotations

import json
import os
import re
import statistics
import sys
import time
from pathlib import Path
from typing import Dict, List, Optional, Tuple

import requests

HERE = Path(__file__).resolve().parent.parent          # site_d
ROOT = HERE.parent
sys.path.insert(0, str(HERE))

from prices import PRICE_BASE_100G  # noqa: E402  (실시간 값을 덮어쓰기 전의 평균가 추정치)

OUT = HERE / "prices_live.json"
URL = "https://www.kamis.or.kr/service/price/xml.do"
CATEGORIES = ["100", "200", "300", "400", "500", "600"]  # 식량작물, 채소, 특용작물, 과일, 축산, 수산
EGG_G = 55  # 계란 한 개 무게(g)

# 우리 재료 -> [(KAMIS 품목명 후보, 품종명에 들어가야 하는 낱말(없으면 None))] , 가공 배율
# 품목·품종 이름은 KAMIS 표기에 맞춰 두었고, 못 찾은 재료는 --report 에 나와서 고칠 수 있다.
MAPPING: Dict[str, dict] = {
    "양파": {"items": [("양파", None)]}, "대파": {"items": [("대파", None)]}, "감자": {"items": [("감자", None)]},
    "당근": {"items": [("당근", None)]}, "애호박": {"items": [("호박", "애호박")]}, "단호박": {"items": [("호박", "단호박")]},
    "시금치": {"items": [("시금치", None)]}, "부추": {"items": [("부추", None)]}, "오이": {"items": [("오이", None)]},
    "토마토": {"items": [("토마토", None)]}, "양배추": {"items": [("양배추", None)]}, "배추": {"items": [("배추", None)]},
    "무": {"items": [("무", None)]}, "파프리카": {"items": [("파프리카", None)]}, "청양고추": {"items": [("풋고추", "청양"), ("풋고추", None)]},
    "고구마": {"items": [("고구마", None)]}, "상추": {"items": [("상추", None)]}, "깻잎": {"items": [("깻잎", None)]},
    "브로콜리": {"items": [("브로콜리", None)]}, "생강": {"items": [("생강", None)]}, "미나리": {"items": [("미나리", None)]},
    "연근": {"items": [("연근", None)]}, "우엉": {"items": [("우엉", None)]}, "도라지": {"items": [("도라지", None)]},
    "옥수수": {"items": [("옥수수", None)]}, "콩나물": {"items": [("콩나물", None)]},
    "버섯": {"items": [("느타리버섯", None), ("새송이버섯", None), ("팽이버섯", None)]},
    "사과": {"items": [("사과", None)]}, "바나나": {"items": [("바나나", None)]},
    "찹쌀": {"items": [("찹쌀", None)]},
    "다진마늘": {"items": [("마늘", "깐마늘"), ("깐마늘", None)], "factor": 1.5},
    "통깨": {"items": [("참깨", None)], "factor": 1.4},
    "계란": {"items": [("계란", None)], "egg": True},
    "돼지고기": {"items": [("돼지고기", "삼겹살"), ("돼지고기", "앞다리")]},
    "닭": {"items": [("닭고기", None)]},
    "소고기": {"items": [("쇠고기", "수입"), ("쇠고기", "불고기")]},
    "고등어": {"items": [("고등어", None)]}, "오징어": {"items": [("오징어", None)]},
    "굴": {"items": [("굴", None)]}, "멸치": {"items": [("멸치", None)]}, "다시마": {"items": [("다시마", None)]},
    "미역": {"items": [("미역", None)]}, "새우": {"items": [("새우", None)]}, "연어": {"items": [("연어", None)]},
}


def keys() -> Tuple[str, str]:
    env = dict(os.environ)
    envfile = ROOT / ".env"
    if envfile.exists():
        try:
            from dotenv import dotenv_values

            env = {**dotenv_values(envfile), **env}
        except Exception:  # noqa: BLE001
            pass
    return env.get("KAMIS_CERT_KEY", "").strip(), env.get("KAMIS_CERT_ID", "").strip()


def call(cat: str, key: str, uid: str, day: str = "") -> List[dict]:
    params = {
        "action": "dailyPriceByCategoryList", "p_cert_key": key, "p_cert_id": uid, "p_returntype": "json",
        "p_product_cls_code": "01", "p_item_category_code": cat, "p_convert_kg_yn": "Y",
    }
    if day:
        params["p_regday"] = day
    r = requests.get(URL, params=params, timeout=30)
    r.raise_for_status()
    data = r.json()
    body = data.get("data") if isinstance(data, dict) else None
    if isinstance(body, dict):
        if str(body.get("error_code", "000")) not in ("000",):
            return []
        return body.get("item") or []
    return []


def to_float(v) -> Optional[float]:
    s = re.sub(r"[^\d.]", "", str(v or ""))
    return float(s) if s else None


def per_100g(row: dict, egg: bool = False) -> Optional[float]:
    """KAMIS 한 줄(가격·단위) -> 100g 당 가격. kg/g 단위가 아니면 None(계란은 개수로 환산)."""
    price = to_float(row.get("dpr1"))
    if not price:
        return None
    unit = str(row.get("unit") or "")
    if egg:
        m = re.search(r"(\d+)\s*개", unit)
        return price / float(m.group(1)) / EGG_G * 100 if m else None
    m = re.search(r"([\d.]*)\s*(kg|g)", unit, re.I)
    if not m:
        return None
    qty = float(m.group(1)) if m.group(1) else 1.0
    grams = qty * (1000 if m.group(2).lower() == "kg" else 1)
    return price / grams * 100 if grams else None


def build(rows: List[dict]) -> Tuple[Dict[str, int], List[str], str]:
    out: Dict[str, int] = {}
    missing: List[str] = []
    day = ""
    for r in rows:
        day = max(day, str(r.get("day1") or ""))
    for ing, spec in MAPPING.items():
        vals: List[float] = []
        for item, kind in spec["items"]:
            for r in rows:
                if str(r.get("item_name") or "").strip() != item:
                    continue
                if kind and kind not in str(r.get("kind_name") or ""):
                    continue
                v = per_100g(r, spec.get("egg", False))
                if v:
                    vals.append(v)
            if vals and kind is not None:
                pass
        if not vals:
            missing.append(ing)
            continue
        price = statistics.median(vals) * spec.get("factor", 1.0)
        base = PRICE_BASE_100G.get(ing)
        if base and not (base * 0.4 <= price <= base * 2.5):  # 이상치(다른 품종·단위 오류)는 버리고 평균가 추정치를 유지
            missing.append(f"{ing}(이상치 {price:.0f} vs {base})")
            continue
        out[ing] = int(round(price))
    return out, missing, day


def main() -> int:
    report = "--report" in sys.argv
    key, uid = keys()
    if not key or not uid:
        print("KAMIS 키(KAMIS_CERT_KEY, KAMIS_CERT_ID)가 없어 가격 갱신을 건너뜁니다.")
        return 0
    rows: List[dict] = []
    for cat in CATEGORIES:
        try:
            rows += call(cat, key, uid)
        except Exception as exc:  # noqa: BLE001
            print(f"분류 {cat} 요청 실패: {str(exc)[:100]}")
        time.sleep(0.3)
    if not rows:
        print("KAMIS 응답이 비어 있어 기존 가격을 유지합니다(휴일이거나 키 오류).")
        return 1
    prices, missing, day = build(rows)
    print(f"기준일 {day}, 갱신 {len(prices)}개, 못 찾음 {len(missing)}개: {', '.join(missing)}")
    if report or not prices:
        return 0
    data = {"date": day, "source": "KAMIS 소매가격(농·축·수산물), 나머지는 평균가 추정", "per100g": prices}
    OUT.write_text(json.dumps(data, ensure_ascii=False, indent=1), encoding="utf-8")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
