"""정책 변화 감시 - 월 1회 변화 감지 + 고정 날짜 알림 + 팩트 시트 기준 연도 점검 (서버 데몬에서 자동 실행).

1. 월 1회: 보조금24(공공서비스) 데이터에서 중앙행정기관·공공기관의 개인/가구 대상 서비스를 받아 지난달 스냅샷과 비교하고,
   새로 생기거나 수정된 제도를 조회수 순으로 텔레그램에 알린다. 첫 실행은 기준 스냅샷만 저장한다.
2. 고정 날짜 알림: 해마다 반복되는 갱신 시점(중위소득·세법 개정, 세제개편안, 장려금 신청 시기, 분기/반기 점검)을 미리 알린다.
3. 기준 연도 점검: fact_sheets.py의 "N년 기준" 표기를 읽어, 올해보다 오래된 시트가 있으면 알린다.

토큰(LLM)을 쓰지 않고 공공데이터 API(무료)와 텔레그램만 쓴다. 상태 파일: data/output/policy_watch_state.json, policy_snapshot.json.
"""
from __future__ import annotations

import html
import json
import re
import time
from datetime import date, datetime, timedelta, timezone
from typing import Any, Dict, List, Optional

from config import OUTPUT_DIR, settings
from utils.http import safe_get
from utils.logger import get_logger

logger = get_logger(__name__)

KST = timezone(timedelta(hours=9))
STATE_PATH = OUTPUT_DIR / "policy_watch_state.json"
SNAP_PATH = OUTPUT_DIR / "policy_snapshot.json"
API_BASE = "https://api.odcloud.kr/api/gov24/v3/serviceList"
TOP_N = 10

# (월, 일, 키, 내용) - 알림은 해당 날짜부터 3일 안에 한 번만 보낸다(데몬이 잠깐 꺼져 있어도 놓치지 않게).
REMINDERS: List[tuple] = [
    (12, 20, "year_end_update",
     "내년 기준 갱신을 시작할 때입니다. ① 기준 중위소득(생계·의료·주거·교육급여, 한부모 소득기준) ② 세법 개정 시행분 "
     "③ 최저임금·각종 지급액을 확인해 fact_sheets.py와 허브 판정 규칙(wizard.js)의 '2026년 기준'을 새 연도로 바꾸세요."),
    (1, 5, "new_year_check",
     "새해 기준 갱신 마무리 점검일입니다. 팩트 시트와 허브 판정 규칙의 기준 연도·금액이 새해 값으로 바뀌었는지 확인하고, "
     "'2026년 기준'으로 남은 글(올해 기준 변경 글)이 없는지 보세요."),
    (2, 25, "march_eitc",
     "3월 반기(하반기분) 근로·자녀장려금 신청 시기가 다가옵니다. 신청 방법·기간 안내 글을 앞세울 시점입니다."),
    (4, 20, "may_eitc",
     "5월 정기 근로·자녀장려금 신청이 곧 시작됩니다. 장려금 글(근로장려금, 자녀장려금)을 점검하고 신청 시기 안내를 갱신하세요."),
    (8, 20, "sep_eitc",
     "9월 반기(상반기분) 장려금 신청 시기가 다가옵니다. 장려금 신청 안내 글을 점검하세요."),
    (8, 28, "tax_reform",
     "정부 세제개편안·다음 해 예산안이 발표되는 시기입니다. 세액공제·소득공제·복지 예산 변경안이 나오면 '개편안(확정 전)'으로만 "
     "다루고, 확정되면 팩트 시트를 갱신하세요."),
    (3, 1, "quarter", "분기 점검일입니다. 이번 분기에 신설·폐지·확대된 제도가 있는지 월간 점검 알림을 모아 보고, 허브 '20개 제도' 목록에 넣을 제도를 판단하세요."),
    (6, 1, "quarter", "분기 점검일입니다. 이번 분기에 신설·폐지·확대된 제도가 있는지 월간 점검 알림을 모아 보고, 허브 '20개 제도' 목록에 넣을 제도를 판단하세요."),
    (9, 1, "quarter", "분기 점검일입니다. 이번 분기에 신설·폐지·확대된 제도가 있는지 월간 점검 알림을 모아 보고, 허브 '20개 제도' 목록에 넣을 제도를 판단하세요."),
    (12, 1, "quarter", "분기 점검일입니다. 이번 분기에 신설·폐지·확대된 제도가 있는지 월간 점검 알림을 모아 보고, 허브 '20개 제도' 목록에 넣을 제도를 판단하세요."),
    (6, 10, "half_year_list", "반기 점검일입니다. 인기 제도 목록(허브 '20개 제도')이 지금 조회수 상위 제도와 맞는지 월간 알림의 인기 순위로 확인하세요."),
    (12, 10, "half_year_list", "반기 점검일입니다. 인기 제도 목록(허브 '20개 제도')이 지금 조회수 상위 제도와 맞는지 월간 알림의 인기 순위로 확인하세요."),
]


def _now() -> datetime:
    return datetime.now(KST)


def _load(path, default):
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return default


def _save(path, data) -> None:
    try:
        OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps(data, ensure_ascii=False), encoding="utf-8")
    except OSError as exc:
        logger.warning("정책 점검 상태 저장 실패: %s", exc)


def _send(text: str, dry: bool = False) -> None:
    if dry:
        print(text)
        print("-" * 60)
        return
    try:
        from utils.telegram_notify import send_message_sync

        send_message_sync(text)
    except Exception as exc:  # noqa: BLE001 - 알림 실패가 데몬을 멈추면 안 된다
        logger.info("정책 점검 알림 전송 실패(무시): %s", exc)


def _esc(text: str, limit: int = 44) -> str:
    return html.escape((text or "").strip()[:limit])


# ---------------------------------------------------------------------------
# 2. 고정 날짜 알림
# ---------------------------------------------------------------------------
def send_due_reminders(now: Optional[datetime] = None, dry: bool = False) -> int:
    now = now or _now()
    today = now.date()
    state = _load(STATE_PATH, {})
    sent = state.setdefault("sent", {})
    count = 0
    for month, day, key, text in REMINDERS:
        try:
            target = date(today.year, month, day)
        except ValueError:
            continue
        sent_key = f"{today.year}-{month:02d}{day:02d}-{key}"
        if 0 <= (today - target).days <= 3 and sent_key not in sent:
            _send(f"📌 <b>[정책 점검 알림] {month}월 {day}일</b>\n{html.escape(text)}", dry)
            sent[sent_key] = today.isoformat()
            count += 1
    # 오래된 기록 정리(최근 2년만 유지)
    for k in [k for k in sent if int(k[:4]) < today.year - 1]:
        sent.pop(k, None)
    if not dry:
        _save(STATE_PATH, state)
    return count


# ---------------------------------------------------------------------------
# 3. 팩트 시트 기준 연도 점검
# ---------------------------------------------------------------------------
def fact_year_report(now: Optional[datetime] = None) -> Dict[str, Any]:
    from fact_sheets import _FACT_SHEETS

    now = now or _now()
    stale: List[str] = []
    years: Dict[int, int] = {}
    for tokens, text in _FACT_SHEETS:
        match = re.search(r"(\d{4})년 기준", text[:200])
        if not match:
            continue
        year = int(match.group(1))
        years[year] = years.get(year, 0) + 1
        if year < now.year:
            stale.append(str(tokens[0]))
    return {"total": sum(years.values()), "years": years, "stale": stale, "current_year": now.year}


# ---------------------------------------------------------------------------
# 1. 월 1회 변화 감지
# ---------------------------------------------------------------------------
def fetch_services() -> Dict[str, List[Any]]:
    """중앙행정기관·공공기관의 개인/가구 대상 서비스를 {id: [이름, 기관, 등록, 수정, 조회수, URL]}로 가져온다."""
    if not settings.public_data_api_key:
        raise RuntimeError("PUBLIC_DATA_API_KEY가 설정되지 않았습니다.")
    out: Dict[str, List[Any]] = {}
    page = 1
    while True:
        resp = safe_get(
            API_BASE,
            params={"page": page, "perPage": 1000, "returnType": "JSON", "serviceKey": settings.public_data_api_key},
            timeout=60,
        )
        if resp is None or resp.status_code != 200:
            raise RuntimeError(f"보조금24 목록 조회 실패(page {page}, status {getattr(resp, 'status_code', None)})")
        rows = resp.json().get("data", [])
        for s in rows:
            if s.get("소관기관유형") not in ("중앙행정기관", "공공기관"):
                continue
            if not any(u in (s.get("사용자구분") or "") for u in ("개인", "가구")):
                continue
            out[str(s["서비스ID"])] = [
                s.get("서비스명", ""), s.get("소관기관명", ""), s.get("등록일시", ""), s.get("수정일시", ""),
                int(s.get("조회수") or 0), s.get("상세조회URL") or "",
            ]
        if len(rows) < 1000:
            return out
        page += 1
        time.sleep(0.3)


def _lines(items: List[tuple], n: int = TOP_N) -> str:
    return "\n".join(f"{i}. {_esc(v[0])} ({_esc(v[1], 12)}) · 조회 {v[4]:,}" for i, (_, v) in enumerate(items[:n], 1))


def run_monthly(now: Optional[datetime] = None, dry: bool = False) -> Dict[str, Any]:
    now = now or _now()
    current = fetch_services()
    previous = _load(SNAP_PATH, None)
    by_views = sorted(current.items(), key=lambda kv: -kv[1][4])
    facts = fact_year_report(now)
    fact_line = (
        f"\n\n🗂 팩트 시트 {facts['total']}개 중 {len(facts['stale'])}개가 {now.year}년보다 오래된 기준입니다"
        + (": " + html.escape(", ".join(facts["stale"][:12])) if facts["stale"] else " (모두 최신)")
    )
    head = f"📊 <b>[정책 월간 점검] {now:%Y-%m}</b>\n보조금24 중앙·공공기관 개인/가구 서비스 {len(current):,}건"

    if not previous:
        _send(head + "\n기준 데이터를 처음 저장했습니다. 다음 달부터 신규·수정 제도를 알려드립니다.\n\n<b>현재 조회수 상위</b>\n" + _lines(by_views) + fact_line, dry)
        result = {"baseline": True, "total": len(current)}
    else:
        new = sorted(((k, v) for k, v in current.items() if k not in previous), key=lambda kv: -kv[1][4])
        gone = [k for k in previous if k not in current]
        changed = sorted(
            ((k, v) for k, v in current.items() if k in previous and previous[k][3] != v[3]), key=lambda kv: -kv[1][4]
        )
        body = f"\n🆕 신규 {len(new)}건 / ✏️ 수정 {len(changed)}건 / 🗑 사라짐 {len(gone)}건"
        if new:
            body += "\n\n<b>🆕 신규 (조회수순)</b>\n" + _lines(new)
        if changed:
            body += "\n\n<b>✏️ 수정 (조회수순)</b>\n" + _lines(changed)
        if now.month in (6, 12):
            body += "\n\n<b>현재 인기 제도 상위</b>\n" + _lines(by_views)
        if not new and not changed:
            body += "\n이번 달은 눈에 띄는 변화가 없습니다."
        _send(head + body + fact_line, dry)
        result = {"baseline": False, "total": len(current), "new": len(new), "changed": len(changed), "gone": len(gone)}
    if not dry:
        _save(SNAP_PATH, current)
    return result


def run_monthly_if_due(now: Optional[datetime] = None, dry: bool = False, force: bool = False) -> Optional[Dict[str, Any]]:
    now = now or _now()
    state = _load(STATE_PATH, {})
    month_key = f"{now.year}-{now.month:02d}"
    if not force and state.get("last_monthly") == month_key:
        return None
    result = run_monthly(now, dry)
    if not dry:
        state = _load(STATE_PATH, {})
        state["last_monthly"] = month_key
        _save(STATE_PATH, state)
    return result


def run_daily_checks() -> None:
    """데몬이 하루 한 번 부른다: 고정 날짜 알림 + (이번 달 아직 안 했으면) 월간 점검."""
    try:
        send_due_reminders()
    except Exception as exc:  # noqa: BLE001
        logger.warning("정책 알림 처리 중 오류(무시): %s", exc)
    try:
        run_monthly_if_due()
    except Exception as exc:  # noqa: BLE001 - API 일시 장애면 내일 다시 시도한다(상태를 저장하지 않았으므로)
        logger.warning("정책 월간 점검 실패(내일 재시도): %s", exc)
