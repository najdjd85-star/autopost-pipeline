"""홍보 영상의 설명 음성을 ElevenLabs 로 만든다(유료 API라 글자 수만큼 크레딧이 든다 - 이 영상은 약 130자).

필요한 키(내 PC .env, 바탕화면 'API 키 입력 (아무 이름)' 으로 입력): ELEVENLABS_API_KEY
  선택: ELEVENLABS_VOICE_ID (목소리를 고정하고 싶을 때)
결과: site_d/promo/out/screens/narr_<장면>.mp3 + narr.json(장면별 길이, record_demo.py 가 장면 길이를 맞추는 데 쓴다)

사용:
  venv/Scripts/python.exe -X utf8 site_d/promo/narrate.py --list            (쓸 수 있는 목소리 목록, 크레딧 안 씀)
  venv/Scripts/python.exe -X utf8 site_d/promo/narrate.py [--voice 아이디]   (음성 만들기)
"""
from __future__ import annotations

import argparse
import json
import subprocess
from pathlib import Path

import requests
from dotenv import dotenv_values

HERE = Path(__file__).resolve().parent
ROOT = HERE.parent.parent
OUT = HERE / "out" / "screens"
API = "https://api.elevenlabs.io/v1"

LINES = {
    "hook": "냉장고 열었는데, 곧 버릴 재료만 잔뜩이야?",
    "type": "재료 이름만 쳐도 바로 찾아줘.",
    "pick": "있는 재료를 톡톡 눌러서 담기만 해.",
    "result": "있는 재료로 바로 되는 요리가 떠. 모자란 재료는 바로 사러 갈 수도 있어.",
    "recipe": "분량이랑 순서까지 다 정리돼 있어서, 그대로 따라 하면 끝.",
    "outro": "오늘 저녁 뭐 먹지 고민 말고, 프로필 링크 클릭!",
}


def key() -> str:
    env = dotenv_values(ROOT / ".env")
    k = (env.get("ELEVENLABS_API_KEY") or "").strip()
    h = len(k) // 2
    if h and len(k) % 2 == 0 and k[:h] == k[h:]:   # 키를 두 번 붙여 넣은 경우(같은 글자가 반복)에는 앞쪽 절반만 쓴다
        k = k[:h]
    if not k:
        raise SystemExit("ELEVENLABS_API_KEY 가 없어요. 바탕화면 'API 키 입력 (아무 이름)' 으로 넣어 주세요.")
    return k


# 키에 '목소리 목록 보기' 권한이 없어도 쓸 수 있는 기본 제공 목소리(다국어 모델이라 한국어도 읽는다)
DEFAULT_VOICES = {
    "jessica": "cgSgspJ2msm6clMCkdW9",   # 밝고 발랄한 여성
    "sarah": "EXAVITQu4vr4xnSDxMaL",     # 차분한 여성
    "adam": "pNInz6obpgDQGcFmaJgB",      # 낮고 또렷한 남성
    "charlie": "IKne3meq5aSn9XLyUdCD",   # 캐주얼한 남성
}


def list_voices(k: str) -> list:
    r = requests.get(f"{API}/voices", headers={"xi-api-key": k}, timeout=30)
    if r.status_code != 200:
        return []   # 목록 권한이 없는 키
    return r.json().get("voices", [])


def pick_voice(k: str) -> str:
    env = dotenv_values(ROOT / ".env")
    if (env.get("ELEVENLABS_VOICE_ID") or "").strip():
        return env["ELEVENLABS_VOICE_ID"].strip()
    vs = list_voices(k)
    if not vs:
        return DEFAULT_VOICES["jessica"]
    for v in vs:   # 한국어 라벨이 붙은 목소리를 먼저
        lab = " ".join(str(x) for x in (v.get("labels") or {}).values()).lower() + " " + (v.get("name") or "").lower()
        if "korean" in lab or "ko" in lab.split():
            return v["voice_id"]
    if not vs:
        raise SystemExit("쓸 수 있는 목소리가 없어요.")
    return vs[0]["voice_id"]


def tts(k: str, voice: str, text: str) -> bytes:
    r = requests.post(
        f"{API}/text-to-speech/{voice}?output_format=mp3_44100_128",
        headers={"xi-api-key": k, "Content-Type": "application/json"},
        json={"text": text, "model_id": "eleven_multilingual_v2", "voice_settings": {"stability": 0.45, "similarity_boost": 0.8, "style": 0.35, "use_speaker_boost": True}},
        timeout=90,
    )
    if r.status_code != 200:
        raise SystemExit(f"음성 만들기 실패: {r.status_code} {r.text[:240].replace(k, '<KEY>')}")
    return r.content


def duration(path: Path) -> float:
    out = subprocess.run(["ffprobe", "-v", "error", "-show_entries", "format=duration", "-of", "csv=p=0", str(path)], capture_output=True, text=True)
    return round(float(out.stdout.strip()), 2)


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--list", action="store_true")
    ap.add_argument("--voice", default="", help="목소리 아이디 또는 jessica/sarah/adam/charlie")
    ap.add_argument("--sample", action="store_true", help="첫 문장만 4가지 목소리로 만들어 들어 보기(크레딧 아주 조금)")
    a = ap.parse_args()
    k = key()
    if a.list:
        vs = list_voices(k)
        if not vs:
            print("이 키는 목소리 목록 권한이 없어요. 기본 목소리:", DEFAULT_VOICES)
        for v in vs:
            print(v["voice_id"], "|", v.get("name"), "|", (v.get("labels") or {}))
        return
    if a.sample:
        OUT.mkdir(parents=True, exist_ok=True)
        for nm, vid in DEFAULT_VOICES.items():
            audio = tts(k, vid, LINES["hook"] + " " + LINES["outro"])
            (OUT / f"sample_{nm}.mp3").write_bytes(audio)
            print("샘플:", OUT / f"sample_{nm}.mp3")
        return
    voice = DEFAULT_VOICES.get(a.voice.lower(), a.voice) if a.voice else pick_voice(k)
    OUT.mkdir(parents=True, exist_ok=True)
    durs = {}
    for name, text in LINES.items():
        audio = tts(k, voice, text)
        f = OUT / f"narr_{name}.mp3"
        f.write_bytes(audio)
        durs[name] = duration(f)
        print(name, durs[name], "초", "|", text)
    (OUT / "narr.json").write_text(json.dumps(durs, ensure_ascii=False), encoding="utf-8")
    print("저장:", OUT, "목소리:", voice)


if __name__ == "__main__":
    main()
