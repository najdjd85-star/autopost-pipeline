"""허브 홈 페이지 생성기 - 3개 사이트의 최신 글과 보조금24 후보 데이터를 읽어 정적 index.html 한 장을 만든다.

서버가 매일 글 발행 뒤에 실행해 data/output/hub/index.html을 만든다(토큰 0, 공개 REST·공공데이터만 사용).
- "자세한 글 보기"는 발행 기록(post_ledger)에서 제도별 가장 최근 글로 잇고, 기록이 없으면 제목 추측으로 보완한다.
- 판정 규칙의 중위소득·기준 연도는 standards_updater가 저장한 standards.json을 읽는다.
실제 허브(dailyfixpoint.com)에 올리는 것은 환경변수 HUB_PUBLISH_PATH를 설정했을 때만 한다(기본은 올리지 않음).

수동 실행: venv/bin/python hub_builder.py [--out 경로]
"""
from __future__ import annotations

import argparse
import html
import json
import re
import shutil
import sys
import time
from pathlib import Path
from typing import Any, Dict, List, Optional

import requests

from config import OUTPUT_DIR, settings
from post_ledger import latest_for, load as load_ledger
from utils.logger import get_logger

logger = get_logger(__name__)

HERE = Path(__file__).resolve().parent
SITE_DIR = HERE / "hub_site"
DEFAULT_OUT = OUTPUT_DIR / "hub" / "index.html"
GOV24_CACHE = OUTPUT_DIR / "gov24_hub_cache.json"
STANDARDS_PATH = OUTPUT_DIR / "standards.json"
GOV24_API = "https://api.odcloud.kr/api/gov24/v3/"
CAND_LIMIT = 520  # 인기순 상위만 담는다(앱 파일 보기 한도 512KB 안에 맞추기 위함)

SITES = {"gov": ("A", "정부지원금"), "life": ("B", "통신비"), "tax": ("C", "세금·연금")}
# 판정 결과의 "자세한 글 보기" 연결용 제도별 키워드(발행 기록의 주제 키워드 또는 제목에서 찾는다)
PROGRAM_KEYWORDS: Dict[str, Any] = {
    "unemp": ("실업급여", "구직급여"), "eitc": "근로장려금", "child_eitc": "자녀장려금", "pension": "기초연금", "rent": "청년월세", "parent": "부모급여",
    "child_allow": "아동수당", "preg": ("임신·출산", "임신출산", "진료비 바우처", "임신"), "livelihood": "생계급여", "housing": "주거급여",
    "medical": "의료급여", "edu": "교육급여", "energy": "에너지바우처", "sp": "한부모", "job": "국민취업지원", "learn": "내일배움",
    "rent_credit": "월세 세액공제", "child_credit": ("자녀 세액공제", "자녀세액공제"), "pension_credit": "연금저축", "isa": "ISA",
    "sme": ("중소기업 취업청년", "취업청년 소득세"),
}

# 보조금24 후보 압축 - 대상 특성 태그(비트 순서 = TAGS 순서). farm~art는 사용자에게 묻지 않으므로 항상 제외 대상이다.
TAGS = ["farm", "biz", "vet", "foreign", "art", "disabled", "pregnant", "newborn", "child", "student", "senior", "youth", "sp", "job", "low"]
_TAG_RE = {
    "farm": r"농업|어업|임업|축산|농어업|귀농|귀어|어민|농민|농촌",
    "biz": r"소상공인|자영업|사업자|법인|기업체|창업|중소기업(?!\s*취업)|수출|제조업|공장",
    "vet": r"국가유공자|보훈|제대군인|군인|병역|참전|전몰",
    "foreign": r"외국인|다문화|북한이탈|새터민|결혼이민|난민|재외동포",
    "art": r"예술인|문화예술|체육인|선수|문화재|종교",
    "disabled": r"장애",
    "pregnant": r"임산부|임신|난임|예비부모",
    "newborn": r"출산|출생|영유아|영아|신생아|산모|육아|양육",
    "child": r"아동|청소년|초등|중학|고등학|학부모|자녀|학교",
    "student": r"대학생|대학원생|학자금|대학",
    "senior": r"노인|어르신|65세|고령|60세 이상",
    "youth": r"청년",
    "sp": r"한부모|조손",
    "job": r"구직|실업|미취업|취업취약|실직|취업준비",
    "low": r"기초생활|수급자|차상위|저소득|취약계층",
}
_TAG_RE = {k: re.compile(v) for k, v in _TAG_RE.items()}
_VERIFIED_NAMES = re.compile(r"근로장려|자녀장려|기초연금|청년월세|부모급여|아동수당|생계급여|주거급여|의료급여|교육급여|에너지바우처|한부모|국민취업지원|내일배움|구직급여|실업급여")


def _strip(text: str) -> str:
    return re.sub(r"\s+", " ", re.sub(r"<[^>]+>", " ", html.unescape(text or ""))).strip()


def _first_image(content: str) -> str:
    m = re.search(r'<img[^>]+src="([^"]+)"', content or "")
    return m.group(1) if m else ""


def _get(url: str, **params) -> Any:
    r = requests.get(url, params=params, timeout=25)
    r.raise_for_status()
    return r.json()


# ---------------------------------------------------------------------------
# 보조금24 후보
# ---------------------------------------------------------------------------
def _fetch_all(endpoint: str) -> List[Dict[str, Any]]:
    rows, page = [], 1
    while True:
        r = requests.get(
            GOV24_API + endpoint,
            params={"page": page, "perPage": 1000, "returnType": "JSON", "serviceKey": settings.public_data_api_key},
            timeout=60,
        )
        r.raise_for_status()
        data = r.json().get("data", [])
        rows.extend(data)
        if len(data) < 1000:
            return rows
        page += 1
        time.sleep(0.3)


def _gov24_raw() -> List[Dict[str, Any]]:
    try:
        if GOV24_CACHE.exists() and time.time() - GOV24_CACHE.stat().st_mtime < 2 * 86400:
            return json.loads(GOV24_CACHE.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        pass
    if not settings.public_data_api_key:
        return []
    services = _fetch_all("serviceList")
    conds = {c["서비스ID"]: c for c in _fetch_all("supportConditions")}
    keep = [
        {"s": s, "c": conds.get(s["서비스ID"], {})}
        for s in services
        if s.get("소관기관유형") in ("중앙행정기관", "공공기관") and any(u in (s.get("사용자구분") or "") for u in ("개인", "가구"))
    ]
    try:
        OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
        GOV24_CACHE.write_text(json.dumps(keep, ensure_ascii=False), encoding="utf-8")
    except OSError:
        pass
    return keep


def _clean(text: str, n: int) -> str:
    return re.sub(r"\s+", " ", re.sub(r"[○▶※\-•]+", " ", text or "")).strip()[:n]


def gov24_candidates() -> List[list]:
    out = []
    for item in _gov24_raw():
        s, c = item["s"], item["c"]
        name = s.get("서비스명", "")
        if _VERIFIED_NAMES.search(name):
            continue
        text = " ".join(str(s.get(k, "")) for k in ("서비스명", "지원대상", "선정기준"))
        mask = sum(1 << i for i, tag in enumerate(TAGS) if _TAG_RE[tag].search(text))
        inc = sum(1 << i for i, code in enumerate(("JA0201", "JA0202", "JA0203", "JA0204", "JA0205")) if c.get(code) == "Y")
        lo, hi = c.get("JA0110"), c.get("JA0111")
        out.append(
            [
                s["서비스ID"], name, s.get("소관기관명", ""), s.get("서비스분야", ""), _clean(s.get("지원내용", ""), 64),
                s.get("상세조회URL") or f"https://www.gov.kr/portal/rcvfvrSvc/dtlEx/{s['서비스ID']}",
                int(s.get("조회수") or 0), lo if isinstance(lo, int) else None, hi if isinstance(hi, int) else None, inc, mask,
            ]
        )
    out.sort(key=lambda r: -r[6])
    return out[:CAND_LIMIT]


# ---------------------------------------------------------------------------
# 허브 데이터
# ---------------------------------------------------------------------------
def collect() -> Dict[str, Any]:
    data: Dict[str, Any] = {"sites": {}, "calc": {}, "pages": {}, "program_posts": {}}
    posts: List[Dict[str, Any]] = []
    for hub_key, (site_key, label) in SITES.items():
        base = settings.sites[site_key].wp_url.rstrip("/")
        for p in _get(f"{base}/wp-json/wp/v2/posts", per_page=100, _fields="date,link,title,excerpt,content"):
            body = p.get("content", {}).get("rendered", "")
            posts.append(
                {
                    "site": hub_key, "title": _strip(p["title"]["rendered"]), "link": p["link"], "date": p["date"][:10],
                    "excerpt": _strip(p.get("excerpt", {}).get("rendered", ""))[:110], "kw": _strip(body)[:320],
                    "image": _first_image(body), "minutes": max(2, round(len(_strip(body)) / 500)),
                }
            )
        data["sites"][hub_key] = {"label": label, "url": base, "count": sum(1 for p in posts if p["site"] == hub_key)}
        for pg in _get(f"{base}/wp-json/wp/v2/pages", per_page=30, _fields="slug,link,title"):
            title = _strip(pg["title"]["rendered"])
            if pg["slug"] == "calculators":
                data["calc"][hub_key] = pg["link"]
            if hub_key == "gov" and title in ("소개", "문의하기", "개인정보처리방침"):
                data["pages"][title] = pg["link"]

    posts.sort(key=lambda p: p["date"], reverse=True)
    data["posts"] = posts

    ledger = load_ledger()
    for pid, kw in PROGRAM_KEYWORDS.items():
        terms = (kw,) if isinstance(kw, str) else tuple(kw)
        rec = latest_for(terms, ledger)  # 발행 기록(정확)
        by_title = next((p for p in posts if any(t in p["title"] for t in terms)), None)  # 제목 추측(보완)
        best: Optional[str] = None
        if rec and (not by_title or rec.get("date", "") >= by_title["date"]):
            best = rec["url"]
        elif by_title:
            best = by_title["link"]
        data["program_posts"][pid] = best or ""
    data["cand"] = gov24_candidates()
    try:
        data["standards"] = json.loads(STANDARDS_PATH.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        pass
    return data


def build(out: Optional[Path] = None) -> Dict[str, Any]:
    data = collect()
    template = (SITE_DIR / "template.html").read_text(encoding="utf-8")
    wizard = (SITE_DIR / "wizard.js").read_text(encoding="utf-8")
    blob = json.dumps(data, ensure_ascii=False).replace("</", "<\\/")
    page = template.replace("__WIZARD__", wizard).replace("__DATA__", blob)
    target = Path(out) if out else DEFAULT_OUT
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(page, encoding="utf-8")
    linked = sum(1 for v in data["program_posts"].values() if v)
    return {"path": str(target), "bytes": len(page.encode("utf-8")), "posts": len(data["posts"]), "linked": linked, "programs": len(PROGRAM_KEYWORDS), "cand": len(data["cand"])}


def publish_if_enabled(built: Path) -> bool:
    """HUB_PUBLISH_PATH가 있을 때만 실제 허브 위치로 복사한다(기본: 올리지 않음 - 애드센스 심사 중에는 건드리지 않는다)."""
    import os

    dest = os.environ.get("HUB_PUBLISH_PATH", "").strip()
    if not dest:
        return False
    shutil.copyfile(built, dest)
    logger.info("허브 페이지를 %s 에 반영했습니다.", dest)
    return True


def run_daily() -> None:
    """데몬이 글 발행 뒤(22:30 KST)에 호출한다. 실패해도 다른 작업에 영향 없음."""
    try:
        info = build()
        logger.info("허브 생성 완료: %s", info)
        publish_if_enabled(Path(info["path"]))
    except Exception as exc:  # noqa: BLE001
        logger.warning("허브 생성 실패(무시): %s", exc)


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--out", help="출력 파일 경로(기본 data/output/hub/index.html)")
    args = parser.parse_args()
    print(build(Path(args.out) if args.out else None))
    sys.exit(0)
