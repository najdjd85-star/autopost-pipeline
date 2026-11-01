"""기상청 단기예보(공공데이터포털 VilageFcstInfoService_2.0)로 주요 도시의 오늘~모레 날씨를 받아 site_d/weather.json 에 저장한다.

- 키: .env 의 PUBLIC_DATA_API_KEY(통계청 온라인수집가격과 같은 공공데이터포털 키). 키는 브라우저에 내보내지 않고, 결과 요약(기온·강수·눈·하늘)만 파일로 둔다.
- 사이트의 '오늘의 추천식단'(meal.js)이 이 파일을 읽어 날씨에 맞게 메뉴를 고른다. 파일이 오래됐거나 도시·날짜가 없으면 계절·요일로만 고른다.
- 매일 18시 scripts/update_site_d.py 가 실행하고 깃에 올린다(서버가 18:10에 받아 사이트를 새로 만든다). 어제 저녁 예보가 오늘 아침의 '오늘 날씨'가 된다.

사용:
  venv/Scripts/python.exe -X utf8 site_d/tools/fetch_weather.py
"""
from __future__ import annotations

import datetime as dt
import json
import re
import sys
from pathlib import Path

import requests

HERE = Path(__file__).resolve().parent
SITE_D = HERE.parent
ROOT = SITE_D.parent
sys.path.insert(0, str(ROOT))

OUT = SITE_D / "weather.json"
URL = "https://apis.data.go.kr/1360000/VilageFcstInfoService_2.0/getVilageFcst"
# (코드, 기상청 격자 x, y) - build.py 의 MEAL_CITIES 와 같은 순서·코드
CITIES = [("seoul", 60, 127), ("busan", 98, 76), ("daegu", 89, 90), ("incheon", 55, 124), ("gwangju", 58, 74), ("daejeon", 67, 100),
          ("ulsan", 102, 84), ("sejong", 66, 103), ("jeju", 52, 38), ("gangneung", 92, 131), ("jeonju", 63, 89)]
BASE_TIMES = ["0200", "0500", "0800", "1100", "1400", "1700", "2000", "2300"]


def api_key() -> str:
    from dotenv import dotenv_values

    return (dotenv_values(ROOT / ".env").get("PUBLIC_DATA_API_KEY") or "").strip()


def latest_base(now: dt.datetime) -> tuple:
    """발표 시각(02·05·08·11·14·17·20·23시)은 약 10분 뒤부터 받을 수 있다. 지금 받을 수 있는 가장 최근 발표를 고른다."""
    t = now - dt.timedelta(minutes=15)
    for bt in reversed(BASE_TIMES):
        if t.strftime("%H%M") >= bt:
            return t.strftime("%Y%m%d"), bt
    y = t - dt.timedelta(days=1)
    return y.strftime("%Y%m%d"), "2300"


def num(s: str, kind: str) -> float:
    """강수량·적설 문자열('강수없음', '1.0mm', '30.0~50.0mm', '1mm 미만', '적설없음', '1.0cm')을 숫자로."""
    if not s or "없음" in s:
        return 0.0
    if "미만" in s:
        return 0.5
    m = re.findall(r"\d+(?:\.\d+)?", s)
    return float(m[-1]) if m else 0.0


def summarize(items: list) -> dict:
    days: dict = {}
    for it in items:
        d = days.setdefault(it["fcstDate"], {"tmp": [], "pop": [], "pty": set(), "rain": 0.0, "snow": 0.0, "sky": [], "tmx": None, "tmn": None})
        v, c = it["fcstValue"], it["category"]
        if c == "TMP":
            d["tmp"].append(float(v))
        elif c == "TMX":
            d["tmx"] = float(v)
        elif c == "TMN":
            d["tmn"] = float(v)
        elif c == "POP":
            d["pop"].append(float(v))
        elif c == "PTY" and v != "0":
            d["pty"].add(v)
        elif c == "PCP":
            d["rain"] += num(v, "mm")
        elif c == "SNO":
            d["snow"] += num(v, "cm")
        elif c == "SKY" and "0900" <= it["fcstTime"] <= "1800":
            d["sky"].append(int(v))
    out = {}
    for date, d in days.items():
        if not d["tmp"]:
            continue
        pty = d["pty"]
        if pty & {"2", "3", "6", "7"}:
            code = 73                       # 눈(또는 비·눈)
        elif pty & {"4"}:
            code = 81                       # 소나기
        elif pty & {"1", "5"}:
            code = 63                       # 비
        else:
            sky = max(set(d["sky"]), key=d["sky"].count) if d["sky"] else 1
            code = {1: 0, 3: 2, 4: 3}.get(sky, 0)
        out[date] = {
            "tmax": d["tmx"] if d["tmx"] is not None else max(d["tmp"]), "tmin": d["tmn"] if d["tmn"] is not None else min(d["tmp"]),
            "pop": max(d["pop"]) if d["pop"] else 0, "rain": round(d["rain"], 1), "snow": round(d["snow"], 1), "code": code,
        }
    return out


def fetch_city(key: str, nx: int, ny: int, base_date: str, base_time: str) -> dict:
    r = requests.get(URL, params={"serviceKey": key, "numOfRows": 1000, "pageNo": 1, "dataType": "JSON", "base_date": base_date, "base_time": base_time, "nx": nx, "ny": ny}, timeout=40)
    r.raise_for_status()
    body = r.json()["response"]
    if body["header"]["resultCode"] != "00":
        raise RuntimeError(body["header"]["resultMsg"])
    return summarize(body["body"]["items"]["item"])


def main() -> int:
    key = api_key()
    if not key:
        print("PUBLIC_DATA_API_KEY 가 없어 날씨를 받지 않았어요.")
        return 1
    base_date, base_time = latest_base(dt.datetime.now())
    cities = {}
    for code, nx, ny in CITIES:
        try:
            cities[code] = fetch_city(key, nx, ny, base_date, base_time)
        except Exception as exc:  # noqa: BLE001
            print(f"  {code} 실패(건너뜀): {str(exc)[:80]}")
    if not cities:
        print("날씨를 받지 못했어요(예전 파일 유지).")
        return 1
    OUT.write_text(json.dumps({"updated": dt.datetime.now().strftime("%Y-%m-%d %H:%M"), "base": f"{base_date} {base_time}", "cities": cities}, ensure_ascii=False, separators=(",", ":")), encoding="utf-8")
    seoul = cities.get("seoul", {})
    today = dt.date.today().strftime("%Y%m%d")
    print(f"날씨 저장: 도시 {len(cities)}곳, 발표 {base_date} {base_time}, 서울 오늘 {seoul.get(today)}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
