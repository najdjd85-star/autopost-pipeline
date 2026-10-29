"""냉장고 파먹기(사이트 D) 정적 사이트 빌드. 서버·AI 호출 없이 site_d/dist 에 HTML을 만든다.

실행: venv/Scripts/python.exe site_d/build.py            (dist 생성)
      SITE_D_BASE=https://주소 venv/Scripts/python.exe site_d/build.py   (사이트맵·canonical 주소 지정)
미리보기: venv/Scripts/python.exe -m http.server 8791 --directory site_d/dist
"""
from __future__ import annotations

import html
import json
import os
import shutil
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))

from nutrition_data import DAILY, EXTRA, NUTRI, compute  # noqa: E402
from recipes_data import ALIASES, CATEGORIES, EMOJI, RECIPE_CATS, RECIPE_ICON, RECIPES, STAPLE_DEFAULTS, STAPLES  # noqa: E402

STEP_IMAGES = os.environ.get("SITE_D_STEP_IMAGES", "0") == "1"  # AI 단계 이미지는 장면이 자주 틀려서 기본으로 끈다
BASE = os.environ.get("SITE_D_BASE", "https://fridge.dailyfixpoint.com").rstrip("/")
SITE_NAME = "냉장고 파먹기"
DIST = HERE / "dist"
COUPANG_DISCLOSURE = "이 포스팅은 쿠팡 파트너스 활동의 일환으로, 이에 따른 일정액의 수수료를 제공받습니다."
FTC_DISCLOSURE = "이 사이트에는 제휴마케팅이 포함된 링크가 있으며 구매 시 커미션을 지급받을 수 있습니다."
REL = "sponsored nofollow noopener noreferrer"


def esc(s: str) -> str:
    return html.escape(s, quote=True)


def load_photos() -> dict:
    path = HERE / "photos.json"
    return json.loads(path.read_text(encoding="utf-8")) if path.exists() else {}


_PART = "을를은는이가에와과로도의만"
_SKIP_Q = ("약간", "적당", "조금")


def annotate_step(text: str, recipe: dict, used: set) -> str:
    """순서 글에서 재료가 처음 나올 때 그 재료의 분량을 괄호로 붙인다(이미 분량이 적혀 있거나 '계란후라이'처럼 다른 낱말의 일부면 건너뜀)."""
    import re as _re

    names = []  # (찾을 낱말, 재료)
    for i in recipe["ingredients"]:
        if any(w in i["q"] for w in _SKIP_Q) and not _re.search(r"\d", i["q"]):
            continue
        for alias in ALIASES.get(i["n"], [i["n"]]) + [i["n"]]:
            if i["n"] != "물":  # 물은 데칠 물·육수 등 쓰임이 달라 분량을 붙이지 않는다
                names.append((alias, i))
    names.sort(key=lambda t: -len(t[0]))
    out, pos = [], 0
    pattern = _re.compile("|".join(_re.escape(a) for a, _ in names)) if names else None
    while pattern:
        m = pattern.search(text, pos)
        if not m:
            break
        word = m.group()
        ing = next(i for a, i in names if a == word)
        nxt = text[m.end():m.end() + 14]
        prev = text[m.start() - 1] if m.start() else ""
        ok_follow = (not nxt) or nxt[0] in " ,.·/" or (nxt[0] in _PART and (len(nxt) == 1 or not ("가" <= nxt[1] <= "힣")))
        has_amount = _re.match(r"\s*[\d(]|\s*(약간|한 |조금|몇|넉넉|반 )", nxt) is not None
        glued = bool(prev) and "가" <= prev <= "힣" and len(word) == 1  # 한 글자 재료(떡·밥·무…)는 다른 낱말 안에 든 경우를 건너뛴다
        if ok_follow and not has_amount and not glued and ing["n"] not in used:
            used.add(ing["n"])
            qd = _re.sub(r"\s*\(([^)]*)\)", lambda mo: " " + mo.group(1), ing["q"]).strip()  # 분량 안의 괄호는 풀어서 겹치지 않게
            out.append(esc(text[pos:m.end()]) + f'<b class="amt">({esc(qd)})</b>')
        else:
            out.append(esc(text[pos:m.end()]))
        pos = m.end()
    out.append(esc(text[pos:]))
    return "".join(out)


# 단계 글의 동사로 정하는 동작 배지(그림이 틀릴 일이 없는 안내용). 앞에서부터 처음 맞는 것을 쓴다.
_STEP_ACTIONS = [
    (r"데쳐|데칩니다|삶", "♨️", "데치기·삶기"),
    (r"불려|불린|담가", "💧", "불리기"),
    (r"썰|썹니다|다집니다|다져|송송|채 ", "🔪", "손질하기"),
    (r"섞|무치|무칩|버무|풀어|풉니다|재웁|비벼|비빕", "🥣", "섞기·무치기"),
    (r"볶", "🍳", "볶기"),
    (r"부칩니다|부쳐|부치|굽", "🥞", "굽기·부치기"),
    (r"끓|졸", "🍲", "끓이기"),
    (r"전자레인지|돌려", "⏲️", "전자레인지"),
    (r"간을|간하|간합니다", "👅", "간 맞추기"),
    (r"뿌립니다|뿌려|올립니다|올려|담습니다|담아|마무리|두릅니다", "🍽️", "마무리"),
]


def step_action(text: str) -> str:
    import re as _re

    for pat, emoji, label in _STEP_ACTIONS:
        if _re.search(pat, text):
            return f'<span class="sact">{emoji} {label}</span>'
    return ""


def annotated_steps(recipe: dict) -> list:
    used: set = set()
    return [annotate_step(st, recipe, used) for st in recipe["steps"]]


def photo_html(slug: str, name: str, photos: dict) -> str:
    """레시피 사진과 출처 표기(작성자·라이선스·원본 링크). CC 라이선스는 출처 표기가 조건이다."""
    p = photos.get(slug)
    if not p:
        return ""
    lic = f'<a href="{esc(p["license_url"])}" target="_blank" rel="noopener">{esc(p["license"])}</a>' if p.get("license_url") else esc(p["license"])
    return (
        f'<figure class="photo"><img src="../assets/img/{esc(p["file"])}" alt="{esc(name)} 사진" width="640" loading="eager">'
        f'<figcaption>사진: {esc(p["artist"])} · {lic} · <a href="{esc(p["page"])}" target="_blank" rel="noopener">Wikimedia Commons</a></figcaption></figure>'
    )


def load_trending() -> dict:
    """화면의 '인기 요리' 줄 데이터. trending.json(데이터랩 일별 추정, 매일 18시 갱신)이 있으면 그것을, 없으면 월간 검색량 순위를 쓴다."""
    known = {r["slug"] for r in RECIPES}
    path = HERE / "trending.json"
    if path.exists():
        try:
            d = json.loads(path.read_text(encoding="utf-8"))
            slugs = [i["slug"] for i in d.get("items", []) if i.get("slug") in known][:8]
            if slugs:
                return {"kind": "daily", "slugs": slugs, "date": d.get("date", ""), "updated": d.get("updated", "")}
        except (ValueError, KeyError):
            pass
    slugs = load_popular()
    pop = HERE / "popularity.json"
    upd = json.loads(pop.read_text(encoding="utf-8")).get("updated", "") if pop.exists() else ""
    return {"kind": "monthly", "slugs": slugs, "date": upd, "updated": upd}


def load_popular() -> list:
    """site_d/popularity.json: {"updated": "YYYY-MM-DD", "volumes": {슬러그: 월간 검색량}} -> 검색량 큰 순서의 슬러그 목록."""
    path = HERE / "popularity.json"
    if not path.exists():
        return []
    try:
        vols = json.loads(path.read_text(encoding="utf-8")).get("volumes", {})
    except ValueError:
        return []
    known = {r["slug"] for r in RECIPES}
    return [s for s, v in sorted(vols.items(), key=lambda t: -t[1]) if s in known and v][:8]


def load_affiliate_all() -> tuple:
    """affiliate.json -> (재료 링크 {이름: url}, 도구 {이름: {label, url, match}}). 링크가 빈 항목은 뺀다. 예전의 평평한 형식도 읽는다."""
    data = json.loads((HERE / "affiliate.json").read_text(encoding="utf-8"))
    if "ingredients" in data or "tools" in data:
        ing = {k: v for k, v in (data.get("ingredients") or {}).items() if v}
        tools = {k: t for k, t in (data.get("tools") or {}).items() if t.get("url")}
    else:
        ing = {k: v for k, v in data.items() if not k.startswith("_") and isinstance(v, str) and v}
        tools = {}
    return ing, tools


def load_affiliate() -> dict:
    return load_affiliate_all()[0]


def tools_for(recipe: dict, tools: dict) -> list:
    """이 레시피의 조리 순서에 쓰이는 도구 중 링크가 있는 것."""
    import re as _re

    text = " ".join(recipe["steps"]) + " " + " ".join(i["q"] for i in recipe["ingredients"])
    return [(k, t) for k, t in tools.items() if t.get("match") and _re.search(t["match"], text)][:5]  # 한 레시피에 도구 버튼은 최대 5개


def validate() -> None:
    """레시피 데이터가 앱에서 깨지지 않는지 검사한다(모르는 재료, 무게 누락, 모호한 분량, 빈 순서, 중복 슬러그 등)."""
    import re as _re

    known = set(ALIASES) | set(STAPLES)
    cat_slugs = {c[0] for c in RECIPE_CATS}
    slugs, problems = set(), []
    for r in RECIPES:
        nm = r["name"]
        if r["slug"] in slugs:
            problems.append(f"슬러그 중복: {r['slug']}")
        slugs.add(r["slug"])
        if len(r["steps"]) < 4:
            problems.append(f"{nm}: 순서가 너무 짧음(4단계 이상)")
        if len(r["tips"]) < 1:
            problems.append(f"{nm}: 팁 없음")
        if not r["cats"] or any(c not in cat_slugs for c in r["cats"]):
            problems.append(f"{nm}: 카테고리 오류 {r['cats']}")
        for i in r["ingredients"]:
            n, q = i["n"], i["q"]
            if n not in known:
                problems.append(f"{nm}: 알 수 없는 재료 '{n}' (ALIASES/STAPLES에 추가 필요)")
                continue
            if n not in NUTRI or n not in EXTRA:
                problems.append(f"{nm}: 영양 표에 없는 재료 '{n}'")
            if not i["g"] and n not in ("물", "후추"):
                problems.append(f"{nm}: '{n}' 무게(g) 누락")
            if "컵" in q and not _re.search(r"\d\s*(ml|g|kg|L)", q):
                problems.append(f"{nm}: '{n}' 분량 '{q}' - 컵만 적지 말고 ml 또는 g을 함께 적으세요")
            if _re.search(r"약간|적당|조금|한 줌|한줌", q) and n not in ("후추",):
                problems.append(f"{nm}: '{n}' 분량이 모호함 '{q}'")
        if r["slug"] not in RECIPE_ICON:
            problems.append(f"{nm}: 아이콘 없음")
    listed = {n for names in CATEGORIES.values() for n in names}
    for n in ALIASES:
        if n not in EMOJI:
            problems.append(f"이모지 없음: {n}")
        if n not in listed:
            problems.append(f"분류에 없는 재료: {n}")
    for n in listed:
        if n not in ALIASES:
            problems.append(f"ALIASES에 없는 분류 재료: {n}")
    for n in STAPLES:
        if n != "물" and n not in EMOJI:
            problems.append(f"이모지 없음(양념): {n}")
    if problems:
        raise SystemExit("데이터 오류:\n- " + "\n- ".join(problems[:60]) + (f"\n... 외 {len(problems) - 60}건" if len(problems) > 60 else ""))


_CHO = "ㄱㄲㄴㄷㄸㄹㅁㅂㅃㅅㅆㅇㅈㅉㅊㅋㅌㅍㅎ"
_CHO_BASE = {"ㄲ": "ㄱ", "ㄸ": "ㄷ", "ㅃ": "ㅂ", "ㅆ": "ㅅ", "ㅉ": "ㅈ"}


def initial(ch: str) -> str:
    """한글 낱말의 첫 글자 초성(쌍자음은 기본 자음으로 묶는다). 한글이 아니면 '기타'."""
    if "가" <= ch <= "힣":
        c = _CHO[(ord(ch) - 0xAC00) // 588]
        return _CHO_BASE.get(c, c)
    return "기타"


def initials_of(name: str) -> str:
    return "".join(_CHO_BASE.get(_CHO[(ord(c) - 0xAC00) // 588], _CHO[(ord(c) - 0xAC00) // 588]) if "가" <= c <= "힣" else c for c in name if c != " ")


def all_recipes_html() -> str:
    """모든 레시피를 가나다순(초성별 묶음)으로 보여 주는 목록. 레시피가 많아져도 초성 필터·검색으로 좁힐 수 있다."""
    ordered = sorted(RECIPES, key=lambda r: r["name"])
    groups: dict = {}
    for r in ordered:
        groups.setdefault(initial(r["name"][0]), []).append(r)
    order = [c for c in "ㄱㄴㄷㄹㅁㅂㅅㅇㅈㅊㅋㅌㅍㅎ" if c in groups] + (["기타"] if "기타" in groups else [])
    chips = '<button type="button" class="chip on" data-i="">전체</button>' + "".join(f'<button type="button" class="chip" data-i="{c}">{c}<small>{len(groups[c])}</small></button>' for c in order)
    body = ""
    for c in order:
        lis = "".join(
            f'<li data-n="{esc(r["name"])}" data-c="{esc(initials_of(r["name"]))}"><a href="recipes/{r["slug"]}.html">{esc(r["name"])}</a>'
            f'<span>{r["minutes"]}분 · {compute(r["slug"])["per"]["kcal"]}kcal</span></li>'
            for r in groups[c]
        )
        body += f'<div class="rgroup" data-i="{c}"><h3>{c} <small>{len(groups[c])}</small></h3><ul class="rlist">{lis}</ul></div>'
    return (
        f'<h2>모든 레시피 <small class="mut">{len(RECIPES)}개 · 가나다순</small></h2>'
        '<div class="rsearch"><input id="rq" type="search" placeholder="요리 이름 검색 (초성도 돼요: ㄱㅊ)" aria-label="레시피 검색" autocomplete="off"></div>'
        f'<div id="ri" class="initials">{chips}</div><div id="rl">{body}</div><p id="rnone" class="empty" hidden>일치하는 요리가 없어요.</p>'
    )


def recipe_card_html(r: dict, photos: dict, prefix: str = "../") -> str:
    p = photos.get(r["slug"])
    thumb = f'<img src="{prefix}assets/img/{esc(p["file"])}" alt="{esc(r["name"])}" loading="lazy" width="96" height="72">' if p else f'<span>{r["icon"]}</span>'
    return (
        f'<a class="rcard" href="{prefix}recipes/{r["slug"]}.html"><div class="rthumb">{thumb}</div>'
        f'<div class="rbody"><b>{esc(r["name"])}</b><small>{r["minutes"]}분 · {r["level"]} · 1인분 {compute(r["slug"])["per"]["kcal"]}kcal</small>'
        f'<p>{esc(r["desc"])}</p></div></a>'
    )


def categories_section() -> str:
    count = {c[0]: sum(1 for r in RECIPES if c[0] in r["cats"]) for c in RECIPE_CATS}
    cards = "".join(
        f'<a class="catcard" href="category/{c[0]}.html"><span class="ce">{c[2]}</span><b>{esc(c[1])}</b><small>{count[c[0]]}개</small></a>' for c in RECIPE_CATS if count[c[0]]
    )
    return f'<h2>어떤 요리를 찾으세요? <small class="mut">카테고리</small></h2><div class="catgrid">{cards}</div>'


def category_page(tpl: str, cat: tuple, photos: dict) -> str:
    slug, name, emoji, desc = cat
    items = sorted([r for r in RECIPES if slug in r["cats"]], key=lambda r: (r["minutes"], r["name"]))
    avg = round(sum(r["minutes"] for r in items) / len(items))
    cards = "".join(recipe_card_html(r, photos) for r in items)
    others = "".join(f'<a class="chip" href="{c[0]}.html" style="text-decoration:none">{c[2]} {esc(c[1])}</a>' for c in RECIPE_CATS if c[0] != slug)
    intro = f"{esc(desc)} 이 카테고리에는 레시피 {len(items)}개가 있고, 평균 조리 시간은 약 {avg}분이에요. 시간이 짧은 순서로 정렬했고, 각 레시피에는 정확한 분량(ml·g), 단계별 조리 순서, 칼로리와 영양성분표가 있어요."
    out = tpl
    for k, v in {
        "SITE_NAME": SITE_NAME, "BASE": BASE, "NAME": esc(name), "SLUG": slug, "EMOJI": emoji, "INTRO": intro,
        "COUNT": str(len(items)), "CARDS": cards, "OTHERS": others,
    }.items():
        out = out.replace("{{" + k + "}}", v)
    return out


def sorted_categories() -> dict:
    """분류 안의 재료를 레시피에 많이 쓰이는 순서로 정렬한다(자주 쓰는 재료가 앞에 오게)."""
    use: dict = {}
    for r in RECIPES:
        for i in r["ingredients"]:
            use[i["n"]] = use.get(i["n"], 0) + 1
    return {cat: sorted(names, key=lambda n: (-use.get(n, 0), n)) for cat, names in CATEGORIES.items()}


def disclosure(has_links: bool) -> str:
    return f"<p>{esc(FTC_DISCLOSURE)}<br>{esc(COUPANG_DISCLOSURE)}</p>" if has_links else ""


def related(recipe: dict, limit: int = 4) -> list:
    mine = {i["n"] for i in recipe["ingredients"] if i["n"] not in STAPLES}
    scored = []
    for o in RECIPES:
        if o["slug"] == recipe["slug"]:
            continue
        theirs = {i["n"] for i in o["ingredients"] if i["n"] not in STAPLES}
        scored.append((len(mine & theirs), -o["minutes"], o))
    scored.sort(key=lambda t: (t[0], t[1]), reverse=True)
    return [o for s, _m, o in scored[:limit] if s > 0]


def recipe_page(tpl: str, r: dict, aff: dict, photos: dict, tools: dict) -> str:
    ing_html = "".join(
        f'<li><span>{esc(i["n"])}{" (선택)" if i["opt"] else ""}</span><span class="q">{esc(i["q"])}</span></li>' for i in r["ingredients"]
    )
    buy_items = [(i["n"], aff[i["n"]]) for i in r["ingredients"] if i["n"] in aff]
    tool_items = tools_for(r, tools)
    buy = ""
    if buy_items:
        links = "".join(f'<a class="buy" href="{esc(u)}" target="_blank" rel="{REL}">{esc(n)} 사러가기</a> ' for n, u in buy_items)
        buy += f'<div class="panel"><strong>재료 사러가기</strong><div class="chips" style="margin-top:8px">{links}</div></div>'
    if tool_items:
        links = "".join(f'<a class="buy" href="{esc(t["url"])}" target="_blank" rel="{REL}">{esc(t["label"])}</a> ' for _k, t in tool_items)
        buy += f'<div class="panel"><strong>이 요리에 쓰는 요리도구</strong><div class="chips" style="margin-top:8px">{links}</div></div>'
    step_imgs = HERE / "stepimgs"
    li = []
    for n, s_html in enumerate(annotated_steps(r), 1):
        img = step_imgs / f'{r["slug"]}-{n}.jpg'
        pic = f'<img class="stepimg" src="../assets/steps/{r["slug"]}-{n}.jpg" alt="{esc(r["name"])} {n}단계 참고 이미지" width="640" height="427" loading="lazy">' if (STEP_IMAGES and img.exists()) else ""
        li.append(f'<li>{step_action(r["steps"][n - 1])}{s_html}{pic}</li>')
    steps = "".join(li)
    steps_note = (
        '<p class="note">※ 단계별 이미지는 AI로 만든 참고 이미지라 실제 모습과 다를 수 있어요.</p>' if (STEP_IMAGES and any((step_imgs / f'{r["slug"]}-{n}.jpg').exists() for n in range(1, len(r["steps"]) + 1))) else ""
    )
    tip = ('<h2>요리 팁</h2><ul class="tips">' + "".join(f"<li>{esc(t)}</li>" for t in r["tips"]) + "</ul>") if r.get("tips") else ""
    cat_names = {c[0]: (c[1], c[2]) for c in RECIPE_CATS}
    cats_html = "".join(f'<a class="chip" href="../category/{c}.html" style="text-decoration:none">{cat_names[c][1]} {esc(cat_names[c][0])}</a>' for c in r["cats"])
    measure = '<p class="note">계량 기준: 1컵 = 200ml, 1큰술 = 15ml, 1작은술 = 5ml. 숟가락은 가득 채워 윗면을 평평하게 깎은 양이에요. 괄호 안 g(그램)은 대략의 무게입니다.</p>' 
    rel = "".join(f'<a class="chip" href="{esc(o["slug"])}.html" style="text-decoration:none">{esc(o["name"])}</a>' for o in related(r))
    nut = compute(r["slug"])
    per = nut["per"]
    nut_rows = "".join(
        f'<tr><td>{esc(x["n"])}</td><td class="num">{x["g"]:g}g</td><td class="num">{x["kcal"]} kcal</td><td class="num">{x["sodium"]:,}mg</td></tr>'
        for x in nut["rows"]
        if x["kcal"] > 0 or x["sodium"] > 0
    )

    def pct(key: str) -> str:
        return f'{round(per[key] / DAILY[key] * 100)}%'

    facts = [
        ("열량", f'{per["kcal"]:,} kcal', pct("kcal"), "main"),
        ("나트륨", f'{per["sodium"]:,} mg', pct("sodium"), "main"),
        ("탄수화물", f'{per["carb"]} g', pct("carb"), "main"),
        ("당류", f'{per["sugar"]} g', pct("sugar"), "sub"),
        ("식이섬유", f'{per["fiber"]:g} g', pct("fiber"), "sub"),
        ("지방", f'{per["fat"]} g', pct("fat"), "main"),
        ("포화지방", f'{per["satfat"]:g} g', pct("satfat"), "sub"),
        ("콜레스테롤", f'{per["chol"]} mg', pct("chol"), "main"),
        ("단백질", f'{per["protein"]} g', pct("protein"), "main"),
    ]
    facts_rows = "".join(
        f'<tr class="{kind}"><td>{name}</td><td class="num">{val}</td><td class="num pc">{p}</td></tr>' for name, val, p, kind in facts
    )
    carb_base = {"밥", "라면", "소면", "떡", "만두", "식빵"}
    rice_note = "" if carb_base & {x["n"] for x in nut["rows"]} else "밥이나 면은 포함하지 않았어요(밥 1공기는 약 315kcal). "
    nutrition = (
        '<h2>영양성분표</h2><div class="panel nutri">'
        f'<div class="kcal-big"><strong>{per["kcal"]:,}</strong> kcal <span>1인분 기준{f" · 총 {nut['servings']}인분 분량" if nut["servings"] > 1 else ""}</span></div>'
        f'<table class="facts"><thead><tr><th>1인분 기준</th><th class="num">함량</th><th class="num">1일 기준치</th></tr></thead><tbody>{facts_rows}</tbody></table>'
        '<p class="note">1일 기준치는 식품표시 기준(열량 2,000kcal 성인 기준)이며, 개인의 필요량에 따라 다를 수 있어요.</p>'
        '<h3>재료별 열량·나트륨 (전체 분량)</h3>'
        f'<table><thead><tr><th>재료</th><th class="num">사용량</th><th class="num">열량</th><th class="num">나트륨</th></tr></thead><tbody>{nut_rows}'
        f'<tr class="sum"><td>전체 합계</td><td class="num"></td><td class="num">{nut["total_kcal"]:,} kcal</td><td class="num">{nut["total_sodium"]:,}mg</td></tr></tbody></table>'
        '<p class="note">식품성분표의 일반적인 평균값으로 계산한 추정치예요(선택 재료 포함). '
        f'{rice_note}특히 나트륨은 소금·간장을 얼마나 넣는지, 국물을 얼마나 먹는지에 따라 크게 달라져요. '
        '브랜드·부위·양에 따라 달라질 수 있으니 참고용으로만 봐주세요. 질환이나 식단 관리가 필요하면 전문가와 상의하세요.</p></div>'
    )
    jsonld = {
        "@context": "https://schema.org",
        "@type": "Recipe",
        "name": r["name"],
        "description": r["desc"],
        "totalTime": f"PT{r['minutes']}M",
        "recipeYield": f'{nut["servings"]}인분',
        "prepTime": f"PT{max(5, r['minutes'] // 3)}M",
        "nutrition": {"@type": "NutritionInformation", "calories": f'{per["kcal"]} kcal', "servingSize": "1인분",
                      "carbohydrateContent": f'{per["carb"]} g', "proteinContent": f'{per["protein"]} g', "fatContent": f'{per["fat"]} g',
                      "sodiumContent": f'{per["sodium"]} mg', "sugarContent": f'{per["sugar"]} g', "fiberContent": f'{per["fiber"]} g',
                      "saturatedFatContent": f'{per["satfat"]} g', "cholesterolContent": f'{per["chol"]} mg'},
        "recipeIngredient": [f'{i["n"]} {i["q"]}' for i in r["ingredients"]],
        "recipeInstructions": [{"@type": "HowToStep", "text": s} for s in r["steps"]],
        **({"image": f'{BASE}/assets/img/{photos[r["slug"]]["file"]}'} if r["slug"] in photos else {}),
        "recipeCategory": cat_names[r["cats"][0]][0],
        "keywords": ", ".join([r["name"], "레시피", cat_names[r["cats"][0]][0]]),
        "recipeCuisine": "한식",
    }
    out = tpl
    for k, v in {
        "SITE_NAME": SITE_NAME, "BASE": BASE, "NAME": esc(r["name"]), "SLUG": r["slug"], "MINUTES": str(r["minutes"]),
        "LEVEL": esc(r["level"]), "DESC": esc(r["desc"]), "INGREDIENTS": ing_html, "BUY": buy, "STEPS": steps, "STEPS_NOTE": steps_note, "TIP": tip, "CATS": cats_html, "MEASURE": measure,
        "RELATED": rel, "DISCLOSURE": disclosure(bool(buy_items or tool_items)),
        "PHOTO": photo_html(r["slug"], r["name"], photos), "ICON": RECIPE_ICON[r["slug"]], "SERVINGS": f'{nut["servings"]}인분', "NUTRITION": nutrition,
        "JSONLD": json.dumps(jsonld, ensure_ascii=False).replace("</", "<\\/"),
    }.items():
        out = out.replace("{{" + k + "}}", v)
    return out


def main() -> None:
    validate()
    aff, tools = load_affiliate_all()
    photos = load_photos()
    if DIST.exists():
        shutil.rmtree(DIST)
    (DIST / "assets").mkdir(parents=True)
    (DIST / "recipes").mkdir()
    (DIST / "category").mkdir()
    for name in ("style.css", "app.js"):
        shutil.copy(HERE / "static" / name, DIST / "assets" / name)
    (DIST / "assets" / "img").mkdir()
    if (HERE / "trending.json").exists():  # 페이지가 직접 읽는 파일(매일 이 파일만 바꿔도 화면이 갱신된다)
        shutil.copy(HERE / "trending.json", DIST / "trending.json")
    if STEP_IMAGES:
        (DIST / "assets" / "steps").mkdir()
        for f in (HERE / "stepimgs").glob("*.jpg"):
            shutil.copy(f, DIST / "assets" / "steps" / f.name)
    for p in photos.values():
        shutil.copy(HERE / "photos" / p["file"], DIST / "assets" / "img" / p["file"])

    data = {
        "staples": STAPLES,
        "stapleDefaults": STAPLE_DEFAULTS,
        "emoji": EMOJI,
        "trending": load_trending(),
        "aliases": ALIASES,
        "categories": sorted_categories(),
        "affiliate": aff,
        "recipes": [
            {"slug": r["slug"], "name": r["name"], "minutes": r["minutes"], "level": r["level"], "desc": r["desc"],
             "icon": RECIPE_ICON[r["slug"]], "img": (f'assets/img/{photos[r["slug"]]["file"]}' if r["slug"] in photos else ""), "kcal": compute(r["slug"])["per"]["kcal"],
             "ingredients": [{"n": i["n"], "opt": i["opt"]} for i in r["ingredients"]]}
            for r in RECIPES
        ],
    }
    intro = (
        categories_section()
        + "<h2>이렇게 쓰세요</h2><p>냉장고에 있는 재료를 눌러 고르면, 부족한 재료가 없는 요리와 1~2가지만 더 있으면 되는 요리를 나눠서 보여드려요. "
        "양념은 마지막 칸 '양념통'에서 집에 있는 것만 고르면 됩니다.</p>"
        + all_recipes_html()
    )
    index = (HERE / "templates" / "index.html").read_text(encoding="utf-8")
    for k, v in {
        "SITE_NAME": SITE_NAME, "BASE": BASE, "COUNT": str(len(RECIPES)), "INTRO": intro,
        "DISCLOSURE": disclosure(bool(aff or tools)), "DATA": json.dumps(data, ensure_ascii=False).replace("</", "<\\/"),
    }.items():
        index = index.replace("{{" + k + "}}", v)
    (DIST / "index.html").write_text(index, encoding="utf-8")

    tpl = (HERE / "templates" / "recipe.html").read_text(encoding="utf-8")
    for r in RECIPES:
        (DIST / "recipes" / f"{r['slug']}.html").write_text(recipe_page(tpl, r, aff, photos, tools), encoding="utf-8")

    ctpl = (HERE / "templates" / "category.html").read_text(encoding="utf-8")
    for cat in RECIPE_CATS:
        if any(cat[0] in r["cats"] for r in RECIPES):
            (DIST / "category" / f"{cat[0]}.html").write_text(category_page(ctpl, cat, photos), encoding="utf-8")
    urls = [f"{BASE}/"] + [f"{BASE}/category/{c[0]}.html" for c in RECIPE_CATS if any(c[0] in r["cats"] for r in RECIPES)] + [f"{BASE}/recipes/{r['slug']}.html" for r in RECIPES]
    sitemap = '<?xml version="1.0" encoding="UTF-8"?>\n<urlset xmlns="http://www.sitemaps.org/schemas/sitemap/0.9">\n' + "\n".join(f"<url><loc>{u}</loc></url>" for u in urls) + "\n</urlset>\n"
    (DIST / "sitemap.xml").write_text(sitemap, encoding="utf-8")
    (DIST / "robots.txt").write_text(f"User-agent: *\nAllow: /\nSitemap: {BASE}/sitemap.xml\n", encoding="utf-8")
    print(f"빌드 완료: 레시피 {len(RECIPES)}개, 제휴 링크: 재료 {len(aff)}개, 도구 {len(tools)}개 -> {DIST}")


if __name__ == "__main__":
    main()
