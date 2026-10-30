"""[홍보 2단계] 냉장고 파먹기(사이트 D)를 스레드에 홍보하는 글을 만들고, 기존 스레드 예약 큐(threads_guard)에 넣는다.

- 글은 반말, 첫 줄은 눈길을 끄는 문장이다. 사이트 소개(냉장고 털기) / 오늘 인기 TOP3 / 레시피 소개 / 재료 조합이 요일별로 돌아가며 나간다.
- 쿠팡 링크는 넣지 않고 사이트로만 보낸다. 하루에 한 편, 최근 60일 안에 쓴 글감은 피한다(기록: data/output/promo_history.json).
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
ROTATION = ["pitch", "top3", "recipe", "combo", "pitch", "recipe", "combo"]   # 요일 순서(월~일)
KEEP_DAYS = 60
NL = chr(10)

# ---- 사이트 소개 글(첫 줄이 후킹) ----
PITCHES = [
    ["냉장고 열어보니 곧 버릴 재료만 잔뜩이야… 😇", "재료 몇 개만 눌러봐, 할 수 있는 요리가 바로 나와!", "남은 재료 빨리 처분하고 싶으면 여기 한번 들어가봐 👉 {link}"],
    ["이번 주에 냉장고 재료 몇 개나 버렸어?", "있는 재료만 눌러봐. 오늘 당장 만들 수 있는 요리만 쏙쏙 뽑아줘", "버리기 전에 한 번만 써봐 👉 {link}"],
    ["시들기 전에 빨리 써야 하는 재료 있지?", "대파든 두부든 계란이든 아무거나 눌러봐. 그걸로 되는 요리만 보여줘", "장 보러 가기 전에 냉장고부터 털자 👉 {link}"],
    ["오늘 저녁 뭐 먹지? 이 고민 이제 안 해도 돼", "냉장고에 있는 재료만 누르면 만들 수 있는 요리가 바로 떠", "지금 한 번 눌러봐 👉 {link}"],
    ["장 보기 전에 냉장고부터 열어봐, 진짜로", "남은 재료 몇 개만 입력하면 할 수 있는 요리가 바로바로 나와", "식재료 버리는 돈 아끼고 싶으면 여기 들어가봐 👉 {link}"],
]


def _load() -> Dict[str, List[dict]]:
    try:
        return json.loads(HISTORY.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return {"posts": []}


def _recent(h: dict, kind: str, today: dt.date) -> set:
    cut = (today - dt.timedelta(days=KEEP_DAYS)).isoformat()
    return {p["key"] for p in h.get("posts", []) if p["kind"] == kind and p["date"] >= cut}


def _link(slug: str, campaign: str) -> str:
    import posts as P

    return P.link(slug, "threads", campaign)


def text_pitch(idx: int) -> str:
    return NL.join(PITCHES[idx % len(PITCHES)]).format(link=_link("", "pitch"))


def text_top3(slugs: List[str], date: str) -> str:
    import posts as P

    names = [P.BY_SLUG[x]["name"] for x in slugs]
    d = date[5:].replace("-", "/") if date else "오늘"
    return NL.join([
        "오늘 다들 뭐 해먹는지 알려줄까?",
        f"{d} 네이버 검색 기준 1위 {names[0]}, 2위 {names[1]}, 3위 {names[2]}",
        f"냉장고에 있는 재료만 누르면 지금 당장 되는 요리도 바로 나와 👉 {_link('', 'top3')}",
    ])


def text_recipe(slug: str) -> str:
    import posts as P

    r = P.BY_SLUG[slug]
    per = P.R.compute(slug)["per"]
    foods = [i["n"] for i in r["ingredients"] if not i["opt"] and i["n"] not in P.R.STAPLES and i["n"] != "물"][:3]
    ing = ", ".join(foods)
    return NL.join([
        f"{ing}만 있으면 {r['name']} 끝이야",
        f"{r['minutes']}분이면 되고 1인분 {per['kcal']}kcal밖에 안 돼",
        f"분량이랑 순서 다 정리해놨으니까 그대로 따라 해봐 👉 {_link(slug, 'recipe')}",
    ])


def text_combo(foods: List[str], slugs: List[str]) -> str:
    import posts as P

    names = " · ".join(P.BY_SLUG[x]["name"] for x in slugs[:3])
    f = foods[0] + ("이랑 " if (ord(foods[0][-1]) - 0xAC00) % 28 else "랑 ") + foods[1]
    return NL.join([
        f"냉장고에 {f}밖에 없어?",
        f"그걸로 {names} 다 돼 🍳",
        f"재료만 눌러봐, 되는 요리 바로 나와 👉 {_link('', 'combo')}",
    ])


def build_post(today: dt.date, h: dict) -> Tuple[str, str, str]:
    """(종류, 중복 확인용 키, 스레드 글)"""
    import posts as P

    kind = ROTATION[today.weekday()]
    if kind == "pitch":
        used = _recent(h, "pitch", today)
        for idx in range(len(PITCHES)):   # 0번(가장 먼저 쓴 문구)부터 차례로, 60일 안에 쓴 건 건너뛴다
            if str(idx) not in used:
                return "pitch", str(idx), text_pitch(idx)
        return "pitch", "0", text_pitch(today.toordinal())
    if kind == "top3":
        slugs, date = P.trending(3)
        if len(slugs) >= 3 and f"{date}" not in _recent(h, "top3", today):
            return "top3", date, text_top3(slugs, date)
        kind = "recipe"
    if kind == "recipe":
        used = _recent(h, "recipe", today)
        pool = [s for s in P.trending(8)[0]] + [r["slug"] for r in P.R.RECIPES]
        for s in pool:
            r = P.BY_SLUG.get(s)
            if r and s not in used and "pet" not in r["cats"] and "baby" not in r["cats"]:
                return "recipe", s, text_recipe(s)
    used = _recent(h, "combo", today)
    for foods in COMBOS:
        key = "+".join(foods)
        if key in used:
            continue
        slugs = P.recipes_for(set(foods) | {"밥"}, 3)
        if len(slugs) >= 2:
            return "combo", key, text_combo(foods, slugs)
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
            print(f"--- {day.isoformat()} ({'월화수목금토일'[day.weekday()]}) [{kind}] ---{NL}{text}{NL}")
        return 0
    if any(p["date"] == today.isoformat() for p in h.get("posts", [])) and send:
        print("오늘 글은 이미 예약했어요. (하루 한 편)")
        return 0
    kind, key, text = build_post(today, h)
    print(f"[{kind}] {key}{NL}{text}{NL}")
    if not send:
        print("(미리보기입니다. 올리지 않았어요. --send 를 주면 스레드 예약 큐에 넣습니다.)")
        return 0
    from threads_guard import enqueue

    res = enqueue("D", text, "", "https://cook.dailyfixpoint.com/")
    print("예약 결과:", res)
    if res.get("status") == "queued":
        h.setdefault("posts", []).append({"date": today.isoformat(), "kind": kind, "key": key, "due_at": res.get("due_at")})
        HISTORY.parent.mkdir(parents=True, exist_ok=True)
        HISTORY.write_text(json.dumps(h, ensure_ascii=False, indent=1), encoding="utf-8")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
