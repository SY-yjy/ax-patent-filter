"""결과 표 렌더링 회귀 테스트 — Styler 를 실제로 계산해 shape 오류를 잡는다.

`_style` 이 표시 열 수와 다른 길이를 돌려주면 pandas 가 ValueError 로 죽는다.
Streamlit 런타임 없이도 검증되므로 UI 실행 전에 여기서 걸러야 한다.

실행:  /opt/anaconda3/bin/python tests/test_ui_render.py
"""
import sys, pathlib
ROOT = pathlib.Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "engine"))
import pandas as pd
import ui_common as ui

SAMPLE = [
    {"no": 1, "country": "KR", "title": "가역 접합 시스템", "label": "issue",
     "confidence": "높음", "criterion_id": "i_기능중심", "hold_code": "",
     "criterion": "독립청구항에 접착제 조성물이 포함되고 전기자극에 따른 박리가 청구된다",
     "evidence": "원문청구항", "reason": "독립청구항에 접착제 조성물…",
     "review_note": "함량 중첩 확인 필요", "narration": "명칭을 본다.\n독립항 1을 읽는다.",
     "answers": {"i_기능중심": "O", "n_비접착": "X", "h_구조식": "X"},
     "n_matched": 1, "n_unknown": 0, "info": {"수지계": "아크릴"},
     "properties": {"초기 접착력": "5 N/mm"},
     "evidence_quotes": {"i_기능중심": "청구항 1 … 아크릴레이트"},
     "independent_claims": [{"no": "1", "text": "청구항 원문"}],
     "criteria_trace": [
         {"key": "노이즈판단", "title": "1단계 · 노이즈인가?", "label": "noise",
          "n_hit": 0, "n_unknown": 0, "decided": False,
          "items": [{"id": "c_n1", "answer": "X", "when": "접착 요소 없음",
                     "system": False, "decided": False}]},
         {"key": "이슈판단", "title": "2단계 · 이슈인가?", "label": "issue",
          "n_hit": 1, "n_unknown": 0, "decided": True,
          "items": [{"id": "c_i1", "answer": "O", "when": "이온성 액체 + 수지",
                     "system": False, "decided": True}]}],
     "gold_valid": "O", "gold_issue": None},
    {"no": 2, "country": "CN", "title": "전해 점착제", "label": "valid",
     "confidence": "중간", "criterion_id": "v_타수지계한정", "hold_code": "",
     "criterion": "독립청구항이 아크릴·우레탄 이외의 수지계만으로 한정된다",
     "evidence": "원문청구항", "reason": "타수지계 한정", "review_note": "",
     "narration": "폴리에스테르계다.", "answers": {"v_타수지계한정": "O"},
     "n_matched": 1, "n_unknown": 0, "info": {}, "properties": {},
     "evidence_quotes": {}, "independent_claims": [{"no": "1", "text": "一种电解粘胶"}],
     "criteria_trace": [], "gold_valid": None, "gold_issue": None},
    {"no": 3, "country": "PCT", "title": "디스플레이", "label": "hold",
     "confidence": "낮음", "criterion_id": "h_원문미확보", "hold_code": "원문_미확보",
     "criterion": "원문 청구항을 확보하지 못해 대표청구항만 검토했다",
     "evidence": "엑셀폴백:스캔판독실패", "reason": "원문 미확보",
     "review_note": "원문 확보 필요", "narration": "", "answers": {"h_원문미확보": "O"},
     "n_matched": 1, "n_unknown": 5, "info": {}, "properties": {},
     "evidence_quotes": {}, "independent_claims": [], "criteria_trace": [],
     "gold_valid": None, "gold_issue": None},
    {"no": 4, "country": "JP", "title": "열수축 필름", "label": "noise",
     "confidence": "중간", "criterion_id": "n_비접착", "hold_code": "",
     "criterion": "접착 관련 요소가 전혀 없다", "evidence": "원문청구항",
     "reason": "접착 요소 없음", "review_note": "", "narration": "필름이다.",
     "answers": {"n_비접착": "O"}, "n_matched": 1, "n_unknown": 0,
     "info": {}, "properties": {}, "evidence_quotes": {},
     "independent_claims": [{"no": "1", "text": "熱可塑性樹脂"}],
     "criteria_trace": [], "gold_valid": None, "gold_issue": None},
]


def main() -> int:
    fails = []
    flat = [ui._flatten(r) for r in SAMPLE]
    df = pd.DataFrame(flat)
    print(f"_flatten → {len(df.columns)}열 ({len(df)}행)")

    # 전체 표
    try:
        st = ui._style(df)
        st._compute()
        n_out = len(st.columns)
        assert n_out == len(df.columns) - 1, f"열 수 불일치 {n_out} vs {len(df.columns)-1}"
        print(f"✅ 전체 표 Styler 계산 OK ({n_out}열)")
    except Exception as e:
        fails.append(f"전체 표: {type(e).__name__}: {e}")
        print(f"❌ 전체 표: {e}")

    # 등급별 부분집합 (실제 화면이 하는 것)
    for lab in ("issue", "hold", "valid", "noise"):
        sub = df[df["_label"] == lab]
        if not len(sub):
            continue
        try:
            ui._style(sub)._compute()
            print(f"✅ {lab} 부분집합({len(sub)}행) OK")
        except Exception as e:
            fails.append(f"{lab}: {type(e).__name__}: {e}")
            print(f"❌ {lab}: {e}")

    # 빈 표 · _label 없는 표도 죽지 않아야 함
    for name, d in (("빈 표", df.iloc[0:0]), ("_label 없음", df.drop(columns=["_label"]))):
        try:
            ui._style(d)._compute()
            print(f"✅ {name} OK")
        except Exception as e:
            fails.append(f"{name}: {type(e).__name__}: {e}")
            print(f"❌ {name}: {e}")

    # 엑셀 변환도 같은 데이터로 확인
    try:
        import criteria as C, excel_export as X
        task = C.load_task("dod")
        cols = X._detail_columns(task)
        for r in SAMPLE:
            assert len(X._detail_row(r, task)) == len(cols), "상세 시트 열 수 불일치"
            assert len(X._main_row(r, task)) == len(X.main_columns(task)), "회차 시트 열 수 불일치"
        print(f"✅ 엑셀 열 수 일치 (회차 {len(X.main_columns(task))}열 · 상세 {len(cols)}열)")
    except Exception as e:
        fails.append(f"엑셀: {type(e).__name__}: {e}")
        print(f"❌ 엑셀: {e}")

    # 화면 구성요소가 편집 중 사라지지 않았는지 (실제로 한 번 유실된 적 있음)
    import inspect
    src = inspect.getsource(ui.render_results)
    for must, why in (("_downloads(", "엑셀·CSV 다운로드 버튼"),
                      ("render_trace(", "규칙 평가 과정"),
                      ("건별 상세", "건별 상세 패널"),
                      (".metric(", "지표"),
                      ("narration", "AI 판단 과정"),
                      ("_result_card(", "이슈·보류 카드")):
        if must not in src:
            fails.append(f"render_results 에 {why}({must}) 가 없다")
            print(f"❌ {why} 누락")
        else:
            print(f"✅ {why} 존재")
    if "on_event" not in inspect.getsource(ui.run_console):
        fails.append("run_console 에 실시간 이벤트 연결이 없다")

    # 실행 콘솔의 필수 기능 — 지워지면 즉시 잡는다
    src = inspect.getsource(ui.run_console)
    for frag, why in (("_request_stop", "정지 버튼 연결이 없다"),
                      ("_hist_item", "완료된 건의 이력 렌더가 없다"),
                      ("run_dir", "run_dir 이벤트 처리가 없다")):
        if frag not in src:
            fails.append(f"run_console: {why}")
    if "criterion_id" in inspect.getsource(ui._flatten):
        fails.append("_flatten 이 내부 기준 id 를 화면에 그대로 내보낸다")

    # 회차 시트에 수집 항목 열이 붙는지 — 상세 시트에만 있던 회귀를 막는다
    import excel_export as X, criteria as Cx
    t = Cx.load_task("dod")
    mc = X.main_columns(t)
    coll = [c for c in mc if c.startswith("[수집]")]
    if not coll:
        fails.append("회차 시트에 [수집] 열이 없다")
    if len(coll) != len(Cx.collect_names(t)):
        fails.append(f"[수집] 열 {len(coll)}개 ≠ 정의된 수집 항목 {len(Cx.collect_names(t))}개")
    probe = {"label": "issue", "collect": {k: f"v{i}" for i, k in enumerate(Cx.collect_names(t))}}
    if len(X._main_row(probe, t)) != len(mc):
        fails.append(f"_main_row 길이 {len(X._main_row(probe, t))} ≠ 열 {len(mc)}")
    if "v0" not in X._main_row(probe, t):
        fails.append("_main_row 가 수집값을 싣지 않는다")

    # 실행 폴더 자동 저장 · 판단 과정 내려받기
    import run_output as RO, inspect as _i, agent
    if "_persist" not in _i.getsource(ui.run_console):
        fails.append("run_console 이 실행 폴더에 저장하지 않는다")
    dl = _i.getsource(ui._downloads)
    for frag, why in (("narration_md", "판단 과정(.md) 내려받기가 없다"),
                      ("results_csv", "판정표(.csv) 내려받기가 없다"),
                      ("run_dir", "저장 위치 안내가 없다")):
        if frag not in dl:
            fails.append(f"_downloads: {why}")
    probe = [{"no": 1, "country": "KR", "title": "t", "label": "issue",
              "criterion_id": "c_i1", "criterion": "청구항에 A 와 B 가 함께 있다",
              "narration": "1항을 읽었다.\n조건을 확인했다.",
              "collect": {"수지 종류": "PU"},
              "criteria_trace": [{"title": "1단계", "label": "noise", "n_hit": 0,
                                  "n_unknown": 0, "items": [{"answer": "X", "when": "배터리 전용"}]}]}]
    md = RO.narration_md(probe, task, "228회차", {"run_dir": "x"})
    for must in ("판단 과정 (AI 서술)", "기준 판정 과정", "수집 항목",
                 "청구항에 A 와 B 가 함께 있다"):
        if must not in md:
            fails.append(f"narration_md 에 '{must}' 가 없다")
    if "c_i1" in md:
        fails.append("narration_md 가 내부 기준 id 를 노출한다")
    if b"PU" not in RO.results_csv(probe, task):
        fails.append("results_csv 가 수집값을 싣지 않는다")

    # 기준 id 하네스 — 서술·메모·md 어디에도 c_ id 가 남지 않아야 한다
    import criteria as Cid, re as _re
    raw = ("전기 인가로 박리되는 접착제로 읽힌다 → c_i3 O.\n"     # 삭제된 기준
           "이온성 액체 있으나 수지 없음 → c_i1 X. c_n2 도 X.")
    hz = Cid.humanize(raw, task)
    if _re.search(r"\bc_[A-Za-z0-9_]+\b", hz):
        fails.append(f"humanize 후에도 기준 id 가 남는다: {hz[:60]}")
    if "「" not in hz:
        fails.append("humanize 가 기준 문장으로 바꾸지 않는다")
    if "지금은 없는 기준" not in hz:
        fails.append("삭제된 기준 id 가 그대로 남는다")
    for bad in ("xc_i1", "c_i1abc", "cc_i1", "c_abcde1"):
        if "「" in Cid.humanize(bad, task):
            fails.append(f"humanize 가 부분일치를 잘못 치환한다: {bad}")
    if "서술에 기준 id 를 쓰지 마라" not in agent.SYS_EXTRACT:
        fails.append("추출 프롬프트에 id 금지 규칙이 없다")
    md2 = RO.narration_md([{"no": 1, "label": "issue", "narration": raw,
                            "criterion_id": "c_i1", "criterion": "A 와 B"}], task, "s", {})
    if _re.search(r"\bc_[A-Za-z0-9_]+\b", md2):
        fails.append("narration_md 에 기준 id 가 남는다")
    if "_request_stop" not in dir(ui) or "run_console" not in dir(ui):
        fails.append("정지/콘솔 함수가 없다")
        print("❌ 실시간 콘솔 누락")
    else:
        print("✅ 실시간 콘솔 연결")

    print(f"\n{'통과' if not fails else '실패 ' + str(len(fails)) + '건'}")
    for f in fails:
        print(f"   ❌ {f}")
    return 1 if fails else 0


if __name__ == "__main__":
    sys.exit(main())
