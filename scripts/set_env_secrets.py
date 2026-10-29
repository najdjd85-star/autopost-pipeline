"""설정 값(API 키 등)을 .env 에 안전하게 넣는다. 값은 화면에 보이지 않게(비밀번호처럼) 입력받는다.

사용:
  set_env_secrets.py                         이름과 값을 직접 입력(여러 개 반복 가능, 어떤 API 키든 가능)
  set_env_secrets.py 이름1 이름2 ...         정해진 이름들만 차례로 입력
  set_env_secrets.py --list                  .env 에 어떤 항목이 있는지(값은 숨김, 길이만) 보기

- 해당 이름의 줄만 바꾸고(중복 줄은 하나로), 다른 설정은 건드리지 않습니다. 값은 출력하지 않습니다.
- 이름은 영문 대문자·숫자·밑줄만 가능합니다(예: NAVER_DATALAB_ID).
- 이미 값이 있으면 덮어쓸지 물어봅니다. 빈 칸으로 Enter 하면 그 항목은 그대로 둡니다.
"""
from __future__ import annotations

import getpass
import re
import sys
from pathlib import Path

ENV = Path(__file__).resolve().parent.parent / ".env"
NAME_RE = re.compile(r"^[A-Z][A-Z0-9_]*$")


def read_lines() -> list:
    return ENV.read_text(encoding="utf-8").splitlines() if ENV.exists() else []


def current(lines: list, name: str) -> str:
    for ln in lines:
        if ln.startswith(name + "="):
            return ln.split("=", 1)[1].strip()
    return ""


def put(lines: list, name: str) -> tuple:
    """이름 하나를 입력받아 lines 에 반영한다. (바뀐 lines, 저장한 값 길이 또는 0)."""
    old = current(lines, name)
    if old:
        ans = input(f"{name} 에 이미 값이 있습니다(길이 {len(old)}). 덮어쓰려면 y, 건너뛰려면 Enter: ").strip().lower()
        if ans != "y":
            return lines, 0
    value = getpass.getpass(f"{name} 의 값 (화면에 안 보임, 건너뛰려면 Enter): ").strip().strip('"').strip("'")
    if not value:
        return lines, 0
    lines = [ln for ln in lines if not ln.startswith(name + "=")]
    lines.append(f"{name}={value}")
    return lines, len(value)


def show_list() -> None:
    lines = read_lines()
    print(f".env 항목 {sum(1 for ln in lines if '=' in ln and not ln.startswith('#'))}개 (값은 숨김):")
    for ln in lines:
        if "=" in ln and not ln.lstrip().startswith("#"):
            k, v = ln.split("=", 1)
            print(f"  {k:<34} {'값 있음(길이 ' + str(len(v.strip())) + ')' if v.strip() else '비어 있음'}")


def main() -> None:
    args = sys.argv[1:]
    if "--list" in args:
        show_list()
        return
    lines = read_lines()
    saved = []
    if args:
        for name in args:
            lines, n = put(lines, name)
            if n:
                saved.append((name, n))
    else:
        print("입력할 항목의 이름을 적고 Enter 하세요(예: NAVER_DATALAB_ID). 끝내려면 빈 칸에서 Enter.")
        print("어떤 이름이 있는지 보려면 'list' 라고 입력하세요.")
        while True:
            name = input("\n이름: ").strip().strip('"').strip("'")
            if not name:
                break
            if name.lower() == "list":
                show_list()
                continue
            name = name.upper().replace("-", "_").replace(" ", "_")
            if not NAME_RE.match(name):
                print("  이름은 영문 대문자·숫자·밑줄만 쓸 수 있습니다.")
                continue
            lines, n = put(lines, name)
            if n:
                saved.append((name, n))
                print(f"  → 저장 준비: {name} (길이 {n})")
    if saved:
        ENV.write_text("\n".join(lines) + "\n", encoding="utf-8")
        print()
        for name, n in saved:
            print(f"저장: {name} (길이 {n})")
    else:
        print("바꾼 항목이 없습니다.")


if __name__ == "__main__":
    main()
