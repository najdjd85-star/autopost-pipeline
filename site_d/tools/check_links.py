"""쿠팡 파트너스 단축 링크(link.coupang.com/a/...)가 아직 살아 있는지 점검한다(무료). 만료된 링크는 사이트에서 자동으로 숨기고 텔레그램으로 알린다.

방식: 링크에 요청을 한 번 보내고(리다이렉트는 따라가지 않음) 이동 주소를 본다.
  - 정상: https://www.coupang.com/vp/products/... 로 이동(302)
  - 만료·잘못된 링크: 쿠팡 첫 화면(https://www.coupang.com)이나 오류 페이지로 이동
쿠팡 상품 페이지 자체는 자동 접속을 막아(403) 품절·삭제 여부는 확인할 수 없다. 링크가 살아 있는지만 본다.
실패한 링크는 30초 뒤 한 번 더 확인해서, 두 번 모두 실패한 것만 '만료'로 본다.
요청은 링크마다 1번, 1.5초 간격이라 클릭 수에 영향이 있을 수 있다 → 기본으로는 일주일에 한 번만 돈다(update_site_d.py).

결과: site_d/links_broken.json (만료 목록, 깃에 올림 → 빌드가 그 링크를 숨김).
사용:
  venv/Scripts/python.exe -X utf8 site_d/tools/check_links.py            (점검 + 결과 저장 + 알림)
  venv/Scripts/python.exe -X utf8 site_d/tools/check_links.py --report   (점검만, 저장·알림 없음)
"""
from __future__ import annotations

import datetime as dt
import json
import sys
import time
from pathlib import Path
from typing import Dict, List, Tuple

import requests

HERE = Path(__file__).resolve().parent.parent          # site_d
ROOT = HERE.parent
sys.path.insert(0, str(HERE))
sys.path.insert(0, str(ROOT))

OUT = HERE / "links_broken.json"
STATE = ROOT / "data" / "output" / "link_check_state.json"
UA = {"User-Agent": "Mozilla/5.0 (compatible; OwnLinkHealthCheck/1.0)"}


def collect() -> Dict[str, List[str]]:
    """링크 주소 -> 쓰이는 곳 이름들(사이트 D의 affiliate.json 전체 + 블로그 고정 상품)."""
    urls: Dict[str, List[str]] = {}

    def add(u: str, where: str) -> None:
        if u and u.startswith("http"):
            urls.setdefault(u, []).append(where)

    data = json.loads((HERE / "affiliate.json").read_text(encoding="utf-8"))
    for n, u in (data.get("ingredients") or {}).items():
        add(u, f"재료:{n}")
    for n, t in (data.get("tools") or {}).items():
        add(t.get("url", ""), f"도구:{n}")
    for n, xs in (data.get("extras") or {}).items():
        for x in xs:
            add(x.get("url", ""), f"추가상품:{n}/{x.get('label', '')}")
    for n, xs in (data.get("variants") or {}).items():
        for x in xs:
            add(x.get("url", ""), f"요리별상품:{n}/{x.get('label', '')}")
    for c, xs in (data.get("category_products") or {}).items():
        for x in xs:
            add(x.get("url", ""), f"카테고리용품:{c}/{x.get('label', '')}")
    try:
        from coupang_static import PRODUCTS

        for p in PRODUCTS:
            add(p.get("url", ""), f"블로그상품:{p.get('name', '')}")
    except Exception:  # noqa: BLE001
        pass
    return urls


def check(url: str) -> Tuple[bool, str]:
    """(살아 있음?, 이유)"""
    try:
        r = requests.get(url, headers=UA, allow_redirects=False, timeout=20)
    except requests.RequestException as exc:
        return False, f"접속 실패: {str(exc)[:60]}"
    loc = r.headers.get("Location", "")
    if r.status_code in (301, 302, 303, 307, 308):
        if "/vp/products/" in loc or "/vm/" in loc or "link.coupang.com" in loc:
            return True, "정상"
        return False, f"상품이 아닌 곳으로 이동: {loc[:70]}"
    if r.status_code == 200:
        return True, "응답 200"
    return False, f"HTTP {r.status_code}"


def run() -> Dict[str, dict]:
    urls = collect()
    result: Dict[str, dict] = {}
    failed: List[str] = []
    for i, (u, where) in enumerate(urls.items(), 1):
        ok, why = check(u)
        result[u] = {"where": where, "ok": ok, "why": why}
        if not ok:
            failed.append(u)
        time.sleep(1.5)
    if failed:  # 일시적인 오류를 걸러 내려고 30초 뒤에 한 번 더
        time.sleep(30)
        for u in failed:
            ok, why = check(u)
            if ok:
                result[u] = {"where": result[u]["where"], "ok": True, "why": "재확인에서 정상"}
            else:
                result[u]["why"] = why
            time.sleep(1.5)
    return result


def notify(text: str) -> None:
    try:
        from utils.telegram_notify import send_message_sync

        send_message_sync(text)
    except Exception as exc:  # noqa: BLE001
        print("텔레그램 알림 실패(무시):", str(exc)[:80])


def main() -> int:
    report = "--report" in sys.argv
    result = run()
    bad = {u: v for u, v in result.items() if not v["ok"]}
    print(f"점검 {len(result)}개 링크, 만료 의심 {len(bad)}개")
    for u, v in bad.items():
        print(" -", ", ".join(v["where"]), "→", v["why"], "|", u)
    if report:
        return 0
    prev = []
    if OUT.exists():
        try:
            prev = [b["url"] for b in json.loads(OUT.read_text(encoding="utf-8")).get("broken", [])]
        except ValueError:
            prev = []
    data = {"checked": dt.date.today().isoformat(), "broken": [{"url": u, "where": v["where"], "why": v["why"]} for u, v in bad.items()]}
    OUT.write_text(json.dumps(data, ensure_ascii=False, indent=1), encoding="utf-8")
    STATE.parent.mkdir(parents=True, exist_ok=True)
    STATE.write_text(json.dumps({"last_check": dt.date.today().isoformat()}), encoding="utf-8")
    new = [u for u in bad if u not in prev]
    fixed = [u for u in prev if u not in bad]
    if new:
        lines = [f"- {', '.join(bad[u]['where'])}" for u in new][:15]
        notify("⚠️ 쿠팡 링크 만료 의심 " + str(len(new)) + "개 (사이트에서 자동으로 숨김)\n" + "\n".join(lines) + "\n새 링크를 주시면 교체합니다.")
    if fixed:
        notify(f"✅ 쿠팡 링크 {len(fixed)}개가 다시 정상이에요(다시 표시됩니다).")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
