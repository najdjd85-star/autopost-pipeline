"""글 품질 지킴이: 작성 과정의 말과 출처 없는 일반화를 걷어내고, 같은 사이트의 관련 글을 이어 준다.

새 글(generator)과 이미 발행한 글 정리(scripts/clean_posts.py)가 같은 규칙을 쓴다.
"""
from __future__ import annotations

import html as _html
import re
import zlib
from typing import Dict, List, Optional, Tuple

from utils.logger import get_logger

logger = get_logger(__name__)

# 작성 과정의 말이 글에 그대로 나온 경우(프롬프트 용어). 바꿔 쓸 말이 있으면 바꾸고, 없으면 지운다.
_LABELS = ("자주 헷갈리는 점", "많이 오해하는 부분", "알아 두면 좋은 점")
_LEAKS: List[Tuple[re.Pattern, str]] = [
    (re.compile(r"상식 깨기 포인트가 바로 이 부분입니다\.\s*"), ""),
    (re.compile(r"(\d)인 페르소나 비교"), r"\1가지 경우 비교"),
    (re.compile(r"(\d)인 페르소나"), r"\1가지 사례"),
    (re.compile(r"페르소나 사례"), "예시 사례"),
    (re.compile(r"페르소나"), "예시"),
    (re.compile(r"(?:많은 |여러 )?레퍼런스[^.,<]{0,30}?(?:에서|에 따르면|처럼|들이)[^.,<]{0,30}?,\s*"), ""),
    (re.compile(r"레퍼런스"), "안내 자료"),
    (re.compile(r"상위 노출[^.,<]{0,10}?(?:글|블로그)"), "다른 안내 글"),
]
_MYTH = re.compile(r"(🔍\s*)?상식\s?깨기(\s*(?:포인트)?\s*[:：]?)")

# 출처를 댈 수 없는 일반화(만들어 낸 통계·상담 사례). 이런 문장은 통째로 뺀다.
CLAIMS = re.compile(
    r"상담 사례를 보면|상담 사례에 따르면|(?<!공식 )통계에 따르면|조사에 따르면|매년 (?:수십|수백)\s?(?:만|천)|"
    r"신청자 중 상당수|상당수가 [^.!?]{0,40}(?:탈락|놓치|모르|잘못|착각|헷갈)|창구에서 가장 많이 나오는|"
    r"허탈해하는 분들이 매년|매년 적지 않은 (?:사람|분)|매(?:년|달|주) [^.!?]{0,20}(?:넘쳐|수백|수천|폭증)|"
    r"폭증하고 있습니다|부지기수|하소연이 넘쳐"
)
# 문장 하나: 따옴표 안의 물음표·마침표에서는 끊지 않는다("어? 난 자녀가 없는데?"라며 … 를 한 문장으로 본다).
_SENT = re.compile(r'(?:“[^”]*”|"[^"]*"|&#8220;.*?&#8221;|[^.!?“"])+(?:[.!?]+|$)\s*', re.S)
_BLOCK_TAG = re.compile(r"</?(?:p|h\d|li|ul|ol|div|table|tr|td|th|details|summary|br|section|figure)\b", re.I)


def _clean_text(text: str, removed: List[str]) -> Tuple[str, bool]:
    """출처 없는 일반화 문장을 뺀다. 뺀 문장이 마침표 없이 끝나면(뒤가 태그로 이어지면) True를 돌려 다음 글자 조각에서 마저 지운다."""
    out, cut = [], False
    for m in _SENT.finditer(text):
        s = m.group()
        if s.strip() and CLAIMS.search(_html.unescape(s)):
            removed.append(s.strip())
            cut = not re.search(r"[.!?]\s*$", s)
            continue
        out.append(s)
        cut = False
    return "".join(out), cut


def clean_html(html: str, seed: str = "") -> Tuple[str, Dict[str, List[str]]]:
    """본문 HTML에서 작성 과정의 말과 출처 없는 일반화 문장을 걷어낸다. (새 HTML, 바꾼 내용)"""
    report: Dict[str, List[str]] = {"leaks": [], "claims": []}
    if not html:
        return html, report
    label = _LABELS[zlib.crc32(seed.encode("utf-8")) % len(_LABELS)]
    new = _MYTH.sub(lambda m: (m.group(1) or "") + label + (m.group(2) or ""), html)
    if new != html:
        report["leaks"].append("상식 깨기")
    for pat, rep in _LEAKS:
        new, n = pat.subn(rep, new)
        if n:
            report["leaks"].append(pat.pattern[:20])
    # 태그 사이의 글자만 문장 단위로 본다(스크립트·스타일은 건드리지 않는다).
    parts = re.split(r"(<script.*?</script>|<style.*?</style>|<[^>]+>)", new, flags=re.S)
    cut, in_link = False, False
    for i, part in enumerate(parts):
        if i % 2:  # 태그
            if cut and _BLOCK_TAG.match(part):
                cut = False
            if re.match(r"<a\b", part, re.I):
                in_link = True
            elif re.match(r"</a\s*>", part, re.I):
                in_link = False
            continue
        if in_link:  # 링크 글자(다른 글 제목)는 건드리지 않는다
            continue
        if cut:  # 앞 조각에서 지우던 문장의 나머지
            m = re.search(r"[.!?]+\s*", part)
            part, cut = (part[m.end():], False) if m else ("", True)
        if part and CLAIMS.search(_html.unescape(part)):
            part, cut = _clean_text(part, report["claims"])
        parts[i] = part
    new = "".join(parts)
    new = re.sub(r"<(strong|b|em|span)[^>]*>\s*</\1>", "", new)
    new = re.sub(r"<p>\s*</p>", "", new)
    return new, report


# ---------------------------------------------------------------- 관련 글
_STOP = {"방법", "조건", "신청", "기준", "정리", "총정리", "2026년", "2026", "달라진", "계산", "비교", "얼마", "한눈에", "이유"}


def _words(text: str) -> List[str]:
    return [w for w in re.findall(r"[가-힣A-Za-z0-9·\-]{2,}", text) if w not in _STOP]


def related_posts(posts: List[Dict], keyword: str, title: str = "", limit: int = 3, exclude_link: str = "") -> List[Tuple[str, str]]:
    """같은 사이트 글 중 주제 낱말이 겹치는 글(없으면 최근 글). posts: WP REST 글 목록."""
    words = set(_words(keyword + " " + title))
    scored = []
    for i, p in enumerate(posts):
        t = _html.unescape(re.sub(r"<[^>]+>", "", p.get("title", {}).get("rendered", "")))
        link = p.get("link", "")
        if not t or not link or link == exclude_link or t == title:
            continue
        hit = sum(1 if w in t else 0.5 if len(w) >= 3 and w[:2] in t else 0 for w in words)  # '전기히터'와 '전기요금'처럼 앞 두 글자가 같으면 반만 친다
        scored.append((hit, -i, t, link))
    scored.sort(reverse=True)
    picked = [(t, link) for hit, _i, t, link in scored if hit > 0][:limit]
    if len(picked) < limit:  # 겹치는 글이 모자라면 최근 글로 채운다
        picked += [(t, link) for _h, _i, t, link in sorted(scored, key=lambda x: x[1], reverse=True) if (t, link) not in picked][: limit - len(picked)]
    return picked


def related_block(items: List[Tuple[str, str]]) -> str:
    if not items:
        return ""
    lis = "".join(f'<li style="margin:4px 0;"><a href="{_html.escape(u, quote=True)}">{_html.escape(t)}</a></li>' for t, u in items)
    return ('<div class="related-posts" style="margin:28px 0 8px;padding:16px 18px;border:1px solid #e5e7eb;border-radius:12px;background:#fafafa;">'
            f'<strong>함께 보면 좋은 글</strong><ul style="margin:8px 0 0;padding-left:18px;">{lis}</ul></div>')


def site_posts(site: str, per_page: int = 100) -> List[Dict]:
    try:
        from wp_client import WordPressClient

        return WordPressClient(site).get_recent_posts(days=400, per_page=per_page)
    except Exception as exc:  # noqa: BLE001 - 관련 글은 없어도 된다
        logger.info("[Site %s] 관련 글 목록 조회 실패: %s", site, exc)
        return []


def prompt_block(items: List[Tuple[str, str]]) -> str:
    if not items:
        return ""
    return "[이 사이트의 관련 글]\n" + "\n".join(f"- {t}: {u}" for t, u in items) + "\n\n"


def strip_affiliate_cards(html: str) -> Tuple[str, int]:
    """쿠팡 카드(고정 링크 카드)를 뺀다. 정부지원금·세금 글에서 주제와 상관없는 상품 카드를 걷어낼 때 쓴다."""
    new, n = re.subn(r'<div class="affiliate-card affiliate-card-coupang".*?쿠팡에서 보기</a>\s*</div>', "", html, flags=re.S)
    return new, n


def first_match(posts: List[Dict], words: List[str]) -> Optional[Tuple[str, str]]:
    for p in posts:
        t = _html.unescape(re.sub(r"<[^>]+>", "", p.get("title", {}).get("rendered", "")))
        if any(w in t for w in words):
            return t, p.get("link", "")
    return None
