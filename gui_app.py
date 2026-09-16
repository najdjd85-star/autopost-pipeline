"""
3사이트 통합 패시브 미디어 파이프라인 - 데스크톱 GUI 런처.

터미널 대신 일반적인 윈도우 창(tkinter)에서 버튼 클릭으로 CLI 명령을
실행하고, 실시간 로그를 창 안에서 확인할 수 있게 해주는 얇은 래퍼.

실제 로직은 전혀 건드리지 않는다 - 각 버튼은 그저
`venv\\Scripts\\python.exe main.py <command>` 를 서브프로세스로 실행하고
그 출력을 창에 스트리밍할 뿐이다 (main.py/CLI 동작은 기존과 완전히 동일).

실행:
    venv\\Scripts\\pythonw.exe gui_app.py   (콘솔 창 없이 실행)
"""
from __future__ import annotations

import queue
import subprocess
import sys
import threading
import tkinter as tk
from pathlib import Path
from tkinter import messagebox, scrolledtext, ttk

BASE_DIR = Path(__file__).resolve().parent
PYTHON_EXE = BASE_DIR / "venv" / "Scripts" / "python.exe"
ENV_FILE = BASE_DIR / ".env"

# Windows에서 자식 프로세스가 별도 콘솔 창을 띄우지 않도록 함.
CREATE_NO_WINDOW = 0x08000000 if sys.platform == "win32" else 0

ACTIONS = [
    ("🏛️ Site A 실행 (정부지원금)", ["run-now", "site_a"], "oneoff"),
    ("📶 Site B 실행 (통신/렌탈)", ["run-now", "site_b"], "oneoff"),
    ("💰 Site C 실행 (세금환급)", ["run-now", "site_c"], "oneoff"),
    ("🚀 전체 사이트 실행", ["run-now", "all"], "oneoff"),
    ("📈 순위 방어 점검", ["refresh-check"], "oneoff"),
    ("📬 뉴스레터 즉시 발송", ["send-newsletter"], "oneoff"),
]

# "미리보기"는 워드프레스/SNS 어디에도 등록/발행하지 않고, 로컬 HTML 파일만
# 생성해서 기본 브라우저로 자동으로 열어준다 (main.py의 preview 서브커맨드).
PREVIEW_ACTIONS = [
    ("🔍 Site A 미리보기", ["preview", "site_a"]),
    ("🔍 Site B 미리보기", ["preview", "site_b"]),
    ("🔍 Site C 미리보기", ["preview", "site_c"]),
]


class PipelineGUI:
    def __init__(self, root: tk.Tk):
        self.root = root
        self.root.title("3사이트 통합 패시브 미디어 파이프라인")
        self.root.geometry("820x680")
        self.root.minsize(680, 540)

        self.log_queue: "queue.Queue[str]" = queue.Queue()
        self.current_process: subprocess.Popen | None = None
        self.daemon_process: subprocess.Popen | None = None
        self.action_buttons: list[tk.Widget] = []

        self._build_ui()
        self._poll_log_queue()
        self.root.protocol("WM_DELETE_WINDOW", self._on_close)

        if not PYTHON_EXE.exists():
            messagebox.showerror(
                "가상환경을 찾을 수 없음",
                f"{PYTHON_EXE}\n가 존재하지 않습니다. 프로젝트 폴더 구조를 확인해주세요.",
            )

    # ------------------------------------------------------------------
    # UI 구성
    # ------------------------------------------------------------------
    def _build_ui(self) -> None:
        style = ttk.Style()
        try:
            style.theme_use("vista")
        except tk.TclError:
            pass

        header = ttk.Frame(self.root, padding=(16, 14, 16, 6))
        header.pack(fill="x")
        ttk.Label(
            header, text="3사이트 통합 패시브 미디어 파이프라인", font=("맑은 고딕", 15, "bold")
        ).pack(anchor="w")
        ttk.Label(
            header,
            text="버튼을 누르면 아래 로그 창에 실시간으로 진행 상황이 표시됩니다.",
            foreground="#555555",
        ).pack(anchor="w", pady=(2, 0))

        btn_frame = ttk.LabelFrame(self.root, text="콘텐츠 파이프라인", padding=12)
        btn_frame.pack(fill="x", padx=16, pady=(6, 4))

        for i, (label, args, kind) in enumerate(ACTIONS):
            btn = ttk.Button(
                btn_frame, text=label, command=lambda a=args, l=label: self._run_oneoff(a, l)
            )
            btn.grid(row=i // 2, column=i % 2, sticky="ew", padx=6, pady=5)
            self.action_buttons.append(btn)
        btn_frame.columnconfigure(0, weight=1)
        btn_frame.columnconfigure(1, weight=1)

        preview_frame = ttk.LabelFrame(
            self.root, text="미리보기 전용 (워드프레스/SNS 어디에도 등록/발행하지 않음)", padding=12
        )
        preview_frame.pack(fill="x", padx=16, pady=4)
        for i, (label, args) in enumerate(PREVIEW_ACTIONS):
            btn = ttk.Button(
                preview_frame, text=label, command=lambda a=args, l=label: self._run_oneoff(a, l)
            )
            btn.grid(row=0, column=i, sticky="ew", padx=6, pady=2)
            self.action_buttons.append(btn)
            preview_frame.columnconfigure(i, weight=1)
        ttk.Label(
            preview_frame,
            text="생성된 글을 로컬 HTML 파일로 저장하고 기본 브라우저로 자동으로 엽니다.",
            foreground="#777777",
        ).grid(row=1, column=0, columnspan=len(PREVIEW_ACTIONS), sticky="w", pady=(6, 0))

        test_btn = ttk.Button(
            preview_frame,
            text="🧪 텔레그램 승인 카드 테스트 (더미 내용, Claude 미호출)",
            command=lambda: self._run_oneoff(["test-approval", "site_a"], "텔레그램 승인 카드 테스트"),
        )
        test_btn.grid(row=2, column=0, columnspan=len(PREVIEW_ACTIONS), sticky="ew", padx=6, pady=(8, 2))
        self.action_buttons.append(test_btn)

        daemon_frame = ttk.LabelFrame(self.root, text="상시 운영 모드", padding=12)
        daemon_frame.pack(fill="x", padx=16, pady=4)

        self.daemon_btn = ttk.Button(
            daemon_frame, text="▶ 데몬 시작 (스케줄러+텔레그램봇+구독서버)", command=self._toggle_daemon
        )
        self.daemon_btn.pack(side="left", padx=(0, 10))
        self.daemon_status = ttk.Label(daemon_frame, text="● 중지됨", foreground="#999999")
        self.daemon_status.pack(side="left")

        util_frame = ttk.Frame(self.root, padding=(16, 4))
        util_frame.pack(fill="x")
        ttk.Button(util_frame, text="⚙️ .env 설정 파일 열기", command=self._open_env).pack(
            side="left"
        )
        ttk.Button(util_frame, text="🗑️ 로그 지우기", command=self._clear_log).pack(
            side="left", padx=8
        )
        ttk.Button(
            util_frame, text="🤖 텔레그램 Chat ID 확인", command=self._check_telegram_chat_id
        ).pack(side="left", padx=(0, 8))
        ttk.Button(
            util_frame, text="🔌 API 연결 테스트 (Claude 토큰 0 소모)", command=self._check_apis
        ).pack(side="left")

        util_frame2 = ttk.Frame(self.root, padding=(16, 0, 16, 4))
        util_frame2.pack(fill="x")
        ttk.Button(
            util_frame2, text="▶️ YouTube OAuth 토큰 발급 (브라우저 로그인)",
            command=self._generate_youtube_token,
        ).pack(side="left")

        log_frame = ttk.LabelFrame(self.root, text="실행 로그", padding=8)
        log_frame.pack(fill="both", expand=True, padx=16, pady=(4, 12))

        self.log_text = scrolledtext.ScrolledText(
            log_frame, wrap="word", font=("Consolas", 10), state="disabled", bg="#0f121c", fg="#d8dcea"
        )
        self.log_text.pack(fill="both", expand=True)

        self.status_bar = ttk.Label(self.root, text="대기 중", relief="sunken", anchor="w", padding=(8, 3))
        self.status_bar.pack(fill="x", side="bottom")

    # ------------------------------------------------------------------
    # 로그 출력
    # ------------------------------------------------------------------
    def _append_log(self, text: str) -> None:
        self.log_text.configure(state="normal")
        self.log_text.insert("end", text)
        self.log_text.see("end")
        self.log_text.configure(state="disabled")

    def _clear_log(self) -> None:
        self.log_text.configure(state="normal")
        self.log_text.delete("1.0", "end")
        self.log_text.configure(state="disabled")

    def _poll_log_queue(self) -> None:
        try:
            while True:
                line = self.log_queue.get_nowait()
                self._append_log(line)
        except queue.Empty:
            pass
        self.root.after(120, self._poll_log_queue)

    # ------------------------------------------------------------------
    # 일회성 명령 실행 (run-now / refresh-check / send-newsletter)
    # ------------------------------------------------------------------
    def _set_buttons_enabled(self, enabled: bool) -> None:
        state = "normal" if enabled else "disabled"
        for btn in self.action_buttons:
            btn.configure(state=state)

    def _run_oneoff(self, args: list[str], label: str) -> None:
        self._run_script("main.py", args, label)

    def _check_telegram_chat_id(self) -> None:
        self._run_script("scripts/get_telegram_chat_id.py", [], "텔레그램 Chat ID 확인")

    def _check_apis(self) -> None:
        self._run_script("scripts/check_apis.py", [], "API 연결 테스트 (Claude 미호출)")

    def _generate_youtube_token(self) -> None:
        self._run_script(
            "scripts/generate_youtube_token.py", [], "YouTube OAuth 토큰 발급"
        )

    def _run_script(self, script: str, args: list[str], label: str) -> None:
        if not PYTHON_EXE.exists():
            messagebox.showerror("오류", "가상환경을 찾을 수 없습니다.")
            return
        if self.current_process is not None:
            messagebox.showwarning("실행 중", "다른 작업이 끝난 뒤 다시 시도해주세요.")
            return

        self._set_buttons_enabled(False)
        self.status_bar.configure(text=f"실행 중: {label}")
        self._append_log(f"\n{'='*60}\n▶ {label} 시작\n{'='*60}\n")

        thread = threading.Thread(target=self._worker_run, args=(script, args, label), daemon=True)
        thread.start()

    def _worker_run(self, script: str, args: list[str], label: str) -> None:
        try:
            process = subprocess.Popen(
                [str(PYTHON_EXE), script, *args],
                cwd=str(BASE_DIR),
                stdout=subprocess.PIPE,
                stderr=subprocess.STDOUT,
                text=True,
                encoding="utf-8",
                errors="replace",
                creationflags=CREATE_NO_WINDOW,
            )
            self.current_process = process
            for line in process.stdout:  # type: ignore[union-attr]
                self.log_queue.put(line)
            process.wait()
            self.log_queue.put(f"\n✅ {label} 완료 (종료 코드 {process.returncode})\n")
        except Exception as exc:  # noqa: BLE001
            self.log_queue.put(f"\n❌ {label} 실행 중 오류: {exc}\n")
        finally:
            self.current_process = None
            self.root.after(0, lambda: self._set_buttons_enabled(True))
            self.root.after(0, lambda: self.status_bar.configure(text="대기 중"))

    # ------------------------------------------------------------------
    # 데몬 모드 (상시 실행 - 시작/중지 토글)
    # ------------------------------------------------------------------
    def _toggle_daemon(self) -> None:
        if self.daemon_process is None:
            self._start_daemon()
        else:
            self._stop_daemon()

    def _start_daemon(self) -> None:
        if not PYTHON_EXE.exists():
            messagebox.showerror("오류", "가상환경을 찾을 수 없습니다.")
            return

        self._append_log(f"\n{'='*60}\n▶ 데몬 모드 시작 (스케줄러+텔레그램봇+구독서버)\n{'='*60}\n")
        self.daemon_process = subprocess.Popen(
            [str(PYTHON_EXE), "main.py", "daemon"],
            cwd=str(BASE_DIR),
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            text=True,
            encoding="utf-8",
            errors="replace",
            creationflags=CREATE_NO_WINDOW,
        )
        self.daemon_btn.configure(text="■ 데몬 중지")
        self.daemon_status.configure(text="● 실행 중", foreground="#1e8e3e")

        thread = threading.Thread(target=self._daemon_reader, daemon=True)
        thread.start()

    def _daemon_reader(self) -> None:
        process = self.daemon_process
        if process is None or process.stdout is None:
            return
        for line in process.stdout:
            self.log_queue.put(line)
        # 프로세스가 (정상/비정상적으로) 종료되면 UI 상태를 되돌린다.
        if self.daemon_process is process:
            self.daemon_process = None
            self.log_queue.put("\n⏹️ 데몬 프로세스가 종료되었습니다.\n")
            self.root.after(0, self._reset_daemon_ui)

    def _reset_daemon_ui(self) -> None:
        self.daemon_btn.configure(text="▶ 데몬 시작 (스케줄러+텔레그램봇+구독서버)")
        self.daemon_status.configure(text="● 중지됨", foreground="#999999")

    def _stop_daemon(self) -> None:
        if self.daemon_process is not None:
            self.daemon_process.terminate()
            self._append_log("\n⏹️ 데몬 중지 요청을 보냈습니다.\n")
        self.daemon_process = None
        self._reset_daemon_ui()

    # ------------------------------------------------------------------
    # 기타
    # ------------------------------------------------------------------
    def _open_env(self) -> None:
        if not ENV_FILE.exists():
            messagebox.showwarning("파일 없음", ".env 파일이 없습니다. .env.example을 복사해 생성해주세요.")
            return
        subprocess.Popen(["notepad.exe", str(ENV_FILE)])

    def _on_close(self) -> None:
        if self.daemon_process is not None or self.current_process is not None:
            if not messagebox.askyesno(
                "종료 확인", "실행 중인 작업이 있습니다. 종료하면 함께 중지됩니다. 종료할까요?"
            ):
                return
            for proc in (self.daemon_process, self.current_process):
                if proc is not None:
                    try:
                        proc.terminate()
                    except Exception:  # noqa: BLE001
                        pass
        self.root.destroy()


def main() -> None:
    root = tk.Tk()
    PipelineGUI(root)
    root.mainloop()


if __name__ == "__main__":
    main()
