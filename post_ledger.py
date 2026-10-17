"""발행 기록(원장) - 어떤 주제의 글이 어느 주소로 발행됐는지 남겨, 허브의 "자세한 글 보기" 링크를 정확히 잇는다.

글 제목에 제도 이름이 들어 있는지 추측하는 대신, 발행 시점에 "이 글의 주제 키워드 = 아동수당, 주소 = ..."를 기록해 둔다.
허브 생성기(hub_builder)가 이 기록에서 제도별 가장 최근 글을 찾는다. 기록이 없는 옛 글은 제목 추측으로 보완한다.
파일: data/output/post_ledger.json
"""
from __future__ import annotations

import json
from datetime import datetime, timedelta, timezone
from typing import Any, Dict, List, Optional, Sequence

from config import OUTPUT_DIR
from utils.logger import get_logger

logger = get_logger(__name__)

LEDGER_PATH = OUTPUT_DIR / "post_ledger.json"
KEEP = 400
KST = timezone(timedelta(hours=9))


def load() -> List[Dict[str, Any]]:
    try:
        data = json.loads(LEDGER_PATH.read_text(encoding="utf-8"))
        return data if isinstance(data, list) else []
    except (OSError, ValueError):
        return []


def record_post(site: str, keyword: str, title: str, url: str, content_type: str = "", date: Optional[str] = None) -> None:
    """발행 직후 호출한다. 실패해도 발행 흐름을 막지 않는다."""
    if not url:
        return
    entries = [e for e in load() if e.get("url") != url]
    entries.append(
        {
            "site": site,
            "keyword": keyword or "",
            "title": title or "",
            "url": url,
            "content_type": content_type or "",
            "date": date or datetime.now(KST).date().isoformat(),
        }
    )
    try:
        OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
        LEDGER_PATH.write_text(json.dumps(entries[-KEEP:], ensure_ascii=False), encoding="utf-8")
    except OSError as exc:
        logger.info("발행 기록 저장 실패(무시): %s", exc)


def latest_for(terms: Sequence[str], entries: Optional[List[Dict[str, Any]]] = None) -> Optional[Dict[str, Any]]:
    """주제 키워드(또는 제목)에 terms 중 하나가 들어 있는 가장 최근 기록."""
    hits = [e for e in (entries if entries is not None else load()) if any(t in e.get("keyword", "") for t in terms)]
    return max(hits, key=lambda e: e.get("date", ""), default=None)
