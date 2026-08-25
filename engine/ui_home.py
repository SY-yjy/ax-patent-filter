"""홈 화면.

구성·위치·색을 직접 통제하기 위해 골격을 HTML 로 그린다.
CTA 만 Streamlit 버튼을 쓰고(동작 보장), st-key- 클래스로 카드에 붙인다.
"""
import streamlit as st

from theme import (BRAND, LEGACY_BLUE, BRAND_800, BRAND_700, BRAND_600, BRAND_400, BRAND_300,
                   BRAND_100, BRAND_050, BRAND_025, GROUND, SHEET, LINE,
                   INK_SUB, INK_MUTED, LABEL_COLOR, R_LG, R_PILL, SHADOW_1)

_FONT = "'Pretendard Variable',Pretendard,-apple-system,sans-serif"
_BAND = 60      # 상단 네이비 밴드 높이
_W = 1080       # 본문 최대폭
_PAD = 40
_LOGO = "app/static/samyang.png"   # server.enableStaticServing

_CSS_CHROME = f"""<style>
[data-testid="stAppViewContainer"], .stApp {{ background:{GROUND} !important; }}

/* ═══ 상단 네이비 밴드 : Streamlit 자체 헤더를 칠한다 (전폭 보장) ═══ */
[data-testid="stHeader"] {{
  background:{BRAND_800} !important; height:{_BAND}px !important;
  border-bottom:1px solid rgba(255,255,255,.08) !important;
}}
[data-testid="stToolbar"] svg {{ fill:rgba(255,255,255,.6) !important; }}
.hm-band {{
  position:fixed; top:0; left:0; right:0; height:{_BAND}px; z-index:1000000;
  pointer-events:none; display:flex; align-items:center;
}}
.hm-band-in {{
  width:100%; padding:0 34px; display:flex; align-items:center; gap:12px;
}}
.hm-logo {{ height:16px; width:auto; display:block; }}
.hm-word {{
  font:600 .875rem/1 {_FONT}; color:rgba(255,255,255,.9); letter-spacing:-.008em;
  padding-left:15px; margin-left:15px; border-left:1px solid rgba(255,255,255,.22);
}}
.hm-env {{
  margin-left:auto; font:500 .76rem/1 {_FONT}; color:{BRAND_300};
  letter-spacing:.01em;
}}
</style>"""


_CSS = f"""<style>
[data-testid="stMainBlockContainer"], .block-container {{
  background:transparent !important; box-shadow:none !important; border:none !important;
  max-width:{_W}px !important; padding:34px {_PAD}px 56px !important; margin:0 auto !important;
}}

/* ═══ 히어로 : 네이비로 채운 큰 사각형 ═══ */
.hm-hero {{
  position:relative; overflow:hidden; border-radius:20px;
  background:
    radial-gradient(760px 420px at 88% 118%, rgba(92,106,196,.5) 0%, rgba(92,106,196,0) 62%),
    linear-gradient(134deg, {LEGACY_BLUE} 0%, {BRAND} 50%, {BRAND_800} 100%);
  box-shadow:0 3px 8px rgba(16,23,67,.18), 0 24px 60px rgba(16,23,67,.26);
  padding:52px 52px 0;
}}
.hm-corner {{
  position:absolute; right:30px; top:26px; height:16px; width:auto;
  pointer-events:none; user-select:none;
}}
.hm-inner {{ position:relative; z-index:1; padding-bottom:48px; }}
.hm-eyebrow {{
  display:inline-flex; align-items:center; gap:9px;
  font:650 .69rem/1 {_FONT}; letter-spacing:.19em; text-transform:uppercase;
  color:{BRAND_300}; background:rgba(255,255,255,.07);
  border:1px solid rgba(255,255,255,.14); border-radius:{R_PILL};
  padding:8px 15px; margin-bottom:28px;
}}
.hm-eyebrow i {{
  width:5px; height:5px; border-radius:50%; background:#5BD69A; font-style:normal;
  box-shadow:0 0 0 3px rgba(91,214,154,.22);
}}
.hm-h1 {{
  font:800 3.15rem/1.09 {_FONT}; letter-spacing:-.05em; color:#fff; margin:0 0 22px;
}}
.hm-h1 em {{ font-style:normal; color:{BRAND_300}; }}
.hm-lead {{
  font:400 1.05rem/1.78 {_FONT}; color:rgba(255,255,255,.66);
  max-width:52ch; margin:0;
}}
.hm-lead b {{ color:#fff; font-weight:650; }}
.hm-spectrum {{ display:flex; height:4px; margin:0 -52px; }}
.hm-spectrum span {{ flex:1; }}

/* ═══ CTA 카드 : HTML 카드 + 붙은 버튼 ═══ */
.hm-card {{
  background:{SHEET}; border:1px solid {LINE};
  border-bottom:none; border-radius:{R_LG} {R_LG} 0 0;
  padding:26px 26px 20px; box-shadow:{SHADOW_1};
}}
.hm-tile {{
  width:38px; height:38px; border-radius:11px; display:grid; place-items:center;
  font:400 1.06rem/1 {_FONT}; margin-bottom:16px;
}}
.hm-tile.p {{
  background:linear-gradient(140deg,{BRAND_600},{BRAND}); color:#fff;
  box-shadow:0 3px 10px rgba(21,31,109,.3);
}}
.hm-tile.s {{ background:{BRAND_025}; border:1px solid {BRAND_050}; color:{BRAND_600}; }}
.hm-card .t {{
  font:750 1.14rem/1 {_FONT}; letter-spacing:-.028em; color:{BRAND}; margin-bottom:9px;
}}
.hm-card .d {{ font:400 .92rem/1.68 {_FONT}; color:{INK_SUB}; min-height:2.7em; }}
.st-key-home_run, .st-key-home_task {{ margin-top:-1.05rem !important; }}
.st-key-home_run button, .st-key-home_task button {{
  border-radius:0 0 {R_LG} {R_LG} !important;
  font:700 .93rem/1 {_FONT} !important; letter-spacing:-.018em !important;
  padding:16px 20px !important; box-shadow:{SHADOW_1} !important;
  transition:.15s ease !important;
}}
.st-key-home_run button {{
  background:linear-gradient(180deg,{BRAND} 0%,{BRAND_800} 100%) !important;
  border:1px solid {BRAND_800} !important;
}}
.st-key-home_run button, .st-key-home_run button *,
.st-key-home_run button:hover, .st-key-home_run button:hover *,
.st-key-home_run button:active, .st-key-home_run button:focus,
.st-key-home_run button:focus *, .st-key-home_run button p {{
  color:#fff !important; -webkit-text-fill-color:#fff !important;
}}
.st-key-home_run button:hover {{
  background:linear-gradient(180deg,{BRAND_700} 0%,{BRAND_800} 100%) !important;
  box-shadow:0 5px 18px rgba(21,31,109,.3) !important;
}}
.st-key-home_task button {{
  background:{SHEET} !important;
  border:1px solid {LINE} !important; border-top:1px solid {BRAND_050} !important;
}}
.st-key-home_task button, .st-key-home_task button *,
.st-key-home_task button:hover, .st-key-home_task button:hover *,
.st-key-home_task button:focus *, .st-key-home_task button p {{
  color:{BRAND} !important; -webkit-text-fill-color:{BRAND} !important;
}}
.st-key-home_task button:hover {{
  background:{BRAND_025} !important; border-color:{BRAND_100} !important;
}}

/* ═══ 최근 실행 ═══ */
.hm-panel {{
  background:{SHEET}; border:1px solid {LINE}; border-radius:{R_LG};
  box-shadow:{SHADOW_1}; margin-top:22px; overflow:hidden;
}}
.hm-panelhead {{
  display:flex; align-items:center; gap:10px;
  background:{BRAND_025}; border-bottom:1px solid {BRAND_050}; padding:14px 24px;
  font:650 .72rem/1 {_FONT}; letter-spacing:.13em; text-transform:uppercase;
  color:{BRAND_600};
}}
.hm-panelhead b {{
  margin-left:auto; font:600 .74rem/1 {_FONT}; letter-spacing:0;
  text-transform:none; color:{INK_MUTED};
}}
.hm-run {{
  display:flex; align-items:center; gap:18px; padding:15px 24px;
  border-bottom:1px solid {BRAND_025}; font:400 .9rem/1.4 {_FONT}; color:{INK_SUB};
  transition:background .12s;
}}
.hm-run:last-child {{ border-bottom:none; }}
.hm-run:hover {{ background:{BRAND_025}; }}
.hm-run .sh {{ font-weight:750; color:{BRAND}; min-width:78px; letter-spacing:-.015em; }}
.hm-run .bar {{
  width:66px; height:5px; border-radius:{R_PILL}; background:{BRAND_050};
  overflow:hidden; flex:none;
}}
.hm-run .bar i {{ display:block; height:100%; background:{BRAND_400}; }}
.hm-run .id {{
  margin-left:auto; color:{INK_MUTED}; font-size:.77rem;
  font-variant-numeric:tabular-nums;
}}
.hm-empty {{
  padding:30px 24px; text-align:center; font:400 .9rem/1 {_FONT}; color:{INK_MUTED};
}}
.hm-foot {{
  font:400 .8rem/1.75 {_FONT}; color:{INK_MUTED}; padding:22px 4px 0; text-align:center;
}}
.hm-org {{
  display:inline-block; margin-top:7px; font:600 .72rem/1 {_FONT};
  letter-spacing:.1em; color:{BRAND_300};
}}
</style>"""


def _pct(r) -> int:
    try:
        done, total = int(r["판정 완료"]), int(r["대상"])
        return max(6, min(100, round(done / total * 100))) if total else 100
    except (TypeError, ValueError, KeyError):
        return 100


def chrome(env: str):
    """모든 페이지 공용 — 상단 네이비 밴드."""
    st.html(_CSS_CHROME + f"""
<div class="hm-band"><div class="hm-band-in">
  <img class="hm-logo" src="{_LOGO}" alt="SAMYANG">
  <div class="hm-word">특허 검토 자동화 AI Agent</div>
  <div class="hm-env">{env}</div>
</div></div>""")


def render(stats: dict, tasks: list, runs: list, env: str):
    """(판정_시작_눌림, 기준관리_눌림) 반환."""
    spectrum = "".join(f'<span style="background:{LABEL_COLOR[k]}"></span>'
                       for k in ("noise", "valid", "issue", "hold"))

    st.html(_CSS + f"""
<div class="hm-hero">
  <img class="hm-corner" src="{_LOGO}" alt="SAMYANG">
  <div class="hm-inner">
    <div class="hm-eyebrow"><i></i>Patent Review Automation</div>
    <h1 class="hm-h1">특허 검토 자동화<br><em>AI Agent</em></h1>
    <p class="hm-lead">AI 는 원문에서 <b>사실만</b> 확인하고, 등급은 담당자가 정한
    <b>기준이 결정</b>합니다. 판정마다 근거 청구항과 판단 과정이 함께 남습니다.</p>
  </div>
  <div class="hm-spectrum">{spectrum}</div>
</div>
<div style="height:22px"></div>""")

    c1, c2 = st.columns(2, gap="medium")
    with c1:
        st.html(f"""
<div class="hm-card">
  <div class="hm-tile s">⚙</div>
  <div class="t">판정기준 관리</div>
  <div class="d">무엇을 걸러내고 무엇을 먼저 볼지 담당자가 직접 정합니다.
  기준을 고치면 다음 판정부터 바로 반영됩니다.</div>
</div>""")
        go_task = st.button("판정기준 관리", use_container_width=True, key="home_task")
    with c2:
        st.html("""
<div class="hm-card">
  <div class="hm-tile p">▶</div>
  <div class="t">판정 실행</div>
  <div class="d">특허 리스트 엑셀을 올려 한 회차를 판정합니다.
  결과는 원본 오른쪽에 열로 덧붙여 내려받습니다.</div>
</div>""")
        go_run = st.button("판정 시작", type="primary", use_container_width=True,
                           key="home_run")

    body = "".join(
        f'<div class="hm-run"><span class="sh">{r["회차"]}</span>'
        f'<span class="bar"><i style="width:{_pct(r)}%"></i></span>'
        f'<span>{r["판정 완료"]}/{r["대상"]}건 판정</span>'
        f'<span class="id">{r["실행"]}</span></div>' for r in runs[:5]) or \
        '<div class="hm-empty">아직 실행 기록이 없습니다 — 판정 시작을 눌러보세요</div>'
    st.html(f"""
<div class="hm-panel">
  <div class="hm-panelhead">최근 실행<b>{len(runs)}건 기록</b></div>
  {body}
</div>
<div class="hm-foot">원본 엑셀 파일은 수정하지 않습니다. 결과는 사본에 열로 덧붙습니다.<br><span class="hm-org">삼양그룹 · AX 100일의 도전</span></div>""")
    return go_run, go_task
