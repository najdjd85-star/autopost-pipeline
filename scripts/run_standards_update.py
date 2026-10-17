"""기준 자동 갱신을 수동으로 실행한다(서버 데몬이 매일 09:40에 자동 실행하므로 보통은 필요 없다).

실행 예:
  venv/bin/python scripts/run_standards_update.py --status                  # 시트별 현재 기준 연도 확인(비용 0)
  venv/bin/python scripts/run_standards_update.py --only 아동수당 --force    # 한 시트만 지금 조사해 갱신(약 $0.1~0.2)
  venv/bin/python scripts/run_standards_update.py --median                  # 기준 중위소득만 조사

--force 없이는 12/20~3/31(및 월요일)이 아니면 아무것도 하지 않는다.
"""
from __future__ import annotations

import argparse
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import standards_updater as su
from fact_sheets import iter_sheets, year_of

parser = argparse.ArgumentParser()
parser.add_argument("--status", action="store_true", help="시트별 기준 연도만 출력")
parser.add_argument("--only", help="이름에 이 글자가 든 시트만 대상으로")
parser.add_argument("--force", action="store_true", help="갱신 기간이 아니어도 실행")
parser.add_argument("--median", action="store_true", help="기준 중위소득만 조사")
args = parser.parse_args()

if args.status:
    target = su.target_year()
    rows = [(k, year_of(t)) for k, _, t in iter_sheets()]
    stale = [k for k, y in rows if y and y < target]
    print(f"목표 기준 연도 {target}년 | 시트 {len(rows)}개 | 낡은 시트 {len(stale)}개")
    for k, y in rows:
        print(f"  {k:22} {y or '(연도 표기 없음)'}{'  <- 갱신 필요' if y and y < target else ''}")
elif args.median:
    print("중위소득:", su.update_median())
else:
    print("결과:", su.run_update(force=args.force, only=args.only))
