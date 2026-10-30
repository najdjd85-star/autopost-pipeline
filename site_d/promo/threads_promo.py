"""[홍보 2단계] 냉장고 파먹기(사이트 D)를 스레드에 홍보하는 글을 만들고, 기존 스레드 예약 큐(threads_guard)에 넣는다.

- 글은 사이트 데이터로 자동 생성한다(오늘 인기 TOP3 / 레시피 소개 / 재료 조합). 쿠팡 링크는 넣지 않고 사이트로만 보낸다.
- 하루에 한 편, 종류는 돌아가며 고르고 최근 60일 안에 쓴 레시피·조합은 피한다(기록: data/output/promo_history.json).
- 기본은 '미리보기'(아무것도 올리지 않음). --send 를 줘야 예약 큐에 들어가고, 실제 게시 시각은 threads_guard 가 정한다(시간대·간격·일일 한도).

사용:
  venv/Scripts/python.exe -X utf8 site_d/promo/threads_promo.py             (오늘 글 미리보기)
  venv/Scripts/python.exe -X utf8 site_d/promo/threads_promo.py --week      (7일치 미리보기, 기록은 남기지 않음)
  venv/Scripts/python.exe -X utf8 site_d/promo/threads_promo.py --send      (오늘 글을 스레드 예약 큐에 넣기)
"""
from __future__ import annotations

import datetime as dt
import json
import sys
from pathlib import Path
from typing import Dict, List, Tuple

HERE = Path(__file__).resolve().parent
SITE_D = HERE.parent
ROOT = SITE_D.parent
sys.path.insert(0, str(HERE))
sys.path.insert(0, str(SITE_D))
sys.path.insert(0, str(ROOT))

HISTORY = ROOT / "data" / "output" / "promo_history.json"
COMBOS = [
    ["계란", "김치"], ["두부", "김치"], ["스팸", "계란"], ["참치캔", "김치"], ["계란", "두부"], ["소시지", "계란"],
    ["감자", "계란"], ["어묵", "라면"], ["닭가슴살", "브로콜리"], ["오징어", "양파"], ["식빵", "계란"], ["소고기", "무"],
]
ROTATION = ["top3", "recipe", "combo", "recipe", "top3", "recipe", "combo"]   # 요일 순서(월~일)
KEEP_DAYS = 60


def _load() -> Dict[str, List[dict]]:
    try:
        return json.loads(HISTORY.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return {"posts": []}


def _recent(h: dict, kind: str, today: dt.date) -> set:
    cut = (today - dt.timedelta(days=KEEP_DAYS)).isoformat()
    return {p["key"] for p in h.get("posts", []) if p["kind"] == kind and p["date"] >= cut}


def build_post(today: dt.date, h: dict) -> Tuple[str, str, str]:
    """(종류, 중복 확인용 키, 스레드 글)"""
    import posts as P

    kind = ROTATION[today.weekday()]
    if kind == "top3":
        slugs, date = P.trending(3)
        if len(slugs) >= 3 and f"{date}" not in _recent(h, "top3", today):
            return "top3", date, P.captions_top3(slugs, date)["threads"]
        kind = "recipe"
    if kind == "recipe":
        used = _recent(h, "recipe", today)
        pool = [s for s in P.trending(8)[0]] + [r["slug"] for r in P.R.RECIPES]
        for s in pool:
            r = P.BY_SLUG.get(s)
            if r and s not in used and "pet" not in r["cats"] and "baby" not in r["cats"]:
                return "recipe", s, P.captions_recipe(s)["threads"]
    used = _recent(h, "combo", today)
    for foods in COMBOS:
        key = "+".join(foods)
        if key in used:
            continue
        slugs = P.recipes_for(set(foods) | {"밥"}, 3)
        if len(slugs) >= 2:
            return "combo", key, P.captions_combo(foods, slugs)["threads"]
    raise SystemExit("오늘 쓸 새 글감이 없습니다(최근 60일 기록을 확인하세요).")


def main() -> int:
    send = "--send" in sys.argv
    week = "--week" in sys.argv
    today = dt.date.today()
    h = _load()
    if week:
        tmp = {"posts": list(h.get("posts", []))}
        for d in range(7):
            day = today + dt.timedelta(days=d)
            kind, key, text = build_post(day, tmp)
            tmp["posts"].append({"date": day.isoformat(), "kind": kind, "key": key})
            print(f"--- {day.isoformat()} ({'월화수목금토일'[day.weekday()]}) [{kind}] ---\n{text}\n")
        return 0
    if any(p["date"] == today.isoformat() for p in h.get("posts", [])) and send:
        print("오늘 글은 이미 예약했어요. (하루 한 편)")
        return 0
    kind, key, text = build_post(today, h)
    print(f"[{kind}] {key}\n{text}\n")
    if not send:
        print("(미리보기입니다. 올리지 않았어요. --send 를 주면 스레드 예약 큐에 넣습니다.)")
        return 0
    from threads_guard import enqueue

    res = enqueue("D", text, "", f"https://cook.dailyfixpoint.com/")
    print("예약 결과:", res)
    if res.get("status") == "queued":
        h.setdefault("posts", []).append({"date": today.isoformat(), "kind": kind, "key": key, "due_at": res.get("due_at")})
        HISTORY.parent.mkdir(parents=True, exist_ok=True)
        HISTORY.write_text(json.dumps(h, ensure_ascii=False, indent=1), encoding="utf-8")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
