"""[매일 18시, 내 PC] 냉장고 파먹기(사이트 D)의 '오늘 많이 찾은 요리'를 갱신하고 사이트를 다시 빌드한다.

순서: 네이버 데이터랩에서 어제 검색 지수 받기 -> site_d/trending.json 저장 -> 사이트 빌드(site_d/dist) -> 텔레그램으로 결과 알림.
키가 아직 없으면 조용히 건너뛴다(알림 없음). 끝나면 trending.json 을 깃에 올리고(deploy), 서버 예약 작업(scripts/publish_site_d.sh)이 18:10에 받아 사이트를 갱신한다.
실행: venv\\Scripts\\python.exe scripts\\update_site_d.py     (예약 작업 'FridgeTrending' 이 매일 18:00 에 실행)
"""
from __future__ import annotations

import subprocess
import sys
import time
import urllib.request
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "site_d"))
sys.path.insert(0, str(ROOT / "site_d" / "tools"))

from utils.logger import get_logger  # noqa: E402

logger = get_logger(__name__)


def _network_ready() -> bool:
    for _ in range(6):
        try:
            urllib.request.urlopen("https://openapi.naver.com", timeout=8)
            return True
        except Exception:  # noqa: BLE001 - 401 등 응답이 오면 연결은 된 것
            try:
                urllib.request.urlopen("https://www.naver.com", timeout=8)
                return True
            except Exception:  # noqa: BLE001
                time.sleep(20)
    return False


def _notify(text: str) -> None:
    try:
        from utils.telegram_notify import send_message_sync

        send_message_sync(text)
    except Exception as exc:  # noqa: BLE001
        logger.info("텔레그램 알림 실패(무시): %s", exc)


def deploy() -> str:
    """오늘 인기 요리(trending.json)와 재료 가격(prices_live.json)만 깃에 올린다. 서버가 매일 18:10(한국시간)에 받아서 사이트를 다시 만든다."""
    def git(*args: str) -> subprocess.CompletedProcess:
        return subprocess.run(["git", *args], cwd=str(ROOT), capture_output=True, text=True, encoding="utf-8")

    changed = [p for p in ("site_d/trending.json", "site_d/prices_live.json") if (ROOT / p).exists() and git("status", "--porcelain", "--", p).stdout.strip()]
    if not changed:
        return "서버 반영: 어제와 같아 올릴 것 없음"
    git("add", *changed)
    msg = git("commit", "-m", "Site D: daily trending/price update", "--", *changed)
    if msg.returncode != 0:
        return "서버 반영 실패(커밋): " + (msg.stderr or msg.stdout)[-120:]
    push = git("push", "origin", "HEAD")
    if push.returncode != 0:
        return "서버 반영 실패(푸시, 다음 날 다시 시도): " + (push.stderr or push.stdout)[-120:]
    return "서버 반영: 깃에 올림(서버가 18:10에 사이트 갱신)"


def update_prices() -> str:
    """KAMIS 소매가격으로 신선식품 가격을 갱신한다(키가 없거나 실패하면 예전 가격 그대로, 사이트는 계속 만들어진다)."""
    try:
        import fetch_prices

        code = fetch_prices.main()
        return "가격 갱신 시도 완료" if code == 0 else "가격 갱신 건너뜀(응답 없음)"
    except Exception as exc:  # noqa: BLE001
        logger.warning("가격 갱신 실패(무시): %s", exc)
        return "가격 갱신 실패(예전 가격 유지)"


def main() -> int:
    import fetch_trending

    if not _network_ready():
        logger.warning("인터넷 연결이 없어 인기 요리 갱신을 건너뜁니다.")
        return 1
    logger.info(update_prices())
    try:
        data = fetch_trending.build()
    except fetch_trending.NotConfigured as exc:
        logger.info("인기 요리 갱신 건너뜀: %s", exc)
        return 0
    except Exception as exc:  # noqa: BLE001
        logger.warning("인기 요리 갱신 실패: %s", exc)
        _notify(f"⚠️ 냉장고 파먹기 인기 요리 갱신 실패\n{str(exc)[:200]}")
        return 1
    import json

    (ROOT / "site_d" / "trending.json").write_text(json.dumps(data, ensure_ascii=False, indent=1), encoding="utf-8")
    res = subprocess.run([sys.executable, "-X", "utf8", str(ROOT / "site_d" / "build.py")], capture_output=True, text=True, encoding="utf-8", cwd=str(ROOT))
    if res.returncode != 0:
        _notify(f"⚠️ 냉장고 파먹기 빌드 실패\n{(res.stderr or res.stdout)[-200:]}")
        return 1
    from recipes_data import RECIPES

    nm = {r["slug"]: r["name"] for r in RECIPES}
    top = ", ".join(nm[r["slug"]] for r in data["items"][:3])
    _notify(f"✅ 냉장고 파먹기 인기 요리 갱신 ({data['date']} 기준)\n1~3위: {top}\n{deploy()}")
    logger.info("인기 요리 갱신 완료: %s", top)
    return 0


if __name__ == "__main__":
    sys.exit(main())
