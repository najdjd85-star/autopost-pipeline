"""Threads 게시 보호 장치 - Meta의 "비정상적인 활동" 감지를 다시 건드리지 않도록 게시를 사람처럼 흩뿌린다.

기존에는 글이 발행되는 즉시 3개 사이트 글이 몇 분 간격으로 스레드에 올라갔고, 본문 직후 링크 댓글이 달렸다.
서버가 해외(싱가포르) 데이터센터 IP인 점과 겹쳐 자동화로 보이기 쉬운 패턴이라서 아래처럼 바꾼다.

1. 큐: 발행 시점에는 스레드 게시를 "예약"만 하고, 데몬이 5분마다 때가 된 것을 한 건씩 올린다.
2. 간격/시간대: 글 사이 75~135분 간격 + 무작위 지터, 한국 시간 08:00~22:30에만 게시, 하루 최대 3건.
3. 댓글 지연: 본문을 올린 뒤 40~110초 뒤에 링크 댓글을 단다.
4. 차단기: Meta가 차단/제한 응답(API access blocked, 토큰/요청 한도 오류)을 주거나 연속 실패하면 일정 시간 스레드 게시를
   멈추고 텔레그램으로 알린다. 막힌 상태에서 계속 두드리지 않는다.

전부 로컬 로직이라 토큰을 쓰지 않는다. 상태 파일: data/output/threads_queue.json, threads_state.json.
설정(환경변수): THREADS_QUEUE_ENABLED(기본 1), THREADS_MAX_PER_DAY(3), THREADS_MIN_GAP_MINUTES(75),
THREADS_PAUSE_HOURS(48).
"""
from __future__ import annotations

import contextlib
import json
import os
import random
import time
from datetime import datetime, timedelta, timezone
from typing import Any, Dict, List, Optional

from config import OUTPUT_DIR
from utils.logger import get_logger

try:  # 리눅스(서버)에서만 사용 가능 - 윈도 개발 환경에서는 잠금 없이 동작
    import fcntl
except ImportError:  # pragma: no cover
    fcntl = None  # type: ignore[assignment]

logger = get_logger(__name__)

KST = timezone(timedelta(hours=9))
QUEUE_PATH = OUTPUT_DIR / "threads_queue.json"
STATE_PATH = OUTPUT_DIR / "threads_state.json"
LOCK_PATH = OUTPUT_DIR / ".threads.lock"

WINDOW_START_MIN = 8 * 60  # KST 08:00
WINDOW_END_MIN = 22 * 60 + 30  # KST 22:30
COMMENT_DELAY_SECONDS = (40, 110)
STALE_HOURS = 36
MAX_ATTEMPTS = 3
FAIL_STREAK_PAUSE = 3
FAIL_STREAK_PAUSE_HOURS = 24


def _int_env(name: str, default: int) -> int:
    try:
        return int(os.environ.get(name, default))
    except (TypeError, ValueError):
        return default


def max_per_day() -> int:
    return _int_env("THREADS_MAX_PER_DAY", 3)


def min_gap_minutes() -> int:
    return _int_env("THREADS_MIN_GAP_MINUTES", 75)


def pause_hours() -> int:
    return _int_env("THREADS_PAUSE_HOURS", 48)


def _now() -> datetime:
    return datetime.now(timezone.utc)


def _iso(dt: datetime) -> str:
    return dt.astimezone(timezone.utc).isoformat(timespec="seconds")


def _parse(value: str) -> Optional[datetime]:
    try:
        return datetime.fromisoformat(value)
    except (TypeError, ValueError):
        return None


@contextlib.contextmanager
def _lock():
    """데몬과 발행 프로세스가 큐 파일을 동시에 고치지 않도록 파일 잠금을 건다."""
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    if fcntl is None:
        yield
        return
    with open(LOCK_PATH, "w") as handle:
        fcntl.flock(handle, fcntl.LOCK_EX)
        try:
            yield
        finally:
            fcntl.flock(handle, fcntl.LOCK_UN)


def _load(path, default):
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return default


def _save(path, data) -> None:
    tmp = path.with_suffix(path.suffix + ".tmp")
    try:
        OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
        tmp.write_text(json.dumps(data, ensure_ascii=False), encoding="utf-8")
        os.replace(tmp, path)
    except OSError as exc:
        logger.warning("스레드 큐/상태 저장 실패: %s", exc)


def _state() -> Dict[str, Any]:
    state = _load(STATE_PATH, {})
    state.setdefault("posted_log", [])
    state.setdefault("fail_streak", 0)
    return state


# ---------------------------------------------------------------------------
# 시간 계산
# ---------------------------------------------------------------------------
def _window_start(day: datetime) -> datetime:
    """해당 KST 날짜의 게시 시작 시각(08:00~10:00 사이 무작위)."""
    kst_day = day.astimezone(KST).replace(hour=8, minute=0, second=0, microsecond=0)
    return kst_day + timedelta(minutes=random.randint(0, 120))


def _clamp_to_window(dt: datetime) -> datetime:
    local = dt.astimezone(KST)
    minutes = local.hour * 60 + local.minute
    if WINDOW_START_MIN <= minutes < WINDOW_END_MIN:
        return dt
    if minutes < WINDOW_START_MIN:
        return _window_start(local)
    return _window_start(local + timedelta(days=1))


def _day_key(dt: datetime) -> str:
    return dt.astimezone(KST).date().isoformat()


def _count_on_day(day_key: str, queue: List[Dict[str, Any]], state: Dict[str, Any]) -> int:
    posted = sum(1 for p in state.get("posted_log", []) if (_parse(p) and _day_key(_parse(p)) == day_key))
    queued = sum(1 for q in queue if (_parse(q.get("due_at", "")) and _day_key(_parse(q["due_at"])) == day_key))
    return posted + queued


def _compute_due(queue: List[Dict[str, Any]], state: Dict[str, Any], now: datetime) -> datetime:
    gap = min_gap_minutes()
    times: List[datetime] = [t for t in (_parse(q.get("due_at", "")) for q in queue) if t]
    times += [t for t in (_parse(p) for p in state.get("posted_log", [])[-5:]) if t]
    last = max(times) if times else None
    if last is None or last < now:
        due = now + timedelta(minutes=random.randint(5, 25))
    else:
        due = last + timedelta(minutes=random.randint(gap, gap + 60))
    due = _clamp_to_window(due)
    for _ in range(14):  # 하루 한도를 넘으면 다음 날로 넘긴다
        if _count_on_day(_day_key(due), queue, state) < max_per_day():
            break
        due = _window_start(due.astimezone(KST) + timedelta(days=1))
    return due


# ---------------------------------------------------------------------------
# 차단기
# ---------------------------------------------------------------------------
def paused_until(now: Optional[datetime] = None) -> Optional[datetime]:
    until = _parse(_state().get("pause_until", ""))
    return until if until and until > (now or _now()) else None


def _notify(text: str) -> None:
    try:
        from utils.telegram_notify import send_message_sync

        send_message_sync(text)
    except Exception as exc:  # noqa: BLE001 - 알림 실패가 게시 흐름을 막으면 안 된다
        logger.info("스레드 알림 전송 실패(무시): %s", exc)


def pause(hours: int, why: str, now: Optional[datetime] = None) -> None:
    now = now or _now()
    until = now + timedelta(hours=hours)
    with _lock():
        state = _state()
        state["pause_until"] = _iso(until)
        _save(STATE_PATH, state)
    logger.warning("[Threads] 게시 일시중지(%s시간): %s", hours, why)
    _notify(
        f"⏸️ 스레드 게시를 {hours}시간 멈춥니다 ({until.astimezone(KST):%m-%d %H:%M} KST까지).\n"
        f"이유: {why}\n워드프레스 발행에는 영향이 없습니다. Meta 계정/앱 상태를 확인해 주세요."
    )


# ---------------------------------------------------------------------------
# 큐
# ---------------------------------------------------------------------------
def enqueue(site: str, text: str, comment: str, post_url: str, now: Optional[datetime] = None) -> Dict[str, Any]:
    """스레드 게시를 예약한다. distribute_all이 즉시 게시 대신 호출한다."""
    now = now or _now()
    if not text:
        return {"status": "skipped", "reason": "no_text"}
    if paused_until(now):
        return {"status": "skipped", "reason": f"paused_until_{_iso(paused_until(now))}"}
    with _lock():
        queue = _load(QUEUE_PATH, [])
        state = _state()
        due = _compute_due(queue, state, now)
        queue.append(
            {
                "site": site,
                "text": text,
                "comment": comment or "",
                "post_url": post_url,
                "created_at": _iso(now),
                "due_at": _iso(due),
                "attempts": 0,
            }
        )
        _save(QUEUE_PATH, queue)
    logger.info("[Threads] Site %s 게시 예약: %s KST", site, due.astimezone(KST).strftime("%m-%d %H:%M"))
    return {"status": "queued", "due_at": _iso(due)}


def _pop_due(now: datetime) -> Optional[Dict[str, Any]]:
    """지금 올려도 되는 항목 하나를 큐에서 꺼낸다. 없으면 None(한도/간격/시간대 조건 포함)."""
    with _lock():
        queue = _load(QUEUE_PATH, [])
        state = _state()

        fresh: List[Dict[str, Any]] = []
        for item in queue:
            created = _parse(item.get("created_at", ""))
            if created and now - created > timedelta(hours=STALE_HOURS):
                logger.info("[Threads] %s시간 넘게 못 올린 예약을 버립니다: %s", STALE_HOURS, item.get("post_url"))
                continue
            fresh.append(item)
        queue = fresh

        picked = None
        for item in sorted(queue, key=lambda i: i.get("due_at", "")):
            due = _parse(item.get("due_at", ""))
            if due and due <= now:
                picked = item
                break
        if picked is None:
            _save(QUEUE_PATH, queue)
            return None

        local = now.astimezone(KST)
        minutes = local.hour * 60 + local.minute
        last_posted = max((t for t in (_parse(p) for p in state["posted_log"]) if t), default=None)
        too_soon = last_posted is not None and now - last_posted < timedelta(minutes=min_gap_minutes())
        over_cap = _count_on_day(_day_key(now), [], state) >= max_per_day()
        out_of_window = not (WINDOW_START_MIN <= minutes < WINDOW_END_MIN)
        if too_soon or over_cap or out_of_window:
            picked["due_at"] = _iso(_compute_due([i for i in queue if i is not picked], state, now))
            _save(QUEUE_PATH, queue)
            return None

        queue.remove(picked)
        _save(QUEUE_PATH, queue)
        return picked


def _requeue(item: Dict[str, Any], delay_minutes: int, now: datetime) -> None:
    with _lock():
        queue = _load(QUEUE_PATH, [])
        item["attempts"] = int(item.get("attempts", 0)) + 1
        item["due_at"] = _iso(now + timedelta(minutes=delay_minutes))
        queue.append(item)
        _save(QUEUE_PATH, queue)


def process_due(now: Optional[datetime] = None, sleep=time.sleep) -> Dict[str, Any]:
    """데몬이 5분마다 호출한다. 때가 된 항목이 있으면 한 건 게시하고 지연 후 링크 댓글을 단다."""
    from social_distributor import add_threads_first_comment, publish_threads_post

    now = now or _now()
    if paused_until(now):
        return {"status": "paused"}
    item = _pop_due(now)
    if item is None:
        return {"status": "idle"}

    result = publish_threads_post(item["text"])
    if result.get("status") == "ok":
        with _lock():
            state = _state()
            state["posted_log"] = (state["posted_log"] + [_iso(now)])[-50:]
            state["fail_streak"] = 0
            _save(STATE_PATH, state)
        comment_result: Dict[str, Any] = {"status": "skipped"}
        if item.get("comment"):
            sleep(random.randint(*COMMENT_DELAY_SECONDS))
            comment_result = add_threads_first_comment(
                result.get("post_id", ""), item["comment"].replace("{POST_URL}", item["post_url"])
            )
            if comment_result.get("status") != "ok":
                logger.warning("[Threads] 링크 댓글 실패(본문은 게시됨): %s", comment_result)
                if comment_result.get("reason") == "blocked":
                    pause(pause_hours(), "링크 댓글 등록 중 Meta가 차단 응답을 보냈습니다.", now)
        logger.info("[Threads] Site %s 게시 완료(댓글 %s)", item.get("site"), comment_result.get("status"))
        return {"status": "ok", "comment": comment_result.get("status")}

    reason = result.get("reason", "error")
    if reason == "blocked":
        _requeue(item, 60, now)
        pause(pause_hours(), "Meta가 'API access blocked' 등 차단 응답을 보냈습니다(비정상 활동 감지 가능성).", now)
        return {"status": "blocked"}

    with _lock():
        state = _state()
        state["fail_streak"] = int(state.get("fail_streak", 0)) + 1
        streak = state["fail_streak"]
        _save(STATE_PATH, state)
    if item.get("attempts", 0) + 1 >= MAX_ATTEMPTS:
        logger.warning("[Threads] %s번 실패해 이 게시는 포기합니다: %s", MAX_ATTEMPTS, item.get("post_url"))
    else:
        _requeue(item, 30, now)
    if streak >= FAIL_STREAK_PAUSE:
        pause(FAIL_STREAK_PAUSE_HOURS, f"스레드 게시가 {streak}번 연속 실패했습니다({reason}).", now)
    return {"status": "error", "reason": reason}
