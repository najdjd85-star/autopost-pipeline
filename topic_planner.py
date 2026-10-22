"""주제 다양화 플래너 - 키워드 쉬어가기, 글 유형 로테이션, 제목 각도 상한, 뉴스 연동.

글이 단조로워 보이던 원인을 코드로 막는다.
1. 같은 핵심 키워드/계열(예: 해외주식 양도세·배당세·손익통산)이 연달아 나오지 않게 한다.
   - 키워드마다 "마지막으로 쓴 지 얼마나 됐는지"를 (선정 히스토리 + 최근 발행 제목)에서 계산해 가장 오래된 것부터 고른다.
   - 최근 선정한 키워드와 같은 계열은 잠시 제외한다.
2. 글 유형(개편 해설/일정 캘린더/계산 사례집/선택 가이드/용어 정리/체크리스트/문제 해결/뉴스 풀이)을 돌려 쓴다.
   기존 "탈락·오해" 각도는 문제 해결 유형 하나로 줄어든다.
3. 최근 제목에 부정 어휘(탈락/오해/손해...)가 몰려 있으면 이번 제목에서 금지한다.
4. 이번 주 정책 뉴스가 사이트 키워드와 맞으면 뉴스 풀이 유형으로 쓴다.
5. 검증된 팩트 시트가 없는 확장 키워드는 수치를 지어내지 않도록 주의 문구를 붙인다.
6. 같은 주제를 중복해서 쓰지 않는다: 쓴 주제는 90일 쿨다운. 쿨다운에 걸린 주제만 남으면 같은 제도의 "아직 안 쓴 세부 질문"
   (자동완성)으로 쓰고, 정책이 바뀐 제도(팩트 시트 갱신·월간 점검에서 수정 감지·관련 뉴스)는 쿨다운과 상관없이 개정 내용 글로 다시 쓴다.

토큰을 쓰지 않는다(전부 로컬 계산). 히스토리는 data/output/topic_history_{site}.json.
"""
from __future__ import annotations

import json
import math
import random
from datetime import datetime, timedelta, timezone
from typing import Any, Dict, List, Optional, Tuple  # noqa: F401

from config import OUTPUT_DIR
from fact_sheets import get_fact_sheet
from utils.logger import get_logger

logger = get_logger(__name__)

_AVOID_RECENT_TYPES = 3
_AVOID_RECENT_FAMILIES = 3
_PICK_FROM_OLDEST = 4
_HISTORY_KEEP = 30
_NEGATIVE_WINDOW = 10
_NEGATIVE_LIMIT = 4
COOLDOWN_DAYS = 90  # 한 번 쓴 주제는 이 기간 동안 다시 뽑지 않는다(정책 변경으로 다시 쓰는 경우와 세부 주제 글은 예외)
_LOG_KEEP = 600
_KST = timezone(timedelta(hours=9))

# 같은 계열로 묶을 첫 단어 (표기가 달라도 같은 주제 덩어리)
_FAMILY_ALIASES = {
    "미국주식": "해외주식",
    "국내시장": "해외주식",
    "연말정산": "연말정산",
    "종합소득세": "소득세",
    "프리랜서": "소득세",
    "연금저축": "연금계좌",
    "IRP": "연금계좌",
    "퇴직연금": "연금계좌",
    "퇴직금": "연금계좌",
    "기초연금": "연금",
    "국민연금": "국민연금",
    "알뜰폰": "알뜰폰",
    "인터넷": "인터넷",
    "정수기": "렌탈",
    "공기청정기": "렌탈",
    "안마의자": "렌탈",
    "비데": "렌탈",
    "휴대폰": "휴대폰",
    "자급제폰": "휴대폰",
    "중고폰": "휴대폰",
    "청년월세": "청년",
    "청년도약계좌": "청년",
    "청년지원금": "청년",
    "청년내일저축계좌": "청년",
    "청년": "청년",
    "근로장려금": "장려금",
    "자녀장려금": "장려금",
    "부모급여": "육아",
    "아동수당": "육아",
    "첫만남이용권": "육아",
    "산후조리비": "육아",
    "다자녀": "육아",
}

NEGATIVE_WORDS = (
    "탈락", "오해", "날렸", "날릴", "날리", "손해", "놓친", "놓치", "폭탄", "추징", "거절", "실화", "사실은 아닙니다",
    "몰라서", "배신", "함정",
)

# 글 유형: angle(다룰 각도), title(제목 톤), layouts(어울리는 구조 키), intro(도입 방식)
CONTENT_TYPES: Dict[str, Dict[str, Any]] = {
    "policy_update": {
        "name": "개편·변경 해설",
        "angle": "올해 무엇이 바뀌었고(기준·금액·일정), 누가 영향을 받는지 해설한다. 바뀌기 전과 후를 대비하고, 해당·비해당 대상을 갈라 준다.",
        "title": "'2026년 달라진 점', '무엇이 바뀌었나' 같은 정보형 제목. 부정 어휘 금지.",
        "intro": "도입부는 '바뀐 점 한 줄 요약'으로 시작(통계 겁주기 문장 금지).",
        "layouts": ["brief_news", "compare_table", "myth_fact"],
    },
    "calendar": {
        "name": "마감일·일정 캘린더",
        "angle": "언제까지 무엇을 해야 하는지를 시간순(월별·단계별)으로 정리한다. 놓치기 쉬운 기한과 준비 시작 시점을 알려 준다.",
        "title": "'언제까지', '일정 총정리', '월별로 정리' 같은 일정형 제목. 부정 어휘 금지.",
        "intro": "도입부는 '지금 시점에서 가장 가까운 기한'으로 시작.",
        "layouts": ["step_guide", "brief_news"],
    },
    "case_calc": {
        "name": "계산 사례집",
        "angle": "구체적인 숫자 사례 3개를 직접 계산해 보여준다(가상 인물, 입력값→계산 과정→결과). 숫자는 확인된 기준 안에서만 쓴다.",
        "title": "'직접 계산해보면', '이 조건이면 얼마' 같은 숫자형 제목. 부정 어휘 금지.",
        "intro": "도입부는 첫 사례의 입력값과 결과를 먼저 보여주며 시작.",
        "layouts": ["calc_first", "case_story"],
    },
    "choose": {
        "name": "선택 가이드(A vs B)",
        "angle": "헷갈리는 두 가지 이상의 선택지를 같은 기준으로 비교하고, 상황별 추천을 제시한다.",
        "title": "'A vs B', '어느 쪽이 유리할까' 같은 비교형 제목. 부정 어휘 금지.",
        "intro": "도입부는 '무엇이 헷갈리는지'를 짚으며 시작.",
        "layouts": ["compare_table", "qa"],
    },
    "glossary": {
        "name": "용어·개념 정리",
        "angle": "이 주제를 이해할 때 자주 막히는 용어와 개념을 쉬운 말로 풀고 예시로 설명한다. 용어는 반드시 이 글의 주제에서 실제로 쓰이는 것만 고른다(다른 분야의 용어를 끌어오지 않는다).",
        "title": "'한 번에 이해하기', '쉽게 풀어보면' 같은 설명형 제목. 부정 어휘 금지.",
        "intro": "도입부는 가장 헷갈리는 용어 하나를 쉬운 비유로 풀며 시작.",
        "layouts": ["qa", "myth_fact"],
    },
    "checklist": {
        "name": "체크리스트·서류 모음",
        "angle": "신청 전에 확인할 항목과 준비 서류를 빠짐없이 정리한다. 항목마다 어디서 확인/발급하는지 알려 준다.",
        "title": "'체크리스트', '준비물 한눈에' 같은 실용형 제목. 부정 어휘 금지.",
        "intro": "도입부는 짧게, 바로 체크리스트로 들어갈 수 있게 시작.",
        "layouts": ["step_guide", "qa"],
    },
    "problem_solve": {
        "name": "탈락·거절 원인 해결",
        "angle": "많은 사람이 탈락·거절되는 구체적 원인과 해결 방법을 사례로 보여 준다.",
        "title": "",  # 기존 시스템 프롬프트의 제목 규칙을 그대로 따른다.
        "intro": "",
        "layouts": ["qa", "case_story", "myth_fact", "step_guide"],
    },
    "news_hook": {
        "name": "이번 주 소식 풀이",
        "angle": "아래 [이번 주 실제 뉴스]를 계기로, 독자에게 어떤 의미인지 풀이한다. 뉴스에 없는 수치는 지어내지 않는다.",
        "title": "'이번 주', '발표', '시행' 같은 소식형 제목. 부정 어휘 금지.",
        "intro": "도입부는 뉴스의 핵심 한 줄로 시작.",
        "layouts": ["brief_news", "qa"],
    },
}

_UNVERIFIED_CAUTION = (
    "[주의 - 검증된 팩트 시트가 없는 주제]\n"
    "이 주제는 검증된 수치 자료가 없습니다. 금액·소득 기준·기한·요율 같은 구체 수치는 위 상위 글 레퍼런스에서 "
    "여러 곳이 일치하는 경우에만 쓰고, 확신이 없으면 숫자를 쓰지 말고 '공식 공고/약관에서 확인'으로 안내하세요. "
    "특정 상품명·요금제 가격을 지어내지 마세요.\n\n"
)


def _history_path(site: str):
    return OUTPUT_DIR / f"topic_history_{site}.json"


def _load_history(site: str) -> Dict[str, List[str]]:
    try:
        data = json.loads(_history_path(site).read_text(encoding="utf-8"))
        return {"keywords": list(data.get("keywords", [])), "types": list(data.get("types", []))}
    except (OSError, ValueError, AttributeError):
        return {"keywords": [], "types": []}


def _log_path(site: str):
    return OUTPUT_DIR / f"topic_log_{site}.json"


def _load_log(site: str) -> List[Dict[str, str]]:
    """날짜가 있는 선정 기록 [{keyword, sub, type, date}]. (topic_history는 날짜가 없어 쿨다운 계산에 못 쓴다)"""
    try:
        data = json.loads(_log_path(site).read_text(encoding="utf-8"))
        return data if isinstance(data, list) else []
    except (OSError, ValueError):
        return []


def _append_log(site: str, keyword: str, content_type: str, subtopic: str) -> None:
    entries = _load_log(site)
    entries.append({"keyword": keyword, "sub": subtopic, "type": content_type, "date": datetime.now(_KST).date().isoformat()})
    try:
        OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
        _log_path(site).write_text(json.dumps(entries[-_LOG_KEEP:], ensure_ascii=False), encoding="utf-8")
    except OSError as exc:
        logger.info("주제 선정 기록 저장 실패(무시): %s", exc)


def in_cooldown(site: str, seed: str, history_keywords: List[str], titles: List[str], days: int = COOLDOWN_DAYS) -> bool:
    """이 주제를 최근(days일) 썼는가. 선정 기록(날짜 있음) + 선정 히스토리(최근 30건) + 최근 발행 제목 중 하나라도 걸리면 True."""
    if seed in history_keywords:
        return True
    cutoff = (datetime.now(_KST).date() - timedelta(days=days)).isoformat()
    if any(e.get("keyword") == seed and e.get("date", "") >= cutoff for e in _load_log(site)):
        return True
    return _title_distance(seed, titles) is not None


def record_pick(site: str, keyword: str, content_type: str, subtopic: str = "") -> None:
    _append_log(site, keyword, content_type, subtopic)
    history = _load_history(site)
    history["keywords"].append(keyword)
    history["types"].append(content_type)
    history = {k: v[-_HISTORY_KEEP:] for k, v in history.items()}
    try:
        OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
        _history_path(site).write_text(json.dumps(history, ensure_ascii=False), encoding="utf-8")
    except OSError as exc:
        logger.info("주제 히스토리 저장 실패(무시): %s", exc)
    _consume_refresh(site, keyword)  # 이 글로 '새 수치로 다시 쓰기'가 끝난 제도는 대기열에서 뺀다


def family_of(keyword: str) -> str:
    first = (keyword or "").split()[0] if (keyword or "").split() else ""
    return _FAMILY_ALIASES.get(first, first)


def _tokens(keyword: str) -> List[str]:
    return [t for t in (keyword or "").split() if len(t) >= 2]


def _title_distance(seed: str, titles: List[str]) -> Optional[int]:
    """최근 제목(최신순)에서 이 키워드가 마지막으로 나온 위치(0=가장 최근). 없으면 None.

    제목은 키워드를 그대로 쓰지 않고 바꿔 쓰는 경우가 많아(예: '인터넷 이사 이전설치' -> '인터넷 이전설치'),
    토큰이 하나만 빠져도 같은 키워드로 본다.
    """
    tokens = _tokens(seed)
    if not tokens:
        return None
    need = len(tokens) if len(tokens) == 1 else len(tokens) - 1
    for index, title in enumerate(titles):
        if sum(1 for t in tokens if t in title) >= need:
            return index
    return None


def _recency(seed: str, history_keywords: List[str], titles: List[str]) -> int:
    """클수록 오래전에 썼다는 뜻(안 쓴 키워드는 매우 큼). 히스토리와 제목 중 더 최근 기록을 쓴다."""
    distances: List[int] = []
    for offset, kw in enumerate(reversed(history_keywords)):
        if kw == seed:
            distances.append(offset)
            break
    title_distance = _title_distance(seed, titles)
    if title_distance is not None:
        distances.append(title_distance)
    return min(distances) if distances else 10_000


def pick_keyword(site: str, seeds: List[str], recent_titles: List[str]) -> str:
    """가장 오래 안 쓴 키워드를 고른다(최근 계열 제외, 오래된 상위 몇 개 중 무작위)."""
    if not seeds:
        return ""
    history = _load_history(site)
    recent_families = {family_of(k) for k in history["keywords"][-_AVOID_RECENT_FAMILIES:]}
    for title in recent_titles[:_AVOID_RECENT_FAMILIES]:
        for seed in seeds:
            if _title_distance(seed, [title]) == 0:
                recent_families.add(family_of(seed))

    scored = [(seed, _recency(seed, history["keywords"], recent_titles)) for seed in seeds]
    eligible = [item for item in scored if family_of(item[0]) not in recent_families] or scored
    eligible.sort(key=lambda item: -item[1])
    pool = [seed for seed, _ in eligible[:_PICK_FROM_OLDEST]]
    try:  # 검색 수요(자동완성·서치콘솔·검색량)가 큰 주제를 더 자주 고른다. 데이터가 없으면 모두 같은 가중치.
        from search_demand import demand_weight

        weights = [demand_weight(site, seed) for seed in pool]
        return random.choices(pool, weights=weights, k=1)[0]
    except Exception as exc:  # noqa: BLE001 - 선택 기능
        logger.info("검색 수요 가중치 적용 실패, 무작위 선택: %s", exc)
        return random.choice(pool)


# 우선 주제: 허브 "내 지원금 확인"에서 연결할 글이 아직 없는 제도. 사이트별로 앞에서부터 하나씩, 아직 안 쓴 것을
# 일반 로테이션보다 먼저 쓴다(코드에만 있어서 서버는 git pull만 하면 된다). 다 쓰면 자동으로 일반 선정으로 돌아간다.
PRIORITY_TOPICS: Dict[str, List[str]] = {
    "A": ["실업급여", "아동수당", "의료급여", "교육급여", "임신·출산 진료비 바우처"],
    "C": ["자녀 세액공제", "중소기업 취업청년 소득세 감면"],
}
# 안내/설명형 글에 어울리는 유형만 쓴다(탈락 겁주기·뉴스 풀이 제외)
_PRIORITY_TYPES = ["policy_update", "checklist", "glossary", "case_calc", "choose", "calendar"]


# 기준 자동 갱신(standards_updater)이 끝난 제도는 새 연도 수치로 글을 한 번 다시 쓴다(허브가 가장 최근 글로 연결하므로).
REFRESH_PATH = OUTPUT_DIR / "refresh_queue.json"
_TAX_REFRESH = ("월세 세액공제", "자녀 세액공제", "연금저축", "ISA", "중소기업 취업청년")
_REFRESH_KEYWORD = {
    "임신·출산": "임신·출산 진료비 바우처", "한부모": "한부모가족 지원", "연금저축": "연금저축 세액공제",
    "ISA": "ISA 비과세 한도", "중소기업 취업청년": "중소기업 취업청년 소득세 감면", "청년월세": "청년월세 지원",
}


def refresh_site(key: str) -> str:
    return "C" if any(t in key for t in _TAX_REFRESH) else "A"


def refresh_keyword(key: str) -> str:
    return _REFRESH_KEYWORD.get(key, key)


def _load_refresh() -> List[Dict[str, Any]]:
    try:
        data = json.loads(REFRESH_PATH.read_text(encoding="utf-8"))
        return data if isinstance(data, list) else []
    except (OSError, ValueError):
        return []


def _save_refresh(entries: List[Dict[str, Any]]) -> None:
    try:
        OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
        REFRESH_PATH.write_text(json.dumps(entries, ensure_ascii=False), encoding="utf-8")
    except OSError as exc:
        logger.info("재작성 대기열 저장 실패(무시): %s", exc)


def add_refresh(key: str) -> None:
    """기준이 새 연도로 갱신된 제도를 '새 수치로 글 다시 쓰기' 대기열에 넣는다."""
    entries = _load_refresh()
    if all(e.get("key") != key for e in entries):
        entries.append({"key": key})
        _save_refresh(entries)


def pick_refresh(site: str) -> str:
    for entry in _load_refresh():
        if refresh_site(entry.get("key", "")) == site:
            return refresh_keyword(entry["key"])
    return ""


def _consume_refresh(site: str, keyword: str) -> None:
    entries = _load_refresh()
    kept = [e for e in entries if not (refresh_site(e.get("key", "")) == site and refresh_keyword(e.get("key", "")) == keyword)]
    if len(kept) != len(entries):
        _save_refresh(kept)


def queue_refresh_for_changes(names: List[str], limit: int = 3, dry: bool = False) -> List[str]:
    """월간 점검에서 '수정'으로 잡힌 제도(조회수순 이름 목록) 중 우리가 이미 쓴 주제와 맞는 것을 개정 글 대기열에 넣는다.

    아직 안 쓴 주제는 일반 선정이 알아서 쓰므로 넣지 않고, 최근 14일 안에 쓴 주제도 넣지 않는다. 한 번에 limit개까지.
    """
    from trend_scraper import SITE_SEED_KEYWORDS

    site = "A"
    seeds = list(dict.fromkeys(SITE_SEED_KEYWORDS.get(site, []) + PRIORITY_TOPICS.get(site, [])))
    history = _load_history(site)["keywords"]
    log = _load_log(site)
    try:
        from post_ledger import load as load_ledger

        ledger = [e for e in load_ledger() if e.get("site") == site]
    except Exception:  # noqa: BLE001
        ledger = []
    recent_cut = (datetime.now(_KST).date() - timedelta(days=14)).isoformat()

    def written(seed: str) -> bool:
        return seed in history or any(e.get("keyword") == seed for e in log + ledger)

    def fresh(seed: str) -> bool:
        return any(e.get("keyword") == seed and e.get("date", "") >= recent_cut for e in log + ledger)

    queued: List[str] = []
    for name in names:
        flat = name.replace(" ", "")
        for seed in seeds:
            key = seed.replace(" ", "")
            first = seed.split()[0] if seed.split() else seed
            if seed in queued or not (key in flat or (len(first) >= 4 and first in flat)):
                continue
            if written(seed) and not fresh(seed):
                queued.append(seed)
                if not dry:
                    add_refresh(seed)
        if len(queued) >= limit:
            break
    return queued[:limit]


def pick_priority(site: str, history: Dict[str, List[str]], recent_titles: List[str]) -> str:
    for kw in PRIORITY_TOPICS.get(site, []):
        # 우선 주제는 한 번만 쓴다: 기록이 있으면(기간 무관) 다 쓴 것으로 본다(히스토리는 30건만 남아 예전 글을 잊기 때문)
        if in_cooldown(site, kw, history["keywords"], recent_titles, days=3650):
            continue
        return kw
    return ""


# 이미 개요를 쓴 제도의 "세부 질문" 글에 어울리는 유형(개요·개편 해설·뉴스 풀이는 제외)
_SUBTOPIC_TYPES = ["checklist", "glossary", "problem_solve", "case_calc", "choose", "calendar"]


def _recent_families(history: Dict[str, List[str]], seeds: List[str], recent_titles: List[str]) -> set:
    families = {family_of(k) for k in history["keywords"][-_AVOID_RECENT_FAMILIES:]}
    for title in recent_titles[:_AVOID_RECENT_FAMILIES]:
        for seed in seeds:
            if _title_distance(seed, [title]) == 0:
                families.add(family_of(seed))
    return families


def pick_subtopic(
    site: str, seeds: List[str], history: Dict[str, List[str]], recent_titles: List[str], cooldown_titles: List[str]
) -> Tuple[str, str]:
    """쿨다운에 걸리지 않은 새 주제가 없을 때: 이미 쓴 제도의 '아직 안 쓴 세부 질문'(자동완성)을 고른다. 없으면 ("", "")."""
    try:
        from search_demand import demand_weight, subtopic_candidates, subtopic_core
    except Exception as exc:  # noqa: BLE001
        logger.info("세부 주제 후보를 불러오지 못했습니다: %s", exc)
        return "", ""

    used_cores = {(e.get("keyword", ""), subtopic_core(e["keyword"], e["sub"])) for e in _load_log(site) if e.get("sub") and e.get("keyword")}
    families = _recent_families(history, seeds, recent_titles)
    flat_titles = [t.replace(" ", "") for t in cooldown_titles]
    candidates: List[Tuple[str, str, float]] = []
    for seed in seeds:
        if family_of(seed) in families:
            continue
        seed_key = seed.replace(" ", "").split("·")[0]
        for text, extra, volume in subtopic_candidates(seed):
            core = subtopic_core(seed, text)
            if (seed, core) in used_cores:
                continue  # 같은 세부 질문('신청'과 '신청방법' 포함)을 이미 썼다
            if core and any(seed_key in title and core in title for title in flat_titles):
                continue  # 같은 세부 질문을 다룬 글이 이미 있다
            weight = demand_weight(site, seed) * (1 + (math.log10(volume + 1) / 3 if volume else 0))
            candidates.append((seed, text, weight))
    if not candidates:
        return "", ""
    seed, text, _ = random.choices(candidates, weights=[c[2] for c in candidates], k=1)[0]
    return seed, text


def pick_content_type(site: str, news_available: bool, allowed: Optional[List[str]] = None) -> str:
    history = _load_history(site)
    recent = history["types"][-_AVOID_RECENT_TYPES:]
    pool = [t for t in CONTENT_TYPES if (t != "news_hook" or news_available) and (not allowed or t in allowed)]
    candidates = [t for t in pool if t not in recent]
    if news_available and "news_hook" in candidates:
        return "news_hook"  # 이번 주 소식은 시의성이 있어서 쓸 수 있을 때 우선
    if candidates:
        return random.choice(candidates)
    return random.choice(pool)


def negative_title_count(titles: List[str]) -> int:
    return sum(1 for t in titles[:_NEGATIVE_WINDOW] if any(w in t for w in NEGATIVE_WORDS))


def find_news_for_site(seeds: List[str], briefings: List[Dict[str, str]]) -> Optional[Dict[str, str]]:
    """사이트 키워드와 맞는 정책 뉴스 한 건과 그 키워드를 찾는다."""
    for item in briefings or []:
        text = f"{item.get('title', '')} {item.get('summary', '')}"
        for seed in seeds:
            tokens = _tokens(seed)
            if tokens and any(t in text for t in tokens if len(t) >= 3):
                return {"keyword": seed, "title": item.get("title", ""), "summary": item.get("summary", ""), "url": item.get("url", "")}
    return None


def _strip(text: str) -> str:
    import re

    return re.sub(r"\s+", " ", re.sub(r"<[^>]+>", " ", text or "")).strip()


def plan_topic(
    site: str,
    seeds: List[str],
    briefings: List[Dict[str, str]],
    recent_titles: List[str],
    forced_keyword: Optional[str] = None,
    unverified_seeds: Optional[set] = None,
    cooldown_titles: Optional[List[str]] = None,
) -> Dict[str, Any]:
    """오늘 글의 키워드·유형·프롬프트 블록·어울리는 구조 목록을 정한다.

    cooldown_titles: 90일치 발행 제목(중복 회피용). 없으면 recent_titles로 대신한다.
    """
    history = _load_history(site)
    titles90 = cooldown_titles if cooldown_titles is not None else recent_titles
    priority_pick = "" if forced_keyword else pick_priority(site, history, titles90)
    refresh_pick = "" if (forced_keyword or priority_pick) else pick_refresh(site)  # 정책 기준이 바뀐 제도: 쿨다운 무시하고 다시 쓴다
    priority = priority_pick or refresh_pick
    news = None if (forced_keyword or priority) else find_news_for_site(seeds, briefings)
    if news:
        families = {family_of(k) for k in history["keywords"][-_AVOID_RECENT_FAMILIES:]}
        if family_of(news["keyword"]) in families or _title_distance(news["keyword"], recent_titles[:_AVOID_RECENT_FAMILIES]) == 0:
            news = None

    content_type = pick_content_type(site, news_available=news is not None, allowed=_PRIORITY_TYPES if priority else None)
    if content_type != "news_hook":
        news = None
    subtopic = ""
    if forced_keyword or priority or news:
        keyword = forced_keyword or priority or news["keyword"]  # type: ignore[index]
    else:
        fresh = [s for s in seeds if not in_cooldown(site, s, history["keywords"], titles90)]
        if fresh:
            keyword = pick_keyword(site, fresh, recent_titles)
        else:
            keyword, subtopic = pick_subtopic(site, seeds, history, recent_titles, titles90)
            if keyword:
                logger.info("[Site %s] 새 주제가 쿨다운 중이라 세부 주제로 작성: %s / %s", site, keyword, subtopic)
                if content_type not in _SUBTOPIC_TYPES:
                    content_type = pick_content_type(site, news_available=False, allowed=_SUBTOPIC_TYPES)
            else:
                keyword = pick_keyword(site, seeds, recent_titles)  # 세부 주제 후보도 없으면 기존 방식(가장 오래된 것)
    if priority:
        logger.info("[Site %s] %s 주제 큐에서 선정: %s", site, "정책 변경 재작성" if refresh_pick else "우선", priority)

    spec = CONTENT_TYPES[content_type]
    block = ""
    if content_type != "problem_solve":
        block += (
            f"[이번 글의 유형 - {spec['name']}]\n"
            f"- 다룰 각도: {spec['angle']}\n"
            f"- 제목 톤: {spec['title']}\n"
        )
        if spec["intro"]:
            block += f"- 도입: {spec['intro']}\n"
        block += (
            "(유형 지시는 '무엇을 어떤 각도로 다룰지', 구조 지시는 '컴포넌트를 어떤 순서로 배치할지'입니다. 둘이 충돌하면 "
            "구조 지시의 컴포넌트 규칙을 따르되 각도와 제목 톤은 유형 지시를 따르세요. 시스템 프롬프트의 FOMO·탈락 겁주기 "
            "도입 규칙은 이번 글에서는 적용하지 않습니다.)\n\n"
        )
    elif negative_title_count(recent_titles) >= _NEGATIVE_LIMIT:
        block += (
            "[제목 톤 제한]\n"
            f"최근 제목 {_NEGATIVE_WINDOW}개 중 {negative_title_count(recent_titles)}개가 탈락·오해·손해 같은 부정 어휘를 썼습니다. "
            "이번 제목에는 그런 어휘를 쓰지 말고, 정보형·숫자형·질문형으로 쓰세요.\n\n"
        )

    if content_type == "news_hook" and news:
        block += (
            "[이번 주 실제 뉴스]\n"
            f"- 제목: {_strip(news['title'])[:150]}\n- 요약: {_strip(news['summary'])[:400]}\n"
            "뉴스에 적힌 사실만 쓰고, 적혀 있지 않은 금액·일정·대상은 지어내지 마세요.\n\n"
        )

    if refresh_pick:
        block += (
            "[이번 글을 다시 쓰는 이유 - 정책 변경]\n"
            f"'{keyword}'는 이미 글을 쓴 제도인데 기준·금액·일정이 바뀌어 다시 씁니다. 이전 글과 같은 개요를 반복하지 말고 "
            "'무엇이 달라졌는지'(바뀐 점, 바뀌기 전과 후, 해당·비해당 대상)를 중심에 두세요. 달라진 내용은 검증된 사실 메모와 "
            "공식 자료에 있는 것만 쓰고, 확인되지 않은 변경은 지어내지 마세요.\n\n"
        )
    if subtopic:
        block += (
            "[이번 글의 세부 주제]\n"
            f"- 이번 글은 '{keyword}' 제도 전체 안내가 아니라, 독자가 실제로 검색하는 질문 '{subtopic}'에 답하는 글입니다. "
            "제목과 첫 단락에서 이 질문을 바로 다루고, 글 전체를 이 질문 중심으로 구성하세요.\n"
            f"- 이미 '{keyword}'의 개요 글이 있으니, 제도 소개·자격 요건을 처음부터 다시 설명하지 말고 이 질문에 필요한 내용만 깊게 다루세요.\n"
            "- 금액·기한 같은 수치는 검증된 사실 메모와 공식 자료 안에서만 쓰세요.\n\n"
        )

    if unverified_seeds and keyword in unverified_seeds and not get_fact_sheet(keyword):
        block += _UNVERIFIED_CAUTION

    try:  # 독자가 실제로 검색하는 말(자동완성·서치콘솔·검색량) - 데이터가 있을 때만
        from search_demand import prompt_block

        block += prompt_block(site, keyword)
    except Exception as exc:  # noqa: BLE001 - 선택 기능
        logger.info("검색 수요 블록 생략: %s", exc)

    return {
        "keyword": keyword,
        "subtopic": subtopic,
        "content_type": content_type,
        "block": block,
        "layouts": spec["layouts"],
    }
