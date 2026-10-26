"""파이프라인 관제 프로그램 화면(tkinter + sv_ttk 다크 테마). 영상 자동 편집기와 같은 사이드바 구성."""
from __future__ import annotations

import os
import queue
import threading
import tkinter as tk
import webbrowser
from datetime import datetime
from pathlib import Path
from tkinter import messagebox, ttk
from typing import Any, Callable, Dict, List, Optional

try:
    import sv_ttk
except ImportError:  # 테마 없이도 동작
    sv_ttk = None

from control_app import core

BG = "#1c1c1c"
SIDE = "#141414"
CARD = "#2a2a2a"
TEXT = "#e7e7ea"
MUT = "#8a8a95"
ORANGE = "#f26b1d"
ORANGE_SOFT = "#3a2314"
GREEN = "#7bd69a"
YELLOW = "#e8c25a"
RED = "#f08080"
FONT = "Malgun Gothic"
MONO = "Consolas"


# ------------------------------------------------------------------ 작은 부품
class Btn(tk.Label):
    def __init__(self, parent, text: str, command: Callable[[], None], primary: bool = False, **kw: Any) -> None:
        self.base = ORANGE if primary else "#3a3a3a"
        self.hover = "#ff8a45" if primary else "#4a4a4a"
        super().__init__(parent, text=text, bg=self.base, fg="#ffffff" if primary else TEXT, font=(FONT, 10),
                         padx=12, pady=6, cursor="hand2", **kw)
        self.command = command
        self.bind("<Enter>", lambda _e: self.config(bg=self.hover))
        self.bind("<Leave>", lambda _e: self.config(bg=self.base))
        self.bind("<Button-1>", lambda _e: self.command())


def card(parent, **kw: Any) -> tk.Frame:
    return tk.Frame(parent, bg=CARD, padx=12, pady=10, **kw)


def label(parent, text: str = "", fg: str = TEXT, size: int = 10, bold: bool = False, bg: Optional[str] = None, **kw: Any) -> tk.Label:
    return tk.Label(parent, text=text, fg=fg, bg=bg or parent["bg"], font=(FONT, size, "bold" if bold else "normal"), **kw)


class LogBox(tk.Frame):
    def __init__(self, parent, height: int = 14) -> None:
        super().__init__(parent, bg="#0b0b0e")
        self.text = tk.Text(self, height=height, bg="#0b0b0e", fg="#b8e0c0", insertbackground=TEXT, relief="flat",
                            font=(MONO, 10), wrap="word", padx=8, pady=6, state="disabled")
        bar = ttk.Scrollbar(self, command=self.text.yview)
        self.text.config(yscrollcommand=bar.set)
        bar.pack(side="right", fill="y")
        self.text.pack(side="left", fill="both", expand=True)
        self.text.tag_config("err", foreground=RED)
        self.text.tag_config("cmd", foreground=ORANGE)
        self.text.tag_config("dim", foreground=MUT)

    def add(self, line: str, tag: str = "") -> None:
        self.text.config(state="normal")
        if not tag and any(w in line for w in ("Error", "Traceback", "실패", "오류")):
            tag = "err"
        self.text.insert("end", line + "\n", tag)
        self.text.see("end")
        self.text.config(state="disabled")

    def clear(self) -> None:
        self.text.config(state="normal")
        self.text.delete("1.0", "end")
        self.text.config(state="disabled")


class Tile(tk.Frame):
    def __init__(self, parent, caption: str) -> None:
        super().__init__(parent, bg=CARD, padx=12, pady=8)
        self.value = label(self, "-", size=17, bold=True)
        self.value.pack(anchor="w")
        label(self, caption, fg=MUT, size=9).pack(anchor="w")

    def set(self, text: str, color: str = TEXT) -> None:
        self.value.config(text=text, fg=color)


class Panel(tk.Frame):
    title = ""
    subtitle = ""

    def __init__(self, app: "App") -> None:
        super().__init__(app.main, bg=BG)
        self.app = app
        label(self, self.title, size=18, bold=True).pack(anchor="w")
        label(self, self.subtitle, fg=MUT, size=9).pack(anchor="w", pady=(0, 10))
        self.body = tk.Frame(self, bg=BG)
        self.body.pack(fill="both", expand=True)

    def on_show(self) -> None:
        pass


# ------------------------------------------------------------------ 대시보드
class Dashboard(Panel):
    title = "대시보드"
    subtitle = "세 사이트와 서버의 오늘 상태입니다. 새로고침을 누르면 워드프레스·서치콘솔·서버에서 읽어 옵니다."

    def __init__(self, app: "App") -> None:
        super().__init__(app)
        top = tk.Frame(self.body, bg=BG)
        top.pack(fill="x")
        self.tiles: Dict[str, Tile] = {}
        for i, (k, cap) in enumerate((("pub", "오늘 발행한 글"), ("queue", "스레드 대기"), ("coupang", "쿠팡 호출(내 PC)"), ("server", "서버 데몬"))):
            t = Tile(top, cap)
            t.grid(row=0, column=i, sticky="nsew", padx=(0 if i == 0 else 8, 0))
            top.columnconfigure(i, weight=1, uniform="k")
            self.tiles[k] = t
        sites = tk.Frame(self.body, bg=BG)
        sites.pack(fill="x", pady=8)
        self.site_cards: Dict[str, Dict[str, tk.Label]] = {}
        for i, (key, _arg, name, _sub) in enumerate(core.SITES):
            c = card(sites)
            c.grid(row=0, column=i, sticky="nsew", padx=(0 if i == 0 else 8, 0))
            sites.columnconfigure(i, weight=1, uniform="s")
            head = tk.Frame(c, bg=CARD)
            head.pack(fill="x")
            label(head, name, size=11, bold=True, bg=CARD).pack(side="left")
            badge = label(head, "", size=9, bg=CARD)
            badge.pack(side="right")
            last = label(c, "-", fg=MUT, size=9, bg=CARD, wraplength=250, justify="left")
            last.pack(anchor="w", pady=(4, 0))
            gsc = label(c, "", fg=MUT, size=9, bg=CARD)
            gsc.pack(anchor="w")
            self.site_cards[key] = {"badge": badge, "last": last, "gsc": gsc}
        row = tk.Frame(self.body, bg=BG)
        row.pack(fill="both", expand=True)
        sched = card(row)
        sched.pack(side="left", fill="both", expand=True)
        label(sched, "일정 (한국 시간)", fg=MUT, size=9, bg=CARD).pack(anchor="w")
        for t, what in (
            ("09:20", "정책 변경 점검"), ("09:40", "표준 수치 자동 갱신(12/20부터)"), ("09:50", "검색량 수집"),
            ("19:00", "쿠팡 링크 갱신 (내 PC)"), ("20:00", "사이트 3곳 글 발행"), ("22:30", "허브 페이지 빌드"),
            ("5분마다", "스레드 대기열 확인"), ("3시간마다", "스레드 일상 글 예약"),
        ):
            r = tk.Frame(sched, bg=CARD)
            r.pack(fill="x")
            label(r, t, fg=ORANGE, size=9, bg=CARD, width=9, anchor="w").pack(side="left")
            label(r, what, size=9, bg=CARD).pack(side="left")
        notes = card(row)
        notes.pack(side="left", fill="both", expand=True, padx=(8, 0))
        label(notes, "서버 상태", fg=MUT, size=9, bg=CARD).pack(anchor="w")
        self.notes = label(notes, "새로고침을 눌러 주세요.", size=9, bg=CARD, justify="left", wraplength=420, anchor="w")
        self.notes.pack(anchor="w", fill="x")
        Btn(self.body, "새로고침", self.refresh, primary=True).pack(anchor="w", pady=(8, 0))

    def on_show(self) -> None:
        self.refresh()

    def refresh(self) -> None:
        s = self.app.settings
        today = datetime.now(core.KST).date().isoformat()
        self.tiles["coupang"].set(core.coupang_state())
        self.app.bg(lambda: [(k, core.site_snapshot(k)) for k, *_ in core.SITES], self._sites_done)
        self.app.bg(lambda: core.server_status(s) if core.ssh_ready(s) else {"ok": "0", "error": "SSH 설정 전"}, self._server_done)
        self._today = today

    def _sites_done(self, res: Any, err: Optional[Exception]) -> None:
        if err or not res:
            return
        published = 0
        for key, snap in res:
            c = self.site_cards[key]
            posts = snap["posts"]
            done = any(p["date"].startswith(self._today) for p in posts)
            published += 1 if done else 0
            c["badge"].config(text="오늘 발행됨" if done else ("확인 필요" if snap["error"] else "오늘 대기"), fg=GREEN if done else YELLOW)
            if posts:
                c["last"].config(text=f"최근: {posts[0]['title'][:34]}  ({posts[0]['date'][5:]})")
            else:
                c["last"].config(text=snap["error"] or "최근 7일 글 없음")
            c["gsc"].config(text="" if snap["clicks"] is None else f"28일 클릭 {snap['clicks']} · 노출 {snap['impressions']}")
        self.tiles["pub"].set(f"{published} / 3", GREEN if published == 3 else TEXT)

    def _server_done(self, res: Any, err: Optional[Exception]) -> None:
        if err or not res:
            return
        if res.get("ok") != "1":
            self.tiles["server"].set("연결 안 됨", YELLOW)
            self.tiles["queue"].set("-")
            self.notes.config(text=res.get("error") or "서버에 연결하지 못했습니다.")
            return
        alive = bool(res.get("DAEMON"))
        stopped = res.get("STOP") == "1"
        self.tiles["server"].set("정지됨" if stopped else ("실행 중" if alive else "꺼짐"), RED if (stopped or not alive) else GREEN)
        self.tiles["queue"].set(res.get("QUEUE", "-"))
        behind = res.get("BEHIND", "0")
        self.notes.config(
            text=f"서버 커밋 {res.get('COMMIT')}" + (f"  ·  GitHub보다 {behind}개 뒤처짐(코드 업데이트 필요)" if behind not in ("", "0") else "  ·  최신")
            + f"\n디스크 {res.get('DISK')}\n마지막 로그: {res.get('LASTLOG', '')}"
        )


# ------------------------------------------------------------------ 글 만들기
class Content(Panel):
    title = "글 만들기"
    subtitle = "검색량이 큰 주제를 골라 미리보기를 만들고, 마음에 들면 서버에서 승인 요청을 보냅니다."

    def __init__(self, app: "App") -> None:
        super().__init__(app)
        self.job = core.Job()
        bar = card(self.body)
        bar.pack(fill="x")
        label(bar, "사이트", fg=MUT, size=9, bg=CARD).pack(side="left")
        self.site = tk.StringVar(value="A")
        for key, _arg, name, _sub in core.SITES:
            tk.Radiobutton(bar, text=name, value=key, variable=self.site, bg=CARD, fg=TEXT, selectcolor="#3a3a3a",
                           activebackground=CARD, activeforeground=ORANGE, font=(FONT, 10), highlightthickness=0).pack(side="left", padx=6)
        Btn(bar, "주제 새로고침", self.load).pack(side="right")
        self.info = label(self.body, "", fg=MUT, size=9)
        self.info.pack(anchor="w", pady=(6, 2))
        cols = ("keyword", "volume", "suggest", "last")
        self.tree = ttk.Treeview(self.body, columns=cols, show="headings", height=11, selectmode="browse")
        for c, t, w in (("keyword", "주제", 300), ("volume", "월 검색량", 90), ("suggest", "자동완성", 70), ("last", "마지막 작성", 130)):
            self.tree.heading(c, text=t)
            self.tree.column(c, width=w, anchor="w" if c in ("keyword", "last") else "e")
        self.tree.pack(fill="x")
        row = card(self.body)
        row.pack(fill="x", pady=8)
        label(row, "직접 입력(비우면 선택한 주제)", fg=MUT, size=9, bg=CARD).pack(side="left")
        self.custom = ttk.Entry(row, width=28)
        self.custom.pack(side="left", padx=8)
        Btn(row, "미리보기 만들기 (내 PC, 토큰 사용)", self.preview, primary=True).pack(side="left", padx=(8, 6))
        Btn(row, "미리보기 열기", self.open_preview).pack(side="left", padx=(0, 6))
        Btn(row, "승인 요청 보내기 (서버)", self.request).pack(side="left")
        self.log = LogBox(self.body, height=9)
        self.log.pack(fill="both", expand=True)

    def on_show(self) -> None:
        if not self.tree.get_children():
            self.load()

    def load(self) -> None:
        s = self.app.settings
        self.info.config(text="불러오는 중…")
        self.app.bg(lambda: (core.server_data(s), True) if core.ssh_ready(s) else (core.local_data(), False), self._loaded)

    def _loaded(self, res: Any, err: Optional[Exception]) -> None:
        if err or not res:
            self.info.config(text=f"불러오지 못했습니다: {err}")
            return
        data, live = res
        if "error" in data:
            self.info.config(text="서버 연결 실패, 내 PC 데이터를 보여 줍니다: " + data["error"][:80])
            data = core.local_data()
            live = False
        else:
            self.info.config(text="서버 데이터" if live else "내 PC 데이터(서버 연결 전이라 오래됐을 수 있음)")
        self.tree.delete(*self.tree.get_children())
        for r in core.topic_rows(data)[:80]:
            self.tree.insert("", "end", values=(r["keyword"], f"{r['volume']:,}" if r["volume"] else "-", r["suggest"], r["last"]))

    def _keyword(self) -> str:
        kw = self.custom.get().strip()
        if kw:
            return kw
        sel = self.tree.selection()
        return self.tree.item(sel[0], "values")[0] if sel else ""

    def _site_arg(self) -> str:
        return next(a for k, a, *_ in core.SITES if k == self.site.get())

    def preview(self) -> None:
        kw = self._keyword()
        if not messagebox.askyesno("미리보기 만들기", f"'{kw or '자동 선정'}' 주제로 글을 한 편 만듭니다.\nClaude를 호출하므로 토큰이 듭니다. 워드프레스·스레드에는 올리지 않습니다.\n\n진행할까요?"):
            return
        args = ["main.py", "preview", self._site_arg()] + (["--keyword", kw] if kw else [])
        self.log.clear()
        self.log.add("$ " + " ".join(args), "cmd")
        core.start_python(self.job, args, lambda ln: self.app.ui(self.log.add, ln), lambda rc: self.app.ui(self.log.add, f"끝 (종료코드 {rc})", "dim"))

    def open_preview(self) -> None:
        d = core.ROOT / "data" / "output" / "previews"
        files = sorted(d.glob(f"{self.site.get()}_*.html"), key=lambda p: p.stat().st_mtime)
        if not files:
            messagebox.showinfo("미리보기", "아직 만든 미리보기가 없습니다.")
            return
        webbrowser.open(files[-1].as_uri())
        self.log.add(f"열었습니다: {files[-1].name} (브라우저에서 F12 → 모바일 보기로 폰 화면을 확인하세요)", "dim")

    def request(self) -> None:
        kw = self._keyword()
        if not messagebox.askyesno("승인 요청 보내기", f"서버에서 '{kw or '자동 선정'}' 주제로 글을 만들어 텔레그램 승인 카드로 보냅니다.\n(평소 자동 발행과 같은 흐름이며 토큰이 듭니다.)\n\n진행할까요?"):
            return
        cmd = f"venv/bin/python main.py run-now {self._site_arg()}" + (f" --keyword {core.quote(kw)}" if kw else "")
        self.log.clear()
        self.log.add("[서버] " + cmd, "cmd")
        core.start_server(self.job, self.app.settings, cmd, lambda ln: self.app.ui(self.log.add, ln), lambda rc: self.app.ui(self.log.add, f"끝 (종료코드 {rc})", "dim"))


# ------------------------------------------------------------------ 발행·스레드
class Publish(Panel):
    title = "발행·스레드"
    subtitle = "최근 7일 발행 글과 서버의 스레드 대기열입니다(읽기 전용). 글을 더블클릭하면 브라우저로 엽니다."

    def __init__(self, app: "App") -> None:
        super().__init__(app)
        Btn(self.body, "새로고침", self.load, primary=True).pack(anchor="w", pady=(0, 8))
        self.posts = ttk.Treeview(self.body, columns=("site", "date", "title"), show="headings", height=10)
        for c, t, w in (("site", "사이트", 90), ("date", "발행", 130), ("title", "제목", 620)):
            self.posts.heading(c, text=t)
            self.posts.column(c, width=w, anchor="w")
        self.posts.pack(fill="x")
        self.links: Dict[str, str] = {}
        self.posts.bind("<Double-1>", self._open)
        label(self.body, "스레드 대기열 (서버)", fg=MUT, size=9).pack(anchor="w", pady=(12, 2))
        self.queue = ttk.Treeview(self.body, columns=("kind", "at", "text"), show="headings", height=6)
        for c, t, w in (("kind", "종류", 80), ("at", "예약", 150), ("text", "내용", 660)):
            self.queue.heading(c, text=t)
            self.queue.column(c, width=w, anchor="w")
        self.queue.pack(fill="x")

    def on_show(self) -> None:
        self.load()

    def load(self) -> None:
        s = self.app.settings
        self.app.bg(lambda: [(k, n, core.site_snapshot(k)) for k, _a, n, _s in core.SITES], self._posts)
        self.app.bg(lambda: core.server_data(s) if core.ssh_ready(s) else core.local_data(), self._queue)

    def _posts(self, res: Any, err: Optional[Exception]) -> None:
        if err or not res:
            return
        self.posts.delete(*self.posts.get_children())
        self.links.clear()
        rows = [(n, p) for _k, n, snap in res for p in snap["posts"]]
        rows.sort(key=lambda r: r[1]["date"], reverse=True)
        for n, p in rows:
            iid = self.posts.insert("", "end", values=(n, p["date"], p["title"]))
            self.links[iid] = p["link"]

    def _queue(self, res: Any, err: Optional[Exception]) -> None:
        if err or not res:
            return
        self.queue.delete(*self.queue.get_children())
        for q in res.get("threads_queue.json") or []:
            self.queue.insert("", "end", values=(q.get("kind", "link"), str(q.get("when") or q.get("at") or q.get("scheduled") or "")[:19], str(q.get("text", "")).replace("\n", " / ")[:120]))

    def _open(self, _e: Any) -> None:
        sel = self.posts.selection()
        if sel and self.links.get(sel[0]):
            webbrowser.open(self.links[sel[0]])


# ------------------------------------------------------------------ 서버
class Server(Panel):
    title = "서버 (클라우드웨이즈)"
    subtitle = "SSH로 연결해 버튼 하나로 명령을 실행합니다. 되돌리기 어려운 버튼은 한 번 더 확인합니다."

    def __init__(self, app: "App") -> None:
        super().__init__(app)
        self.job = core.Job()
        self.tiles: Dict[str, Tile] = {}
        top = tk.Frame(self.body, bg=BG)
        top.pack(fill="x")
        for i, (k, cap) in enumerate((("ssh", "SSH"), ("commit", "서버 커밋"), ("disk", "디스크"), ("daemon", "데몬"))):
            t = Tile(top, cap)
            t.grid(row=0, column=i, sticky="nsew", padx=(0 if i == 0 else 8, 0))
            top.columnconfigure(i, weight=1, uniform="k")
            self.tiles[k] = t
        bt = card(self.body)
        bt.pack(fill="x", pady=8)
        row1 = tk.Frame(bt, bg=CARD)
        row1.pack(fill="x")
        row2 = tk.Frame(bt, bg=CARD)
        row2.pack(fill="x", pady=(6, 0))
        Btn(row1, "코드 업데이트 (pull + 재시작)", self.update, primary=True).pack(side="left", padx=(0, 6))
        Btn(row1, "재시작", self.restart).pack(side="left", padx=(0, 6))
        Btn(row1, "영구 정지", self.stop_daemon).pack(side="left", padx=(0, 6))
        Btn(row1, "정지 해제", self.resume).pack(side="left", padx=(0, 6))
        Btn(row1, "상태 새로고침", self.refresh).pack(side="left")
        Btn(row2, "로그 보기", lambda: self.run("tail -n 80 data/logs/pipeline.log")).pack(side="left", padx=(0, 6))
        Btn(row2, "검색량 지금 수집", lambda: self.run("venv/bin/python scripts/run_search_demand.py --force")).pack(side="left", padx=(0, 6))
        Btn(row2, "토큰 사용량(7일)", lambda: self.run("venv/bin/python main.py usage --days 7")).pack(side="left", padx=(0, 6))
        Btn(row2, "스레드 큐 보기", lambda: self.run("cat data/output/threads_queue.json | head -c 3000")).pack(side="left")
        self.log = LogBox(self.body, height=16)
        self.log.pack(fill="both", expand=True)

    def on_show(self) -> None:
        self.refresh()

    def refresh(self) -> None:
        s = self.app.settings
        self.app.bg(lambda: core.server_status(s) if core.ssh_ready(s) else {"ok": "0", "error": "SSH 설정 전"}, self._status)

    def _status(self, res: Any, err: Optional[Exception]) -> None:
        if err or not res:
            return
        if res.get("ok") != "1":
            self.tiles["ssh"].set("안 됨", YELLOW)
            self.log.add(res.get("error", ""), "err")
            return
        self.tiles["ssh"].set("연결됨", GREEN)
        self.tiles["commit"].set(res.get("COMMIT", "-"))
        self.tiles["disk"].set(res.get("DISK", "-"))
        self.tiles["daemon"].set("정지됨" if res.get("STOP") == "1" else ("실행 중" if res.get("DAEMON") else "꺼짐"),
                                 RED if res.get("STOP") == "1" or not res.get("DAEMON") else GREEN)

    def run(self, cmd: str, then: Optional[Callable[[], None]] = None) -> None:
        self.log.add("[서버] " + cmd, "cmd")

        def done(rc: int) -> None:
            self.app.ui(self.log.add, f"끝 (종료코드 {rc})", "dim")
            if then:
                self.app.ui(then)

        core.start_server(self.job, self.app.settings, cmd, lambda ln: self.app.ui(self.log.add, ln), done)

    def update(self) -> None:
        if messagebox.askyesno("코드 업데이트", "서버에서 최신 코드를 받고(git pull) 데몬을 재시작합니다(최대 5분 안에 반영).\n\n진행할까요?"):
            self.run("git pull origin main && touch deploy/.restart_requested && git rev-parse --short HEAD", self.refresh)

    def restart(self) -> None:
        if messagebox.askyesno("재시작", "데몬 재시작을 요청합니다(최대 5분 안에 반영).\n\n진행할까요?"):
            self.run("touch deploy/.restart_requested && echo '재시작 요청 완료'", self.refresh)

    def stop_daemon(self) -> None:
        if messagebox.askyesno("영구 정지", "데몬을 정지합니다. 글 발행·스레드·검색량 수집이 모두 멈춥니다.\n'정지 해제'를 누르기 전까지 다시 시작되지 않습니다.\n\n정말 정지할까요?"):
            self.run("touch deploy/.stop_requested && echo '정지 요청 완료'", self.refresh)

    def resume(self) -> None:
        if messagebox.askyesno("정지 해제", "정지 신호를 지우고 데몬이 다시 시작되게 합니다(최대 5분 안에).\n\n진행할까요?"):
            self.run("rm -f deploy/.stop_requested && echo '정지 해제 완료'", self.refresh)


# ------------------------------------------------------------------ 터미널·로그
class Terminal(Panel):
    title = "터미널·로그"
    subtitle = "내 PC(파워셸)나 서버(SSH)에서 명령을 실행하고 결과를 봅니다."

    QUICK = (
        ("서버", "pipeline.log 끝 60줄", "tail -n 60 data/logs/pipeline.log"),
        ("서버", "데몬 로그 오류", "tail -n 40 data/logs/daemon.err"),
        ("서버", "디스크 사용량", "df -h ~ | tail -2"),
        ("PC", "쿠팡 예약 작업", "Get-ScheduledTaskInfo CoupangLinkBank | Format-List LastRunTime,LastTaskResult,NextRunTime"),
        ("PC", "쿠팡 호출 기록", "Get-Content data\\output\\coupang_api_guard.json -Raw"),
        ("PC", "깃 상태", "git status -sb; git log --oneline -5"),
    )

    def __init__(self, app: "App") -> None:
        super().__init__(app)
        self.job = core.Job()
        top = card(self.body)
        top.pack(fill="x")
        self.mode = tk.StringVar(value="서버 SSH")
        ttk.Combobox(top, textvariable=self.mode, values=["서버 SSH", "내 PC 파워셸"], width=12, state="readonly").pack(side="left")
        self.entry = ttk.Entry(top)
        self.entry.pack(side="left", fill="x", expand=True, padx=8)
        self.entry.bind("<Return>", lambda _e: self.go())
        Btn(top, "실행", self.go, primary=True).pack(side="left", padx=(0, 6))
        Btn(top, "중지", self.job.stop).pack(side="left")
        quick = tk.Frame(self.body, bg=BG)
        quick.pack(fill="x", pady=8)
        for where, name, cmd in self.QUICK:
            Btn(quick, f"{where} · {name}", lambda w=where, c=cmd: self.quick(w, c)).pack(side="left", padx=(0, 6))
        self.log = LogBox(self.body, height=22)
        self.log.pack(fill="both", expand=True)

    def quick(self, where: str, cmd: str) -> None:
        self.mode.set("서버 SSH" if where == "서버" else "내 PC 파워셸")
        self.entry.delete(0, "end")
        self.entry.insert(0, cmd)
        self.go()

    def go(self) -> None:
        cmd = self.entry.get().strip()
        if not cmd:
            return
        server = self.mode.get() == "서버 SSH"
        self.log.add(("[서버] " if server else "PS> ") + cmd, "cmd")
        on_line = lambda ln: self.app.ui(self.log.add, ln)  # noqa: E731
        done = lambda rc: self.app.ui(self.log.add, f"끝 (종료코드 {rc})", "dim")  # noqa: E731
        if server:
            core.start_server(self.job, self.app.settings, cmd, on_line, done)
        else:
            core.start_local(self.job, cmd, on_line, done)


# ------------------------------------------------------------------ 설정
GUIDE = """서버(SSH) 연결 방법 - 처음 한 번만 하면 됩니다
1) 아래 '키 만들기'를 누릅니다(이미 있으면 건너뜀). 비밀번호는 저장하지 않고 키 파일만 만듭니다.
2) '공개키 복사'를 누릅니다.
3) 클라우드웨이즈 로그인 → Servers → 해당 서버 → Server Management → Master Credentials 화면에서
   SSH 공개키(SSH Public Key)를 등록하는 곳에 붙여넣고 저장합니다. 화면 이름이 다르면 알려주세요.
4) 같은 서버의 Security → Whitelisted IPs(SSH·SFTP 허용 IP)에 아래 '내 공인 IP'를 추가합니다.
   (집 인터넷 IP가 바뀌면 연결이 끊기므로, 그때 같은 곳에서 새 IP로 바꿔 주세요.)
5) 서버 주소(Public IP)와 계정(Master Credentials의 Username)을 위 칸에 입력하고 '저장' → '연결 테스트'를 누릅니다."""


class Settings(Panel):
    title = "설정·키"
    subtitle = "서버 접속 정보는 내 PC의 data 폴더에만 저장되고 깃에는 올라가지 않습니다. 비밀번호는 저장하지 않습니다."

    def __init__(self, app: "App") -> None:
        super().__init__(app)
        self.job = core.Job()
        form = card(self.body)
        form.pack(fill="x")
        self.vars: Dict[str, tk.StringVar] = {}
        s = app.settings
        for i, (k, name) in enumerate((("ssh_host", "서버 주소(Public IP)"), ("ssh_port", "포트"), ("ssh_user", "계정(Username)"),
                                       ("ssh_key", "키 파일 경로"), ("remote_dir", "서버 프로젝트 폴더"))):
            label(form, name, fg=MUT, size=9, bg=CARD, width=20, anchor="w").grid(row=i, column=0, sticky="w", pady=2)
            v = tk.StringVar(value=str(s.get(k, "")))
            ttk.Entry(form, textvariable=v, width=60).grid(row=i, column=1, sticky="w", pady=2)
            self.vars[k] = v
        bt = tk.Frame(form, bg=CARD)
        bt.grid(row=6, column=0, columnspan=2, sticky="w", pady=(8, 0))
        Btn(bt, "저장", self.save, primary=True).pack(side="left", padx=(0, 6))
        Btn(bt, "키 만들기", self.make_key).pack(side="left", padx=(0, 6))
        Btn(bt, "공개키 복사", self.copy_pub).pack(side="left", padx=(0, 6))
        Btn(bt, "내 공인 IP 확인", self.show_ip).pack(side="left", padx=(0, 6))
        Btn(bt, "연결 테스트", self.test).pack(side="left", padx=(0, 6))
        Btn(bt, "키·사이트 점검", self.check).pack(side="left")
        guide = tk.Text(self.body, height=10, bg=CARD, fg=TEXT, relief="flat", font=(FONT, 9), wrap="word", padx=10, pady=8)
        guide.insert("1.0", GUIDE)
        guide.config(state="disabled")
        guide.pack(fill="x", pady=8)
        self.log = LogBox(self.body, height=8)
        self.log.pack(fill="both", expand=True)

    def values(self) -> Dict[str, Any]:
        d = {k: v.get().strip() for k, v in self.vars.items()}
        try:
            d["ssh_port"] = int(d["ssh_port"] or 22)
        except ValueError:
            d["ssh_port"] = 22
        return d

    def save(self) -> None:
        self.app.settings = self.values()
        core.save_settings(self.app.settings)
        self.log.add("저장했습니다.", "dim")

    def make_key(self) -> None:
        key = Path(self.vars["ssh_key"].get().strip())
        if key.exists():
            self.log.add(f"이미 있습니다: {key}", "dim")
            return
        key.parent.mkdir(parents=True, exist_ok=True)
        core.start_local(self.job, f'ssh-keygen -t ed25519 -N "" -C "pipeline-control" -f "{key}"', lambda ln: self.app.ui(self.log.add, ln),
                         lambda rc: self.app.ui(self.log.add, "키를 만들었습니다. 다음은 '공개키 복사'입니다." if rc == 0 else "키 만들기에 실패했습니다.", "dim"))

    def copy_pub(self) -> None:
        pub = Path(self.vars["ssh_key"].get().strip() + ".pub")
        if not pub.exists():
            self.log.add("공개키가 아직 없습니다. '키 만들기'를 먼저 누르세요.", "err")
            return
        self.app.clipboard_clear()
        self.app.clipboard_append(pub.read_text(encoding="utf-8").strip())
        self.log.add("공개키를 복사했습니다. 클라우드웨이즈의 SSH 공개키 칸에 붙여넣으세요(Ctrl+V).", "dim")

    def show_ip(self) -> None:
        self.app.bg(core.public_ip, lambda ip, _e: self.log.add(f"내 공인 IP: {ip}" if ip else "공인 IP를 확인하지 못했습니다.", "" if ip else "err"))

    def test(self) -> None:
        self.save()
        core.start_server(self.job, self.app.settings, "echo 연결 OK; whoami; hostname; git log --oneline -1",
                          lambda ln: self.app.ui(self.log.add, ln), lambda rc: self.app.ui(self.log.add, f"끝 (종료코드 {rc})", "dim"))

    def check(self) -> None:
        def work() -> List[str]:
            lines = [f"{k}: {'설정됨' if ok else '없음'}" for k, ok in core.key_status().items()]
            from wp_client import WordPressClient

            for key, _a, name, _s in core.SITES:
                try:
                    r = WordPressClient(key).test_connection()
                    lines.append(f"워드프레스 {name}: {'연결됨' if r.get('ok', r.get('status') == 'ok') else r}")
                except Exception as exc:  # noqa: BLE001
                    lines.append(f"워드프레스 {name}: 실패 ({exc})")
            return lines

        self.app.bg(work, lambda res, err: [self.log.add(x) for x in (res or [f"점검 실패: {err}"])])


# ------------------------------------------------------------------ 앱
class App(tk.Tk):
    def __init__(self) -> None:
        super().__init__()
        self.title("파이프라인 관제")
        self.geometry("1240x800")
        self.minsize(1000, 640)
        self.configure(bg=BG)
        if sv_ttk:
            sv_ttk.set_theme("dark")
        self.settings = core.load_settings()
        self.q: "queue.Queue[Callable[[], None]]" = queue.Queue()
        side = tk.Frame(self, bg=SIDE, width=170)
        side.pack(side="left", fill="y")
        side.pack_propagate(False)
        label(side, "파이프라인 관제", fg=ORANGE, size=13, bold=True, bg=SIDE).pack(anchor="w", padx=14, pady=(16, 8))
        self.main = tk.Frame(self, bg=BG, padx=18, pady=14)
        self.main.pack(side="left", fill="both", expand=True)
        self.panels: Dict[str, Panel] = {}
        self.items: Dict[str, tk.Label] = {}
        layout = (
            ("현황", (("dash", "대시보드", Dashboard),)),
            ("콘텐츠", (("content", "글 만들기", Content), ("publish", "발행·스레드", Publish))),
            ("운영", (("server", "서버", Server), ("term", "터미널·로그", Terminal), ("set", "설정·키", Settings))),
        )
        for group, entries in layout:
            label(side, group, fg=MUT, size=9, bg=SIDE).pack(anchor="w", padx=14, pady=(10, 2))
            for pid, name, cls in entries:
                it = tk.Label(side, text=name, bg=SIDE, fg=TEXT, font=(FONT, 10), anchor="w", padx=12, pady=7, cursor="hand2")
                it.pack(fill="x", padx=8, pady=1)
                it.bind("<Button-1>", lambda _e, p=pid: self.show(p))
                self.items[pid] = it
                self.panels[pid] = cls(self)
        self.current = ""
        self.show("dash" if core.ssh_ready(self.settings) else "set")
        self.after(100, self._pump)

    def show(self, pid: str) -> None:
        if self.current:
            self.panels[self.current].pack_forget()
            self.items[self.current].config(bg=SIDE, fg=TEXT)
        self.current = pid
        self.items[pid].config(bg=ORANGE_SOFT, fg="#ffb27a")
        self.panels[pid].pack(fill="both", expand=True)
        self.panels[pid].on_show()

    # 스레드에서 화면을 건드리지 않도록, 결과는 큐로 받아 메인 스레드에서 처리한다
    def ui(self, fn: Callable[..., None], *args: Any) -> None:
        self.q.put(lambda: fn(*args))

    def bg(self, work: Callable[[], Any], done: Optional[Callable[[Any, Optional[Exception]], None]] = None) -> None:
        def run() -> None:
            res, err = None, None
            try:
                res = work()
            except Exception as exc:  # noqa: BLE001
                err = exc
            if done:
                self.q.put(lambda: done(res, err))

        threading.Thread(target=run, daemon=True).start()

    def _pump(self) -> None:
        try:
            while True:
                self.q.get_nowait()()
        except queue.Empty:
            pass
        self.after(100, self._pump)


def main() -> None:
    os.chdir(core.ROOT)
    App().mainloop()
