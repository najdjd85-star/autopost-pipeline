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

# 우리 재료 -> {items: [(KAMIS 품목명, 품종명에 들어가야 하는 낱말(없으면 None))], unit_g: 개·포기·마리 같은 '낱개' 단위 하나의 무게(g), factor: 가공 배율}
# KAMIS 는 품종명 끝 괄호에 가격 단위가 있다(예: 수미(노지)(1kg), 다다기계통(10개)). 낱개 단위는 unit_g 로 무게를 환산한다.
# 못 찾거나 평균가와 너무 다른 재료는 --report 에 나오고 prices.py 의 평균가 추정치가 그대로 쓰인다.
MAPPING: Dict[str, dict] = {
    "양파": {"items": [("양파", None)]}, "대파": {"items": [("파", "대파")]}, "쪽파": {"items": [("파", "쪽파")]},
    "감자": {"items": [("감자", None)]}, "당근": {"items": [("당근", None)]},
    "애호박": {"items": [("호박", "애호박")], "unit_g": 300}, "시금치": {"items": [("시금치", None)]},
    "부추": {"items": [("부추", None)]}, "오이": {"items": [("오이", None)], "unit_g": 150},
    "토마토": {"items": [("토마토", None)]}, "양배추": {"items": [("양배추", None)], "unit_g": 1500},
    "배추": {"items": [("배추", None)], "unit_g": 2500}, "무": {"items": [("무", None)], "unit_g": 1300},
    "파프리카": {"items": [("파프리카", None)], "unit_g": 180},
    "청양고추": {"items": [("풋고추", "청양")]}, "고구마": {"items": [("고구마", None)]},
    "상추": {"items": [("상추", None)]}, "깻잎": {"items": [("깻잎", None)]},
    "브로콜리": {"items": [("브로콜리", None)], "unit_g": 350}, "생강": {"items": [("생강", None)]},
    "미나리": {"items": [("미나리", None)]}, "가지": {"items": [("가지", None)], "unit_g": 150},
    "열무": {"items": [("열무", None)]},
    "버섯": {"items": [("느타리버섯", None), ("새송이버섯", None), ("팽이버섯", None)]},
    "사과": {"items": [("사과", None)], "unit_g": 250}, "바나나": {"items": [("바나나", None)]},
    "배": {"items": [("배", None)], "unit_g": 600}, "키위": {"items": [("키위", None)], "unit_g": 100},
    "레몬": {"items": [("레몬", None)], "unit_g": 100}, "귤": {"items": [("감귤", None)], "unit_g": 80},
    "아보카도": {"items": [("아보카도", None)], "unit_g": 200}, "블루베리": {"items": [("블루베리", None)]},
    "쌀": {"items": [("쌀", None)]}, "찹쌀": {"items": [("찹쌀", None)]},
    "다진마늘": {"items": [("깐마늘(국산)", None)], "factor": 1.5},
    "통깨": {"items": [("참깨", "백색")], "factor": 1.2},
    "고춧가루": {"items": [("고춧가루", "국산")]},
    "견과류": {"items": [("호두", None), ("아몬드", None)]},
    "계란": {"items": [("계란", None)], "unit_g": EGG_G},
    "돼지고기": {"items": [("돼지", "삼겹살"), ("돼지", "앞다리")]},
    "닭": {"items": [("닭", "육계")]},
    "소고기": {"items": [("수입 소고기", None)]},
    "우유": {"items": [("우유", None)]},
    "고등어": {"items": [("고등어", None)], "unit_g": 350}, "오징어": {"items": [("물오징어", None)], "unit_g": 300},
    "갈치": {"items": [("갈치", None)], "unit_g": 400}, "조기": {"items": [("조기", None)], "unit_g": 150},
    "삼치": {"items": [("삼치", None)], "unit_g": 600}, "동태": {"items": [("명태", None)], "unit_g": 600},
    "새우": {"items": [("새우", None)], "unit_g": 15}, "전복": {"items": [("전복", None)], "unit_g": 70},
    "굴": {"items": [("굴", None)]}, "멸치": {"items": [("마른멸치", None)]}, "미역": {"items": [("마른미역", None)]},
    "다시마": {"items": [("건다시마", None)]}, "낙지": {"items": [("낙지", None)]}, "꼬막": {"items": [("꼬막", None)]},
    "홍합": {"items": [("홍합", None)]}, "바지락": {"items": [("바지락", None)]},
    "김": {"items": [("김", "마른김")], "unit_g": 2.5},
    "액젓": {"items": [("멸치액젓", None)]},
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
    """한 분류의 소매가격. KAMIS 는 조회일자(p_regday)와 지역(p_country_code)이 꼭 있어야 응답한다. 휴일이라 비면 하루씩 앞으로 4일까지 다시 본다."""
    import datetime as dt

    start = dt.date.fromisoformat(day) if day else dt.date.today()
    for back in range(5):
        params = {
            "action": "dailyPriceByCategoryList", "p_cert_key": key, "p_cert_id": uid, "p_returntype": "json",
            "p_product_cls_code": "01", "p_item_category_code": cat, "p_country_code": "1101",
            "p_regday": (start - dt.timedelta(days=back)).isoformat(), "p_convert_kg_yn": "Y",
        }
        r = requests.get(URL, params=params, timeout=30)
        r.raise_for_status()
        data = r.json()
        body = data.get("data") if isinstance(data, dict) else None
        if isinstance(body, dict) and str(body.get("error_code", "000")) == "000" and body.get("item"):
            return body["item"]
        time.sleep(0.2)
    return []


def to_float(v) -> Optional[float]:
    s = re.sub(r"[^\d.]", "", str(v or ""))
    return float(s) if s else None


_UNIT_RE = re.compile(r"(?:\(|^)\s*([\d.]*)\s*(kg|g|L|ml|개|포기|마리|구|손|장)\s*\)?\s*$", re.I)


def per_100g(row: dict, spec: Optional[dict] = None) -> Optional[float]:
    """KAMIS 한 줄(가격·단위) -> 100g(액체는 100ml) 당 가격. 품종명 끝 괄호(예: (1kg), (10개))를 단위로 보고, 없으면 unit 칸을 본다."""
    spec = spec or {}
    price = to_float(row.get("dpr1"))
    if not price:
        return None
    m = _UNIT_RE.search(str(row.get("kind_name") or "").strip()) or _UNIT_RE.search(str(row.get("unit") or "").strip())
    if not m:
        return None
    qty = float(m.group(1)) if m.group(1) else 1.0
    u = m.group(2).lower()
    if u in ("kg", "l"):
        grams = qty * 1000
    elif u in ("g", "ml"):
        grams = qty
    else:
        unit_g = spec.get("unit_g")
        grams = qty * unit_g if unit_g else 0
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
                v = per_100g(r, spec)
                if v:
                    vals.append(v)
            if vals and kind is not None:
                pass
        if not vals:
            missing.append(ing)
            continue
        price = statistics.median(vals) * spec.get("factor", 1.0)
        base = PRICE_BASE_100G.get(ing)
        if base and not (base * 0.2 <= price <= base * 3.0):  # 이상치(다른 품종·단위 오류)는 버리고 평균가 추정치를 유지
            missing.append(f"{ing}(이상치 {price:.0f} vs {base})")
            continue
        out[ing] = int(round(price))
    m = re.search(r"\((\d+)/(\d+)\)", day)   # "당일 (10/30)" -> 2026-10-30
    if m:
        import datetime as dt

        day = dt.date(dt.date.today().year, int(m.group(1)), int(m.group(2))).isoformat()
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
    data = {}
    if OUT.exists():
        try:
            data = json.loads(OUT.read_text(encoding="utf-8"))
        except ValueError:
            data = {}
    per = data.get("per100g") or {}
    per.update(prices)
    data["per100g"] = per
    data["kamis_date"] = day
    OUT.write_text(json.dumps(data, ensure_ascii=False, indent=1), encoding="utf-8")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
