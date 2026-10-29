"""Gemini(Google AI Studio) API 키 여러 개를 순서대로 돌려 쓰는 키 풀.

설정: .env 의 GEMINI_API_KEYS=키1,키2,키3,키4,키5 (쉼표·공백·줄바꿈 구분). 예전 GOOGLE_AI_STUDIO_API_KEY 도 맨 뒤에 합쳐 쓴다.
동작: 마지막으로 잘 된 키부터 쓰고, 한도 초과(429)·잘못된 키(400/403)면 그 키를 쉬게 하고 다음 키로 넘어간다.
- 분당 한도 초과: 응답이 알려 준 시간(없으면 65초) 동안 그 키를 쉬게 한다.
- 일일 한도 초과: 다음 한도 초기화 시각(UTC 08:00, 태평양 자정 부근)까지 쉬게 한다.
- 잘못된 키·권한 오류: 24시간 쉬게 하고 로그로 알린다.
상태(어느 키가 언제까지 쉬는지)는 data/output/gemini_key_state.json 에 키 대신 지문(해시 앞 10자)으로만 저장한다.
"""
from __future__ import annotations

import hashlib
import json
import os
import re
from datetime import datetime, timedelta, timezone
from typing import Any, Callable, List, Optional

from config import OUTPUT_DIR
from utils.logger import get_logger

logger = get_logger(__name__)

STATE_PATH = OUTPUT_DIR / "gemini_key_state.json"
DEFAULT_COOLDOWN = 65
BAD_KEY_COOLDOWN = 24 * 3600


def _now() -> datetime:
    return datetime.now(timezone.utc)


def fingerprint(key: str) -> str:
    return hashlib.sha256(key.encode("utf-8")).hexdigest()[:10]


def load_keys() -> List[str]:
    """.env 에서 키를 읽어 중복 없이 순서대로 돌려준다."""
    raw = os.environ.get("GEMINI_API_KEYS", "") + "," + os.environ.get("GOOGLE_AI_STUDIO_API_KEY", "")
    keys: List[str] = []
    for k in re.split(r"[,\s;]+", raw):
        k = k.strip().strip('"').strip("'")
        if k and k not in keys:
            keys.append(k)
    return keys


def has_keys() -> bool:
    return bool(load_keys())


def _load_state() -> dict:
    try:
        data = json.loads(STATE_PATH.read_text(encoding="utf-8"))
        return data if isinstance(data, dict) else {}
    except (OSError, ValueError):
        return {}


def _save_state(state: dict) -> None:
    try:
        STATE_PATH.parent.mkdir(parents=True, exist_ok=True)
        STATE_PATH.write_text(json.dumps(state, ensure_ascii=False), encoding="utf-8")
    except OSError as exc:
        logger.info("Gemini 키 상태 저장 실패(무시): %s", exc)


def next_daily_reset(now: Optional[datetime] = None) -> datetime:
    """무료 한도의 일일 초기화(태평양 시간 자정)에 맞춘 다음 UTC 08:00. 서머타임이면 1시간 늦게 풀리는 쪽으로 안전하게 잡는다."""
    now = now or _now()
    reset = now.replace(hour=8, minute=5, second=0, microsecond=0)
    return reset if reset > now else reset + timedelta(days=1)


def _available(keys: List[str], state: dict, now: datetime) -> List[str]:
    bad = state.get("bad_until", {})
    ok = [k for k in keys if not (bad.get(fingerprint(k)) and datetime.fromisoformat(bad[fingerprint(k)]) > now)]
    last = state.get("last_ok")
    ok.sort(key=lambda k: 0 if fingerprint(k) == last else 1)  # 마지막으로 잘 된 키부터(정렬은 안정적이라 나머지는 입력 순서 유지)
    return ok


def classify(status: int, body: str, now: Optional[datetime] = None) -> Optional[int]:
    """응답이 '이 키를 쉬게 해야 하는 오류'면 쉬게 할 초를 돌려주고, 아니면 None(키 문제 아님)."""
    now = now or _now()
    low = (body or "").lower()
    if status == 429 or "resource_exhausted" in low:
        if "perday" in low.replace(" ", "").replace("_", "") or "per day" in low or "daily" in low:
            return max(60, int((next_daily_reset(now) - now).total_seconds()))
        m = re.search(r'"retrydelay"\s*:\s*"(\d+(?:\.\d+)?)s"', low)
        return int(float(m.group(1))) + 5 if m else DEFAULT_COOLDOWN
    if status in (400, 401, 403) and ("api key" in low or "api_key" in low or "permission" in low or "denied" in low or "leaked" in low):
        return BAD_KEY_COOLDOWN
    return None


def call_with_rotation(request: Callable[[str], Any]) -> Any:
    """request(key) -> 응답(.status_code, .text) 또는 None. 키를 돌려가며 성공한 응답을 돌려준다.

    모든 키가 쉬거나 실패하면 마지막 응답(없으면 None)을 돌려준다.
    """
    keys = load_keys()
    if not keys:
        return None
    now = _now()
    state = _load_state()
    candidates = _available(keys, state, now)
    if not candidates:
        logger.warning("Gemini 키 %s개가 모두 한도/오류로 쉬는 중입니다.", len(keys))
        return None
    last_resp = None
    for key in candidates:
        resp = request(key)
        last_resp = resp
        if resp is None:  # 네트워크 오류 등은 키 문제가 아니므로 쉬게 하지 않고 다음 키로
            continue
        if resp.status_code == 200:
            state["last_ok"] = fingerprint(key)
            state.get("bad_until", {}).pop(fingerprint(key), None)
            _save_state(state)
            return resp
        cooldown = classify(resp.status_code, getattr(resp, "text", "") or "", now)
        if cooldown is None:
            return resp  # 요청 자체의 문제(프롬프트 거부 등) - 다른 키로 바꿔도 소용없다
        until = (now + timedelta(seconds=cooldown)).isoformat()
        state.setdefault("bad_until", {})[fingerprint(key)] = until
        _save_state(state)
        logger.warning("Gemini 키(...%s) %s초 쉼 (HTTP %s) - 다음 키로 전환합니다.", key[-4:], cooldown, resp.status_code)
    return last_resp


def status_lines() -> List[str]:
    """키 상태를 사람이 읽기 좋게(키 값은 뒤 4자리만) 돌려준다."""
    keys = load_keys()
    if not keys:
        return ["Gemini 키가 설정돼 있지 않습니다. (.env 의 GEMINI_API_KEYS)"]
    state = _load_state()
    now = _now()
    last = state.get("last_ok")
    lines = []
    for i, k in enumerate(keys, 1):
        until = state.get("bad_until", {}).get(fingerprint(k))
        if until and datetime.fromisoformat(until) > now:
            mins = int((datetime.fromisoformat(until) - now).total_seconds() // 60) + 1
            note = f"쉬는 중 (약 {mins}분 뒤 다시 사용)"
        else:
            note = "사용 가능"
        mark = " ← 마지막으로 성공" if fingerprint(k) == last else ""
        lines.append(f"키 {i} (…{k[-4:]}): {note}{mark}")
    return lines
