"""[홍보 3단계] 사용법 영상(세로 20초)을 유튜브 쇼츠·인스타 릴스·스레드에 올린다. 틱톡은 앱이 막혀 있어 직접 올려야 한다.

- 영상 원본: site_d/promo_media/fridge-demo.mp4 (사이트 빌드가 https://cook.dailyfixpoint.com/promo/fridge-demo.mp4 로 공개한다 → 인스타·스레드는 이 주소가 열려 있어야 올릴 수 있다).
- 기본은 '미리보기'(아무것도 올리지 않음). --send 와 플랫폼(--youtube --instagram --threads, 또는 --all)을 줘야 올린다.
- 이미 올린 플랫폼은 data/output/promo_posted.json 에 기록해서 다시 올리지 않는다(--force 로 무시).
- AI 표기: 그림·음성이 AI로 만들어졌다는 문구를 설명에 넣고, 유튜브는 '합성 콘텐츠' 표시를 켠다. 쿠팡 링크는 넣지 않는다.

사용:
  venv/Scripts/python.exe -X utf8 site_d/promo/post_video.py                      (문구 미리보기)
  venv/Scripts/python.exe -X utf8 site_d/promo/post_video.py --send --youtube     (유튜브만 올리기)
  venv/Scripts/python.exe -X utf8 site_d/promo/post_video.py --send --all         (유튜브·인스타·스레드 전부)
"""
from __future__ import annotations

import argparse
import json
import sys
import time
from pathlib import Path

import requests

HERE = Path(__file__).resolve().parent
SITE_D = HERE.parent
ROOT = SITE_D.parent
sys.path.insert(0, str(HERE))
sys.path.insert(0, str(SITE_D))
sys.path.insert(0, str(ROOT))

MEDIA = SITE_D / "promo_media" / "fridge-demo.mp4"
URL = "https://cook.dailyfixpoint.com/promo/fridge-demo.mp4"
LOG = ROOT / "data" / "output" / "promo_posted.json"
SITE = "https://cook.dailyfixpoint.com/"
AI_NOTE = "※ 그림과 목소리는 AI로 만들었고, 요리 사진은 AI로 만든 참고 이미지예요."
TAGS = "#냉장고파먹기 #냉털 #자취요리 #집밥 #레시피 #냉장고정리"

YT_TITLE = "냉장고 열었는데 곧 버릴 재료만? 재료 누르면 요리가 바로 나와요 #shorts"
YT_DESC = (f"냉장고에 있는 재료를 눌러 담기만 하면 지금 만들 수 있는 요리가 바로 나와요. 분량(ml·g)과 순서까지 정리돼 있어요.\n"
           f"👉 {SITE}?utm_source=youtube&utm_medium=social&utm_campaign=demo\n{AI_NOTE}\n{TAGS} #shorts")
IG_CAPTION = (f"냉장고 열었는데 곧 버릴 재료만 잔뜩? 😇\n재료 몇 개만 누르면 할 수 있는 요리가 바로 나와요!\n"
              f"남은 재료 빨리 처분하고 싶으면 프로필 링크에서 {SITE.replace('https://', '').rstrip('/')}\n{AI_NOTE}\n\n{TAGS}")
TIKTOK_CAPTION = f"냉장고 털기 🧊 재료만 누르면 되는 요리가 바로!\n프로필 링크에서 써 봐\n{AI_NOTE}\n{TAGS}"


def threads_text() -> str:
    import threads_promo as T

    return T.text_pitch(0).replace("pitch", "demo")


def load_log() -> dict:
    try:
        return json.loads(LOG.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return {}


def save_log(d: dict) -> None:
    LOG.parent.mkdir(parents=True, exist_ok=True)
    LOG.write_text(json.dumps(d, ensure_ascii=False, indent=1), encoding="utf-8")


def post_youtube() -> dict:
    from google.oauth2.credentials import Credentials
    from googleapiclient.discovery import build
    from googleapiclient.http import MediaFileUpload

    from config import settings
    from social_distributor import YOUTUBE_SCOPES

    creds = Credentials.from_authorized_user_file(str(settings.youtube_token_path), YOUTUBE_SCOPES)
    yt = build("youtube", "v3", credentials=creds)
    body = {
        "snippet": {"title": YT_TITLE[:100], "description": YT_DESC, "categoryId": "26", "defaultLanguage": "ko"},
        "status": {"privacyStatus": "public", "selfDeclaredMadeForKids": False, "containsSyntheticMedia": True},
    }
    media = MediaFileUpload(str(MEDIA), chunksize=-1, resumable=True, mimetype="video/mp4")
    res = yt.videos().insert(part="snippet,status", body=body, media_body=media).execute()
    return {"status": "ok", "id": res.get("id"), "url": f"https://youtube.com/shorts/{res.get('id')}"}


def check_public_url() -> None:
    r = requests.head(URL, timeout=20, allow_redirects=True)
    if r.status_code != 200 or "video" not in r.headers.get("content-type", ""):
        raise SystemExit(f"영상 공개 주소가 아직 열려 있지 않아요({r.status_code}). 서버에서 git pull 후 publish_site_d.sh 를 먼저 실행해 주세요: {URL}")


def post_instagram() -> dict:
    from social_distributor import publish_instagram_reel

    check_public_url()
    return publish_instagram_reel(URL, IG_CAPTION)


def post_threads() -> dict:
    from config import settings
    from social_distributor import THREADS_API_BASE, _wait_for_threads_container_ready, plain_threads_text
    from utils.http import safe_post

    check_public_url()
    if not settings.threads_access_token:
        return {"status": "skipped", "reason": "not_configured"}
    tok = settings.threads_access_token
    c = safe_post(f"{THREADS_API_BASE}/me/threads", data={"media_type": "VIDEO", "video_url": URL, "text": plain_threads_text(threads_text()), "access_token": tok}, timeout=60)
    if c is None or c.status_code != 200:
        return {"status": "error", "reason": "create_failed", "body": getattr(c, "text", "")[:300]}
    cid = c.json().get("id")
    # 영상은 처리 시간이 걸려서 넉넉히 기다린다(최대 약 3분)
    ready = _wait_for_threads_container_ready(cid, tok, max_attempts=60, delay_seconds=3.0)
    if not ready:
        return {"status": "error", "reason": "container_not_ready"}
    p = safe_post(f"{THREADS_API_BASE}/me/threads_publish", data={"creation_id": cid, "access_token": tok}, timeout=60)
    if p is None or p.status_code != 200:
        return {"status": "error", "reason": "publish_failed", "body": getattr(p, "text", "")[:300]}
    return {"status": "ok", "post_id": p.json().get("id")}


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--send", action="store_true")
    ap.add_argument("--youtube", action="store_true")
    ap.add_argument("--instagram", action="store_true")
    ap.add_argument("--threads", action="store_true")
    ap.add_argument("--all", action="store_true")
    ap.add_argument("--force", action="store_true")
    a = ap.parse_args()
    if not MEDIA.exists():
        raise SystemExit(f"영상이 없어요: {MEDIA}")
    targets = [n for n, on in (("youtube", a.youtube or a.all), ("instagram", a.instagram or a.all), ("threads", a.threads or a.all)) if on]
    if not a.send:
        print(f"영상: {MEDIA} ({MEDIA.stat().st_size // 1024}KB)\n공개 주소: {URL}\n\n[유튜브 제목] {YT_TITLE}\n[유튜브 설명]\n{YT_DESC}\n\n[인스타 릴스 문구]\n{IG_CAPTION}\n\n[스레드 글]\n{threads_text()}\n\n[틱톡 문구(직접 올리기)]\n{TIKTOK_CAPTION}\n")
        print("(미리보기입니다. 올리지 않았어요.)")
        return 0
    log = load_log()
    funcs = {"youtube": post_youtube, "instagram": post_instagram, "threads": post_threads}
    for n in targets:
        if log.get(n, {}).get("status") == "ok" and not a.force:
            print(n, "이미 올렸어요 →", log[n])
            continue
        try:
            res = funcs[n]()
        except SystemExit:
            raise
        except Exception as exc:  # noqa: BLE001
            res = {"status": "error", "reason": str(exc)[:300]}
        print(n, res)
        log[n] = {**res, "at": time.strftime("%Y-%m-%d %H:%M")}
        save_log(log)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
