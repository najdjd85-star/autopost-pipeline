"""스레드(Threads) 액세스 토큰 관리: 60일짜리 장기 토큰을 만료 전에 자동으로 연장하고, 만료되면 텔레그램으로 알린다.

- 연장: GET https://graph.threads.net/refresh_access_token?grant_type=th_refresh_token (아직 유효하고 발급 24시간이 지난 장기 토큰만 가능)
  연장한 토큰은 data/output/threads_token.json 에 저장한다(.env 는 데몬 계정이 못 쓸 수 있고 깃에도 안 올라가야 해서).
- 어떤 토큰을 쓰나: .env 의 THREADS_ACCESS_TOKEN 이 그대로면 저장된(연장된) 토큰, .env 를 새 토큰으로 바꾸면 그 새 토큰을 다시 기준으로 삼는다.
- 데몬이 하루 한 번 daily_check() 를 부른다: 7일마다 연장, 토큰이 죽었으면 하루 한 번 알림.
- 수동: venv/bin/python threads_token.py   (상태 확인 + 바로 연장 시도)
"""
from __future__ import annotations

import hashlib
import json
import time
from datetime import datetime, timedelta, timezone
from typing import Optional

import requests

from config import OUTPUT_DIR, settings
from utils.logger import get_logger

logger = get_logger(__name__)

STORE = OUTPUT_DIR / "threads_token.json"
REFRESH_EVERY_DAYS = 7
API = "https://graph.threads.net"


def _fp(token: str) -> str:
    return hashlib.sha256((token or "").encode()).hexdigest()[:16]


def _load() -> dict:
    try:
        return json.loads(STORE.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return {}


def _save(data: dict) -> None:
    STORE.parent.mkdir(parents=True, exist_ok=True)
    STORE.write_text(json.dumps(data, ensure_ascii=False, indent=1), encoding="utf-8")


def current() -> str:
    """지금 써야 할 스레드 토큰(연장된 것이 있으면 그것)."""
    env = settings.threads_access_token or ""
    data = _load()
    if data.get("token") and data.get("env_fp") == _fp(env):
        return data["token"]
    return env


def check() -> Optional[str]:
    """토큰이 살아 있으면 계정 이름, 죽었으면 None."""
    tok = current()
    if not tok:
        return None
    try:
        r = requests.get(f"{API}/v1.0/me", params={"fields": "username", "access_token": tok}, timeout=20)
    except requests.RequestException:
        return "?"   # 네트워크 문제는 토큰 문제로 보지 않는다
    if r.status_code == 200:
        return r.json().get("username") or "?"
    return None


def refresh() -> str:
    """토큰을 60일 더 연장한다. 결과 문장을 돌려준다."""
    env = settings.threads_access_token or ""
    tok = current()
    if not tok:
        return "스레드 토큰 없음"
    try:
        r = requests.get(f"{API}/refresh_access_token", params={"grant_type": "th_refresh_token", "access_token": tok}, timeout=20)
    except requests.RequestException as exc:
        return f"스레드 토큰 연장 실패(네트워크): {exc.__class__.__name__}"
    if r.status_code != 200:
        msg = (r.json().get("error", {}) if r.headers.get("content-type", "").startswith("application/json") else {}).get("message", r.text[:120])
        return f"스레드 토큰 연장 실패(HTTP {r.status_code}): {msg[:150]}"
    body = r.json()
    expires = datetime.now(timezone.utc) + timedelta(seconds=int(body.get("expires_in") or 0))
    _save({"token": body["access_token"], "env_fp": _fp(env), "refreshed": datetime.now(timezone.utc).isoformat(timespec="seconds"),
           "expires_at": expires.isoformat(timespec="seconds")})
    return f"스레드 토큰 연장 완료(만료 {expires:%Y-%m-%d})"


def daily_check() -> None:
    """데몬이 하루 한 번 부른다. 7일마다 연장하고, 토큰이 죽었으면 하루 한 번 텔레그램으로 알린다."""
    data = _load()
    env_changed = data.get("env_fp") != _fp(settings.threads_access_token or "")
    try:
        last = datetime.fromisoformat(data["refreshed"])
    except (KeyError, ValueError):
        last = datetime.fromtimestamp(0, timezone.utc)
    if env_changed or datetime.now(timezone.utc) - last > timedelta(days=REFRESH_EVERY_DAYS):
        msg = refresh()
        logger.info(msg)
        if "완료" in msg:
            return
    if check() is None:
        data = _load()
        today = time.strftime("%Y-%m-%d")
        if data.get("alerted") != today:
            data["alerted"] = today
            _save(data)
            try:
                from utils.telegram_notify import send_message_sync

                send_message_sync("⚠️ 스레드 토큰이 만료돼 스레드 글이 올라가지 않고 있어요.\n"
                                  "새 토큰을 발급해 서버에서 `venv/bin/python scripts/set_env_secrets.py THREADS_ACCESS_TOKEN` 으로 넣고 "
                                  "`touch deploy/.restart_requested` 해 주세요. 그다음부터는 자동으로 연장돼요.")
            except Exception as exc:  # noqa: BLE001
                logger.info("텔레그램 알림 실패(무시): %s", exc)


if __name__ == "__main__":
    name = check()
    print("현재 토큰:", f"정상 (@{name})" if name else "만료 또는 없음")
    if name:
        print(refresh())
