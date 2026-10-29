"""통계청 '온라인수집가격정보'(공공데이터포털)에서 마트·온라인몰 상품 가격을 받아 가공식품·양념의 100g당 가격을 갱신한다(무료).

- 데이터: 대형 온라인몰 상품 가격(품목 코드별 상품명·판매가·날짜). 올라오는 날짜가 며칠 늦어서 가장 최근 날짜를 거슬러 올라가 찾는다.
- 상품명에서 용량(g·kg·ml·L, 개수·입 곱하기)을 읽어 100g당 가격으로 바꾸고, 상품이 여러 개면 가운데 값(중앙값)을 쓴다.
- 결과는 site_d/prices_live.json 의 per100g 에 합쳐 넣는다(신선식품 KAMIS 값과 같은 파일, 이 도구는 자기 품목만 덮어쓴다).
- 필요한 키: .env 의 PUBLIC_DATA_API_KEY (공공데이터포털에서 '통계청_온라인수집가격정보' 활용신청 승인 필요). 키가 없거나 실패하면 조용히 건너뛴다.
사용:
  venv/Scripts/python.exe -X utf8 site_d/tools/fetch_prices_online.py            (받아서 합쳐 저장)
  venv/Scripts/python.exe -X utf8 site_d/tools/fetch_prices_online.py --report   (저장 없이 품목별 결과만 보기)
"""
from __future__ import annotations

import datetime as dt
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

from prices import PRICE_BASE_100G  # noqa: E402

OUT = HERE / "prices_live.json"
BASE = "https://apis.data.go.kr/1240000/bpp_openapi/getPriceInfo"

# 우리 재료 -> (품목코드, 이름에 꼭 들어갈 정규식, 이름에 들어가면 안 되는 정규식)
MAPPING: Dict[str, Tuple[str, str, str]] = {
    "라면": ("A01110", r"라면|신라면|진라면|너구리|짜파게티", r"컵|사발|용기|우동|볶음|짜장|짜파|비빔"),
    "소면": ("A01109", r"소면", r"라면|칼국수"),
    "당면": ("A01111", r"당면", r""),
    "스파게티면": ("A01118", r"스파게티|파스타", r"소스|리조|치즈|라면"),
    "밀가루": ("A01108", r"밀가루|박력|중력|강력", r"부침|튀김|빵|케이크|믹스"),
    "부침가루": ("A01108", r"부침|튀김가루", r"믹스|빵"),
    "소시지": ("A01205", r"소시지|소세지|비엔나|프랑크", r""),
    "햄": ("A012060", r"햄", r"스팸|베이컨|소시지|샐러드|런천|후랑크"),
    "스팸": ("A012060", r"스팸", r""),
    "베이컨": ("A012060", r"베이컨", r"비트"),
    "치즈": ("A01403", r"슬라이스|체다|치즈", r"크림치즈|모짜|파마산|치즈볼|스틱|피자|떡볶이|과자|스낵"),
    "참기름": ("A01501", r"참기름", r"들기름|혼합|맛"),
    "식용유": ("A01502", r"식용유|카놀라|콩기름|포도씨", r"올리브|참기름|들기름|스프레이"),
    "올리브유": ("A01502", r"올리브", r"스프레이|화장|비누"),
    "들기름": ("A01502", r"들기름", r""),
    "설탕": ("A01808", r"설탕", r"스틱|시럽|믹스|쿠키|과자"),
    "소금": ("A01904", r"소금|천일염", r"죽염|스프레이|비누|입욕|함초"),
    "간장": ("A01905", r"간장", r"국간장|조선|쌈|초간장|조림|볶음|소스|간장게장|비빔"),
    "국간장": ("A01905", r"국간장|조선간장|국산간장", r""),
    "된장": ("A01906", r"된장", r"청국장|쌈장|찌개"),
    "고추장": ("A01908", r"고추장", r"초고추장|쌈장|양념"),
    "고춧가루": ("A01901", r"고춧가루|고추가루", r"장|볶음"),
    "카레가루": ("A01909", r"카레", r"레토르트|즉석|3분|소스|밥"),
    "식초": ("A01910", r"식초", r"사과식초음|음료|드링크"),
    "마요네즈": ("A01911", r"마요네즈|마요네", r"소스|감자"),
    "케첩": ("A01911", r"케첩|케찹", r"소스|핫도그"),
    "김치": ("A01915", r"김치", r"만두|볶음|찌개|전|라면|국물|부침|양념"),
    "단무지": ("A01727", r"단무지", r"치킨|무"),
    "김": ("A01728", r"김", r"김치|스낵|부각|조미|맛|밥|가루|라면"),
    "미역": ("A01730", r"미역", r"국|줄기|분말"),
    "북어": ("A01315", r"북어|황태", r""),
    "멸치": ("A01311", r"멸치", r"볶음|액젓|조림"),
    "견과류": ("A01619", r"아몬드|견과|호두|캐슈|땅콩", r"쿠키|초콜릿|과자|바|오일"),
    "찹쌀": ("A01103", r"찹쌀", r"가루|떡|과자|누룽지"),
    "쌀": ("A01101", r"쌀", r"누룽지|과자|떡|국수|가루"),
}

UNIT = re.compile(r"(\d+(?:\.\d+)?)\s*(kg|KG|Kg|g|G|ml|ML|mL|l|L)(?![a-zA-Z])")
COUNT = re.compile(r"[*xX×]\s*(\d+)|(\d+)\s*(?:입|개입|개|봉|팩|ea|EA|캔|병|포)(?!\w)")


def grams_of(name: str) -> Optional[float]:
    """상품명에서 총 용량(g)을 읽는다. 못 읽으면 None. ml·L 는 g 과 같다고 본다."""
    sizes = []
    for m in UNIT.finditer(name):
        v = float(m.group(1))
        u = m.group(2).lower()
        sizes.append(v * (1000 if u in ("kg", "l") else 1))
    if not sizes:
        return None
    size = sizes[0]
    count = 1
    tail = name[UNIT.search(name).end():]
    m = COUNT.search(tail)
    if m:
        count = int(m.group(1) or m.group(2))
    total = size * max(1, count)
    return total if 20 <= total <= 40000 else None


def key() -> str:
    env = dict(os.environ)
    envfile = ROOT / ".env"
    if envfile.exists():
        try:
            from dotenv import dotenv_values

            env = {**dotenv_values(envfile), **env}
        except Exception:  # noqa: BLE001
            pass
    return (env.get("PUBLIC_DATA_API_KEY") or "").strip()


def fetch(k: str, code: str, day: str, rows: int = 300) -> List[dict]:
    r = requests.get(BASE, params={"ServiceKey": k, "pageNo": 1, "numOfRows": rows, "itemCode": code, "startDate": day, "endDate": day}, timeout=40)
    r.raise_for_status()
    out = []
    for blk in re.findall(r"<item>(.*?)</item>", r.text, flags=re.S):
        d = {t: (re.search(rf"<{t}>(.*?)</{t}>", blk, flags=re.S) or [None, ""])[1] for t in ("pn", "sp", "dp", "sd")}
        out.append(d)
    return out


def latest_day(k: str) -> str:
    """데이터가 있는 가장 최근 날짜(오늘부터 거슬러 올라가며 라면으로 확인)."""
    today = dt.date.today()
    for n in range(1, 21):
        d = (today - dt.timedelta(days=n)).strftime("%Y%m%d")
        r = requests.get(BASE, params={"ServiceKey": k, "pageNo": 1, "numOfRows": 1, "itemCode": "A01110", "startDate": d, "endDate": d}, timeout=40)
        if "<totalCount>" in r.text and "NO DATA" not in r.text and re.search(r"<totalCount>([1-9]\d*)<", r.text):
            return d
        time.sleep(0.2)
    return ""


def per_100g(rows: List[dict], inc: str, exc: str) -> Tuple[Optional[float], int]:
    vals = []
    for r in rows:
        name = r["pn"]
        if not re.search(inc, name) or (exc and re.search(exc, name)):
            continue
        g = grams_of(name)
        price = float(r["dp"] or 0) or float(r["sp"] or 0)
        if g and price > 0:
            vals.append(price / g * 100)
    if len(vals) < 5:
        return None, len(vals)
    vals.sort()
    # 온라인몰에는 소용량·프리미엄 상품이 많아 가운데 값은 높게 나온다. 하위 25% 지점이 대용량·보통 상품 가격에 가장 가깝다.
    return vals[max(0, int(len(vals) * 0.25) - 1)], len(vals)


def main() -> int:
    report = "--report" in sys.argv
    k = key()
    if not k:
        print("PUBLIC_DATA_API_KEY 가 없어 온라인 가격 갱신을 건너뜁니다.")
        return 0
    try:
        day = latest_day(k)
    except Exception as exc:  # noqa: BLE001
        print("온라인 가격 조회 실패:", str(exc)[:100])
        return 1
    if not day:
        print("최근 3주 안에 가격 자료가 없어 기존 가격을 유지합니다.")
        return 1
    cache: Dict[str, List[dict]] = {}
    result: Dict[str, int] = {}
    lines = []
    for ing, (code, inc, exc) in MAPPING.items():
        try:
            if code not in cache:
                cache[code] = fetch(k, code, day)
                time.sleep(0.25)
            v, n = per_100g(cache[code], inc, exc)
        except Exception as e:  # noqa: BLE001
            lines.append(f"  {ing}: 오류 {str(e)[:60]}")
            continue
        base = PRICE_BASE_100G.get(ing)
        if v is None:
            lines.append(f"  {ing}: 쓸 수 있는 상품 {n}개(5개 미만) - 건너뜀")
        elif base and not (base * 0.5 <= v <= base * 2.0):
            lines.append(f"  {ing}: {v:.0f}원/100g 은 어림값 {base} 과 너무 달라 버림(상품 {n}개)")
        else:
            result[ing] = int(round(v))
            lines.append(f"  {ing}: {v:.0f}원/100g (어림값 {base}, 상품 {n}개)")
    print(f"기준일 {day[:4]}-{day[4:6]}-{day[6:]}, 갱신 {len(result)}개 / 대상 {len(MAPPING)}개")
    print("\n".join(lines))
    if report or not result:
        return 0
    data = {}
    if OUT.exists():
        try:
            data = json.loads(OUT.read_text(encoding="utf-8"))
        except ValueError:
            data = {}
    per = data.get("per100g") or {}
    per.update(result)
    data["per100g"] = per
    data["online_date"] = f"{day[:4]}-{day[4:6]}-{day[6:]}"
    OUT.write_text(json.dumps(data, ensure_ascii=False, indent=1), encoding="utf-8")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
