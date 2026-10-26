"""블로그 글 모바일 최적화 CSS.

글 본문은 모델이 인라인 스타일로 만든 카드·타임라인·FAQ라 모바일(폭 375px 안팎)에서 다음 문제가 있었다:
- 한글이 글자 단위로 끊겨 읽기 힘듦 → word-break: keep-all
- 제목·본문 글씨가 크고 카드 안 설명은 11~12px로 너무 작음
- 지표 카드·타임라인이 어색하게 접힘 → 모바일에서는 세로로 쌓음
- 박스 안쪽 여백이 커서 실제 글 폭이 좁음

사이트 전역 스타일(글로벌 스타일의 사용자 CSS)로 넣으면 기존 글과 새 글에 한 번에 적용된다.
인라인 스타일을 이기려면 !important가 필요하다. 적용은 scripts/apply_mobile_css.py.
"""

CSS_MARKER = "/* dfp-mobile-v1 */"

MOBILE_CSS = CSS_MARKER + """
.wp-block-post-content,.wp-block-post-title,.wp-block-post-content h2,.wp-block-post-content h3{word-break:keep-all;overflow-wrap:break-word}
.wp-block-post-content img,.wp-block-post-content video,.wp-block-post-content iframe{max-width:100%;height:auto}
.wp-block-post-content table{display:block;max-width:100%;overflow-x:auto;-webkit-overflow-scrolling:touch}
.wp-block-post-content summary{cursor:pointer;font-weight:600;line-height:1.5;padding:6px 0;min-height:44px;display:flex;align-items:center}
@media (max-width:640px){
body{--wp--style--root--padding-left:16px!important;--wp--style--root--padding-right:16px!important}
.wp-block-post-title{font-size:clamp(1.4rem,6.6vw,1.9rem)!important;line-height:1.38!important;letter-spacing:-.02em}
.wp-block-post-content p:not([style*="font-size"]),.wp-block-post-content li{font-size:16.5px!important;line-height:1.85!important}
.wp-block-post-content p:not([style*="font-size"]){margin-top:0;margin-bottom:1.1em}
.wp-block-post-content h2{font-size:1.2rem!important;line-height:1.4!important;margin:1.8em 0 .7em!important;padding:10px 12px!important}
.wp-block-post-content h3{font-size:1.05rem!important;line-height:1.45!important}
.wp-block-post-content [style*="font-size:10px"],.wp-block-post-content [style*="font-size:11px"],.wp-block-post-content [style*="font-size:12px"],.wp-block-post-content [style*="font-size:13px"],.wp-block-post-content [style*="font-size: 10px"],.wp-block-post-content [style*="font-size: 11px"],.wp-block-post-content [style*="font-size: 12px"],.wp-block-post-content [style*="font-size: 13px"]{font-size:14px!important;line-height:1.6!important}
.wp-block-post-content > div:not(.affiliate-card)[style*="padding"]{padding:14px!important}
.wp-block-post-content ul[style*="padding"],.wp-block-post-content ol[style*="padding"]{padding:14px 14px 14px 30px!important}
.wp-block-post-content div[style*="flex-wrap:wrap"]{flex-direction:column!important;flex-wrap:nowrap!important;gap:10px!important}
.wp-block-post-content div[style*="flex-wrap:wrap"] > *{flex:1 1 auto!important;min-width:0!important;width:100%!important;box-sizing:border-box!important}
.wp-block-post-content div[style*="gap:0"][style*="flex-wrap:wrap"]{gap:0!important}
.wp-block-post-content div[style*="gap:0"][style*="flex-wrap:wrap"] > *{border-radius:0!important;text-align:left!important;padding:12px 14px!important}
.wp-block-post-content div[style*="gap:0"][style*="flex-wrap:wrap"] > *:first-child{border-radius:8px 8px 0 0!important}
.wp-block-post-content div[style*="gap:0"][style*="flex-wrap:wrap"] > *:last-child{border-radius:0 0 8px 8px!important}
.wp-block-post-content details{padding:6px 14px!important}
.wp-block-post-content a[style*="padding"][style*="display:inline-block"]{display:block!important;text-align:center!important;box-sizing:border-box!important;min-height:48px;line-height:1.4!important}
.wp-block-post-content .affiliate-card-coupang{gap:12px!important;padding:12px!important}
.wp-block-post-content .affiliate-card{box-sizing:border-box}
.wp-block-post-content input,.wp-block-post-content select,.wp-block-post-content button{font-size:16px!important;min-height:44px}
.wp-block-post-content figure{margin-left:0;margin-right:0}
}
"""
