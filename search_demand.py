"""검색 수요 데이터: 사람들이 실제로 검색하는 말을 모아 주제 선정과 글 작성에 반영한다.

세 가지 출처를 쓰고, 있는 것만 쓴다(없어도 기존 방식 그대로 동작).
1) 구글·네이버 자동완성: 무료, 키 불필요. 시드 키워드마다 실제로 붙여 검색하는 말을 모은다.
2) 서치콘솔: 우리 사이트가 이미 노출된 검색어와 순위. 순위가 낮은데 노출이 있는 주제를 더 쓰게 한다.
3) 네이버 검색광고 키워드 도구(선택): 월간 검색량 수치. NAVER_AD_* 키를 넣었을 때만 쓴다.

결과는 data/output/search_demand.json 에 저장하고, 서버 데몬이 하루 한 번(한국 09:50) 오래된 것만 갱신한다. 토큰은 쓰지 않는다.
"""
from __future__ import annotations

import base64
import hashlib
import hmac
import json
import math
import re
import time
from datetime import date, datetime, timedelta, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional
from urllib.parse import urlparse

from config import OUTPUT_DIR, settings
from utils.http import safe_get
from utils.logger import get_logger

logger = get_logger(__name__)

DEMAND_PATH = OUTPUT_DIR / "search_demand.json"
GOOGLE_SUGGEST_URL = "https://suggestqueries.google.com/complete/search"
NAVER_AD_URL = "https://api.searchad.naver.com/keywordstool"
KEYWORD_REFRESH_DAYS = 7
GSC_REFRESH_HOURS = 20
USE_MAX_AGE_DAYS = 21  # 이보다 오래된 수요 데이터는 믿지 않고 무시한다
REQUEST_GAP_SECONDS = 0.6
_SITE_KEYS = ("A", "B", "C")


def _now() -> datetime:
    return datetime.now(timezone.utc)


def _load() -> Dict[str, Any]:
    try:
        data = json.loads(DEMAND_PATH.read_text(encoding="utf-8"))
        return data if isinstance(data, dict) else {}
    except (OSError, ValueError):
        return {}


def _save(data: Dict[str, Any]) -> None:
    try:
        OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
        DEMAND_PATH.write_text(json.dumps(data, ensure_ascii=False), encoding="utf-8")
    except OSError as exc:
        logger.info("검색 수요 데이터 저장 실패(무시): %s", exc)


def _age_days(iso: str) -> float:
    try:
        return (_now() - datetime.fromisoformat(iso)).total_seconds() / 86400
    except (TypeError, ValueError):
        return 10_000.0


def _tokens(text: str) -> List[str]:
    return [t for t in (text or "").replace("·", " ").split() if len(t) >= 2]


def _related(keyword: str, candidate: str) -> bool:
    """자동완성 결과가 시드 키워드와 관련 있는지(시드의 핵심 단어를 하나라도 포함) 본다."""
    cand = (candidate or "").replace(" ", "")
    return any(t.replace(" ", "") in cand for t in _tokens(keyword))


# ---------------------------------------------------------------------------
# 1. 자동완성
# ---------------------------------------------------------------------------
def _google_suggest(keyword: str) -> List[str]:
    resp = safe_get(GOOGLE_SUGGEST_URL, params={"client": "firefox", "hl": "ko", "q": keyword}, timeout=6)
    if resp is None or resp.status_code != 200:
        return []
    try:
        data = json.loads(resp.text)
        return [s for s in data[1] if isinstance(s, str)]
    except (ValueError, IndexError, TypeError):
        return []


_AMOUNT_RE = re.compile(r"\d[\d,]*\s*(만|억|천)?\s*원|\d+\s*만")  # "아동수당 100 만원"처럼 금액이 붙은 자동완성은 글에 근거 없는 수치를 부르므로 뺀다


def suggestions_for(keyword: str, limit: int = 12) -> List[str]:
    from keyword_expander import _naver_autocomplete

    merged: List[str] = []
    for text in _naver_autocomplete(keyword, 12) + _google_suggest(keyword):
        text = text.strip()
        if text and text != keyword and text not in merged and _related(keyword, text) and not _AMOUNT_RE.search(text):
            merged.append(text)
    return merged[:limit]


# ---------------------------------------------------------------------------
# 3. 네이버 검색광고 키워드 도구(월간 검색량) - 선택
# ---------------------------------------------------------------------------
def naver_ad_configured() -> bool:
    return bool(settings.naver_ad_api_key and settings.naver_ad_secret_key and settings.naver_ad_customer_id)


def _to_count(value: Any) -> int:
    if isinstance(value, (int, float)):
        return int(value)
    if isinstance(value, str):
        text = value.replace(",", "").strip()
        if "<" in text:
            return 5  # 네이버는 10 미만을 "< 10"으로 준다
        try:
            return int(float(text))  # 숫자가 문자열("1420", "1420.0")로 오는 경우
        except ValueError:
            return 0
    return 0


def _item_volume(item: Dict[str, Any]) -> int:
    """항목의 월간 검색량(PC+모바일). 네이버 필드 이름은 monthlyPcQcCnt/monthlyMobileQcCnt(QryCnt가 아님)."""
    pc = item.get("monthlyPcQcCnt", item.get("monthlyPcQryCnt"))
    mobile = item.get("monthlyMobileQcCnt", item.get("monthlyMobileQryCnt"))
    return _to_count(pc) + _to_count(mobile)


def _naver_ad_raw(hints: List[str]) -> Any:
    """점검용: 키워드 도구의 응답(상태 코드, 앞쪽 항목)을 그대로 돌려준다. 키는 포함되지 않는다."""
    timestamp = str(int(time.time() * 1000))
    signature = base64.b64encode(
        hmac.new(settings.naver_ad_secret_key.encode(), f"{timestamp}.GET./keywordstool".encode(), hashlib.sha256).digest()
    ).decode()
    resp = safe_get(
        NAVER_AD_URL,
        params={"hintKeywords": ",".join(h.replace(" ", "") for h in hints), "showDetail": 1},
        headers={"X-Timestamp": timestamp, "X-API-KEY": settings.naver_ad_api_key, "X-Customer": settings.naver_ad_customer_id, "X-Signature": signature},
        timeout=12,
    )
    if resp is None:
        return "응답 없음"
    return resp.status_code, resp.text[:600]


def _naver_ad_items(hints: List[str]) -> List[Dict[str, Any]]:
    """키워드 도구 응답의 항목 목록(점검용). 실패하면 빈 리스트."""
    timestamp = str(int(time.time() * 1000))
    signature = base64.b64encode(
        hmac.new(settings.naver_ad_secret_key.encode(), f"{timestamp}.GET./keywordstool".encode(), hashlib.sha256).digest()
    ).decode()
    resp = safe_get(
        NAVER_AD_URL,
        params={"hintKeywords": ",".join(h.replace(" ", "") for h in hints), "showDetail": 1},
        headers={"X-Timestamp": timestamp, "X-API-KEY": settings.naver_ad_api_key, "X-Customer": settings.naver_ad_customer_id, "X-Signature": signature},
        timeout=12,
    )
    try:
        return resp.json().get("keywordList", []) if resp is not None and resp.status_code == 200 else []
    except ValueError:
        return []


def _naver_ad_volumes(hints: List[str]) -> Dict[str, int]:
    """힌트 키워드(최대 5개)와 연관 키워드의 월간 검색량(PC+모바일). 공백은 네이버 규칙대로 제거해 키로 쓴다."""
    timestamp = str(int(time.time() * 1000))
    uri = "/keywordstool"
    signature = base64.b64encode(
        hmac.new(settings.naver_ad_secret_key.encode(), f"{timestamp}.GET.{uri}".encode(), hashlib.sha256).digest()
    ).decode()
    resp = safe_get(
        NAVER_AD_URL,
        params={"hintKeywords": ",".join(h.replace(" ", "") for h in hints), "showDetail": 1},
        headers={
            "X-Timestamp": timestamp,
            "X-API-KEY": settings.naver_ad_api_key,
            "X-Customer": settings.naver_ad_customer_id,
            "X-Signature": signature,
        },
        timeout=12,
    )
    if resp is None or resp.status_code != 200:
        logger.info("네이버 검색광고 키워드 도구 조회 실패 (status=%s)", getattr(resp, "status_code", "no_response"))
        return {}
    try:
        items = resp.json().get("keywordList", [])
    except ValueError:
        return {}
    volumes: Dict[str, int] = {}
    for i in items:
        key = i.get("relKeyword")
        if key:  # 같은 키워드가 여러 번 올 수 있어(힌트가 여러 개일 때) 마지막 값으로 덮지 않고 가장 큰 값을 쓴다
            volumes[key] = max(volumes.get(key, 0), _item_volume(i))
    return volumes


# ---------------------------------------------------------------------------
# 2. 서치콘솔
# ---------------------------------------------------------------------------
def fetch_gsc_queries(site: str, days: int = 28) -> List[Dict[str, Any]]:
    """사이트(A/B/C)의 최근 N일 검색어별 노출·클릭·평균 순위. 서비스 계정이 없거나 실패하면 빈 리스트."""
    key_path = Path(settings.google_key_path)
    wp_url = settings.sites[site].wp_url if site in settings.sites else ""
    host = urlparse(wp_url).hostname if wp_url else ""
    if not key_path.exists() or not host:
        return []
    try:
        from google.oauth2 import service_account
        from googleapiclient.discovery import build

        creds = service_account.Credentials.from_service_account_file(
            str(key_path), scopes=["https://www.googleapis.com/auth/webmasters.readonly"]
        )
        service = build("searchconsole", "v1", credentials=creds, cache_discovery=False)
        end = date.today()
        body = {
            "startDate": (end - timedelta(days=days)).isoformat(),
            "endDate": end.isoformat(),
            "dimensions": ["query"],
            "rowLimit": 500,
        }
        rows = service.searchanalytics().query(siteUrl=f"sc-domain:{host}", body=body).execute().get("rows", [])
    except Exception as exc:  # noqa: BLE001 - 선택 기능
        logger.info("[Site %s] 서치콘솔 검색어 조회 실패(무시): %s", site, exc)
        return []
    return [
        {
            "query": r["keys"][0],
            "impressions": int(r.get("impressions", 0)),
            "clicks": int(r.get("clicks", 0)),
            "position": round(float(r.get("position", 0)), 1),
        }
        for r in rows
    ]


# ---------------------------------------------------------------------------
# 갱신
# ---------------------------------------------------------------------------
def refresh_keywords(seeds: List[str], force: bool = False) -> int:
    """시드 키워드의 자동완성·월간 검색량을 모은다. 7일 안에 모은 것은 건너뛴다. 처리한 키워드 수를 돌려준다."""
    data = _load()
    store: Dict[str, Any] = data.setdefault("keywords", {})
    todo = [s for s in dict.fromkeys(seeds) if force or _age_days(store.get(s, {}).get("at", "")) >= KEYWORD_REFRESH_DAYS]
    for seed in todo:
        store[seed] = {"suggest": suggestions_for(seed), "volume": store.get(seed, {}).get("volume"), "at": _now().isoformat(timespec="seconds")}
        time.sleep(REQUEST_GAP_SECONDS)

    if todo and naver_ad_configured():
        for i in range(0, len(todo), 5):
            batch = todo[i : i + 5]
            volumes = _naver_ad_volumes(batch)
            for seed in batch:
                vol = volumes.get(seed.replace(" ", ""))
                if vol is not None:
                    store[seed]["volume"] = vol
                related = sorted(
                    ((k, v) for k, v in volumes.items() if k != seed.replace(" ", "") and _related(seed, k)),
                    key=lambda kv: -kv[1],
                )[:6]
                store[seed]["related_volume"] = [{"q": k, "v": v} for k, v in related]
            time.sleep(REQUEST_GAP_SECONDS)

    if todo:
        data["keywords_updated"] = _now().isoformat(timespec="seconds")
        _save(data)
    return len(todo)


def refresh_gsc(force: bool = False) -> int:
    data = _load()
    gsc: Dict[str, Any] = data.setdefault("gsc", {})
    done = 0
    for site in _SITE_KEYS:
        entry = gsc.get(site, {})
        if not force and _age_days(entry.get("at", "")) * 24 < GSC_REFRESH_HOURS:
            continue
        rows = fetch_gsc_queries(site)
        if rows:
            gsc[site] = {"at": _now().isoformat(timespec="seconds"), "rows": rows}
            done += 1
    if done:
        _save(data)
    return done


def run_daily(force: bool = False) -> Dict[str, int]:
    """서버 데몬이 매일 호출한다. 필요한 것만 갱신하고 토큰은 쓰지 않는다."""
    from trend_scraper import SITE_SEED_KEYWORDS

    seeds = [s for site in _SITE_KEYS for s in SITE_SEED_KEYWORDS.get(site, [])]
    result = {"keywords": refresh_keywords(seeds, force=force), "gsc_sites": refresh_gsc(force=force)}
    logger.info("검색 수요 갱신: %s", result)
    return result


# ---------------------------------------------------------------------------
# 사용: 주제 선정 가중치 + 프롬프트 블록
# ---------------------------------------------------------------------------
def _fresh_keyword_entry(keyword: str) -> Dict[str, Any]:
    entry = _load().get("keywords", {}).get(keyword, {})
    return entry if entry and _age_days(entry.get("at", "")) <= USE_MAX_AGE_DAYS else {}


def _gsc_rows(site: str) -> List[Dict[str, Any]]:
    entry = _load().get("gsc", {}).get(site, {})
    return entry.get("rows", []) if entry and _age_days(entry.get("at", "")) <= USE_MAX_AGE_DAYS else []


def _matching_gsc(site: str, keyword: str) -> List[Dict[str, Any]]:
    tokens = _tokens(keyword)
    rows = [r for r in _gsc_rows(site) if any(t.replace(" ", "") in r["query"].replace(" ", "") for t in tokens)]
    return sorted(rows, key=lambda r: -r["impressions"])


def demand_weight(site: str, keyword: str) -> float:
    """주제 선정 가중치(기본 1.0). 자동완성이 풍부하고, 월간 검색량이 크고, 이미 노출되는데 순위가 낮은 주제일수록 크다."""
    weight = 1.0
    entry = _fresh_keyword_entry(keyword)
    if entry:
        weight += min(len(entry.get("suggest", [])), 10) / 30  # 자동완성은 인기 순위를 말해 주지 못하므로 최대 +0.33만(없는 주제를 살짝 뒤로 미는 정도)
        volume = entry.get("volume")
        if volume:
            weight += min(math.log10(volume + 1) / 3, 2.0)  # 1,000건 ≈ +1, 100,000건 ≈ +1.7
    rows = _matching_gsc(site, keyword)
    if rows:
        impressions = sum(r["impressions"] for r in rows)
        weight += min(impressions / 30, 1.0)  # 이미 노출되는 주제는 밀어준다
        if any(r["position"] > 8 and r["impressions"] >= 3 for r in rows):
            weight += 0.5  # 노출은 되는데 1페이지 밖 - 글을 더 쓰면 올라갈 여지
    return round(weight, 2)


def prompt_block(site: str, keyword: str) -> str:
    """글 작성 프롬프트에 붙일 '독자가 실제로 검색하는 말' 블록. 데이터가 없으면 빈 문자열."""
    entry = _fresh_keyword_entry(keyword)
    suggest = entry.get("suggest", [])[:8]
    related = entry.get("related_volume", [])[:5]
    rows = [r for r in _matching_gsc(site, keyword) if r["impressions"] >= 2][:5]
    if not (suggest or related or rows):
        return ""
    lines = ["[독자가 실제로 검색하는 말 - 자동완성·검색 데이터]"]
    if suggest:
        lines.append("- 자동완성: " + " / ".join(suggest))
    if related:
        lines.append("- 월간 검색량이 큰 연관어: " + ", ".join(f"{r['q']}({r['v']:,}회)" for r in related))
    if rows:
        lines.append("- 우리 사이트가 이미 노출된 검색어: " + ", ".join(f"{r['query']}(노출 {r['impressions']}, 순위 {r['position']})" for r in rows))
    lines.append(
        "이 중 검색 의도가 가장 분명한 표현을 제목이나 소제목(H2)에 자연스럽게 쓰고, 이 말들이 실제로 묻는 질문에 글 안에서 답하세요. "
        "목록을 그대로 나열하지 말고, 목록에 없는 금액·조건·날짜를 지어내지 마세요(수치는 검증된 사실 메모와 공식 자료만 쓰세요).\n\n"
    )
    return "\n".join(lines)
