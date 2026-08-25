"""End-to-end 오케스트레이션 — 회차(시트) 하나를 전 건 원문 판정한다.

  엑셀 한 회차 → (건별) ON key → 원문 PDF → 청구항 → AI 추출 → 규칙 엔진 → 등급
              → output/runs/<회차>_<시각>/records.jsonl 에 건별 append

**사전 게이트 없음.** 모든 건의 원문 청구항을 읽는다.
**LLM은 등급을 정하지 않는다.** AI는 사실만 추출하고 rules.py 가 등급을 확정한다
(같은 추출값 → 항상 같은 등급). 원문 미확보 건은 규칙이 자동으로 보류로 보낸다.

사용:  python pipeline.py <엑셀경로> <시트명> --task dod [--limit N] [--resume <실행폴더>]
"""
import re
import json
import argparse
from datetime import datetime
from pathlib import Path
from collections import Counter
import requests
import config
import excel_loader
import wips_downloader
import claims_extractor
import agent
import rules
import criteria as criteria_mod

_ON_KEY = re.compile(r"\d{13}")   # 실측: WIPS skey 는 13자리 숫자 (다운로드 성공으로 검증)

LABELS = rules.LABELS
LABEL_KO = rules.LABEL_KO


# ---------------------------------------------------------------- 근거 확보
def _emit(on_event, kind, payload):
    if on_event:
        try:
            on_event(kind, payload)
        except Exception:
            pass


def _scan_claims(on_key: str, pdf_path: str, on_event=None) -> str:
    """스캔 이미지 PDF → 청구항. 에이전트가 페이지를 이미지로 읽어 전사한다.

    **결과를 캐시**한다(output/pdf/<on_key>.claims.txt). 판독은 텍스트 PDF의 60배 비용이라
    (실측 231,517토큰·68초) 특허당 딱 한 번만 지불해야 한다. 두 번째부터는 파일 읽기.
    """
    cache = config.PDF_CACHE / f"{on_key}.claims.txt"
    if cache.is_file() and cache.stat().st_size > 0:
        _emit(on_event, "stage", "스캔 판독 결과 캐시 사용 (이전에 읽어둔 청구항)")
        return cache.read_text(encoding="utf-8")
    if not config.SCAN_READ:
        return ""
    _emit(on_event, "stage", "스캔 이미지 PDF — 에이전트가 페이지를 읽어 청구항을 찾습니다")
    text = agent.read_claims_from_scan(pdf_path, on_event=on_event)
    if len(text.strip()) >= 50:                 # 너무 짧으면 판독 실패로 본다
        cache.write_text(text, encoding="utf-8")
        return text
    return ""


def gather_claims(rec: dict, session, on_event=None) -> tuple[str, str, str]:
    """판정에 넣을 텍스트를 확보한다. 반환: (청구항텍스트, 근거등급, 추출경로).

    근거등급 = 판정 신뢰도(화면 노출): 원문청구항 / 원문전체 / 엑셀폴백:<이유>
    추출경로 = 기술 디버깅용(비노출): claims:CN · fulltext · scan_read · excel

    원문 청구항을 확보했다면 텍스트에서 뽑았는지 스캔을 읽었는지는 신뢰도가 같으므로
    둘 다 `원문청구항`으로 묶는다. `엑셀폴백`만이 근거가 약한 판정이다(규칙이 보류로 보냄).
    """
    fallback = rec.get("rep_claim") or ""
    on_key = str(rec.get("on_key") or "").strip()

    if not on_key:
        return fallback, "엑셀폴백:ONkey없음", "excel"
    if not _ON_KEY.fullmatch(on_key):
        return fallback, "엑셀폴백:ONkey형식오류", "excel"

    _emit(on_event, "stage", f"WIPS 원문 PDF 확보 중 (ON key {on_key})")
    pdf = wips_downloader.download_pdf(on_key, session=session)
    if not pdf:
        return fallback, "엑셀폴백:PDF실패", "excel"

    claims, how = claims_extractor.extract_claims(pdf, rec.get("country") or "")
    if how == "no_text":                        # PCT·일부 EP 등 텍스트 레이어 없음
        scanned = _scan_claims(on_key, pdf, on_event=on_event)
        if scanned:
            return scanned, "원문청구항", "scan_read"
        return fallback, "엑셀폴백:스캔판독실패", "excel"
    return claims, ("원문청구항" if how.startswith("claims:") else "원문전체"), how


# ---------------------------------------------------------------- 신뢰도
def confidence(evidence: str, answers: dict, raw: dict, warns: list) -> str:
    """높음 / 중간 / 낮음 — 등급이 아니라 **근거의 질**을 나타낸다(결정적 계산).

    원문 확보 여부 + '모르겠음' 개수 + 정규화 경고로 정한다.
    """
    unknown = sum(1 for v in (answers or {}).values() if v == rules.U)
    if raw.get("_parse_failed") or not str(evidence).startswith("원문"):
        return "낮음"
    if unknown >= 3 or warns:
        return "중간"
    if unknown == 0 and (raw.get("independent_claims") or []):
        return "높음"
    return "중간"


# ---------------------------------------------------------------- 건별 처리
def judge_one(rec: dict, task: dict, criteria_text: str, session, on_event=None) -> dict:
    out = {"no": rec.get("no"), "title": rec.get("title"), "country": rec.get("country"),
           "on_key": rec.get("on_key"), "pub_no": rec.get("pub_no"),
           "gold_valid": rec.get("valid"), "gold_issue": rec.get("issue")}  # 참고용(신뢰 근거 아님)

    claims, evidence, via = gather_claims(rec, session, on_event=on_event)
    out.update(evidence=evidence, claims_via=via, claims_chars=len(claims))

    if not claims.strip():
        out.update(label="hold", criterion_id="근거없음", step="보류",
                   criterion="판정 근거 텍스트를 전혀 확보하지 못했다",
                   reason="판정 근거 텍스트를 전혀 확보하지 못했다.",
                   review_note="원문 PDF를 확보해야 판정할 수 있다.",
                   confidence="낮음", tech_summary="", answers={}, collect={},
                   independent_claims=[], evidence_quotes={},
                   notes="", narration="", criteria_trace=[])
        return out

    _emit(on_event, "stage", f"근거 확보 완료 — {evidence} · 청구항 {len(claims):,}자")
    _emit(on_event, "extract_start", None)
    raw = agent.extract_facts(rec, claims, criteria_text, evidence,
                              on_event=on_event, task=task)
    _emit(on_event, "narration", criteria_mod.humanize(raw.get("_narration", ""), task))

    answers, warns = rules.normalize(raw.get("answers"), task)
    tr = rules.trace(answers, task)
    _emit(on_event, "criteria", tr)
    verdict = rules.evaluate(answers, task)

    out.update(
        label=verdict["label"], criterion_id=verdict["criterion_id"],
        criterion=verdict.get("criterion", ""), step=verdict.get("step", ""),
        note=verdict.get("note", ""), matched=verdict.get("matched", {}),
        reason=verdict["reason"], review_note=verdict.get("review", ""),
        confidence=confidence(evidence, answers, raw, warns),
        tech_summary=raw.get("tech_summary", ""),
        answers=answers, collect=raw.get("collect", {}) or raw.get("properties", {}),
        independent_claims=raw.get("independent_claims", []),
        evidence_quotes=raw.get("evidence", {}),
        notes=criteria_mod.humanize(raw.get("notes", ""), task),
        narration=criteria_mod.humanize(raw.get("_narration", ""), task),
        normalize_warnings=warns, criteria_trace=tr,
        n_unknown=sum(1 for v in answers.values() if v == rules.U),
        n_matched=sum(1 for v in answers.values() if v == rules.O),
    )
    return out


def _row_key(rec: dict, i: int):
    n = rec.get("no")
    return f"no:{n}" if n not in (None, "") else f"idx:{i}"


# ---------------------------------------------------------------- 실행
def run(sheet: str, task: dict, xlsx_path=None, records: list[dict] | None = None,
        limit: int | None = None, resume: str | None = None, quiet: bool = False,
        progress=None, on_event=None):
    """회차(시트) 하나를 전 건 판정. 건별로 즉시 디스크에 append → 중단 시 이어가기.

    records 를 주면 그걸 쓰고(웹앱: 이미 로드된 레코드), 없으면 xlsx_path 에서 시트를 읽는다.
    progress(i, total, result) 콜백으로 건별 진행을 밖에 알린다(웹앱 라이브 표).
    CLI·웹앱이 같은 이 함수를 쓰므로 체크포인트·리포트 로직이 한 벌만 존재한다.
    """
    problems = rules.lint(task)
    if problems:
        raise rules.RuleError("판정 규칙에 문제가 있어 실행을 중단한다:\n  - " + "\n  - ".join(problems))

    if records is None:
        records = excel_loader.load_sheet(xlsx_path, sheet)
    if limit:
        records = records[:limit]
    criteria_text = criteria_mod.render_for_extract(task)

    run_dir = Path(resume) if resume else (
        config.RUNS_DIR / f"{sheet}_{datetime.now().strftime('%Y%m%d_%H%M%S')}")
    run_dir.mkdir(parents=True, exist_ok=True)
    if on_event:
        on_event(0, {}, "run_dir", str(run_dir))   # 중간 정지해도 폴더를 찾을 수 있게
    jsonl = run_dir / "records.jsonl"

    done, results = set(), []
    if jsonl.is_file():
        for line in jsonl.read_text(encoding="utf-8").splitlines():
            if line.strip():
                r = json.loads(line)
                done.add(r.get("_key"))
                results.append(r)
        if not quiet:
            print(f"[재개] {run_dir.name} — 이미 {len(done)}건 완료")

    (run_dir / "meta.json").write_text(json.dumps({
        "sheet": sheet, "xlsx": str(xlsx_path or "(업로드/메모리)"), "n_records": len(records),
        "model": config.MODEL_JUDGE,
        "backend": "subscription" if config.USE_SUBSCRIPTION else "api",
        "prompt_extract": agent.SYS_EXTRACT,
        "task": task,                     # 판정기준·규칙 전문 스냅샷
        "started": datetime.now().isoformat(timespec="seconds"),
    }, ensure_ascii=False, indent=2), encoding="utf-8")

    agent.reset_usage()
    session = requests.Session()
    session.headers.update({"User-Agent": config.USER_AGENT})

    with open(jsonl, "a", encoding="utf-8") as f:
        for i, rec in enumerate(records, 1):
            key = _row_key(rec, i)
            if key in done:
                continue
            try:
                r = judge_one(rec, task, criteria_text, session,
                              on_event=(lambda k, p: on_event(i, rec, k, p)) if on_event else None)
            except Exception as e:
                r = {"no": rec.get("no"), "country": rec.get("country"), "title": rec.get("title"),
                     "label": "hold", "criterion_id": "실행오류", "step": "보류",
                     "reason": repr(e), "evidence": "오류", "confidence": "낮음",
                     "gold_valid": rec.get("valid"), "gold_issue": rec.get("issue")}
            r["_key"] = key
            f.write(json.dumps(r, ensure_ascii=False) + "\n")
            f.flush()
            results.append(r)
            if progress:
                progress(i, len(records), r)
            if not quiet:
                print(f"[{i}/{len(records)}] no={r.get('no')} {LABEL_KO.get(r.get('label'), r.get('label'))} "
                      f"({r.get('criterion_id')}) {r.get('evidence')} · {str(r.get('reason'))[:50]}")

    # 한 건도 판정되지 않았으면 실행 폴더를 남기지 않는다(빈 폴더가 목록을 어지럽힌다)
    if not results:
        try:
            for f in run_dir.iterdir():
                f.unlink()
            run_dir.rmdir()
            if not quiet:
                print(f"[정리] 판정 0건 — 실행 폴더 삭제: {run_dir.name}")
        except OSError:
            pass
        return results, run_dir

    if not quiet:
        report(results, run_dir)
    return results, run_dir


def report(results: list[dict], run_dir: Path | None = None):
    n = len(results)
    lab = Counter(LABEL_KO.get(r.get("label"), r.get("label")) for r in results)
    print(f"\n=== 판정 분포 ({n}건) ===", dict(lab))
    print("=== 해당 기준 ===", dict(Counter(r.get("criterion_id") for r in results)))
    print("=== 결정 단계 ===", dict(Counter(r.get("step") for r in results)))
    print("=== 근거등급 ===", dict(Counter(r.get("evidence") for r in results)))
    print("=== 신뢰도 ===", dict(Counter(r.get("confidence") for r in results)))
    holds = Counter(r.get("hold_code") for r in results if r.get("label") == "hold")
    if holds:
        print("=== 보류 사유 ===", dict(holds))
    print("=== 추출경로(디버깅) ===", dict(Counter(r.get("claims_via") for r in results)))

    ev = Counter(r.get("evidence") for r in results)
    src = sum(v for k, v in ev.items() if str(k).startswith("원문"))
    print(f"=== 원문 근거 비율: {src}/{n} = {100*src/max(n,1):.0f}% ===")

    unk = [r.get("no") for r in results if (r.get("n_unknown") or 0) >= 3]
    if unk:
        print(f"⚠️ '모르겠음' 3개 이상 {len(unk)}건: {unk[:15]}")
    noq = [r.get("no") for r in results if r.get("label") in ("noise", "valid", "issue")
           and not (r.get("independent_claims") or [])]
    if noq:
        print(f"⚠️ 근거 청구항 인용 누락 {len(noq)}건: {noq[:15]}")
    warned = [r.get("no") for r in results if r.get("normalize_warnings")]
    if warned:
        print(f"⚠️ 추출값 보정 발생 {len(warned)}건 (누락·미정의값): {warned[:15]}")

    rep = agent.usage_report()
    for model, u in rep["per_model"].items():
        print(f"\n=== {model}: 호출 {u['calls']}, in {u['in']:,} / out {u['out']:,} → ${u['cost_usd']}")
    if rep.get("parse_fails"):
        print(f"⚠️ 추출 JSON 파싱 실패 {rep['parse_fails']}건 (보류로 처리됨)")

    gold = [r for r in results if r.get("gold_valid") == "O"]
    if gold:
        kept = [r for r in gold if r.get("label") != "noise"]
        print(f"\n(참고) 사람 유효라벨 O {len(gold)}건 중 AI가 noise 아님: {len(kept)}건"
              f" — 라벨 정확도 미검증이므로 성능 지표로 쓰지 않는다")
    if run_dir:
        print(f"\n결과: {run_dir}/records.jsonl")


if __name__ == "__main__":
    ap = argparse.ArgumentParser(description="특허 판정 엔진 — 회차 하나를 전 건 원문 판정")
    ap.add_argument("xlsx"); ap.add_argument("sheet")
    ap.add_argument("--task", required=True, help=f"과제 이름 (tasks/). 선택지: {criteria_mod.list_tasks()}")
    ap.add_argument("--limit", type=int, default=None)
    ap.add_argument("--resume", default=None, help="이어서 돌릴 실행 폴더 (output/runs/<이름>)")
    ap.add_argument("--excel", action="store_true", help="끝나면 원본 엑셀에 결과 열을 붙여 저장")
    a = ap.parse_args()
    _task = criteria_mod.load_task(a.task)
    _res, _dir = run(a.sheet, _task, xlsx_path=a.xlsx, limit=a.limit, resume=a.resume)
    if a.excel:
        import excel_export
        import run_output
        _w = run_output.save_outputs(_dir, a.sheet, _res, _task, src=a.xlsx,
                                     meta={"run_dir": str(_dir), "model": config.MODEL_JUDGE},
                                     quiet=False)
        p = _w.get("판정결과.xlsx", _dir)
        print(f"엑셀: {p}")
