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
cp -rf site_d/dist/. "$TARGET"/   # -a 는 폴더 시간 복사 권한 오류로 중단되므로 쓰지 않는다
# Cloudways 기본 화면(index.php)이 index.html 보다 먼저 열리므로 치운다(이름만 바꿈, 안 되면 지움)
if [ -f "$TARGET/index.php" ]; then
  mv -f "$TARGET/index.php" "$TARGET/index.php.bak" 2>/dev/null || rm -f "$TARGET/index.php" 2>/dev/null     || echo "경고: index.php 를 치우지 못했습니다(권한). Cloudways 기본 화면이 계속 보일 수 있습니다."
fi
# 쪽마다 따로 새로고침하지 않아도 항상 최신 화면이 보이도록: 화면(html)·데이터 파일은 열 때마다 서버에 "바뀌었나?"만 확인한다(안 바뀌었으면 가볍게 304).
cat > "$TARGET/.htaccess" <<'HTACCESS'
DirectoryIndex index.html index.php
<IfModule mod_headers.c>
<FilesMatch "\.(html|json|xml|txt)$">
Header set Cache-Control "no-cache, must-revalidate"
</FilesMatch>
</IfModule>
HTACCESS
# 앞단 캐시(Varnish)에 남은 옛 화면을 모든 쪽에서 비운다(실패해도 무시)
( cd site_d/dist && { echo /; find . -name '*.html' -o -name '*.json' -o -name '*.xml' -o -name '*.txt' | sed 's#^\./#/#'; } ) | while read -r u; do
  curl -s -m 5 -o /dev/null -X PURGE "http://cook.dailyfixpoint.com$u" || true
done
echo "반영 완료: $TARGET ($(ls "$TARGET"/recipes | wc -l)개 레시피 페이지)"
