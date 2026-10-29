"""여러 설정 값을 .env 에 안전하게 넣는다. 값은 화면에 보이지 않게(비밀번호처럼) 입력받는다.

사용: venv\\Scripts\\python.exe scripts\\set_env_secrets.py 이름1 이름2 ...
예:   scripts\\set_env_secrets.py NAVER_AD_API_KEY NAVER_AD_SECRET_KEY NAVER_AD_CUSTOMER_ID
- 해당 이름의 줄만 바꾸고(중복 줄은 하나로), 다른 설정은 건드리지 않습니다. 값은 출력하지 않고 길이만 알려 줍니다.
- 이미 값이 있으면 덮어쓸지 물어봅니다. 빈 칸으로 Enter 하면 그 항목은 그대로 둡니다.
"""
from __future__ import annotations

import getpass
import sys
from pathlib import Path

ENV = Path(__file__).resolve().parent.parent / ".env"


def read_lines() -> list:
    return ENV.read_text(encoding="utf-8").splitlines() if ENV.exists() else []


def current(lines: list, name: str) -> str:
    for ln in lines:
        if ln.startswith(name + "="):
            return ln.split("=", 1)[1].strip()
    return ""


def main() -> None:
    names = sys.argv[1:]
    if not names:
        print("사용법: set_env_secrets.py 이름1 이름2 ...")
        return
    lines = read_lines()
    changed = []
    for name in names:
        old = current(lines, name)
        if old:
            ans = input(f"{name} 에 이미 값이 있습니다(길이 {len(old)}). 덮어쓰려면 y, 건너뛰려면 Enter: ").strip().lower()
            if ans != "y":
                continue
        value = getpass.getpass(f"{name} (화면에 안 보임, 건너뛰려면 Enter): ").strip().strip('"').strip("'")
        if not value:
            continue
        lines = [ln for ln in lines if not ln.startswith(name + "=")]
        lines.append(f"{name}={value}")
        changed.append((name, len(value)))
    if changed:
        ENV.write_text("\n".join(lines) + "\n", encoding="utf-8")
        for name, n in changed:
            print(f"저장: {name} (길이 {n})")
    else:
        print("바꾼 항목이 없습니다.")


if __name__ == "__main__":
    main()
