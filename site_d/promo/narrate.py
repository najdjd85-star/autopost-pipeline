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
    "pick": "냉장고에 있는 재료를 눌러서 담아봐.",
    "result": "그러면 지금 바로 할 수 있는 요리가 나와.",
    "recipe": "분량이랑 순서까지 다 정리돼 있어서, 그대로 따라 하면 끝.",
    "outro": "남은 재료 빨리 처분하고 싶으면, 여기 한번 들어가봐.",
}


def key() -> str:
    env = dotenv_values(ROOT / ".env")
    k = (env.get("ELEVENLABS_API_KEY") or "").strip()
    if not k:
        raise SystemExit("ELEVENLABS_API_KEY 가 없어요. 바탕화면 'API 키 입력 (아무 이름)' 으로 넣어 주세요.")
    return k


def list_voices(k: str) -> list:
    r = requests.get(f"{API}/voices", headers={"xi-api-key": k}, timeout=30)
    r.raise_for_status()
    return r.json().get("voices", [])


def pick_voice(k: str) -> str:
    env = dotenv_values(ROOT / ".env")
    if (env.get("ELEVENLABS_VOICE_ID") or "").strip():
        return env["ELEVENLABS_VOICE_ID"].strip()
    vs = list_voices(k)
    for v in vs:   # 한국어 라벨이 붙은 목소리를 먼저
        lab = " ".join(str(x) for x in (v.get("labels") or {}).values()).lower() + " " + (v.get("name") or "").lower()
        if "korean" in lab or "ko" in lab.split():
            return v["voice_id"]
    if not vs:
        raise SystemExit("쓸 수 있는 목소리가 없어요.")
    return vs[0]["voice_id"]


def duration(path: Path) -> float:
    out = subprocess.run(["ffprobe", "-v", "error", "-show_entries", "format=duration", "-of", "csv=p=0", str(path)], capture_output=True, text=True)
    return round(float(out.stdout.strip()), 2)


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--list", action="store_true")
    ap.add_argument("--voice", default="")
    a = ap.parse_args()
    k = key()
    if a.list:
        for v in list_voices(k):
            print(v["voice_id"], "|", v.get("name"), "|", (v.get("labels") or {}))
        return
    voice = a.voice or pick_voice(k)
    OUT.mkdir(parents=True, exist_ok=True)
    durs = {}
    for name, text in LINES.items():
        r = requests.post(
            f"{API}/text-to-speech/{voice}?output_format=mp3_44100_128",
            headers={"xi-api-key": k, "Content-Type": "application/json"},
            json={"text": text, "model_id": "eleven_multilingual_v2", "voice_settings": {"stability": 0.45, "similarity_boost": 0.8, "style": 0.35, "use_speaker_boost": True}},
            timeout=90,
        )
        if r.status_code != 200:
            raise SystemExit(f"음성 만들기 실패({name}): {r.status_code} {r.text[:200].replace(k, '<KEY>')}")
        f = OUT / f"narr_{name}.mp3"
        f.write_bytes(r.content)
        durs[name] = duration(f)
        print(name, durs[name], "초", "|", text)
    (OUT / "narr.json").write_text(json.dumps(durs, ensure_ascii=False), encoding="utf-8")
    print("저장:", OUT, "목소리:", voice)


if __name__ == "__main__":
    main()
