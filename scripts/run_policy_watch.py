"""정책 변화 감시를 수동으로 실행한다(서버 데몬이 매일 자동으로도 실행하므로 보통은 필요 없다).

실행 예:
  venv/bin/python scripts/run_policy_watch.py --monthly --dry     # 월간 점검 결과를 화면에만 출력(스냅샷 저장·텔레그램 없음)
  venv/bin/python scripts/run_policy_watch.py --monthly --force   # 이번 달에 이미 했어도 지금 실행하고 텔레그램으로 보냄
  venv/bin/python scripts/run_policy_watch.py --reminders --dry   # 오늘 보낼 고정 날짜 알림 확인
"""
from __future__ import annotations

import argparse
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import policy_watch as pw

parser = argparse.ArgumentParser()
parser.add_argument("--monthly", action="store_true", help="월간 변화 점검 실행")
parser.add_argument("--reminders", action="store_true", help="오늘 보낼 고정 날짜 알림 처리")
parser.add_argument("--force", action="store_true", help="이번 달에 이미 실행했어도 다시 실행")
parser.add_argument("--dry", action="store_true", help="텔레그램 전송·상태 저장 없이 화면에만 출력")
args = parser.parse_args()

if not (args.monthly or args.reminders):
    parser.print_help()
    sys.exit(0)
if args.reminders:
    print("알림 처리:", pw.send_due_reminders(dry=args.dry), "건")
if args.monthly:
    print("월간 점검:", pw.run_monthly_if_due(dry=args.dry, force=args.force))

