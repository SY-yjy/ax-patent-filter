"""앱 셸 — 홈 화면 + 라우팅. 실험용/배포용이 이 한 벌을 공유한다.

화면 구성
  🏠 홈           큰 버튼 두 개(판정 실행 / 판정기준 관리) + 최근 실행 목록
  ▶ 판정 실행     본문에서 단계별로: 과제 → 데이터 → 회차 → 실행 → 결과
  ⚙️ 판정기준 관리  과제 생성·편집 (ui_task_editor)

사이드바에 컨트롤을 흩뿌리지 않는다. 모든 입력은 본문 흐름 안에 있다.
"""
import json
from pathlib import Path
import streamlit as st

import config
import criteria as C
import ui_common as ui
import ui_home as home
import ui_task_editor as ted

HOME, RUN, TASKS = "home", "run", "tasks"
BUILD = "2026-08-21 · v4"
_ISSUE_BG = "#FDF1F0"   # 삭제 탭 강조 면   # 화면에 표시 — 새 빌드가 로드됐는지 즉시 구분

# ===========================================================================
#  디자인 시스템 — Pantone 2756 C(#151F6D) 기반
#  색 6단 · 타이포 5단 · 라운드 3단 · 그림자 2단으로 제한해 화면을 일관되게 유지한다.
#  실측: Pantone 2756 C = #151F6D (RGB 21,31,109), 2026-08-21 확인
# ===========================================================================
from theme import (BRAND, BRAND_800, BRAND_700, BRAND_600, BRAND_400, BRAND_300,
                   BRAND_100, BRAND_050, BRAND_025, GROUND, SHEET, LINE, LINE_STRONG,
                   INK, INK_SUB, INK_MUTED, R_SM, R_MD, R_LG, R_PILL,
                   SHADOW_1, SHADOW_2, SHADOW_BRAND)

# ⚠️ 폰트는 여기서 못 불러온다 — st.html 은 DOMPurify 로 살균되고 <link>·<meta> 는
#    허용 태그가 아니다(실측 2026-08-24). <style> 은 통과한다.
#    폰트는 .streamlit/config.toml 의 theme.font "이름:URL" 형식으로 넣는다.
_CSS = f"""
<style>
  /* ═══ 바탕 · 시트 ═══════════════════════════════════════════════════ */
  [data-testid="stAppViewContainer"], .stApp {{ background:{GROUND} !important; }}

  [data-testid="stMainBlockContainer"], .block-container {{
    background:linear-gradient(180deg, {BRAND_050} 0px, {BRAND_025} 120px, {SHEET} 340px);
    border:1px solid {LINE}; border-top:3px solid {BRAND};
    border-radius:{R_LG}; box-shadow:{SHADOW_2};
    padding:42px 52px 60px !important; max-width:1420px;
    margin-top:22px !important; margin-bottom:44px !important;
  }}

  /* ═══ 타이포 ════════════════════════════════════════════════════════ */
  .stApp {{ color:{INK}; }}
  h1,h2,h3,h4,h5 {{ color:{BRAND}; letter-spacing:-.022em; }}
  p, li, label, .stMarkdown {{ color:{INK}; }}
  [data-testid="stCaptionContainer"], [data-testid="stCaptionContainer"] p {{
    color:{INK_MUTED} !important; font-size:.82rem; line-height:1.65;
  }}
  code {{ font-size:.86em; padding:1px 5px; border-radius:5px; }}
  hr {{ border-color:{LINE} !important; margin:26px 0 !important; }}

  /* ═══ 카드 · 컨테이너 ═══════════════════════════════════════════════ */
  .ax-card-t {{ color:{BRAND}; font-size:1.14rem; font-weight:750; margin:2px 0 12px;
                letter-spacing:-.018em; }}
  .ax-card-d {{ color:{INK_SUB}; font-size:.9rem; line-height:1.85; min-height:106px; }}

  /* ═══ 버튼 ══════════════════════════════════════════════════════════ */
  .stButton button, .stDownloadButton button, .stFormSubmitButton button {{
    font-weight:650; border-radius:{R_SM}; letter-spacing:-.005em;
    transition:background .14s ease, border-color .14s ease, box-shadow .14s ease,
               transform .14s ease;
  }}
  .stButton button[kind="primary"], .stFormSubmitButton button[kind="primary"],
  .stDownloadButton button[kind="primary"] {{
    background:{BRAND}; border:1px solid {BRAND};
    box-shadow:0 1px 2px rgba(21,31,109,.18);
  }}
  .stButton button[kind="primary"], .stButton button[kind="primary"] *,
  .stButton button[kind="primary"]:hover, .stButton button[kind="primary"]:hover *,
  .stButton button[kind="primary"]:focus, .stButton button[kind="primary"]:focus *,
  .stButton button[kind="primary"] p,
  .stFormSubmitButton button[kind="primary"], .stFormSubmitButton button[kind="primary"] *,
  .stDownloadButton button[kind="primary"], .stDownloadButton button[kind="primary"] * {{
    color:#fff !important; -webkit-text-fill-color:#fff !important;
  }}
  .stButton button[kind="primary"] svg, .stDownloadButton button[kind="primary"] svg {{
    fill:#fff !important;
  }}
  .stButton button[kind="primary"]:hover, .stFormSubmitButton button[kind="primary"]:hover,
  .stDownloadButton button[kind="primary"]:hover {{
    background:{BRAND_700}; border-color:{BRAND_700}; box-shadow:{SHADOW_BRAND};
    transform:translateY(-1px);
  }}
  .stButton button[kind="secondary"], .stDownloadButton button[kind="secondary"],
  .stFormSubmitButton button[kind="secondary"] {{
    background:{SHEET}; border:1px solid {LINE_STRONG};
  }}
  .stButton button[kind="secondary"], .stButton button[kind="secondary"] *,
  .stButton button[kind="secondary"] p,
  .stDownloadButton button[kind="secondary"], .stDownloadButton button[kind="secondary"] *,
  .stFormSubmitButton button[kind="secondary"], .stFormSubmitButton button[kind="secondary"] * {{
    color:{BRAND} !important; -webkit-text-fill-color:{BRAND} !important;
  }}
  .stButton button[kind="secondary"]:hover {{
    border-color:{BRAND_400}; background:{BRAND_025};
  }}
  .stButton button:focus-visible {{ outline:2px solid {BRAND_400}; outline-offset:2px; }}

  /* ═══ 입력 ══════════════════════════════════════════════════════════ */
  input, textarea,
  div[data-baseweb="select"] > div, div[data-baseweb="input"] > div,
  div[data-baseweb="textarea"] > div {{
    border-radius:{R_SM} !important; background:{BRAND_025} !important;
  }}
  div[data-baseweb="input"], div[data-baseweb="textarea"], div[data-baseweb="select"] {{
    border-color:{BRAND_100} !important; background:{BRAND_025} !important;
  }}
  div[data-baseweb="select"] svg {{ fill:{BRAND_400} !important; }}
  div[data-baseweb="popover"] li:hover {{ background:{BRAND_025} !important; }}
  div[data-baseweb="input"]:focus-within, div[data-baseweb="textarea"]:focus-within,
  div[data-baseweb="select"]:focus-within {{
    border-color:{BRAND} !important;
    box-shadow:0 0 0 3px {BRAND_100} !important;
  }}
  textarea {{ line-height:1.7 !important; }}

  /* ═══ 태그 (multiselect) ════════════════════════════════════════════ */
  span[data-baseweb="tag"] {{
    background:{BRAND_025} !important; color:{BRAND} !important;
    border:1px solid {BRAND_050} !important; border-radius:{R_PILL} !important;
    font-weight:600 !important; font-size:.82rem !important;
  }}
  span[data-baseweb="tag"] svg {{ fill:{BRAND_400} !important; }}
  span[data-baseweb="tag"]:hover svg {{ fill:{BRAND} !important; }}

  /* ═══ 탭 ════════════════════════════════════════════════════════════ */
  div[data-baseweb="tab-list"] {{ gap:4px; border-bottom:1px solid {LINE}; }}
  button[data-baseweb="tab"] {{
    font-weight:650; color:{INK_MUTED}; letter-spacing:-.01em; padding:10px 14px;
  }}
  button[data-baseweb="tab"]:hover {{ color:{BRAND_600}; }}
  button[data-baseweb="tab"][aria-selected="true"] {{ color:{BRAND} !important; }}
  div[data-baseweb="tab-highlight"] {{ display:none !important; }}
  button[data-baseweb="tab"][aria-selected="true"] {{
    box-shadow:inset 0 -2px 0 {BRAND} !important;
  }}
  div[data-baseweb="tab-border"] {{ display:none; }}

  /* ═══ 확장패널 ══════════════════════════════════════════════════════ */
  details {{
    border:1px solid {LINE} !important; border-radius:{R_MD} !important;
    background:{SHEET} !important; margin-bottom:10px;
    box-shadow:{SHADOW_1};
  }}
  details summary {{
    background:{BRAND_025} !important; border-radius:{R_MD} !important;
    padding:12px 16px !important;
  }}
  details summary:hover {{ background:{BRAND_050} !important; }}
  details[open] summary {{ border-bottom:1px solid {LINE}; border-radius:{R_MD} {R_MD} 0 0 !important; }}
  details summary p, details summary span, details summary div {{
    color:{BRAND} !important; font-weight:650 !important; letter-spacing:-.01em;
  }}

  /* ═══ 지표 타일 ═════════════════════════════════════════════════════ */
  div[data-testid="stMetric"] {{
    background:{BRAND_025}; border:1px solid {BRAND_050};
    border-radius:{R_MD}; padding:15px 17px;
  }}
  div[data-testid="stMetricLabel"] p {{
    color:{INK_MUTED} !important; font-weight:650; font-size:.78rem;
    letter-spacing:.01em;
  }}
  div[data-testid="stMetricValue"] {{
    color:{BRAND} !important; font-weight:750; letter-spacing:-.03em;
  }}

  /* ═══ 표 ════════════════════════════════════════════════════════════ */
  .stDataFrame thead tr th {{
    color:{BRAND} !important; font-weight:700 !important; letter-spacing:-.005em;
  }}
  [data-testid="stDataFrameResizable"] {{ border-radius:{R_SM}; border-color:{LINE} !important; }}

  /* ═══ 다이얼로그 ════════════════════════════════════════════════════ */
  div[role="dialog"] {{ border-radius:{R_LG} !important; box-shadow:{SHADOW_2} !important; }}
  div[role="dialog"] h2 {{ letter-spacing:-.02em; }}

  /* ═══ 알림 (info/warning/error) ═════════════════════════════════════ */
  div[data-testid="stAlert"] {{ border-radius:{R_SM}; border-width:1px; }}

  /* ═══ 진행 표시 ═════════════════════════════════════════════════════ */
  div[data-testid="stProgress"] div[role="progressbar"] > div {{ background:{BRAND} !important; }}

  /* ═══ 의식의 흐름 패널 ═════════════════════════════════════════════ */
  .ax-think {{
    background:linear-gradient(180deg, {BRAND_025} 0%, {SHEET} 100%);
    border:1px solid {BRAND_050}; border-left:3px solid {BRAND};
    border-radius:{R_MD}; padding:18px 20px;
    min-height:180px; max-height:360px; overflow-y:auto;
    font-size:.9rem; line-height:1.9; color:{INK};
  }}
  .ax-think.big {{
    min-height:340px; max-height:600px; font-size:.94rem; line-height:2.0;
    padding:22px 24px;
  }}
  .ax-think .ln {{ margin:0 0 8px; }}
  .ax-think .cur {{ color:{BRAND_600}; font-weight:650; }}
  .ax-think .dim {{ color:{INK_MUTED}; }}

  /* ═══ 파일 업로더 : 큰 흰 구멍을 옅은 파랑으로 ═════════════════════ */
  [data-testid="stFileUploaderDropzone"] {{
    background:{BRAND_025} !important; border:1.5px dashed {BRAND_100} !important;
    border-radius:{R_MD} !important; padding:20px !important;
  }}
  [data-testid="stFileUploaderDropzone"]:hover {{
    background:{BRAND_050} !important; border-color:{BRAND_400} !important;
  }}
  [data-testid="stFileUploaderDropzoneInstructions"] svg {{ fill:{BRAND_400} !important; }}
  [data-testid="stFileUploaderFile"] {{
    background:{BRAND_025} !important; border:1px solid {BRAND_050} !important;
    border-radius:{R_SM} !important; padding:9px 12px !important;
  }}

  /* ═══ 표 머리 ═══════════════════════════════════════════════════════ */
  .stDataFrame thead tr th, [data-testid="stDataFrameResizable"] thead tr th {{
    background:{BRAND_025} !important;
  }}

  /* ═══ 탭 : 선택된 탭에 면을 준다 ════════════════════════════════════ */
  div[data-baseweb="tab-list"] {{ background:{BRAND_025}; border-radius:{R_MD} {R_MD} 0 0;
    padding:5px 6px 0 !important; }}
  button[data-baseweb="tab"] {{ border-radius:{R_SM} {R_SM} 0 0 !important; }}
  button[data-baseweb="tab"][aria-selected="true"] {{ background:{SHEET} !important; }}

  /* ═══ 섹션 라벨 : 색 악센트 바 ══════════════════════════════════════ */
  .ax-sec {{ display:flex; align-items:center; gap:10px; margin:0 0 12px; }}
  .ax-sec i {{
    width:3px; height:17px; border-radius:2px; flex:none;
    background:linear-gradient(180deg,{BRAND_400},{BRAND});
  }}
  .ax-sec b {{ color:{BRAND}; font-weight:750; font-size:1rem; letter-spacing:-.018em; }}
  .ax-sec s {{ text-decoration:none; color:{INK_MUTED}; font-size:.83rem; }}

  /* ═══ 페이지 머리 ═══════════════════════════════════════════════════ */
  .ax-ph {{
    display:flex; align-items:flex-end; justify-content:space-between; gap:20px;
    background:linear-gradient(100deg,{BRAND_050},{BRAND_025} 62%,transparent);
    border-left:3px solid {BRAND}; border-radius:0 {R_MD} {R_MD} 0;
    padding:17px 22px 15px; margin:0 0 30px;
  }}
  .ax-ph .cr {{
    color:{BRAND_400}; font-size:.75rem; font-weight:650; letter-spacing:.05em;
    margin-bottom:5px;
  }}
  .ax-ph .ti {{
    color:{BRAND}; font-size:1.6rem; font-weight:800; letter-spacing:-.032em; line-height:1.2;
  }}
  .ax-ph .rt {{ color:{INK_MUTED}; font-size:.79rem; text-align:right; padding-bottom:4px; }}

  /* ═══ 파괴적 동작 버튼 (과제 삭제) ═════════════════════════════════ */
  [class*="_delbtn"] button {{
    background:linear-gradient(180deg,#C0342C 0%,#9E2A23 100%) !important;
    border:1px solid #9E2A23 !important;
    box-shadow:0 2px 8px rgba(192,52,44,.28) !important;
  }}
  [class*="_delbtn"] button:hover {{
    background:linear-gradient(180deg,#D03A31 0%,#A82D25 100%) !important;
    border-color:#8E251F !important;
    box-shadow:0 4px 14px rgba(192,52,44,.38) !important;
    transform:translateY(-1px) !important;
  }}
  [class*="_delbtn"] button, [class*="_delbtn"] button *,
  [class*="_delbtn"] button:hover, [class*="_delbtn"] button:hover *,
  [class*="_delbtn"] button:focus, [class*="_delbtn"] button:focus *,
  [class*="_delbtn"] button p {{
    color:#fff !important; -webkit-text-fill-color:#fff !important;
  }}
  [class*="_delbtn"] button:focus-visible {{
    outline:2px solid #C0342C !important; outline-offset:2px !important;
  }}

  /* ═══ 삭제 탭 (6번째) 빨강 강조 ════════════════════════════════════ */
  div[data-baseweb="tab-list"] button[data-baseweb="tab"]:nth-child(6),
  div[data-baseweb="tab-list"] button[data-baseweb="tab"]:nth-child(6) * {{
    color:#C0342C !important; -webkit-text-fill-color:#C0342C !important;
    font-weight:700 !important;
  }}
  div[data-baseweb="tab-list"] button[data-baseweb="tab"]:nth-child(6):hover {{
    background:{_ISSUE_BG} !important;
  }}
  div[data-baseweb="tab-list"] button[data-baseweb="tab"]:nth-child(6)[aria-selected="true"] {{
    background:{_ISSUE_BG} !important;
    box-shadow:inset 0 -2px 0 #C0342C !important;
  }}
</style>
"""


def card(title: str, lines: list[str]) -> None:
    st.markdown(
        f'<div class="ax-card-t">{title}</div>'
        f'<div class="ax-card-d">' + "<br>".join(lines) + '</div>',
        unsafe_allow_html=True)


def inject_css():
    """CSS 주입 — st.html 을 쓴다.

    st.markdown(unsafe_allow_html=True) 는 마크다운 살균기를 거쳐 <style> 이 누락될 수 있다.
    st.html 은 CSS/HTML 주입용 정식 경로이고 iframe 이 아니라 인라인으로 들어간다.
    """
    st.html(_CSS)





def _goto(page: str):
    st.session_state["_page"] = page
    st.rerun()


def _recent_runs(limit: int = 8):
    """output/runs 의 최근 실행 목록."""
    rows = []
    if not config.RUNS_DIR.is_dir():
        return rows
    for d in sorted(config.RUNS_DIR.iterdir(), key=lambda p: p.name, reverse=True):
        if not d.is_dir():
            continue
        jl, mt = d / "records.jsonl", d / "meta.json"
        n = sum(1 for line in open(jl, encoding="utf-8") if line.strip()) if jl.is_file() else 0
        if n == 0:
            continue                       # 빈 실행은 목록에 넣지 않는다
        sheet = total = "?"
        if mt.is_file():
            try:
                m = json.loads(mt.read_text(encoding="utf-8"))
                sheet, total = m.get("sheet", "?"), m.get("n_records", "?")
            except Exception:
                pass
        rows.append({"실행": d.name, "회차": sheet, "판정 완료": n, "대상": total,
                     "엑셀": "있음" if (d / "판정결과.xlsx").is_file() else "—"})
        if len(rows) >= limit:
            break
    return rows


# ---------------------------------------------------------------- 홈
_GRADES = [("noise", "노이즈", "명백히 무관"), ("valid", "유효", "관련 있음"),
           ("issue", "이슈", "권리 중첩 가능"), ("hold", "보류", "판단 불가")]


def page_home(title: str, subtitle: str):
    """홈."""
    names = C.list_tasks()
    runs = _recent_runs(12)
    stats = {"tasks": len(names), "runs": len(runs),
             "judged": sum(int(r["판정 완료"]) for r in runs
                           if str(r["판정 완료"]).isdigit())}
    go_run, go_task = home.render(stats, names, runs, ui.engine_badge())
    if go_run:
        _goto(RUN)
    if go_task:
        _goto(TASKS)


def page_header(crumb: str, title: str, right: str = ""):
    """모든 하위 페이지의 머리 — 경로 · 제목 · 우측 문맥."""
    st.html(f'<div class="ax-ph"><div><div class="cr">{crumb}</div>'
            f'<div class="ti">{title}</div></div>'
            f'<div class="rt">{right}</div></div>')


def _field(label: str, value: str, strong: bool = False) -> str:
    return (f'<div style="display:flex;justify-content:space-between;gap:12px;'
            f'padding:7px 0;border-bottom:1px solid {BRAND_050}">'
            f'<span style="color:{INK_MUTED};font-size:.8rem">{label}</span>'
            f'<span style="color:{BRAND if strong else INK};font-size:.82rem;'
            f'font-weight:{750 if strong else 600};text-align:right;'
            f'overflow:hidden;text-overflow:ellipsis;white-space:nowrap;'
            f'max-width:60%">{value}</span></div>')


def _sec_label(text: str, hint: str = "") -> None:
    st.html(f'<div class="ax-sec"><i></i><b>{text}</b>'
            + (f'<s>{hint}</s>' if hint else '') + '</div>')


def _rule() -> None:
    st.markdown(f'<hr style="border:none;border-top:1px solid {LINE};margin:22px 0 20px">',
                unsafe_allow_html=True)


def page_run(state_key: str, show_reference: bool):
    """설정 흐름(좌) + 실행 요약·시작(우) 2단 구성. 실행 중에는 콘솔 전용 화면."""
    import re
    if st.session_state.get(f"{state_key}_running"):
        ui.run_console(state_key)
        return

    names = C.list_tasks()
    page_header("홈 / 판정 실행", "판정 실행", ui.engine_badge())

    n_stop = st.session_state.pop(f"{state_key}_stopped_n", None)
    if n_stop is not None:
        st.warning(f"실행을 정지했습니다 — 그때까지 판정한 **{n_stop}건**은 그대로 남아 "
                   f"아래에서 보고 내려받을 수 있습니다.")

    if not names:
        st.warning("등록된 과제가 없습니다. 먼저 판정기준을 만들어주세요.")
        if st.button("판정기준 관리로 이동", type="primary"):
            _goto(TASKS)
        return

    left, right = st.columns([2.9, 1.5], gap="large")

    with left:
        _sec_label("과제", "판정 기준을 고릅니다")
        c1, c2 = st.columns([3, 1])
        choice = c1.selectbox("과제", names, key=f"{state_key}_choice",
                              label_visibility="collapsed")
        if c2.button("기준 편집", use_container_width=True, key=f"{state_key}_edit"):
            _goto(TASKS)
        try:
            task = C.load_task(choice)
        except Exception as e:
            st.error(f"과제 로드 실패: {e}")
            return
        st.session_state[f"{state_key}_task"] = task
        st.markdown(f'<div style="color:{INK_SUB};font-size:.85rem;line-height:1.6;'
                    f'margin:6px 0 10px">{task.get("task","")}</div>',
                    unsafe_allow_html=True)
        ui.criteria_panel(task)

        _rule()
        _sec_label("특허 리스트", "회차별 시트가 있는 엑셀")
        wb = ui.data_picker(state_key)

        sheet, recs, n_key, n_target = None, [], 0, 0
        if wb:
            _rule()
            _sec_label("회차", "한 번에 한 회차만 처리합니다")
            s1, s2 = st.columns([1.2, 1])
            sheet = s1.selectbox("회차/시트", list(wb.keys()), key=f"{state_key}_sheet",
                                 label_visibility="collapsed")
            recs = wb[sheet]["records"]
            n_key = sum(1 for r in recs if re.fullmatch(r"\d{13}", str(r.get("on_key") or "")))
            ok = bool(recs) and n_key == len(recs)
            s2.markdown(
                f'<div style="padding:7px 0;font-size:.83rem;'
                f'color:{"#1B7A46" if ok else "#A96A12"};font-weight:650">'
                + (f'원문키 전건 정상 · {len(recs)}건' if ok
                   else f'원문키 {n_key}/{len(recs)}건 — 나머지는 보류')
                + '</div>', unsafe_allow_html=True)
            with st.expander("회차별 요약", expanded=False):
                st.dataframe(ui.sheet_summary(wb), hide_index=True, use_container_width=True)

            limit = st.number_input("처리 건수 (0 = 전체)", 0, value=5, step=5,
                                    key=f"{state_key}_limit")
            n_target = len(recs) if limit == 0 else min(limit, len(recs))

    with right:
        n_crit = len(task.get("criteria") or [])
        fname = st.session_state.get(f"{state_key}_name") or "—"
        eta = f"약 {max(1, round(n_target * 35 / 60))}분" if n_target else "—"
        st.markdown(
            f'<div style="background:{BRAND_025};border:1px solid {BRAND_050};'
            f'border-radius:{R_MD};padding:18px 20px 16px">'
            f'<div style="color:{BRAND};font-weight:750;font-size:.95rem;'
            f'letter-spacing:-.015em;margin-bottom:12px">실행 요약</div>'
            + _field("과제", choice, True)
            + _field("판정 기준", f"{n_crit}개")
            + _field("파일", fname)
            + _field("회차", sheet or "—")
            + _field("대상", f"{n_target}건" if n_target else "—", True)
            + _field("예상 시간", eta)
            + '</div>', unsafe_allow_html=True)
        st.write("")
        ready = bool(wb and sheet and n_target)
        if st.button("판정 시작", type="primary", use_container_width=True,
                     key=f"{state_key}_go", disabled=not ready):
            st.session_state[f"{state_key}_sheet_run"] = sheet
            st.session_state[f"{state_key}_target"] = n_target
            st.session_state[f"{state_key}_running"] = True
            st.session_state.pop(f"{state_key}_results", None)
            st.rerun()
        if not ready:
            st.caption("엑셀을 올리면 시작할 수 있습니다.")
        else:
            st.caption("건당 30~50초 · 진행이 실시간으로 보입니다")

    ui.render_results(state_key, show_reference=show_reference)


# ---------------------------------------------------------------- 셸
def render_app(mode: str):
    """mode: 'experiment' | 'launch'"""
    is_exp = mode == "experiment"
    title = "특허 판정 — 실험·검증" if is_exp else "특허 판정 시스템"
    subtitle = ("배포 버전과 같은 엔진입니다. 판정기준을 다듬고 결과를 검증합니다."
                if is_exp else
                "AI는 원문에서 사실만 확인하고, 등급은 담당자가 정한 기준이 결정합니다.<br>"
                "판정마다 <b style=\"color:#fff\">근거 청구항</b>과 "
                "<b style=\"color:#fff\">판단 과정</b>이 함께 남습니다.")
    page = st.session_state.setdefault("_page", HOME)

    inject_css()
    home.chrome(ui.engine_badge())
    if page != HOME:
        nav = st.columns([1, 7])
        if nav[0].button("← 홈", use_container_width=True, key="btn_home"):
            _goto(HOME)

    if page == HOME:
        page_home(title, subtitle)
    elif page == RUN:
        page_run("exp" if is_exp else "launch", show_reference=is_exp)
    else:
        page_header("홈 / 판정기준 관리", "판정기준 관리",
                    "판정에 쓰이는 기준을 만들고 고칩니다")
        saved = ted.task_editor("te_exp" if is_exp else "te_launch")
        if saved:
            st.success(f"`{saved}` 저장 완료 — 판정 실행에서 바로 쓸 수 있습니다.")
            if st.button("▶ 판정 실행으로 이동", type="primary"):
                _goto(RUN)
