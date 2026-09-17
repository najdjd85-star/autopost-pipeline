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

RESTART_FLAG="$APP_DIR/deploy/.restart_requested"
STOP_FLAG="$APP_DIR/deploy/.stop_requested"

# 데몬을 영구적으로(재시작 없이) 종료하고 싶을 때 사용한다(예: 렌더링 전용 VPS로
# 데몬 자체를 이전하면서 이 서버의 데몬은 완전히 꺼야 할 때). 이것도 같은 이유로
# 크론 자신의 권한으로 kill해야 한다: `touch deploy/.stop_requested` 후 최대
# 크론 주기 이내에 데몬이 종료되고, 이 스크립트는 더 이상 재시작하지 않는다.
if [ -f "$STOP_FLAG" ]; then
    echo "$(date -u '+%Y-%m-%d %H:%M:%S UTC') - 영구 정지 요청 감지 - 데몬을 종료하고 재시작하지 않습니다." >> "$LOG_DIR/watchdog.log"
    pkill -f "python.*main\.py daemon" || true
    exit 0
fi

# 새 코드를 배포한 뒤 데몬을 강제로 재시작하고 싶을 때, 이 크론(=데몬을 실제로
# 띄운 것과 같은 사용자 계정으로 실행됨)이 아니면 다른 로그인 세션(예: 마스터
# SSH 계정)에서는 이 데몬을 kill할 권한이 없는 경우가 있다(사용자가 달라서).
# 그래서 "재시작 해달라"는 신호를 파일로 남겨두면, 이 크론이 자기 자신의
# 권한으로 스스로 재시작한다: `touch deploy/.restart_requested` 후 최대
# 크론 주기(5분) 이내에 반영된다.
if [ -f "$RESTART_FLAG" ]; then
    echo "$(date -u '+%Y-%m-%d %H:%M:%S UTC') - 재시작 요청 감지 - 기존 데몬을 종료합니다." >> "$LOG_DIR/watchdog.log"
    pkill -f "python.*main\.py daemon" || true
    rm -f "$RESTART_FLAG"
    sleep 2
fi

if ! pgrep -f "python.*main\.py daemon" > /dev/null; then
    echo "$(date -u '+%Y-%m-%d %H:%M:%S UTC') - 데몬이 꺼져 있어 재시작합니다." >> "$LOG_DIR/watchdog.log"
    nohup "$APP_DIR/venv/bin/python" "$APP_DIR/main.py" daemon >> "$LOG_DIR/daemon.out" 2>> "$LOG_DIR/daemon.err" &
    disown
fi
