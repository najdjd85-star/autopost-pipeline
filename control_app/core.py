"""관제 프로그램의 핵심 로직(화면 없음): 설정, 내 PC·서버(SSH) 명령 실행, 사이트·서버 상태 조회.

서버는 SSH 키로 접속한다. 비밀번호는 저장하지 않는다. 설정은 data/control_settings.json(깃에 올라가지 않음)에 둔다.
"""
from __future__ import annotations

import json
import os
import shlex
import subprocess
import sys
import threading
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any, Callable, Dict, List, Optional, Tuple

ROOT = Path(__file__).resolve().parent.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

SETTINGS_PATH = ROOT / "data" / "control_settings.json"
KST = timezone(timedelta(hours=9))
CREATE_NO_WINDOW = 0x08000000 if sys.platform == "win32" else 0

# (내부 키, main.py 인자, 이름, 서브도메인)
SITES: List[Tuple[str, str, str, str]] = [
    ("A", "site_a", "정부지원금", "gov"),
    ("B", "site_b", "통신비·렌탈", "life"),
    ("C", "site_c", "세금·연금", "tax"),
]

DEFAULTS: Dict[str, Any] = {
    "ssh_host": "",
    "ssh_port": 22,
    "ssh_user": "",
    "ssh_key": str(Path.home() / ".ssh" / "id_ed25519_cloudways"),
    "remote_dir": "~/autopost-pipeline",
}


# ------------------------------------------------------------------ 설정
def load_settings() -> Dict[str, Any]:
    data = dict(DEFAULTS)
    try:
        data.update(json.loads(SETTINGS_PATH.read_text(encoding="utf-8")))
    except (OSError, ValueError):
        pass
    return data


def save_settings(data: Dict[str, Any]) -> None:
    SETTINGS_PATH.parent.mkdir(parents=True, exist_ok=True)
    SETTINGS_PATH.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")


def ssh_ready(s: Dict[str, Any]) -> bool:
    return bool(s.get("ssh_host") and s.get("ssh_user") and Path(str(s.get("ssh_key", ""))).exists())


# ------------------------------------------------------------------ 명령 실행
def ssh_argv(s: Dict[str, Any]) -> List[str]:
    return [
        "ssh",
        "-i", str(s["ssh_key"]),
        "-p", str(s.get("ssh_port") or 22),
        "-o", "BatchMode=yes",
        "-o", "StrictHostKeyChecking=accept-new",
        "-o", "ConnectTimeout=12",
        "-o", "ServerAliveInterval=15",
        f"{s['ssh_user']}@{s['ssh_host']}",
    ]


def _server_script(s: Dict[str, Any], body: str) -> str:
    return f"cd {s.get('remote_dir') or '~/autopost-pipeline'} || exit 1\n{body}\n"


class Job:
    """프로세스 하나를 스레드에서 돌리며 줄 단위로 출력을 흘려 준다(화면 쪽에서 on_line/on_done을 큐로 받는다)."""

    def __init__(self) -> None:
        self.proc: Optional[subprocess.Popen] = None

    def start(
        self,
        argv: List[str],
        on_line: Callable[[str], None],
        on_done: Callable[[int], None],
        stdin_text: Optional[str] = None,
        cwd: Optional[str] = None,
    ) -> None:
        env = dict(os.environ, PYTHONIOENCODING="utf-8", PYTHONUNBUFFERED="1")

        def run() -> None:
            rc = -1
            try:
                self.proc = subprocess.Popen(
                    argv,
                    stdin=subprocess.PIPE if stdin_text is not None else subprocess.DEVNULL,
                    stdout=subprocess.PIPE,
                    stderr=subprocess.STDOUT,
                    cwd=cwd,
                    env=env,
                    creationflags=CREATE_NO_WINDOW,
                )
                if stdin_text is not None and self.proc.stdin:
                    self.proc.stdin.write(stdin_text.encode("utf-8"))
                    self.proc.stdin.close()
                assert self.proc.stdout is not None
                for raw in iter(self.proc.stdout.readline, b""):
                    on_line(raw.decode("utf-8", errors="replace").rstrip("\r\n"))
                rc = self.proc.wait()
            except FileNotFoundError as exc:
                on_line(f"실행 파일을 찾을 수 없습니다: {exc}")
            except Exception as exc:  # noqa: BLE001
                on_line(f"실행 중 오류: {exc}")
            on_done(rc)

        threading.Thread(target=run, daemon=True).start()

    def stop(self) -> None:
        if self.proc and self.proc.poll() is None:
            self.proc.terminate()


def start_local(job: Job, command: str, on_line, on_done) -> None:
    """내 PC에서 파워셸 명령을 실행한다(작업 폴더는 프로젝트 폴더)."""
    wrapped = "[Console]::OutputEncoding=[Text.Encoding]::UTF8; " + command
    job.start(["powershell", "-NoProfile", "-NonInteractive", "-Command", wrapped], on_line, on_done, cwd=str(ROOT))


def start_python(job: Job, args: List[str], on_line, on_done) -> None:
    """프로젝트 가상환경의 파이썬으로 main.py 등을 실행한다(내 PC)."""
    py = ROOT / "venv" / "Scripts" / "python.exe"
    job.start([str(py if py.exists() else sys.executable), "-X", "utf8"] + args, on_line, on_done, cwd=str(ROOT))


def start_server(job: Job, s: Dict[str, Any], body: str, on_line, on_done) -> None:
    """서버에서 bash 스크립트를 실행한다(스크립트는 표준입력으로 보내 따옴표 문제를 피한다)."""
    if not ssh_ready(s):
        on_line("서버 연결 설정이 아직 없습니다. 왼쪽 '설정·키'에서 SSH를 먼저 설정하세요.")
        on_done(-1)
        return
    job.start(ssh_argv(s) + ["bash", "-s"], on_line, on_done, stdin_text=_server_script(s, body))


def server_capture(s: Dict[str, Any], body: str, timeout: int = 45) -> Tuple[int, str]:
    """서버 명령을 실행하고 끝날 때까지 기다려 (종료코드, 출력)을 돌려준다."""
    if not ssh_ready(s):
        return -1, "서버 연결 설정이 아직 없습니다."
    try:
        res = subprocess.run(
            ssh_argv(s) + ["bash", "-s"],
            input=_server_script(s, body).encode("utf-8"),
            capture_output=True,
            timeout=timeout,
            creationflags=CREATE_NO_WINDOW,
        )
    except subprocess.TimeoutExpired:
        return -2, "서버 응답이 없습니다(시간 초과)."
    except FileNotFoundError:
        return -1, "ssh 프로그램을 찾을 수 없습니다."
    return res.returncode, (res.stdout + res.stderr).decode("utf-8", errors="replace")


# ------------------------------------------------------------------ 서버 상태
STATUS_SCRIPT = r"""
echo "COMMIT=$(git rev-parse --short HEAD)"
git fetch -q origin main 2>/dev/null
echo "BEHIND=$(git rev-list --count HEAD..origin/main 2>/dev/null)"
echo "DAEMON=$(pgrep -f 'main.py daemon' | head -1)"
echo "DISK=$(df -h ~ | tail -1 | awk '{print $3"/"$2}')"
echo "STOP=$([ -f deploy/.stop_requested ] && echo 1 || echo 0)"
echo "RESTART=$([ -f deploy/.restart_requested ] && echo 1 || echo 0)"
echo "QUEUE=$(python3 -c "import json;print(len(json.load(open('data/output/threads_queue.json'))))" 2>/dev/null || echo 0)"
echo "LASTLOG=$(tail -n 1 data/logs/pipeline.log 2>/dev/null | cut -c1-140)"
"""


def server_status(s: Dict[str, Any]) -> Dict[str, str]:
    rc, out = server_capture(s, STATUS_SCRIPT)
    info: Dict[str, str] = {"ok": "1" if rc == 0 else "0"}
    if rc != 0:
        info["error"] = out.strip()[:300]
        return info
    for line in out.splitlines():
        if "=" in line:
            k, v = line.split("=", 1)
            info[k.strip()] = v.strip()
    return info


DEMAND_SCRIPT = r"""
for f in search_demand.json topic_log_A.json topic_log_B.json topic_log_C.json threads_queue.json; do
  echo "@@$f"
  cat data/output/$f 2>/dev/null || echo "null"
done
"""


def server_data(s: Dict[str, Any]) -> Dict[str, Any]:
    """서버의 검색량·주제 기록·스레드 대기열 파일을 읽어 온다."""
    rc, out = server_capture(s, DEMAND_SCRIPT, timeout=60)
    if rc != 0:
        return {"error": out.strip()[:300]}
    parts: Dict[str, Any] = {}
    name = None
    buf: List[str] = []

    def flush() -> None:
        if name:
            try:
                parts[name] = json.loads("\n".join(buf) or "null")
            except ValueError:
                parts[name] = None

    for line in out.splitlines():
        if line.startswith("@@"):
            flush()
            name, buf = line[2:], []
        else:
            buf.append(line)
    flush()
    return parts


def local_data() -> Dict[str, Any]:
    """서버에 연결하기 전에 보여 줄 내 PC의 데이터(서버보다 오래됐을 수 있다)."""
    out_dir = ROOT / "data" / "output"
    parts: Dict[str, Any] = {}
    for name in ("search_demand.json", "topic_log_A.json", "topic_log_B.json", "topic_log_C.json", "threads_queue.json"):
        try:
            parts[name] = json.loads((out_dir / name).read_text(encoding="utf-8"))
        except (OSError, ValueError):
            parts[name] = None
    return parts


def topic_rows(parts: Dict[str, Any]) -> List[Dict[str, Any]]:
    """검색량이 큰 순서로 정렬한 주제 목록 + 가장 최근에 쓴 날짜."""
    demand = (parts.get("search_demand.json") or {}).get("keywords") or {}
    last: Dict[str, Tuple[str, str]] = {}
    for key, label in (("A", "정부"), ("B", "통신"), ("C", "세금")):
        for e in parts.get(f"topic_log_{key}.json") or []:
            kw, date = e.get("keyword", ""), e.get("date", "")
            if kw and date >= last.get(kw, ("", ""))[0]:
                last[kw] = (date, label)
    rows = []
    for kw, v in demand.items():
        date, label = last.get(kw, ("", ""))
        rows.append(
            {
                "keyword": kw,
                "volume": v.get("volume") or 0,
                "suggest": len(v.get("suggest") or []),
                "last": f"{label} {date}" if date else "",
                "date": date,
            }
        )
    rows.sort(key=lambda r: (-r["volume"], -r["suggest"], r["keyword"]))
    return rows


# ------------------------------------------------------------------ 사이트(워드프레스·서치콘솔)
def site_snapshot(site: str) -> Dict[str, Any]:
    """사이트 한 곳의 최근 글(7일)과 서치콘솔 28일 합계를 읽는다. 실패한 항목은 빈 값."""
    snap: Dict[str, Any] = {"posts": [], "clicks": None, "impressions": None, "error": ""}
    try:
        from wp_client import WordPressClient

        wp = WordPressClient(site)
        if not wp.is_configured:
            snap["error"] = "워드프레스 설정 없음"
        else:
            for p in wp.get_recent_posts(days=7, per_page=10):
                snap["posts"].append(
                    {
                        "title": (p.get("title") or {}).get("rendered", ""),
                        "date": (p.get("date") or "")[:16].replace("T", " "),
                        "link": p.get("link", ""),
                    }
                )
    except Exception as exc:  # noqa: BLE001
        snap["error"] = f"워드프레스 조회 실패: {exc}"[:200]
    try:
        from urllib.parse import urlparse

        from config import settings as cfg
        from google.oauth2 import service_account
        from googleapiclient.discovery import build

        key = Path(cfg.google_key_path)
        host = urlparse(cfg.sites[site].wp_url).hostname if site in cfg.sites else ""
        if key.exists() and host:
            creds = service_account.Credentials.from_service_account_file(
                str(key), scopes=["https://www.googleapis.com/auth/webmasters.readonly"]
            )
            svc = build("searchconsole", "v1", credentials=creds, cache_discovery=False)
            end = datetime.now(KST).date()
            body = {"startDate": (end - timedelta(days=28)).isoformat(), "endDate": end.isoformat()}
            rows = svc.searchanalytics().query(siteUrl=f"sc-domain:{host}", body=body).execute().get("rows", [])
            snap["clicks"] = int(rows[0].get("clicks", 0)) if rows else 0
            snap["impressions"] = int(rows[0].get("impressions", 0)) if rows else 0
    except Exception:  # noqa: BLE001 - 선택 항목
        pass
    return snap


def coupang_state() -> str:
    """내 PC의 쿠팡 호출 한도 상태(서버는 쿠팡을 부르지 않는다)."""
    try:
        from constants import COUPANG_API_ENABLED

        if not COUPANG_API_ENABLED:
            return "API 꺼짐 · 고정 링크 7종"
        from smart_affiliate_matcher import coupang_blocked_minutes, coupang_calls_left

        blocked = coupang_blocked_minutes()
        if blocked:
            return f"차단 {blocked}분 남음"
        return f"남은 호출 {coupang_calls_left()}"
    except Exception:  # noqa: BLE001
        return "확인 불가"


def key_status() -> Dict[str, bool]:
    """키가 설정돼 있는지만 돌려준다(값은 읽어 오지 않는다)."""
    from config import settings as cfg

    names = {
        "Claude": "anthropic_api_key",
        "스레드": "threads_access_token",
        "네이버 검색광고": "naver_ad_api_key",
        "텔레그램": "telegram_bot_token",
    }
    return {label: bool(getattr(cfg, attr, "")) for label, attr in names.items()}


def public_ip() -> str:
    import urllib.request

    try:
        with urllib.request.urlopen("https://api.ipify.org", timeout=8) as r:
            return r.read().decode().strip()
    except Exception:  # noqa: BLE001
        return ""


def quote(text: str) -> str:
    return shlex.quote(text)
