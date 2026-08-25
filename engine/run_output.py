"""실행 산출물을 실행 폴더에 남긴다.

내려받기와 별개로, 판정을 돌리면 그 결과가 디스크에 남아야 한다.
나중에 "그때 뭐라고 판단했지?" 를 다시 볼 수 있어야 하기 때문이다.

  판정결과.xlsx   원본 회차 시트 오른쪽에 판정 열 + [수집] 열 (원본은 건드리지 않는다)
  AI판단과정.md   건별 판단 서술 + 판정 과정 + 근거 청구항
  판정표.csv      한 줄 = 한 건 (엑셀 없이도 열리는 형식)
"""
import csv
import io
import json
from pathlib import Path

import criteria as criteria_mod
import excel_export

LABEL_KO = {"noise": "노이즈", "valid": "유효", "issue": "이슈", "hold": "보류"}
LABEL_ICON = {"noise": "🔘", "valid": "🟢", "issue": "🔴", "hold": "🟠"}
_ANS_KO = {"O": "해당", "X": "비해당", "?": "모르겠음"}
_RANK = {"issue": 0, "hold": 1, "valid": 2, "noise": 3}


def _crit_text(r: dict, limit: int = 90) -> str:
    """내부 기준 id 대신 사람이 읽는 기준 문장."""
    cid = str(r.get("criterion_id") or "")
    if not cid:
        return ""
    if not cid.startswith("c_"):
        return cid
    txt = " ".join(str(r.get("criterion") or "").split())
    return (txt[:limit] + "…") if len(txt) > limit else (txt or LABEL_KO.get(r.get("label"), ""))


def narration_md(results: list[dict], task: dict, sheet: str, meta: dict | None = None) -> str:
    """건별 판단 과정을 읽을 수 있는 마크다운으로."""
    meta = meta or {}
    n = len(results)
    counts = {}
    for r in results:
        k = LABEL_KO.get(r.get("label"), "?")
        counts[k] = counts.get(k, 0) + 1
    head = [f"# AI 판단 과정 — {sheet}", "",
            f"- 판정 건수: **{n}건**"
            + ("  *(중간 정지)*" if meta.get("stopped") else ""),
            "- 등급 분포: " + " · ".join(f"{k} {v}" for k, v in counts.items()),
            f"- 모델: {meta.get('model', '') or ''}",
            f"- 과제: {task.get('task', '')}",
            f"- 실행 폴더: `{meta.get('run_dir', '')}`", "",
            "> AI 는 원문에서 사실만 확인하고, 등급은 담당자가 정한 기준이 결정합니다.", "",
            "---", ""]

    body = []
    for r in sorted(results, key=lambda x: (_RANK.get(x.get("label"), 9), str(x.get("no")))):
        lab = r.get("label") or "hold"
        body.append(f"## {LABEL_ICON.get(lab,'')} {LABEL_KO.get(lab, lab)} · "
                    f"no {r.get('no')} [{r.get('country')}] {str(r.get('title') or '')[:90]}")
        body.append("")
        body.append(f"- 신뢰도: {r.get('confidence') or '—'} · "
                    f"근거등급: {r.get('evidence') or '—'} · "
                    f"추출경로: {r.get('claims_via') or '—'}")
        body.append(f"- 해당 기준: **{_crit_text(r) or '—'}**")
        if r.get("reason"):
            body.append(f"- 판정 근거: {' '.join(str(r['reason']).split())}")
        if r.get("review_note"):
            body.append(f"- 검토 필요: {r['review_note']}")
        if r.get("tech_summary"):
            body.append(f"- 기술 요약: {r['tech_summary']}")

        got = {**(r.get("properties") or {}), **(r.get("info") or {}), **(r.get("collect") or {})}
        got = {k: v for k, v in got.items() if str(v).strip()}
        if got:
            body.append("")
            body.append("**수집 항목**")
            body += [f"- {k}: {v}" for k, v in got.items()]

        if r.get("narration"):
            body.append("")
            body.append("**판단 과정 (AI 서술)**")
            body.append("")
            for line in criteria_mod.humanize(str(r["narration"]), task).splitlines():
                line = line.strip()
                if line:
                    body.append(f"> {line}")

        tr = r.get("criteria_trace") or []
        if tr:
            body.append("")
            body.append("**기준 판정 과정**")
            for g in tr:
                mark = "  ← 여기서 확정" if g.get("decided") else ""
                body.append(f"- **{g.get('title', g.get('label'))}** "
                            f"(해당 {g.get('n_hit')} · 모르겠음 {g.get('n_unknown')} / "
                            f"{len(g.get('items') or [])}){mark}")
                for it in (g.get("items") or []):
                    hit = " ← 확정" if it.get("decided") else ""
                    body.append(f"    - `{_ANS_KO.get(it.get('answer'), it.get('answer'))}` "
                                f"{it.get('when')}{hit}")

        ic = r.get("independent_claims") or []
        if ic:
            body.append("")
            body.append(f"**근거 청구항 {len(ic)}건**")
            body.append("")
            for c in ic:
                body.append("```")
                body.append(f"[청구항 {c.get('no','')}] {c.get('text','')}")
                body.append("```")
        body.append("")
        body.append("---")
        body.append("")
    return "\n".join(head + body)


def results_csv(results: list[dict], task: dict) -> bytes:
    """한 줄 = 한 건. 엑셀 없이도 열린다."""
    cols = criteria_mod.collect_names(task)
    buf = io.StringIO()
    w = csv.writer(buf)
    w.writerow(["번호", "국가", "발명의 명칭", "AI판정", "신뢰도", "해당 기준",
                "판정근거", "근거등급", "검토필요사항"] + [f"[수집] {k}" for k in cols])
    for r in sorted(results, key=lambda x: (_RANK.get(x.get("label"), 9), str(x.get("no")))):
        got = {**(r.get("properties") or {}), **(r.get("info") or {}), **(r.get("collect") or {})}
        w.writerow([r.get("no"), r.get("country"), r.get("title"),
                    LABEL_KO.get(r.get("label"), ""), r.get("confidence") or "",
                    _crit_text(r), " ".join(str(r.get("reason") or "").split()),
                    r.get("evidence") or "", r.get("review_note") or ""]
                   + [str(got.get(k, "")) for k in cols])
    return buf.getvalue().encode("utf-8-sig")


def save_outputs(run_dir, sheet: str, results: list[dict], task: dict,
                 src=None, meta: dict | None = None, quiet: bool = True) -> dict:
    """실행 폴더에 산출물을 남긴다. 실패한 항목은 건너뛰고 무엇을 썼는지 돌려준다."""
    run_dir = Path(run_dir)
    if not results or not run_dir.is_dir():
        return {}
    written, failed = {}, {}

    if src is not None:
        try:
            p = run_dir / "판정결과.xlsx"
            excel_export.annotate_workbook(src, sheet, results, task, out_path=p)
            written["판정결과.xlsx"] = p
        except Exception as e:
            failed["판정결과.xlsx"] = repr(e)

    for name, data in (("AI판단과정.md", narration_md(results, task, sheet, meta)),
                       ("판정표.csv", results_csv(results, task))):
        try:
            p = run_dir / name
            p.write_bytes(data if isinstance(data, bytes) else data.encode("utf-8"))
            written[name] = p
        except Exception as e:
            failed[name] = repr(e)

    if failed:
        try:
            (run_dir / "저장실패.json").write_text(
                json.dumps(failed, ensure_ascii=False, indent=2), encoding="utf-8")
        except OSError:
            pass
    if not quiet:
        for k, v in written.items():
            print(f"[저장] {v}")
        for k, v in failed.items():
            print(f"[저장실패] {k}: {v}")
    return written
