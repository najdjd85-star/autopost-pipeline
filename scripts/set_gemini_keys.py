"""Gemini API 키를 .env 에 안전하게 넣는다. 키는 화면에 보이지 않게(비밀번호처럼) 입력받는다.

실행(내 PC):   venv\\Scripts\\python.exe scripts\\set_gemini_keys.py
실행(서버):    venv/bin/python scripts/set_gemini_keys.py
옵션:  --status  키 상태 보기(키는 뒤 4자리만)     --test  키마다 아주 작은 글자 요청 1번으로 유효한지 확인(무료 키면 비용 없음)

- 키는 최대 5개까지 한 칸씩 붙여넣고 Enter. 칸을 비우고 Enter 하면 거기서 끝납니다.
- .env 의 GEMINI_API_KEYS 한 줄만 바꿉니다(여러 줄로 중복되지 않게). 다른 설정은 건드리지 않습니다.
- 이미 키가 있으면 '추가'할지 '새로 바꿀지' 물어봅니다.
"""
from __future__ import annotations

import getpass
import json
import re
import sys
import urllib.error
import urllib.request
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
ENV = ROOT / ".env"
NAME = "GEMINI_API_KEYS"
MAX_KEYS = 5


def read_env_keys() -> list:
    if not ENV.exists():
        return []
    for line in ENV.read_text(encoding="utf-8").splitlines():
        if line.startswith(NAME + "="):
            return [k for k in re.split(r"[,\s;]+", line.split("=", 1)[1].strip().strip('"')) if k]
    return []


def write_env_keys(keys: list) -> None:
    lines = ENV.read_text(encoding="utf-8").splitlines() if ENV.exists() else []
    lines = [ln for ln in lines if not ln.startswith(NAME + "=")]  # 중복 줄 제거
    lines.append(f"{NAME}={','.join(keys)}")
    ENV.write_text("\n".join(lines) + "\n", encoding="utf-8")


def mask(k: str) -> str:
    return f"…{k[-4:]}"


def ask_keys(existing: list) -> list:
    keys = list(existing)
    print(f"키를 한 칸씩 붙여넣고 Enter 하세요(화면에는 안 보입니다). 끝내려면 빈 칸에서 Enter. 최대 {MAX_KEYS}개.")
    while len(keys) < MAX_KEYS:
        k = getpass.getpass(f"  키 {len(keys) + 1}: ").strip().strip('"').strip("'")
        if not k:
            break
        if not k.startswith("AIza") or len(k) < 30:
            print("    ⚠ 보통 'AIza'로 시작하는 39자 키입니다. 잘못 붙여넣었다면 이 칸은 건너뛰고 다시 실행하세요.")
        if k in keys:
            print("    이미 넣은 키라 건너뜁니다.")
            continue
        keys.append(k)
    return keys


def test_key(key: str) -> str:
    url = "https://generativelanguage.googleapis.com/v1beta/models/gemini-2.5-flash-lite:generateContent"
    body = json.dumps({"contents": [{"parts": [{"text": "OK라고만 답해"}]}], "generationConfig": {"maxOutputTokens": 5}}).encode()
    req = urllib.request.Request(url, data=body, headers={"x-goog-api-key": key, "Content-Type": "application/json"})
    try:
        with urllib.request.urlopen(req, timeout=30) as r:
            return "정상" if r.status == 200 else f"HTTP {r.status}"
    except urllib.error.HTTPError as e:
        txt = e.read().decode("utf-8", "replace").lower()
        if e.code == 429:
            return "한도 초과(키는 유효, 잠시 뒤 다시 사용)"
        if e.code in (400, 401, 403):
            return "키가 잘못되었거나 권한 없음"
        return f"HTTP {e.code}"
    except Exception as e:  # noqa: BLE001
        return f"연결 실패: {e}"


def main() -> None:
    if "--status" in sys.argv:
        import os

        os.environ["GEMINI_API_KEYS"] = ",".join(read_env_keys())
        from gemini_keys import status_lines

        print("\n".join(status_lines()))
        return
    if "--test" in sys.argv:
        keys = read_env_keys()
        if not keys:
            print("저장된 키가 없습니다.")
        for i, k in enumerate(keys, 1):
            print(f"키 {i} ({mask(k)}): {test_key(k)}")
        return
    existing = read_env_keys()
    keys: list = []
    if existing:
        print(f"이미 키 {len(existing)}개가 있습니다: " + ", ".join(mask(k) for k in existing))
        mode = input("추가하려면 a, 모두 새로 바꾸려면 r, 취소는 Enter: ").strip().lower()
        if mode == "a":
            keys = existing
        elif mode != "r":
            print("취소했습니다.")
            return
    keys = ask_keys(keys)
    if not keys:
        print("입력된 키가 없어 .env 를 바꾸지 않았습니다.")
        return
    write_env_keys(keys)
    print(f"\n저장했습니다: 키 {len(keys)}개 (" + ", ".join(mask(k) for k in keys) + ")")
    print("다음: 서버라면 'touch deploy/.restart_requested' 로 재시작 요청을 하세요. 확인은 --status / --test")


if __name__ == "__main__":
    main()
