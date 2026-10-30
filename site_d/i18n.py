"""사이트 D 다국어: 언어 목록과 번역 사전.

원본(레시피·재료 데이터)은 한국어이고, 다른 언어는 site_d/i18n/<코드>/ 안의 json 으로 얹는다.
- ui.json          화면 문구: {한국어 문구: 번역}   (build.py 의 T("…") 와 템플릿의 {%t …%} 가 찾는다)
- ingredients.json 재료 이름: {한국어 재료: {name, aliases}}
- quantities.json  분량 문구: {한국어 분량: 번역}
- recipes.json     레시피 글: {슬러그: {name, desc, steps, tips, h}}
- labels.json      제휴 버튼 이름: {한국어 라벨: 번역}
새 언어를 더하려면 LANGS 에 한 줄 넣고 위 파일을 채우면 된다(번역은 tools/translate_i18n.py).
"""
from __future__ import annotations

import json
import re
from pathlib import Path

HERE = Path(__file__).resolve().parent

# (코드, 언어 이름, html lang, 주소 앞부분)  - 한국어가 기본이라 주소 앞부분이 없다
LANGS = [("ko", "한국어", "ko", ""), ("en", "English", "en", "en/")]


def _load(p: Path) -> dict:
    try:
        return json.loads(p.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return {}


class Lang:
    def __init__(self, code: str) -> None:
        self.code = code
        d = HERE / "i18n" / code
        self.ui = _load(d / "ui.json")
        self.ing = _load(d / "ingredients.json")
        self.qty = _load(d / "quantities.json")
        self.rec = _load(d / "recipes.json")
        self.labels = _load(d / "labels.json")
        self.missing: set = set()   # 번역을 못 찾은 화면 문구(빌드 끝에 알린다)


_cur = Lang("ko")
_cache: dict = {}


def get(code: str) -> Lang:
    """언어 사전을 (현재 언어를 바꾸지 않고) 가져온다."""
    if code not in _cache:
        _cache[code] = Lang(code)
    return _cache[code]


def use(code: str) -> Lang:
    global _cur
    _cur = get(code)
    return _cur


def cur() -> Lang:
    return _cur


def code() -> str:
    return _cur.code


def is_ko() -> bool:
    return _cur.code == "ko"


def T(ko: str, **kw) -> str:
    """화면 문구를 현재 언어로. 한국어는 그대로이고, {이름} 자리는 kw 로 채운다."""
    if _cur.code == "ko":
        s = ko
    else:
        s = _cur.ui.get(ko)
        if s is None:
            _cur.missing.add(ko)
            s = ko
        else:   # 한국어 문구 앞뒤의 공백(문장을 이어 붙일 때 쓰는 띄어쓰기)은 번역에서도 그대로 살린다
            s = ko[:len(ko) - len(ko.lstrip())] + s.strip() + ko[len(ko.rstrip()):]
    return s.format(**kw) if kw else s


def cap(s: str) -> str:
    return s[:1].upper() + s[1:]


def ing(n: str) -> str:
    """재료 이름(문장 속에서 쓰는 형태). 한국어는 그대로."""
    if _cur.code == "ko":
        return n
    return (_cur.ing.get(n) or {}).get("name", n)


def ing_cap(n: str) -> str:
    """재료 이름(버튼·목록 맨 앞 글자를 대문자로)."""
    return n if _cur.code == "ko" else cap(ing(n))


def qty(q: str) -> str:
    if _cur.code == "ko":
        return q
    return _cur.qty.get(q, q)


def label(ko: str) -> str:
    """제휴 버튼 이름(상품명)."""
    if _cur.code == "ko":
        return ko
    return _cur.labels.get(ko, ko)


def translated(slug: str) -> bool:
    return _cur.code == "ko" or slug in _cur.rec


def rtext(r: dict) -> dict:
    """레시피의 {name, desc, steps, tips} - 현재 언어."""
    if _cur.code == "ko":
        return {"name": r["name"], "desc": r["desc"], "steps": r["steps"], "tips": r["tips"]}
    return _cur.rec[r["slug"]]


def initial_en(name: str) -> str:
    m = re.search(r"[A-Za-z]", name)
    return m.group().upper() if m else "#"


def english_aliases(all_ko_aliases: dict, names: list) -> dict:
    """앱 검색용 별칭표 {한국어 재료: [별칭…]}. 한국어 별칭 + 영어 이름·별칭을 합치되, 같은 낱말이 여러 재료에 겹치면 그 낱말을 주 이름으로 쓰는 재료(없으면 먼저 나온 재료)만 갖는다."""
    en = _cur.ing
    norm = lambda s: re.sub(r"\s+", "", s).lower()  # noqa: E731
    owner: dict = {}
    for n in names:                          # 1순위: 영어 대표 이름
        nm = (en.get(n) or {}).get("name")
        if nm:
            owner.setdefault(norm(nm), n)
    for n in names:                          # 2순위: 영어 별칭(겹치면 먼저 온 재료가 갖는다)
        for a in (en.get(n) or {}).get("aliases", []):
            owner.setdefault(norm(a), n)
    out: dict = {n: list(all_ko_aliases.get(n, [])) for n in names}
    for k, c in owner.items():
        # 원래 표기(공백 포함)를 되살릴 필요는 없다: 앱이 공백을 지우고 비교한다
        out[c].append(k)
    return out
