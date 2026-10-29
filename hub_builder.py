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

SITES = {"gov": ("A", "정부지원금·주거"), "life": ("B", "생활비 절약"), "tax": ("C", "세금·절세")}
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
        for pg in _get(f"{base}/wp-json/wp/v2/pages", per_page=30, _fields="slug,link,title,content"):
            title = _strip(pg["title"]["rendered"])
            if pg["slug"] == "calculators":
                data["calc"][hub_key] = pg["link"]
            if hub_key == "gov" and title == "개인정보처리방침":
                data.setdefault("page_html", {})[title] = pg.get("content", {}).get("rendered", "")
    data["pages"] = {"소개": "/about/", "문의하기": "/contact/", "개인정보처리방침": "/privacy/"}  # 허브 루트의 자체 페이지

    posts.sort(key=lambda p: p["date"], reverse=True)
    data["posts"] = posts

    ledger = load_ledger()
    for pid, kw in PROGRAM_KEYWORDS.items():
        terms = (kw,) if isinstance(kw, str) else tuple(kw)
        rec = latest_for(terms, ledger)  # 발행 기록(정확)
        by_title = next((p for p in posts if any(t in p["title"] for t in terms)), None)  # 제목 추측(보완)
        best: Optional[str] = None
        live_links = {p["link"] for p in posts}
        if rec and rec.get("url") in live_links and (not by_title or rec.get("date", "") >= by_title["date"]):
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



SITE_URL = "https://dailyfixpoint.com"
CONTACT_EMAIL = "najdjd85@gmail.com"
SITE_NAME = "데일리픽스 포인트"


def _esc(text: str) -> str:
    return html.escape(text or "", quote=True)


def static_today(posts: List[Dict[str, Any]]) -> str:
    """JS 없이도 읽히는 '오늘의 새 글'(JS가 켜지면 같은 자리를 다시 그린다)."""
    return "".join(
        f'<article><p><a href="{_esc(p["link"])}">{_esc(p["title"])}</a></p><p>{_esc(p["excerpt"])}</p></article>' for p in posts[:3]
    )


def static_list(posts: List[Dict[str, Any]]) -> str:
    return '<ul class="sx">' + "".join(
        f'<li><a href="{_esc(p["link"])}">{_esc(p["title"])}</a><small>{_esc(p["excerpt"])}</small></li>' for p in posts[:12]
    ) + "</ul>"


def intro_html(data: Dict[str, Any]) -> str:
    n = len(data["posts"])
    return f"""<section class="aintro" id="about-site"><h2>데일리픽스 포인트는 이런 사이트입니다</h2>
<p>제도 이름은 알아도 내가 대상인지, 어떤 조건에서 탈락하는지, 언제까지 무엇을 해야 하는지는 한눈에 보기 어렵습니다. 데일리픽스 포인트는 정부지원금·주거 지원, 생활비 절약, 세금·절세 정보를 공식 기관 자료를 기준으로 정리하고, 직접 넣어 보는 모의 계산기와 1분 지원금 확인으로 내 상황에 맞게 판단할 수 있게 돕습니다. 현재 세 개 안내소에 글 {n}개가 있습니다.</p>
<div class="ixg">
<div class="ixb"><b>정부지원금·주거</b><span>복지 급여, 청년·육아 지원, 청약·분양, 공공임대, 주거금융까지 자격 조건과 신청 절차를 정리합니다.</span></div>
<div class="ixb"><b>생활비 절약</b><span>통신비와 교통비, 전기·가스 요금, 보험·금융 비용처럼 매달 나가는 고정비를 줄이는 방법을 다룹니다.</span></div>
<div class="ixb"><b>세금·절세</b><span>연말정산과 종합소득세부터 개인사업자·가맹점·법인 절세, 부동산·금융 세금까지 정리합니다.</span></div>
</div>
<p>모든 글에는 참고한 공식 사이트와 정보 기준일을 적고, 제도와 수치는 바뀔 수 있으므로 신청 전에 해당 기관에서 최신 내용을 확인하도록 안내합니다. 작성에는 AI 도구를 활용하며, 오류를 발견하시면 <a href="/contact/">문의</a>로 알려 주세요. 확인 후 정정합니다. 자세한 운영 원칙은 <a href="/about/">소개</a>에서 볼 수 있습니다.</p></section>"""


def sitemap_html(data: Dict[str, Any]) -> str:
    out = ['<details class="smap" id="sitemap"><summary>사이트 지도 · 전체 글 보기 (총 ' + str(len(data["posts"])) + '개)</summary><div class="sg">']
    for key, (_k, label) in SITES.items():
        mine = [p for p in data["posts"] if p["site"] == key]
        if not mine:
            continue
        out.append(f'<div class="sc"><h3>{_esc(label)} 안내소 ({len(mine)})</h3><ul>')
        out += [f'<li><a href="{_esc(p["link"])}">{_esc(p["title"])}</a></li>' for p in mine]
        out.append("</ul></div>")
    out.append("</div></details>")
    return "".join(out)


_PAGE_SHELL = """<!DOCTYPE html>
<html lang="ko"><head><meta charset="UTF-8"><meta name="viewport" content="width=device-width, initial-scale=1">
<title>{title} - 데일리픽스 포인트</title><meta name="description" content="{desc}">
<link rel="canonical" href="{url}">
<script async src="https://pagead2.googlesyndication.com/pagead/js/adsbygoogle.js?client=ca-pub-5672149391967711"
     crossorigin="anonymous"></script>
<style>body{{margin:0;font-family:-apple-system,BlinkMacSystemFont,"Apple SD Gothic Neo","Noto Sans KR","Malgun Gothic",sans-serif;background:#f6f6f4;color:#1d1d1b;line-height:1.8;word-break:keep-all}}
.w{{max-width:760px;margin:0 auto;padding:0 18px 60px}}header{{padding:16px 0;border-bottom:1px solid #e4e3de;margin-bottom:24px}}header a{{font-weight:700;color:#185fa5;text-decoration:none}}
h1{{font-size:26px;margin:0 0 14px}}h2{{font-size:19px;margin:28px 0 8px}}p,li{{font-size:16px;color:#3b3a36}}a{{color:#185fa5}}footer{{margin-top:40px;padding-top:16px;border-top:1px solid #e4e3de;font-size:14px;color:#6b6a65}}
footer a{{margin-right:14px}}@media (prefers-color-scheme:dark){{body{{background:#1b1b19;color:#f1efe8}}p,li{{color:#d3d1c7}}a,header a{{color:#85b7eb}}header,footer{{border-color:#383835}}}}</style></head>
<body><div class="w"><header><a href="/">← 데일리픽스 포인트 홈</a></header><main><h1>{title}</h1>{body}</main>
<footer><a href="/about/">소개</a><a href="/contact/">문의</a><a href="/privacy/">개인정보처리방침</a><div style="margin-top:8px">이 사이트의 일부 링크에는 제휴 수수료가 포함될 수 있습니다.</div></footer></div></body></html>"""


def _page(title: str, desc: str, path: str, body: str) -> str:
    return _PAGE_SHELL.format(title=_esc(title), desc=_esc(desc), url=f"{SITE_URL}{path}", body=body)


def about_body(data: Dict[str, Any]) -> str:
    rows = "".join(
        f'<li><a href="{_esc(info["url"])}">{_esc(info["label"])} 안내소</a> - 글 {info["count"]}개</li>' for info in data["sites"].values()
    )
    return f"""<p>데일리픽스 포인트는 정부지원금·주거 지원, 생활비 절약, 세금·절세 정보를 공식 기관 자료를 기준으로 정리해 제공하는 정보 사이트입니다. 제도 이름은 알아도 내가 대상인지, 어떤 조건에서 탈락하는지, 언제까지 무엇을 해야 하는지 한눈에 보기 어렵다는 점에서 출발했습니다.</p>
<h2>운영 안내소</h2><ul>{rows}</ul>
<h2>글을 쓰는 원칙</h2>
<ul><li>제도의 자격 조건·금액·기한은 복지로, 정부24, 국세청 홈택스, 청약홈, LH 등 공식 기관 자료를 기준으로 하며, 글마다 참고한 출처와 정보 기준일을 적습니다.</li>
<li>확인되지 않은 수치는 쓰지 않고, 제도가 바뀌어 달라진 내용이 확인되면 글을 고치거나 다시 작성합니다.</li>
<li>모의 계산기와 지원금 확인 도구는 이해를 돕기 위한 참고용이며, 실제 자격과 금액은 반드시 해당 기관에서 확인해야 합니다.</li>
<li>같은 내용을 반복하는 글은 만들지 않고, 이미 다룬 주제는 새로운 질문이나 달라진 점이 있을 때만 다시 다룹니다.</li></ul>
<h2>작성 방식 안내</h2><p>글의 초안 작성에는 AI 도구를 활용하며, 공식 자료의 기준과 수치를 바탕으로 정리합니다. 오류를 발견하시면 아래 문의로 알려 주세요. 확인 후 정정합니다.</p>
<h2>광고와 제휴 고지</h2><p>일부 글에는 쿠팡 파트너스 제휴 링크가 포함될 수 있으며, 링크를 통해 구매가 이루어지면 일정액의 수수료를 받을 수 있습니다. 이 수수료는 구매자에게 추가 비용을 발생시키지 않습니다. 향후 Google 애드센스 등 광고가 게재될 수 있습니다. 광고와 제휴는 글의 내용과 결론에 영향을 주지 않습니다.</p>
<h2>문의</h2><p>오류 제보, 정정 요청, 제휴·광고 문의는 <a href="/contact/">문의 페이지</a>를 이용해 주세요.</p>"""


def contact_body() -> str:
    return f"""<p>사이트 내용의 오류 제보, 정정 요청, 제휴·광고 문의를 받습니다. 아래 이메일로 보내 주세요.</p>
<h2>이메일</h2><p><a href="mailto:{CONTACT_EMAIL}">{CONTACT_EMAIL}</a></p>
<h2>문의할 때 적어 주시면 좋은 내용</h2>
<ul><li>오류 제보·정정 요청: 해당 글의 주소와 잘못된 부분, 근거가 되는 공식 자료(가능하면 링크)</li>
<li>제휴·광고 문의: 회사(또는 서비스) 이름과 제안 내용</li></ul>
<p>확인에는 영업일 기준 며칠이 걸릴 수 있으며, 개별 상황에 대한 법률·세무·복지 상담은 제공하지 않습니다. 정확한 자격 판정은 해당 기관(복지로·정부24·국세청·청약홈 등)에 문의해 주세요.</p>"""


def write_site(outdir: Path, data: Dict[str, Any], index_html: str) -> List[str]:
    """허브 index.html 과 함께 소개·문의·개인정보처리방침, sitemap.xml, robots.txt 를 outdir 에 쓴다. 쓴 파일 목록을 돌려준다."""
    files: Dict[str, str] = {"index.html": index_html}
    files["about/index.html"] = _page("소개", "데일리픽스 포인트의 운영 원칙과 글 작성 방식, 광고·제휴 고지", "/about/", about_body(data))
    files["contact/index.html"] = _page("문의", "오류 제보와 제휴·광고 문의 방법", "/contact/", contact_body())
    privacy = data.get("page_html", {}).get("개인정보처리방침") or "<p>개인정보처리방침을 불러오지 못했습니다.</p>"
    files["privacy/index.html"] = _page("개인정보처리방침", "개인정보 처리와 광고·쿠키 사용 안내", "/privacy/", privacy)
    today = time.strftime("%Y-%m-%d")
    urls = "".join(f"<url><loc>{SITE_URL}{p}</loc><lastmod>{today}</lastmod></url>" for p in ("/", "/about/", "/contact/", "/privacy/"))
    files["sitemap-hub.xml"] = f'<?xml version="1.0" encoding="UTF-8"?>\n<urlset xmlns="http://www.sitemaps.org/schemas/sitemap/0.9">{urls}</urlset>\n'
    subs = "".join(f"<sitemap><loc>{info['url']}/wp-sitemap.xml</loc></sitemap>" for info in data["sites"].values())
    files["sitemap.xml"] = (
        '<?xml version="1.0" encoding="UTF-8"?>\n<sitemapindex xmlns="http://www.sitemaps.org/schemas/sitemap/0.9">'
        f"<sitemap><loc>{SITE_URL}/sitemap-hub.xml</loc></sitemap>{subs}</sitemapindex>\n"
    )
    files["robots.txt"] = f"User-agent: *\nAllow: /\n\nSitemap: {SITE_URL}/sitemap.xml\n"
    for rel, content in files.items():
        path = outdir / rel
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(content, encoding="utf-8")
    return sorted(files)


def build(out: Optional[Path] = None) -> Dict[str, Any]:
    data = collect()
    template = (SITE_DIR / "template.html").read_text(encoding="utf-8")
    wizard = (SITE_DIR / "wizard.js").read_text(encoding="utf-8")
    blob = json.dumps(data, ensure_ascii=False).replace("</", "<\\/")
    page = (
        template.replace("__WIZARD__", wizard).replace("__DATA__", blob)
        .replace("__STATIC_TODAY__", static_today(data["posts"]))
        .replace("__STATIC_LIST__", static_list(data["posts"]))
        .replace("__INTRO__", intro_html(data))
        .replace("__SITEMAP__", sitemap_html(data))
    )
    target = Path(out) if out else DEFAULT_OUT
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(page, encoding="utf-8")
    extra = write_site(target.parent, data, page)  # 소개·문의·개인정보처리방침·sitemap·robots 도 같은 폴더에 만든다
    linked = sum(1 for v in data["program_posts"].values() if v)
    return {"path": str(target), "bytes": len(page.encode("utf-8")), "posts": len(data["posts"]), "linked": linked, "programs": len(PROGRAM_KEYWORDS), "cand": len(data["cand"]), "files": extra}


def purge_cache() -> None:
    """서버 앞단 캐시(Varnish)가 옛 허브·옛 404를 내주지 않도록 올린 주소들을 PURGE 요청으로 비운다(안 되는 환경이면 로그만 남기고 넘어간다)."""
    for path in ("/", "/about", "/about/", "/contact/", "/privacy/", "/robots.txt", "/sitemap.xml", "/sitemap-hub.xml"):
        try:
            r = requests.request("PURGE", f"{SITE_URL}{path}", timeout=10)
            logger.info("캐시 비우기 %s -> HTTP %s", path, r.status_code)
        except Exception as exc:  # noqa: BLE001
            logger.info("캐시 비우기 %s 실패(무시): %s", path, exc)


def publish_if_enabled(built: Path) -> bool:
    """HUB_PUBLISH_PATH가 있을 때만 실제 허브 위치로 복사한다(기본: 올리지 않음 - 애드센스 심사 중에는 건드리지 않는다)."""
    import os

    dest_dir = os.environ.get("HUB_PUBLISH_DIR", "").strip()
    if dest_dir:  # 허브 폴더(public_html)에 생성된 파일 전부를 복사한다. ads.txt 등 생성하지 않는 파일은 건드리지 않는다.
        src = built.parent
        live_index = Path(dest_dir).expanduser() / "index.html"
        backup = Path(dest_dir).expanduser() / "index.before-redesign.html"
        if live_index.exists() and not backup.exists():  # 처음 올릴 때 예전 허브를 한 번만 백업한다(되돌리려면 이 파일을 index.html 로 복사)
            shutil.copyfile(live_index, backup)
        for rel in ("index.html", "about/index.html", "contact/index.html", "privacy/index.html", "sitemap.xml", "sitemap-hub.xml", "robots.txt"):
            target = Path(dest_dir).expanduser() / rel
            target.parent.mkdir(parents=True, exist_ok=True)
            shutil.copyfile(src / rel, target)
        logger.info("허브 사이트 파일을 %s 에 반영했습니다.", dest_dir)
        purge_cache()
        return True
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
    parser.add_argument("--publish", action="store_true", help="만든 뒤 HUB_PUBLISH_DIR(또는 HUB_PUBLISH_PATH)에 바로 반영한다")
    args = parser.parse_args()
    info = build(Path(args.out) if args.out else None)
    print(info)
    if args.publish:
        print("반영:", "완료" if publish_if_enabled(Path(info["path"])) else "HUB_PUBLISH_DIR 가 .env 에 없어 반영하지 않았습니다")
    sys.exit(0)
