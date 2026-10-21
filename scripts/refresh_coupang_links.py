"""[데스크탑(한국 IP)에서 실행] 쿠팡 상품 링크를 만들어 서버가 쓰는 비공개 페이지에 올린다.

서버는 해외 IP라 쿠팡 API가 막히므로, 이 스크립트를 하루 한 번 돌려 링크 은행을 갱신한다.
실행: venv\\Scripts\\python.exe scripts\\refresh_coupang_links.py
종료 코드: 0 = 업로드 성공, 1 = 실패(작업 스케줄러에서 재시도 용도)

절전에서 막 깨어난 직후에는 인터넷이 아직 안 붙어 있을 수 있어서 연결될 때까지 기다리고,
실행 중(약 3분)에는 PC가 다시 절전으로 들어가지 않도록 막는다.
"""
from __future__ import annotations

import socket
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from coupang_link_bank import refresh_bank
from utils.logger import get_logger

logger = get_logger(__name__)

NETWORK_WAIT_SECONDS = 240
_REQUIRED_HOSTS = (("api-gateway.coupang.com", 443), ("gov.dailyfixpoint.com", 443))


def _network_ready() -> bool:
    try:
        for host, port in _REQUIRED_HOSTS:
            socket.create_connection((host, port), timeout=5).close()
        return True
    except OSError:
        return False


def _wait_for_network() -> bool:
    deadline = time.time() + NETWORK_WAIT_SECONDS
    while time.time() < deadline:
        if _network_ready():
            return True
        time.sleep(10)
    return False


def _notify(result: dict) -> None:
    """결과를 텔레그램으로 알린다. 성공이면 한 줄, 실패(업로드 못 함)면 경고. 알림 실패는 무시."""
    ok = bool(result.get("uploaded"))
    head = "✅ 쿠팡 링크 갱신 완료" if ok else "⚠️ 쿠팡 링크 갱신 실패 (쿠팡 한도·접속 확인)"
    text = f"{head}\n새 링크 {result.get('made', 0)}개 · 유지 {result.get('kept', 0)}개 · 실패 {result.get('failed', 0)}개"
    try:
        from utils.telegram_notify import send_message_sync

        send_message_sync(text)
    except Exception as exc:  # noqa: BLE001
        logger.info("쿠팡 링크 갱신 알림 전송 실패(무시): %s", exc)


def _keep_awake(on: bool) -> None:
    """Windows에서 실행 중 절전 진입을 막는다(ES_CONTINUOUS | ES_SYSTEM_REQUIRED). 다른 OS에서는 무시."""
    try:
        import ctypes

        flags = 0x80000001 if on else 0x80000000
        ctypes.windll.kernel32.SetThreadExecutionState(flags)  # type: ignore[attr-defined]
    except (AttributeError, OSError):
        pass


if __name__ == "__main__":
    _keep_awake(True)
    try:
        if not _wait_for_network():
            logger.warning("인터넷 연결을 %s초 기다렸지만 연결되지 않아 중단합니다(스케줄러가 재시도).", NETWORK_WAIT_SECONDS)
            sys.exit(1)
        result = refresh_bank()
        logger.info("쿠팡 링크 은행 갱신 결과: %s", result)
        if not result.get("skipped"):  # 한도 보호로 건너뛴 재시도는 알리지 않는다(스팸 방지)
            _notify(result)
        sys.exit(0 if result.get("uploaded") else 1)
    finally:
        _keep_awake(False)
