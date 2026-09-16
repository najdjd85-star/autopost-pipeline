# 3사이트 통합 패시브 미디어 파이프라인

정부지원금(Site A) / 통신비·렌탈 비교(Site B) / 세금환급(Site C) 3개 워드프레스 사이트를
단일 엔진으로 운영하며, 콘텐츠 생성(Claude) → 이미지 확보 → 영상 렌더링 → 5개 플랫폼
동시 배포(워드프레스/유튜브/인스타 릴스/스레드/핀터레스트) → CPA·쿠팡 수익화 →
이메일 뉴스레터 → 검색 순위 방어까지 자동화하는 파이프라인입니다.

## 1. 설치

```powershell
python -m venv venv
.\venv\Scripts\Activate.ps1
python -m pip install --upgrade pip
pip install -r requirements.txt
Copy-Item .env.example .env
```

`.env`를 열어 실제 API 키/자격증명으로 채워 넣으세요. 어떤 키가 비어 있어도
프로그램은 크래시 없이 해당 기능만 건너뜁니다 (우아한 저하 원칙).

## 2. 검증 (문법/임포트 자가진단)

```powershell
python -m py_compile config.py constants.py main.py generator.py smart_affiliate_matcher.py wp_client.py video_engine.py longform_engine.py social_distributor.py content_updater.py newsletter_system.py telegram_bot.py trend_scraper.py keyword_expander.py competitor_analyzer.py image_hybrid_engine.py utils\http.py utils\logger.py utils\tts.py utils\telegram_notify.py scripts\check_imports.py
python scripts\check_imports.py
```

## 3. CLI 사용법

```powershell
python main.py run-now site_a      # Site A(지원금) 콘텐츠 생성 + 텔레그램 승인 요청
python main.py run-now all         # 3개 사이트 전체 실행
python main.py refresh-check       # 서치콘솔 순위 방어(4~15위) 점검
python main.py send-newsletter     # 주간 뉴스레터 즉시 발송
python main.py daemon              # 스케줄러 + 텔레그램봇 + 구독서버(5000) 상시 구동
```

기본 스케줄(`.env`의 `SCHEDULE_TIME`/`NEWSLETTER_SCHEDULE_TIME`로 변경 가능):
- 매일 07:00 — 3사이트 콘텐츠 생성 파이프라인
- 매주 월요일 08:00 — 주간 뉴스레터 발송
- 매주 일요일 23:00 — 서치콘솔 순위 방어 점검

## 4. 텔레그램 승인 플로우

`daemon` 모드로 실행하면 콘텐츠 생성 완료 시 텔레그램으로
`[Site 뱃지] + 제목 + 요약 + 쇼츠 미리보기`가 전송되고, 아래 버튼으로 제어합니다.

- 🌐 웹 미리보기 / ✏️ WP 수정 / ✅ 일괄 발행 승인 / ❌ 반려
- ✅ 승인 시: 워드프레스 발행 → 구글/네이버 색인 핑 → 스레드 → 인스타그램 릴스 →
  핀터레스트 → 유튜브 순으로 자동 배포되고 결과가 채팅으로 보고됩니다.

## 5. 모듈 구조

| 파일 | 역할 |
|---|---|
| `config.py` | 전역 설정 로더 (모든 모듈의 공통 의존점) |
| `constants.py` | 슬롯 플레이스홀더/사이트 키 등 공유 상수 |
| `trend_scraper.py` | 공공데이터/정책브리핑/구글트렌드 수집 |
| `keyword_expander.py` | 네이버 자동완성 기반 롱테일 키워드 확장 |
| `competitor_analyzer.py` | 네이버 상위 1~3위 블로그 벤치마킹 |
| `generator.py` | Claude 콘텐츠 생성 엔진 (심리 저격 + 반응형 UI 강제) |
| `image_hybrid_engine.py` | Pexels → Pollinations.ai 하이브리드 이미지 처리 |
| `smart_affiliate_matcher.py` | CPA/쿠팡 제휴 슬롯 자동 주입 |
| `wp_client.py` | 멀티 워드프레스 REST API 클라이언트 |
| `video_engine.py` | 30초 세로 쇼츠 렌더링 |
| `longform_engine.py` | 5~7분 가로 롱폼 렌더링 |
| `social_distributor.py` | Pinterest/IG/Threads/YouTube 배포 + 색인 핑 |
| `content_updater.py` | 서치콘솔 기반 순위 방어 리라이팅 |
| `newsletter_system.py` | 구독 API(Flask) + 주간 뉴스레터 발송 |
| `telegram_bot.py` | 승인 봇 + 통합 배포 체인 트리거 |
| `main.py` | CLI + 스케줄러 엔트리포인트 |

의존성 그래프, 설계 원칙, 알려진 제한사항은
`C:\Users\JD\.claude\plans\100-wise-tarjan.md` 계획 문서에 상세히 기록되어 있습니다.

## 6. 알려진 제한사항

- **ffmpeg**: `moviepy` import는 성공하지만 실제 영상 렌더링에는 시스템에 ffmpeg
  바이너리가 필요합니다 (없으면 `imageio-ffmpeg`가 자동 다운로드를 시도합니다).
- **외부 API 승인**: 네이버/쿠팡/Meta(IG·Threads)/Pinterest/Google/Resend는 각각
  실계정 등록·앱 심사가 필요합니다. 키가 없으면 해당 기능은 로그만 남기고 스킵됩니다.
- **네이버 자동완성**: 비공식 엔드포인트라 언제든 변경/차단될 수 있어
  `keyword_expander.py`는 접미사 휴리스틱 폴백을 항상 병행합니다.
- **YouTube 업로드**: 서비스 계정만으로는 개인 채널 업로드 권한이 없어
  `YOUTUBE_CLIENT_SECRETS_PATH`/`YOUTUBE_TOKEN_PATH`로 최초 1회 OAuth 사용자
  인증이 별도로 필요합니다.
- **`deploy/autopost.service`**: Ubuntu systemd 전용 템플릿이며 이 Windows
  개발 환경에서는 직접 실행/검증할 수 없습니다. **root/sudo 권한이 없는 관리형
  호스팅(예: Cloudways)에서는 systemd를 쓸 수 없으므로**, 대신
  `deploy/watchdog.sh`를 Cloudways Cron Job(예: 5분마다)에 등록해 "안 돌고
  있으면 다시 시작"하는 방식으로 24시간 가동을 대체합니다.
- **쿠팡 파트너스 API**: 해외 리전 서버(예: 싱가포르)에서는 IP 기반으로
  차단될 수 있습니다. 이 경우 `constants.COUPANG_FALLBACK_LINKS`에 등록된
  사이트별 고정 딥링크로 자동 대체됩니다(실시간 상품 매칭은 안 되지만
  수수료는 정상 발생).
