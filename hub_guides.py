"""허브 '생활 가이드'(dailyfixpoint.com/guide/...). 허브가 직접 쓰는 긴 안내서다.

안내소(워드프레스) 자동 글처럼 짧은 글이 아니라, 여러 글에 흩어진 내용을 한 페이지에 정리한다.
글 내용은 hub_guides_tax.py / hub_guides_life.py / hub_guides_gov.py 에 간단한 표기법으로 적는다.

표기법(본문 한 줄씩):
  ## 제목            소제목(목차에 자동으로 들어간다)
  ### 제목           작은 제목
  1) 제목 | 설명      번호 단계 상자
  - 내용             글머리 목록
  | 칸 | 칸 |        표(첫 줄은 머리글)
  ! 내용             주의 상자
  Q 질문 / A 답       자주 묻는 질문
  그 밖의 줄          문단(빈 줄로 나눔). 문단 안에 HTML(<b>, <a>)을 써도 된다.
해마다 바뀌는 금액은 적지 않거나 '확인할 곳'으로 안내한다. 고칠 때는 updated(기준일)도 바꾼다.
"""
from __future__ import annotations

import html
import json
import re
from typing import Dict, List, Optional, Tuple

SITE_URL = "https://dailyfixpoint.com"
CATS = {"gov": "정부지원금·주거", "life": "생활비 절약", "tax": "세금·절세"}

CSS = """<style>
.gtag{font-size:13px;font-weight:700;color:#185fa5;margin:0}
.meta{font-size:14px;color:#6b6a65;margin:-6px 0 18px}
.sum{background:#fff;border:1px solid #e4e3de;border-left:4px solid #185fa5;border-radius:12px;padding:14px 18px;margin:18px 0}
.sum b{display:block;margin-bottom:4px}.sum ul{margin:0;padding-left:20px}
.toc{background:#fff;border:1px solid #e4e3de;border-radius:12px;padding:12px 18px;margin:18px 0;font-size:15px}.toc ol{margin:6px 0 0;padding-left:20px}.toc a{text-decoration:none}
.step{display:flex;gap:12px;background:#fff;border:1px solid #e4e3de;border-radius:12px;padding:14px;margin:10px 0}
.step i{font-style:normal;flex:0 0 28px;height:28px;border-radius:50%;background:#1d1d1b;color:#fff;font-weight:700;display:flex;align-items:center;justify-content:center;font-size:14px}
.step p{margin:0}.step b{display:block}
.gt{width:100%;border-collapse:collapse;background:#fff;border-radius:12px;overflow:hidden;font-size:15px;margin:12px 0}
.gt th,.gt td{border-bottom:1px solid #e4e3de;padding:9px 10px;text-align:left;vertical-align:top}.gt th{background:#efeee9;font-size:14px}
.tw{overflow-x:auto}
.warn{background:#fdf3e7;border:1px solid #f1d3a8;border-radius:12px;padding:12px 16px;font-size:15px;margin:16px 0}
.src{background:#fff;border:1px solid #e4e3de;border-radius:12px;padding:12px 16px;font-size:14px;margin:22px 0}.src ul{margin:4px 0;padding-left:20px}.src li{font-size:14px}
.dim{color:#8a8985}
.rel,.glist{display:grid;grid-template-columns:repeat(auto-fit,minmax(220px,1fr));gap:10px;padding:0;list-style:none;margin:0}
.rel li{background:#fff;border:1px solid #e4e3de;border-radius:12px;padding:12px;font-size:15px}.rel small{display:block;color:#8a8985;font-size:12px}
.glist li{background:#fff;border:1px solid #e4e3de;border-radius:16px;padding:16px}.glist a{text-decoration:none;color:inherit;display:block}
.glist .tg{font-size:12px;font-weight:700;color:#185fa5}.glist b{display:block;font-size:17px;line-height:1.45;margin:4px 0 6px;color:#1d1d1b}.glist span{font-size:14px;color:#5f5e5a;display:block}
.glist small{display:block;margin-top:8px;font-size:12px;color:#8a8985}
.gcat{display:flex;gap:6px;flex-wrap:wrap;margin:6px 0 18px}.gcat a{border:1px solid #cfcec7;border-radius:999px;padding:5px 12px;font-size:14px;background:#fff;text-decoration:none;color:#3b3a36}
.faq h3{font-size:17px;margin:18px 0 4px}
@media (prefers-color-scheme:dark){.sum,.toc,.step,.gt,.src,.rel li,.glist li,.gcat a{background:#252523;border-color:#383835}.gt th{background:#2e2e2b}.gt td,.gt th{border-color:#383835}
.warn{background:#2c2419;border-color:#5a4526}.step i{background:#f1efe8;color:#1b1b19}.glist b{color:#f1efe8}.glist span,.gcat a{color:#d3d1c7}.gtag,.glist .tg{color:#85b7eb}}
</style>"""

GUIDES: Dict[str, Dict] = {}


def G(slug: str, cat: str, title: str, desc: str, minutes: int, updated: str, summary: List[str], body: str,
      sources: List[Tuple[str, str]], calcs: Tuple[str, ...] = (), words: Tuple[str, ...] = (), guides: Tuple[str, ...] = ()) -> None:
    """가이드 한 편을 등록한다. calcs: 허브 계산기 slug, words: 관련 안내소 글을 찾을 낱말, guides: 함께 볼 가이드 slug."""
    assert cat in CATS and slug not in GUIDES, slug
    GUIDES[slug] = {"cat": cat, "title": title, "desc": desc, "minutes": minutes, "updated": updated, "summary": summary,
                    "body": body, "sources": sources, "calcs": calcs, "words": words, "guides": guides}


def _render(body: str) -> Tuple[str, List[Tuple[str, str]]]:
    """표기법을 HTML로 바꾸고 목차(앵커, 제목)를 돌려준다."""
    out: List[str] = []
    toc: List[Tuple[str, str]] = []
    para: List[str] = []
    lst: List[str] = []
    table: List[List[str]] = []
    faq: List[str] = []

    def flush() -> None:
        if para:
            out.append("<p>" + " ".join(para) + "</p>")
            para.clear()
        if lst:
            out.append("<ul>" + "".join(f"<li>{x}</li>" for x in lst) + "</ul>")
            lst.clear()
        if table:
            head = "".join(f"<th>{c}</th>" for c in table[0])
            rows = "".join("<tr>" + "".join(f"<td>{c}</td>" for c in r) + "</tr>" for r in table[1:])
            out.append(f'<div class="tw"><table class="gt"><tr>{head}</tr>{rows}</table></div>')
            table.clear()

    for raw in body.strip().splitlines():
        line = raw.strip()
        if not line:
            flush()
            continue
        if line.startswith("## "):
            flush()
            n = len(toc) + 1
            toc.append((f"s{n}", line[3:]))
            out.append(f'<h2 id="s{n}">{n}. {line[3:]}</h2>')
        elif line.startswith("### "):
            flush()
            out.append(f"<h3>{line[4:]}</h3>")
        elif re.match(r"^\d+\) ", line):
            flush()
            num, rest = line.split(") ", 1)
            head, _, text = rest.partition(" | ")
            out.append(f'<div class="step"><i>{num}</i><p><b>{head}</b>{text}</p></div>')
        elif line.startswith("- "):
            if para or table:
                flush()
            lst.append(line[2:])
        elif line.startswith("|"):
            if para or lst:
                flush()
            table.append([c.strip() for c in line.strip("|").split("|")])
        elif line.startswith("! "):
            flush()
            out.append(f'<div class="warn">{line[2:]}</div>')
        elif line.startswith("Q "):
            flush()
            faq.append(f"<h3>{line[2:]}</h3>")
        elif line.startswith("A "):
            flush()
            faq.append(f"<p>{line[2:]}</p>")
        else:
            if lst or table:
                flush()
            para.append(line)
    flush()
    if faq:
        n = len(toc) + 1
        toc.append((f"s{n}", "자주 묻는 질문"))
        out.append(f'<section class="faq"><h2 id="s{n}">{n}. 자주 묻는 질문</h2>{"".join(faq)}</section>')
    return "".join(out), toc


def _faq_pairs(body: str) -> List[Tuple[str, str]]:
    pairs, q = [], None
    for raw in body.splitlines():
        line = raw.strip()
        if line.startswith("Q "):
            q = line[2:]
        elif line.startswith("A ") and q:
            pairs.append((q, re.sub(r"<[^>]+>", "", line[2:])))
            q = None
    return pairs


def page_body(slug: str, related_posts: List[Tuple[str, str]], calc_titles: Dict[str, str]) -> str:
    """가이드 글 페이지 본문. related_posts: (제목, 주소) - 이미 이스케이프된 값."""
    g = GUIDES[slug]
    content, toc = _render(g["body"])
    summ = "".join(f"<li>{x}</li>" for x in g["summary"])
    toc_html = "".join(f'<li><a href="#{a}">{t}</a></li>' for a, t in toc)
    srcs = "".join(f'<li><a href="{u}" target="_blank" rel="noopener">{n}</a></li>' for n, u in g["sources"])
    rel = [f'<li><a href="/calc/{c}/">{calc_titles[c]}</a><small>허브 계산기</small></li>' for c in g["calcs"] if c in calc_titles]
    rel += [f'<li><a href="/guide/{s}/">{GUIDES[s]["title"]}</a><small>생활 가이드</small></li>' for s in g["guides"] if s in GUIDES]
    rel += [f'<li><a href="{u}">{t}</a><small>관련 글</small></li>' for t, u in related_posts]
    ld = {"@context": "https://schema.org", "@type": "Article", "headline": g["title"], "description": g["desc"],
          "dateModified": g["updated"], "datePublished": g.get("published", g["updated"]), "inLanguage": "ko",
          "author": {"@type": "Organization", "name": "데일리픽스 포인트", "url": SITE_URL},
          "publisher": {"@type": "Organization", "name": "데일리픽스 포인트"}, "mainEntityOfPage": f"{SITE_URL}/guide/{slug}/"}
    faq = _faq_pairs(g["body"])
    lds = [ld]
    if faq:
        lds.append({"@context": "https://schema.org", "@type": "FAQPage",
                    "mainEntity": [{"@type": "Question", "name": q, "acceptedAnswer": {"@type": "Answer", "text": a}} for q, a in faq]})
    ld_html = "".join('<script type="application/ld+json">' + json.dumps(x, ensure_ascii=False).replace("</", "<\\/") + "</script>" for x in lds)
    return (CSS + f'<p class="meta">{CATS[g["cat"]]} 가이드 · 기준일 {g["updated"]} · 읽는 시간 약 {g["minutes"]}분 · 데일리픽스 포인트 편집</p>'
            + f'<div class="sum"><b>3줄 요약</b><ul>{summ}</ul></div>'
            + (f'<nav class="toc"><b>목차</b><ol>{toc_html}</ol></nav>' if len(toc) > 2 else "")
            + content
            + f'<div class="src"><b>확인할 곳</b><ul>{srcs}</ul><span class="dim">이 가이드는 공식 자료를 바탕으로 정리한 참고용 안내입니다. '
              f'제도와 금액은 바뀔 수 있으니 신청·신고 전에 해당 기관에서 최신 기준을 확인하세요. 잘못된 내용은 <a href="/contact/">문의</a>로 알려 주시면 확인 후 고칩니다.</span></div>'
            + (f'<h2>함께 쓰면 좋은 도구와 글</h2><ul class="rel">{"".join(rel)}</ul>' if rel else "")
            + f'<p style="margin-top:24px"><a href="/guide/">← 생활 가이드 전체 보기</a></p>' + ld_html)


def _card(slug: str) -> str:
    g = GUIDES[slug]
    return (f'<li><a href="/guide/{slug}/"><span class="tg">{CATS[g["cat"]]}</span><b>{html.escape(g["title"])}</b>'
            f'<span>{html.escape(g["desc"])}</span><small>읽는 시간 {g["minutes"]}분 · 기준일 {g["updated"]}</small></a></li>')


def index_body() -> str:
    """가이드 목록 페이지 본문: 분야별로 묶는다."""
    chips = "".join(f'<a href="#c-{k}">{v}</a>' for k, v in CATS.items())
    parts = [CSS, "<p>지원금·생활비·세금에서 자주 막히는 문제를 처음부터 끝까지 한 페이지로 정리했습니다. "
                  "각 가이드는 공식 기관 자료를 기준으로 쓰고, 기준일과 확인할 곳을 함께 적습니다. "
                  "자세한 개별 제도는 각 안내소 글과 <a href=\"/calc/\">생활 계산기</a>로 이어집니다.</p>",
             f'<div class="gcat">{chips}</div>']
    for k, v in CATS.items():
        mine = [s for s, g in GUIDES.items() if g["cat"] == k]
        if mine:
            parts.append(f'<h2 id="c-{k}">{v} ({len(mine)})</h2><ul class="glist">{"".join(_card(s) for s in mine)}</ul>')
    return "".join(parts)


# 홈 첫 화면에 걸 가이드(달마다). 없는 달은 FEATURED_DEFAULT.
FEATURED: Dict[int, Tuple[str, ...]] = {
    11: ("year-end-tax-prep", "winter-heating-cost", "find-government-benefits"),
    12: ("pension-savings-irp", "winter-heating-cost", "find-government-benefits"),
    1: ("year-end-tax-documents", "winter-heating-cost", "find-government-benefits"),
    2: ("year-end-tax-documents", "phone-bill-saving", "youth-housing-support"),
    5: ("comprehensive-income-tax-may", "earned-income-tax-credit", "phone-bill-saving"),
}
FEATURED_DEFAULT = ("find-government-benefits", "phone-bill-saving", "year-end-tax-prep")


def home_html(month: int) -> str:
    """허브 홈의 '생활 가이드' 묶음(템플릿 안에서 쓰므로 템플릿 변수로 꾸민다)."""
    picks = [s for s in FEATURED.get(month, FEATURED_DEFAULT) if s in GUIDES] or list(GUIDES)[:3]
    cards = "".join(
        f'<a class="gd-i" href="/guide/{s}/"><span class="tag t-{GUIDES[s]["cat"]}">{CATS[GUIDES[s]["cat"]]}</span>'
        f'<b>{html.escape(GUIDES[s]["title"])}</b><p>{html.escape(GUIDES[s]["desc"])}</p><small>읽는 시간 {GUIDES[s]["minutes"]}분</small></a>'
        for s in picks)
    return (f'<section id="guides"><p class="h2">생활 가이드</p><p class="gd-d">여러 글에 흩어진 내용을 한 번에 정리한 데일리픽스 포인트의 기본 안내서입니다. '
            f'모두 {len(GUIDES)}편.</p><div class="gd">{cards}</div><a class="gd-all" href="/guide/">생활 가이드 전체 보기 →</a></section>')


def slugs() -> List[str]:
    return list(GUIDES)


def load() -> Dict[str, Dict]:
    """분야별 글 파일을 읽어 GUIDES를 채운다(여러 번 불러도 한 번만 읽는다)."""
    if not GUIDES:
        import hub_guides_gov  # noqa: F401
        import hub_guides_life  # noqa: F401
        import hub_guides_tax  # noqa: F401
    return GUIDES


def problems() -> List[str]:
    """글 점검: 빠진 칸, 없는 가이드·계산기 연결, 너무 짧은 글."""
    load()
    out: List[str] = []
    try:
        from hub_calcs import CALCS
    except Exception:  # noqa: BLE001
        CALCS = {}
    for s, g in GUIDES.items():
        if len(g["summary"]) != 3:
            out.append(f"{s}: 3줄 요약이 {len(g['summary'])}줄")
        if not g["sources"]:
            out.append(f"{s}: 확인할 곳 없음")
        text = re.sub(r"<[^>]+>", "", g["body"])
        if len(text) < 1200:
            out.append(f"{s}: 본문이 짧음({len(text)}자)")
        for c in g["calcs"]:
            if c not in CALCS:
                out.append(f"{s}: 없는 계산기 {c}")
        for x in g["guides"]:
            if x not in GUIDES:
                out.append(f"{s}: 없는 가이드 {x}")
        if not re.fullmatch(r"\d{4}-\d{2}-\d{2}", g["updated"]):
            out.append(f"{s}: 기준일 형식")
    for m, picks in list(FEATURED.items()) + [(0, FEATURED_DEFAULT)]:
        for x in picks:
            if x not in GUIDES:
                out.append(f"홈 추천({m}월): 없는 가이드 {x}")
    return out


if __name__ == "__main__":
    import hub_guides as _m  # 글 파일들이 'hub_guides' 이름으로 등록하므로 그 모듈로 점검한다

    _m.load()
    print(len(_m.GUIDES), "편", _m.problems() or "문제 없음")
