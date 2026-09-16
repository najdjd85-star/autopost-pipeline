"""
.env의 TELEGRAM_BOT_TOKEN으로 내 텔레그램 chat_id를 찾아주는 도우미 스크립트.

사용법:
    1. 텔레그램에서 내가 만든 봇에게 아무 메시지나 하나 보낸다 (예: /start)
    2. venv\\Scripts\\python.exe scripts\\get_telegram_chat_id.py 실행
    3. 출력된 chat_id를 .env의 TELEGRAM_ADMIN_CHAT_ID에 붙여넣는다

이 스크립트는 토큰을 어디에도 전송하지 않고, 텔레그램 공식 API에만 조회한다.
"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from config import settings  # noqa: E402
from utils.http import safe_get  # noqa: E402


def main() -> int:
    token = settings.telegram_bot_token
    if not token:
        print("[오류] .env에 TELEGRAM_BOT_TOKEN이 설정되어 있지 않습니다.")
        return 1

    resp = safe_get(f"https://api.telegram.org/bot{token}/getUpdates", timeout=10)
    if resp is None:
        print("[오류] 텔레그램 서버에 연결하지 못했습니다. 네트워크를 확인해주세요.")
        return 1
    if resp.status_code == 401:
        print("[오류] 토큰이 올바르지 않습니다 (401 Unauthorized). TELEGRAM_BOT_TOKEN을 다시 확인해주세요.")
        return 1
    if resp.status_code != 200:
        print(f"[오류] 텔레그램 API 응답 오류: status={resp.status_code}")
        return 1

    data = resp.json()
    results = data.get("result", [])
    if not results:
        print(
            "[안내] 아직 메시지가 없습니다.\n"
            "  1) 텔레그램에서 내가 만든 봇을 검색해서 대화를 열고\n"
            "  2) 아무 메시지나 (예: /start) 하나 보낸 뒤\n"
            "  3) 이 스크립트를 다시 실행해주세요."
        )
        return 0

    print("찾은 chat_id 목록:\n")
    seen = set()
    for item in results:
        message = item.get("message") or item.get("channel_post") or {}
        chat = message.get("chat", {})
        chat_id = chat.get("id")
        if chat_id is None or chat_id in seen:
            continue
        seen.add(chat_id)
        name = chat.get("username") or chat.get("first_name") or chat.get("title") or "(이름 없음)"
        print(f"  chat_id = {chat_id}   (보낸 사람/채널: {name})")

    print("\n본인이 보낸 메시지의 chat_id를 TELEGRAM_ADMIN_CHAT_ID에 붙여넣으세요.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
