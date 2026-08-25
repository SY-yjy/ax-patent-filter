"""과제(판정기준) 관리 화면 — 코딩 없이 기준을 만들고 고친다.

이 시스템은 특정 과제를 모른다. 새 사용자는 빈 템플릿에서 시작한다.

★ 판정 기준은 **하나의 순서 목록**이다. 각 줄이 곧 판정 기준이고,
  AI는 각 줄에 해당/비해당/모르겠음만 답한다. **위에서부터 첫 '해당'이 등급을 정한다.**
  → 순서가 곧 우선순위. 화면은 등급별로 묶어 보여주되 전체 순서를 함께 노출한다.
"""
import copy
import yaml
import pandas as pd
import streamlit as st

import criteria as C
import rules as R

from theme import (BRAND, BRAND_600, BRAND_100, BRAND_050, BRAND_025,
                   LINE, LINE_STRONG, INK, INK_SUB, INK_MUTED,
                   R_SM, R_MD, R_PILL, SHADOW_1,
                   LABEL_COLOR as _LAB_COLOR, LABEL_BG as _LAB_BG,
                   LABEL_LINE as _LAB_LINE)
LABELS = list(R.LABELS)
LABEL_KO = R.LABEL_KO
LABEL_ICON = {"noise": "🔘", "valid": "🟢", "issue": "🔴", "hold": "🟠"}


def _lines(s) -> list[str]:
    return [x.strip() for x in (s or "").splitlines() if x.strip()]


def _txt(items) -> str:
    return "\n".join(str(x) for x in (items or []))


# ---------------------------------------------------------------- 섹션
def _sec_basic(t: dict):
    """과제 이름 + 검토 대상 정의만.

    자사 기술 목록 칸은 없앴다 — 자사 소재·조성은 이슈 기준 문장에 직접 쓴다.
    같은 내용을 두 군데 적으면 어긋나고, 어긋나도 아무도 모른다.
    """
    st.caption("판정은 ② 판정 기준으로만 이뤄집니다. 이 탭은 AI가 원문을 읽을 때의 배경입니다.")

    t["task"] = st.text_input("과제 이름 — 한 줄로", value=t.get("task", ""),
                              placeholder="예: OLED 봉지재 — 수분투습 차단 접착제")
    sc = t.setdefault("scope", {})
    for k in ("target_signals", "target_elements", "mechanisms", "include_even_if_vague"):
        sc.pop(k, None)
    t.pop("sample_data", None)
    t.pop("own_composition", None)          # 옛 구조 정리(구조화 필드 → 메모 한 칸)
    sc["definition"] = st.text_area(
        "검토 대상 기술의 정의", height=120, value=sc.get("definition", ""),
        placeholder="이 과제가 무엇을 찾는지 한두 문장으로. AI가 가장 먼저 읽는 문장입니다.",
        help="목록이 아니라 문장으로. 구체적인 판정 조건은 ② 판정 기준에 씁니다.")

    st.divider()
    st.markdown(
        f'<div style="display:flex;align-items:center;gap:8px;margin-bottom:2px">'
        f'<span style="color:{BRAND};font-weight:700">자사 기술</span>'
        f'<span style="background:{BRAND_050};color:{BRAND};font-size:.72rem;font-weight:700;'
        f'padding:2px 9px;border-radius:20px">참고용</span></div>'
        f'<div style="color:{INK_MUTED};font-size:.85rem;margin-bottom:12px">'
        f'판정에는 쓰이지 않습니다 — 기준을 쓸 때 참고하는 정보입니다.</div>',
        unsafe_allow_html=True)

    # 옛 구조(own_composition / own_tech_note) → own_tech 로 이관
    ot = t.get("own_tech")
    if not isinstance(ot, dict):
        legacy = t.pop("own_composition", None) or {}
        ot = {"materials": list(legacy.get("key_materials") or []),
              "application": legacy.get("application", ""),
              "ranges": legacy.get("composition_ranges", "")}
        t.pop("own_tech_note", None)
    t["own_tech"] = ot

    c1, c2 = st.columns([1, 1])
    ot["materials"] = _lines(c1.text_area(
        "핵심 소재 (한 줄에 하나)", height=118, value=_txt(ot.get("materials")),
        placeholder="폴리우레탄\n폴리올 + 이소시아네이트\n아크릴\n이온성 액체"))
    ot["application"] = c2.text_input("적용 제품·용도", value=ot.get("application", ""),
                                      placeholder="예: EV 배터리 접합")
    ot["ranges"] = c2.text_area("조성·구조 범위", height=68, value=ot.get("ranges", ""),
                                placeholder="예: 이온성 액체 3~10 wt%")


_ID_PREFIX = {"hold": "h", "issue": "i", "noise": "n", "valid": "v"}

# 판정 흐름 — 화면에 이 흐름으로만 보여준다. 기준 하나하나에는 번호가 없다.
_STEPS = [("noise", "1단계", "노이즈인가?", "해당하면 버립니다."),
          ("valid", "1단계 통과", "유효", "노이즈가 아니면 유효입니다. 그 근거를 적습니다."),
          ("issue", "2단계", "이슈인가?", "유효 중에서 권리 중첩 가능성을 봅니다."),
          ("hold", "언제든", "보류", "판단이 안 서면. 어느 단계에서든 발생합니다.")]


def _sec_criteria(t: dict):
    """판정 흐름대로 3칸. 기준에 번호·사유코드·확인사항을 두지 않는다.

    유효 기준은 두지 않는다 — 노이즈가 아니고 이슈도 아니면 자동으로 유효다.
    """
    items = t.setdefault("criteria", [])

    st.markdown(
        f'<div style="background:{BRAND};border-radius:12px;padding:20px 22px;margin-bottom:16px">'
        f'<div style="color:#fff;font-weight:750;font-size:1.05rem;margin-bottom:10px">'
        f'판정 흐름</div>'
        f'<div style="color:#c2cbef;font-size:.92rem;line-height:1.9">'
        f'<b style="color:#fff">1단계</b> 노이즈인가? &nbsp;→&nbsp; 해당하면 버림, 아니면 '
        f'<b style="color:#fff">유효</b><br>'
        f'<b style="color:#fff">2단계</b> 유효 중에 이슈인가? &nbsp;→&nbsp; 해당하면 '
        f'<b style="color:#fff">이슈</b>, 아니면 <b style="color:#fff">유효</b><br>'
        f'<b style="color:#fff">언제든</b> 판단이 안 서면 &nbsp;→&nbsp; '
        f'<b style="color:#fff">보류</b></div>'
        f'<div style="color:#8f9bd4;font-size:.82rem;margin-top:10px;line-height:1.6">'
        f'AI는 각 문장에 해당·비해당·모르겠음만 답합니다. 등급은 정하지 않습니다.</div></div>',
        unsafe_allow_html=True)

    edit = st.toggle("✏️ 편집", value=False, key="crit_edit",
                     help="칸마다 한 줄에 기준 하나씩 적습니다")

    for row in (_STEPS[:2], _STEPS[2:]):
        cols = st.columns(len(row), gap="medium")
        for col, (lab, step, title, desc) in zip(cols, row):
            with col:
                _step_box(t, items, lab, step, title, desc, edit)
        st.write("")

    if not items:
        st.info("기준이 없습니다. **✏️ 편집**을 켜고 각 칸에 한 줄씩 적으세요.")
    st.caption("어느 기준에도 해당하지 않으면 **보류**로 갑니다 — 판단이 서지 않은 것이므로 "
               "연구원이 확인합니다.")


def _step_box(t, items, lab, step, title, desc, edit):
    mine = [c for c in items if c.get("label") == lab]
    editable = mine
    col = _LAB_COLOR[lab]

    st.markdown(
        f'<div style="background:{_LAB_BG[lab]};border:1px solid {col}33;'
        f'border-radius:12px 12px 0 0;padding:12px 16px;border-bottom:none">'
        f'<div style="color:{INK_MUTED};font-size:.72rem;font-weight:700;'
        f'letter-spacing:.08em">{step}</div>'
        f'<div style="color:{col};font-weight:800;font-size:1.02rem;margin-top:1px">'
        f'{LABEL_ICON[lab]} {title}'
        f'<span style="font-weight:700;margin-left:8px">{len(mine)}</span></div>'
        f'<div style="color:{INK_MUTED};font-size:.78rem;margin-top:3px;line-height:1.5">'
        f'{desc}</div></div>', unsafe_allow_html=True)

    with st.container(border=True):
        if edit:
            txt = st.text_area(
                f"{LABEL_KO[lab]} 기준", height=200, key=f"ta_{lab}",
                value="\n".join(" ".join(str(c.get("when", "")).split()) for c in editable),
                label_visibility="collapsed",
                placeholder=f"한 줄에 기준 하나씩.\n{LABEL_KO[lab]}로 판정할 조건을 적습니다.")
            _apply_lines(t, items, lab, txt)
            st.caption("한 줄 = 기준 하나")
        else:
            if not editable:
                st.caption("_(기준 없음)_")
            for c in editable:
                st.markdown(
                    f"<div style='display:flex;gap:8px;margin:0 0 10px 0;font-size:.89rem;"
                    f"line-height:1.6'><span style='color:{col};font-weight:700'>·</span>"
                    f"<span style='color:#20264a'>"
                    f"{' '.join(str(c.get('when','')).split())}</span></div>",
                    unsafe_allow_html=True)


def _apply_lines(t: dict, items: list, lab: str, txt: str):
    """텍스트박스 내용 → 그 등급의 기준 목록으로 반영. id 는 자동 부여."""
    lines = _lines(txt)
    keep = [c for c in items if c.get("label") != lab]
    new = [{"id": f"c_{_ID_PREFIX[lab]}{i}", "label": lab, "when": line}
           for i, line in enumerate(lines, 1)]
    merged = keep + new
    rank = {"noise": 0, "valid": 1, "issue": 2, "hold": 3}
    merged.sort(key=lambda c: rank.get(c.get("label"), 9))
    items[:] = merged


def _collect_items(t: dict) -> list[str]:
    """수집 항목 목록. 옛 구조(fields + properties)도 읽어 합친다."""
    e = t.setdefault("extract", {})
    items = list(e.get("collect") or [])
    if not items:
        items = list((e.get("fields") or {}).keys()) + list(e.get("properties") or [])
    e.pop("fields", None)
    e.pop("properties", None)
    e["collect"] = items
    return items


@st.dialog("수집 항목 편집", width="large")
def _collect_dialog(t: dict):
    """편집은 별도 창. 항목은 태그로 넣는다(타이핑 → 추가, 태그의 ✕ → 삭제)."""
    items = _collect_items(t)
    st.caption("입력창에 타이핑하면 항목이 추가됩니다. 태그의 ✕ 로 지웁니다.")
    picked = st.multiselect(
        "수집 항목", options=items, default=items, key="collect_tags",
        label_visibility="collapsed", accept_new_options=True,
        placeholder="예: 유리전이온도")
    t["extract"]["collect"] = list(picked)
    st.caption(f"{len(picked)}개")
    if st.button("닫기", type="primary", use_container_width=True):
        st.rerun()


def _sec_info(t: dict):
    """추가 수집 정보 — 첫 화면은 읽기 전용 칩 목록, 편집은 별도 창."""
    items = _collect_items(t)

    top = st.columns([4, 1])
    top[0].markdown(
        f'<div style="font-size:.92rem;color:#3d4463;line-height:1.7">'
        f'판정과 <b>별개로</b> 원문에서 함께 뽑아두는 정보입니다.</div>',
        unsafe_allow_html=True)
    if top[1].button("편집", use_container_width=True, key="collect_edit"):
        _collect_dialog(t)

    st.write("")
    if not items:
        st.info("수집 항목이 없습니다. **편집**에서 추가하세요.")
        return

    st.markdown(f'<div style="color:{INK_MUTED};font-size:.78rem;margin-bottom:10px">'
                f'수집 항목 <b style="color:{BRAND}">{len(items)}</b>개</div>',
                unsafe_allow_html=True)
    chips = "".join(
        f'<span style="display:inline-block;background:{BRAND_025};color:#2b3157;'
        f'border:1px solid {BRAND_050};border-radius:14px;padding:5px 13px;'
        f'font-size:.85rem;margin:0 7px 7px 0;white-space:nowrap">{x}</span>'
        for x in items)
    st.markdown(
        f'<div style="border:1px solid {LINE};border-radius:10px;padding:14px 15px 8px;'
        f'background:#fff">{chips}</div>', unsafe_allow_html=True)


@st.dialog("동의어 편집", width="large")
def _syn_dialog(t: dict):
    """편집은 별도 창. 표기는 태그로 넣는다(타이핑 → 추가, 태그의 ✕ → 삭제)."""
    rows = list(t.get("synonyms") or [])
    st.caption("키워드마다 같은 뜻으로 쓰이는 표현을 등록합니다. 입력창에 타이핑하면 추가됩니다.")

    for i, r in enumerate(rows):
        with st.container(border=True):
            h = st.columns([5, 0.6], gap="small")
            r["keyword"] = h[0].text_input(
                "키워드", value=r.get("keyword", ""), key=f"dk_{i}",
                label_visibility="collapsed", placeholder="키워드")
            if h[1].button("✕", key=f"dx_{i}", use_container_width=True, help="키워드 삭제"):
                rows.pop(i)
                t["synonyms"] = rows
                st.rerun()
            terms = C.synonym_terms(r)
            r["terms"] = list(st.multiselect(
                "표현", options=terms, default=terms, key=f"dt_{i}",
                label_visibility="collapsed", accept_new_options=True,
                placeholder="같은 뜻으로 쓰이는 표현을 입력해 추가"))
            r.pop("detail", None)

    st.divider()
    with st.form("syn_add", clear_on_submit=True):
        kw = st.text_input("새 키워드", placeholder="예: 에폭시 수지")
        if st.form_submit_button("키워드 추가", use_container_width=True):
            n = kw.strip()
            if n and n not in [x.get("keyword") for x in rows]:
                rows.append({"keyword": n, "terms": []})
                t["synonyms"] = rows
                st.rerun()

    t["synonyms"] = [r for r in rows if str(r.get("keyword") or "").strip()]
    if st.button("닫기", type="primary", use_container_width=True):
        st.rerun()


def _sec_synonyms(t: dict):
    """첫 화면은 읽기 전용 — 키워드마다 표기를 칩 하나씩 펼쳐 한눈에 보이게."""
    rows = list(t.get("synonyms") or [])
    t.pop("disambiguation", None)

    top = st.columns([4, 1])
    top[0].markdown(
        f'<div style="font-size:.92rem;color:#3d4463;line-height:1.7">'
        f'키워드와 <b>같은 뜻으로 쓰이는 표현</b>을 등록합니다.</div>'
        f'<div style="font-size:.82rem;color:{INK_MUTED};line-height:1.6">'
        f'특허마다 용어가 달라 같은 개념이 여러 말로 나옵니다. '
        f'등록해 두면 AI가 함께 인식합니다.</div>',
        unsafe_allow_html=True)
    if top[1].button("편집", use_container_width=True, key="syn_edit"):
        _syn_dialog(t)

    st.write("")
    if not rows:
        st.info("등록된 키워드가 없습니다. **편집**에서 추가하세요.")
        return

    total = sum(len(C.synonym_terms(r)) for r in rows)
    st.markdown(f'<div style="color:{INK_MUTED};font-size:.78rem;margin-bottom:10px">'
                f'키워드 <b style="color:{BRAND}">{len(rows)}</b>개 · '
                f'표현 <b style="color:{BRAND}">{total}</b>개</div>', unsafe_allow_html=True)

    for r in rows:
        kw = str(r.get("keyword") or "").strip()
        terms = C.synonym_terms(r)
        chips = "".join(
            f'<span style="display:inline-block;background:{BRAND_025};color:#2b3157;'
            f'border:1px solid {BRAND_050};border-radius:14px;padding:3px 11px;'
            f'font-size:.82rem;margin:0 6px 6px 0;white-space:nowrap">{x}</span>'
            for x in terms)
        st.markdown(
            f'<div style="border:1px solid {LINE};border-radius:10px;padding:12px 15px;'
            f'margin-bottom:9px;background:#fff;display:flex;gap:16px;align-items:baseline">'
            f'<div style="flex:0 0 150px;color:{BRAND};font-weight:750;font-size:.94rem;'
            f'line-height:1.5">{kw}'
            f'<div style="color:{INK_MUTED};font-weight:600;font-size:.72rem">'
            f'{len(terms)}개</div></div>'
            f'<div style="flex:1;min-width:0">'
            + (chips or f'<span style="color:#B06000;font-size:.82rem">'
                        f'등록된 표현 없음 — AI가 스스로 판단합니다</span>')
            + '</div></div>', unsafe_allow_html=True)


# ---------------------------------------------------------------- 메인
def _sec_delete(sel, key_prefix: str):
    """탭 자체가 확인 화면 — 들어오면 바로 삭제 여부를 묻는다."""
    if not sel:
        st.info("새로 만드는 중인 과제는 지울 대상이 없습니다. "
                "저장된 과제를 고르면 여기서 지울 수 있습니다.")
        return

    path = C.TASKS_DIR / f"{sel}.yaml"
    if not path.is_file():
        st.warning(f"`{sel}.yaml` 파일이 없습니다.")
        return
    size = path.stat().st_size
    n_crit = len(C.criteria_ids(C.load_task(sel)))

    st.html(
        f'<div style="background:{_LAB_BG["issue"]};border:1px solid {_LAB_LINE["issue"]};'
        f'border-left:3px solid {_LAB_COLOR["issue"]};border-radius:{R_MD};'
        f'padding:22px 24px">'
        f'<div style="color:{BRAND};font-weight:800;font-size:1.28rem;'
        f'letter-spacing:-.03em;margin-bottom:11px">'
        f'&#8220;{sel}&#8221; 과제를 삭제하겠습니까?</div>'
        f'<div style="color:{INK_SUB};font-size:.9rem;line-height:1.78">'
        f'판정 기준 파일을 <b style="color:{_LAB_COLOR["issue"]}">영구 삭제</b>합니다. '
        f'휴지통에 남지 않아 되돌릴 수 없습니다.<br>'
        f'이미 저장된 실행 기록과 내려받은 엑셀 결과물은 지워지지 않습니다.</div>'
        f'<div style="display:flex;gap:30px;margin-top:16px;padding-top:14px;'
        f'border-top:1px solid {_LAB_LINE["issue"]};font-size:.82rem;color:{INK_MUTED}">'
        f'<span>판정 기준 <b style="color:{BRAND}">{n_crit}개</b></span>'
        f'<span>파일 크기 <b style="color:{BRAND}">{size:,}B</b></span>'
        f'<span>{path.name}</span></div></div>')

    st.write("")
    c1, _ = st.columns([1, 3])
    if c1.button("🗑 영구 삭제", type="primary", use_container_width=True,
                 key=f"{key_prefix}_delbtn"):
        if C.delete_task(sel):
            st.session_state[f"{key_prefix}_cur"] = None
            st.session_state["_deleted"] = sel
            st.rerun()
        else:
            st.error(f"삭제하지 못했습니다: {path}")


def task_editor(key_prefix: str = "te"):
    st.markdown(
        f'<div style="color:{BRAND};font-weight:700;font-size:1.1rem">판정기준 관리</div>'
        '<div style="color:#454b66;font-size:.9rem;margin-bottom:10px">'
        '코딩 없이 판정 기준을 만들고 고칩니다. 저장하면 <code>tasks/&lt;이름&gt;.yaml</code> 로 남습니다.</div>',
        unsafe_allow_html=True)

    if st.session_state.pop("_deleted", None):
        st.success("과제를 삭제했습니다.")

    names = C.list_tasks()
    mode = st.radio("무엇을 하시겠습니까?",
                    ["기존 과제 수정", "➕ 새 과제 만들기 (빈 템플릿에서)"],
                    horizontal=True, key=f"{key_prefix}_mode")

    if mode.startswith("기존"):
        if not names:
            st.info("저장된 과제가 없습니다. **새 과제 만들기**를 선택하세요.")
            return None
        sel = st.selectbox("과제", names, key=f"{key_prefix}_sel")
        base_name, seed = sel, f"{key_prefix}_seed_{sel}"
    else:
        sel, base_name, seed = None, "", f"{key_prefix}_seed_new"

    if st.session_state.get(f"{key_prefix}_cur") != seed:
        st.session_state[f"{key_prefix}_cur"] = seed
        try:
            st.session_state[f"{key_prefix}_task"] = (
                copy.deepcopy(C.load_task(sel)) if sel else copy.deepcopy(C.load_template()))
        except Exception as e:
            st.error(f"불러오기 실패: {e}")
            return None
    t = st.session_state[f"{key_prefix}_task"]
    t["version"] = 3

    tabs = st.tabs(["① 과제 정의", "② 판정 기준  ★", "③ 수집 항목",
                    "④ 동의어", "💾 저장", "🗑 삭제"])
    with tabs[0]:
        _sec_basic(t)
    with tabs[1]:
        _sec_criteria(t)
    with tabs[2]:
        _sec_info(t)
    with tabs[3]:
        _sec_synonyms(t)
    with tabs[4]:
        problems = R.lint(t)
        if problems:
            st.error("기준에 문제가 있습니다 — 고치지 않으면 실행이 거부됩니다:\n\n"
                     + "\n".join(f"- {p}" for p in problems))
        else:
            st.success("기준 검사 통과")
        miss = [LABEL_KO[k] for k in LABELS
                if not any(c.get("label") == k for c in (t.get("criteria") or []))]
        if miss:
            st.warning(f"기준이 하나도 없는 등급: {', '.join(miss)} — 그 등급은 절대 나오지 않습니다.")

        name = st.text_input("저장 이름 (파일명)", value=base_name, placeholder="예: oled_encap",
                             key=f"{key_prefix}_name")
        c1, c2 = st.columns([1, 3])
        if c1.button("💾 저장", type="primary", disabled=bool(problems), key=f"{key_prefix}_save"):
            n = name.strip()
            if not n:
                st.error("이름을 입력하세요.")
            elif n.startswith("_"):
                st.error("`_` 로 시작하는 이름은 템플릿 전용입니다.")
            else:
                p = C.save_task(n, t)
                st.success(f"저장됨: `{p}`")
                st.session_state[f"{key_prefix}_cur"] = None
                return n
        with c2.expander("yaml"):
            y = yaml.safe_dump(t, allow_unicode=True, sort_keys=False)
            st.code(y, language="yaml")
            st.download_button("⬇️ yaml", y.encode("utf-8"),
                               file_name=f"{name or 'task'}.yaml", mime="text/yaml")

    with tabs[5]:
        _sec_delete(sel, key_prefix)
    return None
