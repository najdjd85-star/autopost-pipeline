#!/bin/bash
# 냉장고 파먹기(사이트 D)를 서버에서 빌드해 Cloudways 'cook' 앱 폴더에 올린다.
# 사용: bash scripts/publish_site_d.sh <cook 앱 폴더 이름>      (폴더 이름은 `ls ~/applications` 로 확인)
# 기존 파일을 지우지 않고 덮어쓰기만 한다(복사). 이미 있던 index.php 등은 index.html 이 우선 보이도록 아래에서 따로 처리한다.
set -e
APP="$1"
ROOT="$(cd "$(dirname "$0")/.." && pwd)"
if [ -z "$APP" ]; then
  echo "앱 폴더 이름을 적어 주세요. 예: bash scripts/publish_site_d.sh abcdefghij"
  echo "현재 앱 폴더 목록:"; ls ~/applications
  exit 1
fi
TARGET="$HOME/applications/$APP/public_html"
[ -d "$TARGET" ] || { echo "폴더가 없습니다: $TARGET"; exit 1; }
cd "$ROOT"
SITE_D_BASE=https://cook.dailyfixpoint.com "$ROOT/venv/bin/python" -X utf8 site_d/build.py
mkdir -p ~/site_d_backup
tar -czf ~/site_d_backup/before_$(date +%Y%m%d_%H%M%S).tgz -C "$TARGET" . 2>/dev/null || true
ls -t ~/site_d_backup/before_*.tgz 2>/dev/null | tail -n +8 | xargs -r rm -f   # 백업은 최근 7개만 남긴다
cp -a site_d/dist/. "$TARGET"/
# Cloudways 기본 페이지(index.php 등)가 있으면 우리 index.html 이 먼저 열리도록 이름만 바꿔 둔다(삭제 아님)
for f in index.php; do [ -f "$TARGET/$f" ] && mv "$TARGET/$f" "$TARGET/$f.bak" || true; done
echo "반영 완료: $TARGET ($(ls "$TARGET"/recipes | wc -l)개 레시피 페이지)"
