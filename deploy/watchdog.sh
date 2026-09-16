#!/bin/bash
# Cloudways Cron Job에 등록해서 주기적으로(예: 5분마다) 실행하는 워치독 스크립트.
#
# systemd(Restart=always)를 쓸 수 없는 환경(sudo/root 권한 없는 관리형 호스팅)에서,
# "데몬이 안 돌고 있으면 다시 시작"하는 역할을 대신한다. 서버 재시작/프로세스
# 크래시 후에도 이 크론이 주기적으로 확인해서 최대 크론 주기 이내에 자동 복구된다.
#
# 사용법 (Cloudways Cron Job Management에 등록):
#   */5 * * * * /bin/bash /home/master/applications/<앱폴더>/autopost-pipeline/deploy/watchdog.sh
set -euo pipefail

APP_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$APP_DIR"

LOG_DIR="$APP_DIR/data/logs"
mkdir -p "$LOG_DIR"

if ! pgrep -f "python.*main\.py daemon" > /dev/null; then
    echo "$(date -u '+%Y-%m-%d %H:%M:%S UTC') - 데몬이 꺼져 있어 재시작합니다." >> "$LOG_DIR/watchdog.log"
    nohup "$APP_DIR/venv/bin/python" "$APP_DIR/main.py" daemon >> "$LOG_DIR/daemon.out" 2>> "$LOG_DIR/daemon.err" &
    disown
fi
