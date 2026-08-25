"""두 앱(실험·배포) 공유 UI 로직 — 과제에 무관.

판정은 **전 건 원문 추출 + 규칙 엔진** 단일 단계다. LLM이 등급을 정하지 않으므로
화면은 ① 등급 ② 적용 규칙 ③ 근거등급 ④ 근거 청구항을 항상 함께 보여준다.
정답 라벨은 성능 지표로 쓰지 않고 '참고'로만 표시한다.
"""
import io
import time
import pandas as pd
import streamlit as st

import config
import agent
import excel_loader
import pipeline
import run_output
import excel_export
import rules
import criteria as C

# 등급 의미색 — Pantone 2756 C(#151F6D) 브랜드와 조화되도록 채도를 낮춘 값
LABEL_KO = {"noise": ("노이즈", "#7A82A0"),   # 브랜드 계열 회청색
            "valid": ("유효", "#137333"),
            "issue": ("이슈", "#C5221F"),
            "hold":  ("보류", "#B06000")}
CONF_ICON = {"높음": "🟢 높음", "중간": "🟡 중간", "낮음": "🔴 낮음"}
from theme import (BRAND_400, BRAND, BRAND_600, BRAND_100, BRAND_050, BRAND_025,
                   GROUND, SHEET, LINE, LINE_STRONG, INK, INK_SUB, INK_MUTED,
                   R_SM, R_MD, R_LG, R_PILL, SHADOW_1, SHADOW_2)


def label_ko(lbl: str) -> str:
    return LABEL_KO.get(lbl, (lbl or "", "#5f6368"))[0]


# ---------------- 상태 배지 ----------------
def engine_badge() -> str:
    """엔진 상태 한 줄 — 화면 하단·홈에 캡션으로 쓴다."""
    back = "Claude 구독" if config.USE_SUBSCRIPTION else "API 키"
    return f"엔진 · 추출 `{config.MODEL_JUDGE}` · 백엔드 {back} · 등급은 규칙 엔진이 결정"


# ---------------- 데이터 선택 (본문 인라인) ----------------
def data_picker(state_key: str):
    """엑셀을 올린다. 웹으로 쓰는 도구라 서버 로컬 경로는 받지 않는다.
    반환: wb dict({sheet: {records, has_on_key}}) 또는 None."""
    loaded = st.session_state.get(f"{state_key}_name")
    if loaded:
        c1, c2 = st.columns([5, 1])
        c1.success(f"📄 **{loaded}** — {len(st.session_state.get(state_key) or {})}개 회차 로드됨")
        if c2.button("다시 올리기", key=f"{state_key}_reset", use_container_width=True):
            for k in (state_key, f"{state_key}_raw", f"{state_key}_name",
                      f"{state_key}_results", f"{state_key}_meta"):
                st.session_state.pop(k, None)
            st.rerun()
        return st.session_state.get(state_key)

    raw = name = None
    up = st.file_uploader("특허 리스트 엑셀 (.xlsx)", type=["xlsx"], key=f"{state_key}_up",
                          label_visibility="collapsed")
    if up is not None:
        raw, name = up.getvalue(), up.name

    if raw:
        with st.spinner(f"회차 읽는 중… ({name})"):
            try:
                st.session_state[state_key] = excel_loader.load_all_sheets(io.BytesIO(raw))
                st.session_state[f"{state_key}_raw"] = raw
                st.session_state[f"{state_key}_name"] = name
                st.session_state.pop(f"{state_key}_results", None)
                st.rerun()
            except Exception as e:
                st.error(f"로드 실패: {e}")
    return st.session_state.get(state_key)


def sheet_summary(wb: dict) -> pd.DataFrame:
    """회차별 요약. 원문키 상태가 곧 원문 판정 가능 여부다."""
    import re
    rows = []
    for name, d in wb.items():
        recs = d["records"]
        ok = sum(1 for r in recs if re.fullmatch(r"\d{13}", str(r.get("on_key") or "")))
        state = "❌ 컬럼 없음" if not d["has_on_key"] else (
            "✅ 전건 정상" if (recs and ok == len(recs)) else f"⚠️ {ok}/{len(recs)}")
        rows.append({"회차/시트": name, "행수": len(recs), "원문키(ON key)": state,
                     "유효 O(참고)": sum(1 for r in recs if r.get("valid") == "O"),
                     "이슈 O(참고)": sum(1 for r in recs if r.get("issue") == "O")})
    return pd.DataFrame(rows)


# ---------------- 판정기준 표시 ----------------
def criteria_panel(task: dict):
    """판정 실행 화면에서 기준을 접힌 토글로 보여준다.

    판정 흐름(1단계 노이즈 → 2단계 이슈 → 언제든 보류)대로 등급별 불릿만 보여준다.
    """
    problems = rules.lint(task)
    if problems:
        st.error("판정 기준에 문제가 있습니다 — 실행이 거부됩니다:\n\n"
                 + "\n".join(f"- {p}" for p in problems))

    g = rules.by_label(task)
    steps = [("noise", "🔘 노이즈", "1단계"), ("valid", "🟢 유효", "1단계 통과"),
             ("issue", "🔴 이슈", "2단계"), ("hold", "🟠 보류", "언제든")]
    counts = " · ".join(f"{ic} {len(g[lab])}" for lab, ic, _ in steps)

    with st.expander(f"판정 기준   {counts}", expanded=False):
        st.caption("1단계 노이즈인가? → 2단계 유효 중 이슈인가? → 판단이 안 서면 보류. "
                   "AI는 각 문장에 해당·비해당·모르겠음만 답합니다.")
        cols = st.columns(4)
        for col, (lab, title, step) in zip(cols, steps):
            with col:
                st.markdown(f"**{title}**  \n<span style='color:#6A7192;font-size:.78rem'>"
                            f"{step}</span>", unsafe_allow_html=True)
                if g[lab]:
                    st.markdown("\n".join(
                        f"- {' '.join(str(c.get('when','')).split())}"
                        for c in g[lab]))
                else:
                    st.caption("_(없음)_")
        st.caption("어느 기준에도 해당하지 않으면 **보류**입니다.")

        ot = task.get("own_tech") or {}
        if any(ot.values()):
            st.markdown("---")
            st.markdown("**자사 기술** — 참고용 (판정에 쓰이지 않음)")
            rows = []
            if ot.get("materials"):
                rows.append("핵심 소재 : " + ", ".join(map(str, ot["materials"])))
            if ot.get("application"):
                rows.append("적용      : " + str(ot["application"]))
            if ot.get("ranges"):
                rows.append("조성 범위 : " + str(ot["ranges"]))
            st.code("\n".join(rows), language=None)

        st.markdown("---")
        st.markdown("**🤖 AI에게 들어가는 전문**")
        st.code(C.render_for_extract(task), language=None)



# ---------------- 실행 ----------------
_ERR_KO = {
    "maximum buffer size": "원문이 너무 커서 한 번에 받지 못했습니다",
    "timeout": "응답 시간이 초과됐습니다",
    "rate limit": "사용량 한도에 걸렸습니다",
    "connection": "연결이 끊겼습니다",
}


def err_text(msg: str) -> str:
    """실행오류 원인을 사람 말로. 원문 메시지는 상세·기록에 그대로 남는다."""
    low = str(msg).lower()
    for k, v in _ERR_KO.items():
        if k in low:
            return v
    return " ".join(str(msg).split())[:90]


def crit_text(r: dict, limit: int = 46) -> str:
    """해당한 기준을 사람이 읽는 말로. `c_i1` 같은 내부 id 는 화면에 내보내지 않는다."""
    cid = str(r.get("criterion_id") or "")
    if not cid:
        return ""
    if cid == "실행오류":
        return f"실행오류 — {err_text(r.get('reason') or '')}"
    if not cid.startswith("c_"):
        return cid                      # 판단충돌·판단불가·근거없음 등 이미 한국말
    txt = " ".join(str(r.get("criterion") or "").split())
    return (txt[:limit] + "…") if len(txt) > limit else (txt or label_ko(r.get("label")))


def _flatten(r: dict) -> dict:
    claims = "; ".join(f"[{c.get('no','')}] {str(c.get('text',''))[:120]}"
                       for c in (r.get("independent_claims") or []))
    return {
        "번호": r.get("no"), "국가": r.get("country"),
        "발명의 명칭": str(r.get("title") or "")[:55],
        "AI판정": label_ko(r.get("label")),
        "신뢰도": CONF_ICON.get(r.get("confidence"), r.get("confidence") or ""),
        "해당기준": crit_text(r),
        "보류사유": (" ".join(str(r.get("criterion") or "").split())[:60]
                    if r.get("label") == "hold" else ""),
        "근거등급": ("📄 " + str(r.get("evidence"))) if str(r.get("evidence", "")).startswith("원문")
                    else ("⚠️ " + str(r.get("evidence") or "")),
        "판정근거": " ".join(str(r.get("criterion") or r.get("reason") or "").split()),
        "근거청구항": claims,
        "검토필요사항": r.get("review_note") or "",
        "사람라벨(참고)": (("유효" if r.get("gold_valid") == "O" else "")
                        + ("·이슈" if r.get("gold_issue") == "O" else "")) or "—",
        "_label": r.get("label") or "",
    }


def _think_html(buf: str, done: bool = False) -> str:
    """스트리밍 버퍼 → 의식의 흐름 패널 HTML.

    모델이 `<<<THINKING … THINKING>>>` 사이에 판단 과정을 서술하게 되어 있다.
    그 구간만 문장 단위로 보여주고, 뒤따르는 JSON 은 화면에 내보내지 않는다
    (JSON 은 결과 표·엑셀로 나가므로 여기서는 사람이 읽을 것만 남긴다).
    """
    import html as _h
    txt = buf.split("<<<THINKING", 1)[-1]
    finished = "THINKING>>>" in txt
    txt = txt.split("THINKING>>>", 1)[0]
    lines = [l.strip() for l in txt.splitlines() if l.strip()]
    if not lines:
        return ('<div class="ax-think"><div class="ln dim">원문을 읽는 중…</div></div>')
    body = []
    for i, l in enumerate(lines):
        last = (i == len(lines) - 1) and not (finished or done)
        cls = "ln cur" if last else "ln"
        body.append(f'<div class="{cls}">{_h.escape(l)}'
                    + ('<span class="dim"> ▌</span>' if last else '') + '</div>')
    if finished or done:
        body.append('<div class="ln dim">— 판단 종료, 추출값 정리 중</div>')
    return '<div class="ax-think">' + "".join(body) + "</div>"


from theme import (LABEL_COLOR as _TR_COLOR, LABEL_BG as _TR_BG,
                   LABEL_LINE as _TR_LINE, LABEL_ICON as _TR_ICON)
_ANS = {"O": ("해당", "#137333"), "X": ("비해당", "#9aa0b8"), "?": ("모르겠음", "#B06000")}


def render_trace(trace: list[dict], task: dict | None = None):
    """판정 과정 — 단계별로 무엇에 해당했는지.

    이 시스템의 차별점이다. AI에게 등급을 물어보는 방식으로는 만들 수 없다.
    """
    if not trace:
        st.caption("_(판정 과정 기록이 없습니다)_")
        return
    for g in trace:
        lab = g["label"]
        col, bg, line = _TR_COLOR[lab], _TR_BG[lab], _TR_LINE[lab]
        decided = g.get("decided")
        rows = "".join(
            (lambda txt, c, strong: (
                f'<div style="display:flex;gap:8px;align-items:baseline;padding:3px 0 3px 2px">'
                f'<span style="flex:0 0 52px;color:{c};font-weight:700;font-size:.75rem;'
                f'letter-spacing:-.01em">{txt}</span>'
                f'<span style="color:{INK if strong else INK_SUB};font-size:.83rem;'
                f'line-height:1.6;{"font-weight:650" if strong else ""}">{it["when"]}'
                + ('  <span style="color:' + col + ';font-weight:700">← 확정</span>'
                   if strong else '')
                + '</span></div>'))(*_ANS.get(it["answer"], (it["answer"], INK_MUTED)),
                                    it.get("decided"))
            for it in g["items"])
        st.markdown(
            f'<div style="border:1px solid {line};border-radius:{R_SM};overflow:hidden;'
            f'margin-bottom:9px">'
            f'<div style="background:{bg};padding:7px 12px;display:flex;align-items:center;'
            f'gap:8px;border-bottom:1px solid {line}">'
            f'<b style="color:{col};font-size:.85rem;letter-spacing:-.01em">'
            f'{_TR_ICON[lab]} {g.get("title", lab)}</b>'
            f'<span style="color:{col};opacity:.8;font-size:.76rem">'
            f'해당 {g["n_hit"]} · 모르겠음 {g["n_unknown"]} / {len(g["items"])}</span>'
            + (f'<span style="margin-left:auto;background:{col};color:#fff;font-size:.7rem;'
               f'font-weight:700;padding:2px 8px;border-radius:{R_PILL}">여기서 확정</span>'
               if decided else '')
            + f'</div><div style="padding:6px 12px 8px;background:{SHEET}">{rows}</div></div>',
            unsafe_allow_html=True)


def render_trace_pending(task: dict, note: str = "AI가 원문을 읽는 중"):
    """아직 답이 오지 않은 판정 과정 — 기준 목록을 미리 세워둔다.

    답은 추출이 끝나야 한 번에 온다. 그때까지 패널을 비워두면 화면이 죽어 보이고,
    끝나자마자 다음 건으로 넘어가 한 번 깜빡이고 사라진다. 그래서 기준을 먼저 세우고
    답이 오면 그 자리에 채운다.
    """
    steps = [("1단계 · 노이즈인가?", "noise"), ("2단계 · 이슈인가?", "issue"),
             ("유효 근거", "valid"), ("판단이 안 서면 · 보류", "hold")]
    g = rules.by_label(task)
    for title, lab in steps:
        items = g.get(lab) or []
        if not items:
            continue
        col, bg, line = _TR_COLOR[lab], _TR_BG[lab], _TR_LINE[lab]
        rows = "".join(
            f'<div style="display:flex;gap:8px;align-items:baseline;padding:3px 0 3px 2px">'
            f'<span style="flex:0 0 52px;color:{LINE_STRONG};font-weight:700;'
            f'font-size:.75rem">대기</span>'
            f'<span style="color:{INK_MUTED};font-size:.83rem;line-height:1.6">'
            f'{" ".join(str(c.get("when") or "").split())[:150]}</span></div>'
            for c in items)
        st.html(
            f'<div style="border:1px solid {line};border-radius:{R_SM};overflow:hidden;'
            f'margin-bottom:9px;opacity:.62">'
            f'<div style="background:{bg};padding:7px 12px;display:flex;align-items:center;'
            f'gap:8px;border-bottom:1px solid {line}">'
            f'<b style="color:{col};font-size:.85rem;letter-spacing:-.01em">'
            f'{_TR_ICON[lab]} {title}</b>'
            f'<span style="color:{col};opacity:.75;font-size:.76rem">기준 {len(items)}개</span>'
            f'<span style="margin-left:auto;color:{INK_MUTED};font-size:.74rem">{note}</span>'
            f'</div><div style="padding:6px 12px 8px;background:{SHEET}">{rows}</div></div>')


def _now_card(i: int, total: int, rec: dict) -> str:
    """지금 처리 중인 특허 — 실행 화면의 시선 고정점."""
    return (
        f'<div style="display:flex;align-items:center;gap:14px;background:{BRAND};'
        f'border-radius:{R_MD};padding:14px 18px;margin-bottom:14px">'
        f'<div style="flex:0 0 auto;background:rgba(255,255,255,.14);color:#fff;'
        f'border-radius:{R_SM};padding:5px 11px;font-size:.8rem;font-weight:700;'
        f'letter-spacing:.02em">{i} / {total}</div>'
        f'<div style="min-width:0;flex:1">'
        f'<div style="color:#c5cdee;font-size:.74rem;font-weight:650;letter-spacing:.08em">'
        f'no {rec.get("no")} · {rec.get("country")}</div>'
        f'<div style="color:#fff;font-size:.95rem;font-weight:650;letter-spacing:-.015em;'
        f'overflow:hidden;text-overflow:ellipsis;white-space:nowrap">'
        f'{str(rec.get("title") or "")[:90]}</div></div></div>')


def _panel_head(icon: str, title: str, sub: str) -> str:
    return (f'<div style="display:flex;align-items:baseline;gap:8px;margin:0 0 8px 2px">'
            f'<span style="font-size:.9rem">{icon}</span>'
            f'<span style="color:{BRAND};font-weight:750;font-size:.9rem;'
            f'letter-spacing:-.01em">{title}</span>'
            f'<span style="color:{INK_MUTED};font-size:.76rem">{sub}</span></div>')


def _stage_html(stages: list[str]) -> str:
    if not stages:
        return ""
    rows = "".join(
        f'<div style="display:flex;gap:8px;align-items:baseline;padding:2px 0">'
        f'<span style="color:{BRAND_600};font-size:.7rem;flex:0 0 auto">●</span>'
        f'<span style="color:{INK_SUB};font-size:.8rem;line-height:1.6">{x}</span></div>'
        for x in stages[-4:])
    return (f'<div style="background:{BRAND_025};border:1px solid {BRAND_050};'
            f'border-radius:{R_SM};padding:10px 14px;margin-top:10px">{rows}</div>')


def _hz(text: str, state_key: str | None = None) -> str:
    """예전 실행 기록에 남은 기준 id 도 화면에서는 문장으로 보이게(하네스 2차)."""
    for k in ([f"{state_key}_task"] if state_key else []) + ["exp_task", "launch_task"]:
        t = st.session_state.get(k)
        if t:
            return C.humanize(text, t)
    return text


def _persist(state_key: str, run_dir, sheet: str, results: list, task: dict, meta: dict):
    """판정이 끝나면(또는 정지하면) 실행 폴더에 산출물을 남긴다. 내려받기와 별개다."""
    raw = st.session_state.get(f"{state_key}_raw")
    try:
        return {k: str(v) for k, v in run_output.save_outputs(
            run_dir, sheet, results, task,
            src=io.BytesIO(raw) if raw else None, meta=meta).items()}
    except Exception as e:
        return {"_error": repr(e)}


def _request_stop(state_key: str):
    """정지 버튼 콜백 — 플래그만 세운다. 실행 중인 스크립트는 리런으로 끊긴다."""
    st.session_state[f"{state_key}_stop"] = True


def _bar(done: int, total: int, elapsed: float, avg: float) -> str:
    pct = (done / total * 100) if total else 0
    left = (total - done) * avg
    return (
        f'<div style="background:{BRAND};border-radius:{R_MD};padding:18px 22px 16px;'
        f'margin-bottom:14px">'
        f'<div style="display:flex;align-items:baseline;gap:14px;margin-bottom:13px">'
        f'<span style="color:#fff;font-size:1.7rem;font-weight:800;letter-spacing:-.04em;'
        f'font-variant-numeric:tabular-nums">{done}<span style="color:#98A2DC;'
        f'font-size:1.05rem;font-weight:600"> / {total}건</span></span>'
        f'<span style="color:#C5CDEE;font-size:.84rem">경과 {elapsed:.0f}초</span>'
        f'<span style="color:#98A2DC;font-size:.84rem">평균 {avg:.0f}초/건</span>'
        + (f'<span style="margin-left:auto;color:#C5CDEE;font-size:.84rem">'
           f'남은 시간 약 {left/60:.0f}분</span>' if done and total > done else
           '<span style="margin-left:auto"></span>')
        + '</div>'
        f'<div style="height:7px;border-radius:{R_PILL};background:rgba(255,255,255,.16);'
        f'overflow:hidden"><div style="height:100%;width:{pct:.1f}%;border-radius:{R_PILL};'
        f'background:linear-gradient(90deg,#8E9BE0,#fff)"></div></div></div>')


def _hist_row(r: dict) -> str:
    lab = r.get("label") or "hold"
    col, bg, line = _TR_COLOR.get(lab, INK_MUTED), _TR_BG.get(lab, BRAND_025), _TR_LINE.get(lab, LINE)
    return (
        f'<span style="background:{bg};color:{col};border:1px solid {line};font-weight:750;'
        f'padding:2px 10px;border-radius:{R_PILL};font-size:.76rem">'
        f'{_TR_ICON.get(lab,"")} {label_ko(lab)}</span>')


def run_console(state_key: str):
    """실행 전용 전체 화면 — 큼직하게 보고, 언제든 정지하고, 지난 건도 다시 본다."""
    # ── 정지 요청이 들어온 상태로 다시 들어왔다 → 부분 결과를 확정하고 나간다
    if st.session_state.pop(f"{state_key}_stop", None):
        part = st.session_state.get(f"{state_key}_partial") or []
        st.session_state[f"{state_key}_results"] = part
        st.session_state[f"{state_key}_meta"] = {
            **(st.session_state.get(f"{state_key}_meta") or {}),
            "elapsed": st.session_state.get(f"{state_key}_elapsed", 0.0),
            "usage": agent.usage_report(),
            "stopped": True,
            "sheet": st.session_state.get(f"{state_key}_sheet_run", ""),
        }
        rd = (st.session_state.get(f"{state_key}_meta") or {}).get("run_dir")
        if rd and part:
            st.session_state[f"{state_key}_saved"] = _persist(
                state_key, rd, st.session_state.get(f"{state_key}_sheet_run", ""),
                part, st.session_state.get(f"{state_key}_task") or {},
                st.session_state[f"{state_key}_meta"])
        st.session_state[f"{state_key}_running"] = False
        st.session_state[f"{state_key}_stopped_n"] = len(part)
        st.rerun()

    task = st.session_state.get(f"{state_key}_task") or {}
    wb = st.session_state.get(state_key) or {}
    sheet = st.session_state.get(f"{state_key}_sheet_run") or ""
    records = (wb.get(sheet) or {}).get("records") or []
    n_target = int(st.session_state.get(f"{state_key}_target") or 0)
    total = min(n_target, len(records))
    st.session_state[f"{state_key}_partial"] = []

    # ── 머리 : 무엇을 돌리는지 + 정지
    h1, h2 = st.columns([4, 1])
    with h1:
        st.html(f'<div style="padding-bottom:2px">'
                f'<div style="color:{BRAND_400};font-size:.75rem;font-weight:650;'
                f'letter-spacing:.05em;margin-bottom:4px">판정 실행 중</div>'
                f'<div style="color:{BRAND};font-size:1.55rem;font-weight:800;'
                f'letter-spacing:-.032em">{sheet} · {total}건</div></div>')
    with h2:
        st.write("")
        st.button("⏹ 정지", use_container_width=True, key=f"{state_key}_stopbtn",
                  on_click=_request_stop, args=(state_key,),
                  help="지금까지 판정한 건은 그대로 남습니다")

    bar_ph = st.empty()
    bar_ph.html(_bar(0, total, 0.0, 0.0))
    cur_ph = st.empty()

    col_l, col_r = st.columns([3, 2], gap="medium")
    with col_l:
        st.html(_panel_head("🧠", "AI 판단 과정", "원문을 읽으며 실시간으로"))
        stream_ph = st.empty()
    with col_r:
        st.html(_panel_head("⚖️", "판정 과정", "기준별 해당 여부 → 등급 확정"))
        rules_ph = st.empty()
        with rules_ph.container():
            render_trace_pending(task, "판정 시작 대기")
    stage_ph = st.empty()

    st.html('<hr style="border:none;border-top:1px solid ' + LINE + ';margin:22px 0 14px">')
    hist_head = st.empty()
    hist_ph = st.empty()

    done_res, t0 = [], time.time()
    stt = {"i": 0, "buf": "", "stages": [], "judged": False}

    def on_event(i, rec, kind, payload):
        if kind == "run_dir":
            st.session_state[f"{state_key}_meta"] = {
                **(st.session_state.get(f"{state_key}_meta") or {}), "run_dir": str(payload)}
            return
        if i != stt["i"]:
            stt.update(i=i, buf="", stages=[], judged=False)
            stream_ph.empty(); stage_ph.empty()
            cur_ph.html(_now_card(i, total, rec))
            with rules_ph.container():                 # 비우지 않고 기준을 미리 세운다
                render_trace_pending(task)
        if kind in ("stage", "tool"):
            stt["stages"].append(str(payload))
            stage_ph.html(_stage_html(stt["stages"]))
        elif kind == "extract_start":
            stt["stages"].append("추출 시작 — 추론 중")
            stage_ph.html(_stage_html(stt["stages"]))
            stream_ph.html('<div class="ax-think big"><div class="ln dim">'
                           '원문을 읽는 중… 첫 문장까지 10~30초</div></div>')
        elif kind == "delta":
            stt["buf"] += str(payload)
            stream_ph.html(_think_html(stt["buf"]).replace('class="ax-think"',
                                                           'class="ax-think big"'))
        elif kind == "narration" and payload:
            stream_ph.html(_think_html(f"<<<THINKING{payload}THINKING>>>", done=True)
                           .replace('class="ax-think"', 'class="ax-think big"'))
        elif kind == "usage":
            stt["stages"].append(f"입력 {payload.get('in',0):,} · 출력 {payload.get('out',0):,} 토큰")
            stage_ph.html(_stage_html(stt["stages"]))
        elif kind == "criteria":
            stt["judged"] = True
            with rules_ph.container():
                render_trace(payload)
            # 판정 결과를 읽을 틈을 준다 — 없으면 채워지자마자 다음 건이 덮어쓴다
            if config.TRACE_HOLD_SEC > 0:
                stage_ph.html(_stage_html(stt["stages"] +
                                          [f"판정 확정 — 결과를 {config.TRACE_HOLD_SEC:.0f}초간 표시"]))
                time.sleep(config.TRACE_HOLD_SEC)

    def on_progress(i, total_n, r):
        done_res.append(r)
        st.session_state[f"{state_key}_partial"] = list(done_res)
        el = time.time() - t0
        st.session_state[f"{state_key}_elapsed"] = el
        bar_ph.html(_bar(i, total_n, el, el / max(i, 1)))
        hist_head.html(
            f'<div style="display:flex;align-items:baseline;gap:10px;margin-bottom:9px">'
            f'<span style="color:{BRAND};font-weight:750;font-size:.95rem;'
            f'letter-spacing:-.015em">판정 완료</span>'
            f'<span style="color:{INK_MUTED};font-size:.8rem">'
            f'{len(done_res)}건 · 최근 것이 위에 · 펼치면 판단 과정을 다시 볼 수 있습니다</span></div>')
        with hist_ph.container():
            for k, rr in enumerate(reversed(done_res)):
                _hist_item(rr, len(done_res) - k)

    try:
        results, run_dir = pipeline.run(sheet, task, records=records, limit=n_target,
                                        quiet=True, progress=on_progress, on_event=on_event)
    except rules.RuleError as e:
        st.session_state[f"{state_key}_running"] = False
        st.error(f"기준 오류로 실행하지 못했습니다:\n\n{e}")
        if st.button("돌아가기", type="primary", key=f"{state_key}_ruleback"):
            st.rerun()
        return

    meta = {"elapsed": time.time() - t0, "usage": agent.usage_report(),
            "run_dir": str(run_dir), "sheet": sheet, "model": config.MODEL_JUDGE}
    st.session_state[f"{state_key}_results"] = results
    st.session_state[f"{state_key}_meta"] = meta
    st.session_state[f"{state_key}_saved"] = _persist(state_key, run_dir, sheet, results,
                                                      task, meta)
    st.session_state[f"{state_key}_running"] = False
    st.rerun()


def _hist_item(r: dict, idx: int):
    """완료된 한 건 — 접힌 채로 쌓이고, 펼치면 판단 과정·판정 과정·청구항을 본다."""
    lab = label_ko(r.get("label"))
    head = (f"{_TR_ICON.get(r.get('label'),'')} {lab}  ·  no {r.get('no')} "
            f"[{r.get('country')}]  ·  {str(r.get('title') or '')[:52]}")
    with st.expander(head, expanded=False):
        st.html(
            f'<div style="display:flex;gap:9px;align-items:center;flex-wrap:wrap;'
            f'margin-bottom:10px">{_hist_row(r)}'
            f'<span style="color:{INK_MUTED};font-size:.79rem">신뢰도 '
            f'{r.get("confidence","")}</span>'
            f'<span style="color:{LINE_STRONG}">·</span>'
            f'<span style="color:{INK_MUTED};font-size:.79rem">{r.get("evidence","")}</span>'
            f'<span style="color:{LINE_STRONG}">·</span>'
            f'<span style="color:{INK_SUB};font-size:.79rem">해당 기준 '
            f'<b style="color:{BRAND}">{crit_text(r, 60)}</b></span></div>')
        if r.get("reason"):
            st.html(f'<div style="background:{BRAND_025};border:1px solid {BRAND_050};'
                    f'border-radius:{R_SM};padding:11px 13px;color:{INK};font-size:.87rem;'
                    f'line-height:1.65;margin-bottom:10px">{r["reason"]}</div>')
        t1, t2 = st.columns([3, 2], gap="medium")
        with t1:
            st.html(_panel_head("🧠", "AI 판단 과정", ""))
            if r.get("narration"):
                st.html(_think_html(
                f"<<<THINKING{_hz(r['narration'])}THINKING>>>", done=True))
            else:
                st.caption("_(판단 서술이 없습니다)_")
        with t2:
            st.html(_panel_head("⚖️", "판정 과정", ""))
            render_trace(r.get("criteria_trace") or [])
        ic = r.get("independent_claims") or []
        if ic:
            with st.expander(f"근거 청구항 {len(ic)}건", expanded=False):
                for c in ic:
                    st.code(f"[청구항 {c.get('no','')}] {c.get('text','')}", language=None)


# ---------------- 결과 ----------------
def _style(df: pd.DataFrame):
    """등급 색 · 폴백 강조를 입힌 Styler.

    ⚠️ 반드시 **표시할 열(view)의 개수와 같은 길이**를 돌려줘야 한다.
    `_label` 은 색을 고르는 데만 쓰고 표에서는 뺀다 — 예전엔 `_label` 포함 행을
    넘겨서 길이가 1 많았고 pandas가 shape 불일치로 죽었다.
    """
    view = df.drop(columns=["_label"], errors="ignore")
    labels = df["_label"] if "_label" in df.columns else None
    cols = list(view.columns)
    i_label = cols.index("AI판정") if "AI판정" in cols else None
    i_ev = cols.index("근거등급") if "근거등급" in cols else None

    def _row(r):
        base = [""] * len(cols)
        lab = labels.get(r.name) if labels is not None else None
        color = LABEL_KO.get(lab, ("", "#5F6368"))[1]
        if i_label is not None:
            base[i_label] = f"background-color:{color}22;color:{color};font-weight:600"
        if i_ev is not None and str(r.get("근거등급", "")).startswith("⚠️"):
            base[i_ev] = "background-color:#FEF7E0;color:#B06000"
        return base

    return view.style.apply(_row, axis=1)


def _result_card(r: dict, key: str):
    """이슈·보류 한 건을 카드로. 등급 색을 왼쪽 띠로 두고, 근거 → 청구항 → 과정 순으로 읽힌다."""
    col = _TR_COLOR.get(key, INK_MUTED)
    bg = _TR_BG.get(key, BRAND_025)
    line = _TR_LINE.get(key, LINE)
    conf = r.get("confidence") or ""
    fallback = not str(r.get("evidence", "")).startswith("원문")

    st.markdown(
        f'<div style="border:1px solid {line};border-left:4px solid {col};'
        f'border-radius:{R_MD};background:{SHEET};box-shadow:{SHADOW_1};'
        f'padding:16px 18px 14px;margin-bottom:2px">'
        # 머리 — 등급 배지 · 번호 · 국가 · 신뢰도 · 근거등급
        f'<div style="display:flex;gap:9px;align-items:center;flex-wrap:wrap;margin-bottom:9px">'
        f'<span style="background:{bg};color:{col};border:1px solid {line};font-weight:750;'
        f'padding:3px 11px;border-radius:{R_PILL};font-size:.79rem;letter-spacing:-.005em">'
        f'{_TR_ICON.get(key,"")} {label_ko(key)}</span>'
        f'<span style="color:{BRAND};font-weight:750;font-size:.9rem">no {r.get("no")}</span>'
        f'<span style="color:{INK_MUTED};font-size:.8rem">{r.get("country")}</span>'
        f'<span style="color:{LINE_STRONG}">·</span>'
        f'<span style="color:{INK_MUTED};font-size:.8rem">신뢰도 {conf}</span>'
        + (f'<span style="background:{_TR_BG["hold"]};color:{_TR_COLOR["hold"]};'
           f'font-size:.75rem;font-weight:650;padding:2px 9px;border-radius:{R_PILL}">'
           f'{r.get("evidence","")}</span>' if fallback else '')
        + '</div>'
        # 제목
        f'<div style="font-weight:700;color:{INK};font-size:.98rem;line-height:1.5;'
        f'letter-spacing:-.015em">{str(r.get("title") or "")[:120]}</div>'
        + (f'<div style="color:{INK_MUTED};font-size:.83rem;line-height:1.7;margin-top:6px">'
           f'{r.get("tech_summary")}</div>' if r.get("tech_summary") else '')
        # 판정 근거
        + f'<div style="background:{bg};border-radius:{R_SM};padding:11px 13px;margin-top:12px">'
          f'<div style="color:{col};font-size:.72rem;font-weight:700;letter-spacing:.07em;'
          f'margin-bottom:3px">해당한 기준</div>'
          f'<div style="color:{INK};font-size:.88rem;line-height:1.65">{r.get("reason","")}</div>'
        + (f'<div style="color:{INK_SUB};font-size:.82rem;line-height:1.6;margin-top:7px;'
           f'padding-top:7px;border-top:1px solid {line}">'
           f'<b style="color:{col}">확인 필요</b> · {r["review_note"]}</div>'
           if r.get("review_note") else '')
        + '</div></div>', unsafe_allow_html=True)

    ic = r.get("independent_claims") or []
    c1, c2, c3 = st.columns(3, gap="small")
    if r.get("narration"):
        with c1.expander("AI 판단 과정", expanded=False):
            st.markdown(_think_html(
                f"<<<THINKING{_hz(r['narration'])}THINKING>>>", done=True),
                unsafe_allow_html=True)
    if ic:
        with c2.expander(f"근거 청구항 {len(ic)}", expanded=False):
            for c in ic:
                st.code(f"[청구항 {c.get('no','')}] {c.get('text','')}", language=None)
    if r.get("criteria_trace"):
        with c3.expander("판정 과정", expanded=False):
            render_trace(r["criteria_trace"])
    st.write("")


def render_results(state_key: str, show_reference: bool = False):
    res = st.session_state.get(f"{state_key}_results")
    if not res:
        return
    meta = st.session_state.get(f"{state_key}_meta", {})
    df = pd.DataFrame([_flatten(r) for r in res])
    st.divider()
    st.markdown(f'<div style="color:{BRAND};font-weight:700;font-size:1.15rem;">판정 결과</div>',
                unsafe_allow_html=True)

    n = len(df)
    n_src = int(df["근거등급"].str.startswith("📄").sum())
    m = st.columns(6)
    m[0].metric("처리", n)
    m[1].metric("노이즈", int((df["_label"] == "noise").sum()))
    m[2].metric("유효", int((df["_label"] == "valid").sum()))
    m[3].metric("이슈", int((df["_label"] == "issue").sum()))
    m[4].metric("보류", int((df["_label"] == "hold").sum()))
    m[5].metric("원문 근거", f"{n_src}/{n}", f"{100*n_src/max(n,1):.0f}%",
                help="원문 청구항으로 판정한 비율. 낮으면 그만큼 근거가 약합니다.")

    holds = df[df["_label"] == "hold"]["보류사유"].value_counts()
    if len(holds):
        st.info("**보류 사유** — " + " · ".join(f"{k} ({v}건)" for k, v in holds.items()))
    low = int((df["신뢰도"] == CONF_ICON["낮음"]).sum())
    if low:
        st.warning(f"신뢰도 **낮음 {low}건** — 근거가 약해 판정을 신뢰하기 어렵습니다.")

    usage = meta.get("usage", {})
    if config.USE_SUBSCRIPTION:
        calls = sum(u.get("calls", 0) for u in usage.get("per_model", {}).values())
        tin = sum(u.get("in", 0) for u in usage.get("per_model", {}).values())
        st.caption(f"⏱ {meta.get('elapsed',0):.0f}초 · LLM 호출 {calls}회 · 입력 {tin:,}토큰 · 구독 사용량")
    else:
        st.caption(f"⏱ {meta.get('elapsed',0):.0f}초 · 실측 비용 **${usage.get('total_usd',0)}**")
    if usage.get("parse_fails"):
        st.error(f"추출 JSON 파싱 실패 {usage['parse_fails']}건 → 보류로 처리됨")
    if meta.get("run_dir"):
        st.caption(f"💾 `{meta['run_dir']}/records.jsonl` (중단 시 이어서 실행 가능)")

    if show_reference and (df["사람라벨(참고)"] != "—").any():
        gv = df[df["사람라벨(참고)"].str.contains("유효", na=False)]
        st.caption(f"(참고) 사람 유효라벨 {len(gv)}건 중 AI가 노이즈로 보지 않은 것 "
                   f"{int((gv['_label'] != 'noise').sum())}건 — 라벨 정확도가 검증되지 않아 "
                   f"성능 지표로 쓰지 않습니다.")

    # ---- 다운로드는 결과 바로 아래(찾기 쉬운 위치) ----
    _downloads(state_key, res, df)

    st.markdown(f'<div style="color:{BRAND};font-weight:700;font-size:1.02rem;'
                'border-bottom:2px solid #E7EAF6;padding-bottom:6px;margin:20px 0 12px;">'
                '등급별 결과</div>', unsafe_allow_html=True)
    st.caption("확인이 필요한 **이슈·보류는 카드로**, 훑어보는 유효·노이즈는 표로 접어 뒀습니다.")

    by_label = {}
    for r in res:
        by_label.setdefault(r.get("label"), []).append(r)

    for key, title, note in (("issue", "🔴 이슈", "독립청구항이 자사 기술과 중첩될 가능성"),
                             ("hold", "🟠 보류", "판정 불가 — 사람 확인 필요")):
        items = by_label.get(key) or []
        if not items:
            continue
        with st.expander(f"{title} · {len(items)}건 — {note}", expanded=True):
            for r in items:
                _result_card(r, key)

    for key, title in (("valid", "🟢 유효"), ("noise", "🔘 노이즈")):
        sub = df[df["_label"] == key]
        if not len(sub):
            continue
        with st.expander(f"{title} · {len(sub)}건", expanded=False):
            st.dataframe(_style(sub), hide_index=True, use_container_width=True,
                         column_config={"판정근거": st.column_config.TextColumn(width="large"),
                                        "근거청구항": st.column_config.TextColumn(width="large")})

    with st.expander(f"전체 {n}건", expanded=False):
        st.dataframe(_style(df), hide_index=True, use_container_width=True,
                     column_config={"판정근거": st.column_config.TextColumn(width="large"),
                                    "근거청구항": st.column_config.TextColumn(width="large")})

    with st.expander("건별 상세", expanded=False):
        _rank = {"issue": 0, "hold": 1, "valid": 2, "noise": 3}
        for r in sorted(res, key=lambda x: _rank.get(x.get("label"), 9)):
            st.markdown(f"**no={r.get('no')} [{r.get('country')}] · {label_ko(r.get('label'))}** "
                        f"· {CONF_ICON.get(r.get('confidence'),'')} · 기준 {crit_text(r, 70)}")
            if r.get("tech_summary"):
                st.caption(r["tech_summary"])
            st.write(f"**판정근거:** {r.get('reason','')}")
            if r.get("review_note"):
                st.write(f"**확인 필요:** {r['review_note']}")
            c1, c2 = st.columns(2)
            ans = r.get("answers") or {}
            c1.write(f"**기준 답변** (해당 {r.get('n_matched',0)} · 모르겠음 {r.get('n_unknown',0)})")
            c1.json({k: v for k, v in ans.items() if v != "X"} or {"(전부 비해당)": ""}, expanded=False)
            c2.write("**수집 항목**")
            c2.json({**(r.get("properties") or {}), **(r.get("info") or {}),
                     **(r.get("collect") or {})} or {"(없음)": ""}, expanded=False)
            if r.get("narration"):
                st.markdown("**🧠 AI 판단 과정**")
                st.markdown(_think_html(f"<<<THINKING{r['narration']}THINKING>>>", done=True),
                            unsafe_allow_html=True)
            for c in (r.get("independent_claims") or []):
                st.code(f"[청구항 {c.get('no','')}] {c.get('text','')}", language=None)
            if r.get("criteria_trace"):
                st.markdown("**⚖️ 이 등급이 나온 과정**")
                render_trace(r["criteria_trace"])
            st.divider()


def _downloads(state_key: str, res: list[dict], df: pd.DataFrame):
    task = st.session_state.get(f"{state_key}_task") or {}
    meta = st.session_state.get(f"{state_key}_meta", {})
    raw = st.session_state.get(f"{state_key}_raw")
    sheet = meta.get("sheet") or ""

    # 실행 폴더에 이미 저장돼 있음을 알린다 (내려받기는 사본을 하나 더 만드는 것)
    saved = st.session_state.get(f"{state_key}_saved") or {}
    rd = meta.get("run_dir")
    if rd:
        names = [k for k in saved if not k.startswith("_")]
        st.html(
            f'<div style="background:{BRAND_025};border:1px solid {BRAND_050};'
            f'border-left:3px solid {BRAND_400};border-radius:{R_SM};padding:12px 15px;'
            f'margin-bottom:12px">'
            f'<div style="color:{BRAND};font-weight:700;font-size:.86rem;margin-bottom:4px">'
            f'실행 폴더에 저장됐습니다</div>'
            f'<div style="color:{INK_SUB};font-size:.82rem;line-height:1.7">'
            f'<code>{rd}</code><br>'
            + (" · ".join(names) if names else "records.jsonl · meta.json")
            + '</div></div>')

    c = st.columns(3)
    if raw and sheet and task:
        try:
            xls = excel_export.annotate_workbook(io.BytesIO(raw), sheet, res, task)
            n_col = len(excel_export.main_columns(task))
            c[0].download_button(
                "⬇️ 엑셀 (원본 + 판정열)", xls,
                file_name=f"판정결과_{sheet}.xlsx",
                mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
                use_container_width=True, type="primary",
                help=f"{sheet} 시트 오른쪽에 {n_col}열 추가(판정 12 + 수집 "
                     f"{len(C.collect_names(task))}) + '{sheet}_AI상세' 시트")
        except Exception as e:
            c[0].error(f"엑셀 생성 실패: {e}")

    try:
        md = run_output.narration_md(res, task, sheet, meta)
        c[1].download_button(
            "⬇️ AI 판단 과정 (.md)", md.encode("utf-8"),
            file_name=f"AI판단과정_{sheet or state_key}.md", mime="text/markdown",
            use_container_width=True,
            help="건별 판단 서술 · 기준 판정 과정 · 근거 청구항 · 수집 항목")
    except Exception as e:
        c[1].error(f"판단 과정 생성 실패: {e}")

    try:
        c[2].download_button(
            "⬇️ 판정표 (.csv)", run_output.results_csv(res, task),
            file_name=f"판정표_{sheet or state_key}.csv", mime="text/csv",
            use_container_width=True)
    except Exception:
        c[2].download_button("⬇️ CSV (판정표만)",
                             df.drop(columns=["_label"]).to_csv(index=False).encode("utf-8-sig"),
                             file_name=f"판정결과_{state_key}.csv", mime="text/csv",
                             use_container_width=True)
