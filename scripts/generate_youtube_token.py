"""
YouTube OAuth 토큰 발급 스크립트.

client_secret.json(Google Cloud Console에서 발급받은 "데스크톱 앱" OAuth
클라이언트)을 읽어 브라우저에서 로그인 동의를 받고, 그 결과로 받은 자격증명을
youtube_token.json으로 저장한다. social_distributor.publish_youtube_longform()/
add_youtube_comment()가 이 파일을 그대로 사용한다.

브라우저 로그인/동의는 사용자가 직접 하며, 이 스크립트는 그 과정을 열어줄
뿐 비밀번호 등 자격정보를 대신 입력하지 않는다.

주의: 스코프가 youtube.upload(업로드 전용) -> youtube.force-ssl(업로드+댓글 등
포함)로 넓어졌다. 예전에 youtube.upload로만 발급받은 토큰이 있다면 댓글 작성
API 호출 시 권한 부족 오류가 나므로, 이 스크립트를 다시 실행해 토큰을
재발급받아야 한다.

사용법:
    venv\\Scripts\\python.exe scripts\\generate_youtube_token.py
"""
from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from config import settings  # noqa: E402
from social_distributor import YOUTUBE_SCOPES as SCOPES  # noqa: E402


def main() -> int:
    secrets_path = Path(settings.youtube_client_secrets_path)
    token_path = Path(settings.youtube_token_path)

    if not secrets_path.exists():
        print(f"[오류] {secrets_path} 파일이 없습니다.")
        print("Google Cloud Console에서 다운로드한 OAuth 클라이언트 JSON을")
        print(f"프로젝트 폴더에 '{secrets_path.name}' 이름으로 저장해주세요.")
        return 1

    try:
        from google_auth_oauthlib.flow import InstalledAppFlow
    except ImportError:
        print("[오류] google-auth-oauthlib가 설치되어 있지 않습니다.")
        return 1

    if token_path.exists():
        print(f"[안내] 기존 토큰({token_path})을 새 스코프(youtube.force-ssl)로 재발급합니다.")
    print("브라우저가 열립니다. 유튜브 채널을 소유한 구글 계정으로 로그인 후 동의해주세요...")
    flow = InstalledAppFlow.from_client_secrets_file(str(secrets_path), SCOPES)
    creds = flow.run_local_server(port=0)

    token_path.write_text(creds.to_json(), encoding="utf-8")
    print(f"[완료] 토큰이 저장되었습니다: {token_path}")
    print("이제 영상 업로드와 댓글 자동 작성(add_youtube_comment) 모두 이 토큰으로 가능합니다.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
