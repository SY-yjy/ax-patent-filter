"""판정 엔진 — 기준 + AI 답변 → 등급.

AI는 기준 문장마다 해당(O) / 비해당(X) / 모르겠음(?) 만 답한다. 등급은 정하지 않는다.

★ 판정 흐름 (사용자 정의, 2026-08-24)
    1단계  노이즈인가?           → 노이즈 기준에 해당하면 노이즈, 아니면 유효로 남긴다
    2단계  유효 중에 이슈인가?    → 이슈 기준에 해당하면 이슈, 아니면 유효
    언제든 판단이 안 서면          → 보류

  구체적으로 위에서부터:
    ① 보류 기준에 해당                     → 보류
    ② 노이즈와 이슈가 동시에 해당(모순)     → 보류   (버리지도, 올리지도 않는다)
    ③ 노이즈 기준에 해당                   → 노이즈
         단 이슈·보류 기준에 '모르겠음'이 있으면 → 보류 (모르는 채로 버리지 않는다)
    ④ 이슈 기준에 해당                     → 이슈
    ⑤ 유효 기준에 해당                     → 유효 (그 문장이 '왜 유효인가'의 근거가 된다)
    ⑥ 어느 기준에도 해당하지 않음            → 보류 (판단이 서지 않은 것이므로)

  ※ '기본 등급' 같은 설정은 두지 않는다. 판단이 안 되면 보류다 — 그게 전부다.

  '기준 하나하나의 순서'는 없다. 등급 사이의 흐름만 있다.
"""

O, X, U = "O", "X", "?"          # 해당 / 비해당 / 모르겠음
LABELS = ("noise", "valid", "issue", "hold")
LABEL_KO = {"noise": "노이즈", "valid": "유효", "issue": "이슈", "hold": "보류"}


class RuleError(ValueError):
    """기준 정의 자체가 잘못된 경우 — 조용히 넘기지 않고 즉시 알린다."""


def criteria_of(task: dict) -> list[dict]:
    return list(task.get("criteria") or [])


def by_label(task: dict) -> dict:
    """{등급: [기준…]} — 화면이 등급별로 묶어 보여줄 때 쓴다."""
    g = {lab: [] for lab in LABELS}
    for c in criteria_of(task):
        if c.get("label") in g:
            g[c["label"]].append(c)
    return g


# ---------------------------------------------------------------- 답변 정규화
def _recover_keys(ans: dict, task: dict) -> tuple[dict, list[str]]:
    """모델이 키를 틀리게 넣었을 때 되살린다.

    번호 키는 **추측하지 않는다** — 렌더링에 따라 한 칸씩 밀린 매핑이 조용히 만들어진다
    (2026-08-24 실측). 대신 사용 불가로 판정해 교정 재요청을 유발한다.
    """
    ids = [c["id"] for c in criteria_of(task)]
    by_norm = {i.lower().replace(" ", "").replace("-", "_"): i for i in ids}
    by_when = {" ".join(str(c.get("when", "")).split())[:40]: c["id"] for c in criteria_of(task)}

    out, notes = {}, []
    for k, v in (ans or {}).items():
        key = str(k).strip()
        if key in ids:
            out[key] = v
            continue
        if key.lstrip("#").strip().isdigit():
            notes.append(f"번호 키 {key!r} — 매핑 불가(재요청 필요)")
            continue
        nk = key.lower().replace(" ", "").replace("-", "_")
        if nk in by_norm:
            out[by_norm[nk]] = v
            notes.append(f"표기 차이 {key!r} → {by_norm[nk]}")
            continue
        hit = next((cid for w, cid in by_when.items() if key[:40] == w), None)
        if hit:
            out[hit] = v
            notes.append(f"문장 키 → {hit}")
            continue
        notes.append(f"알 수 없는 키 무시: {key[:30]!r}")
    return out, notes


def answers_usable(raw_answers: dict, task: dict) -> bool:
    """모델 답변이 쓸 만한가 — 기준 id 와 겹치는 게 절반 이상인지."""
    ids = set(c["id"] for c in criteria_of(task))
    rec, _ = _recover_keys(raw_answers or {}, task)
    return len(set(rec) & ids) >= max(1, len(ids) // 2)


def normalize(answers: dict, task: dict) -> tuple[dict, list[str]]:
    """AI 답변을 기준 목록에 맞춰 보정한다. 빠진 항목·불량 값은 ?(모르겠음).

    모든 기준은 AI가 답한다 — 엔진이 대신 판단하는 기준은 없다(2026-08-24).
    원문 확보에 실패한 경우는 등급이 아니라 `근거등급`과 `신뢰도`로 표시한다.
    """
    recovered, notes = _recover_keys(
        {str(k): str(v).strip().upper() for k, v in (answers or {}).items()}, task)
    out, warn, n_missing = {}, list(notes), 0
    for c in criteria_of(task):
        cid = c["id"]
        v = recovered.get(cid)
        if v in (O, X, U):
            out[cid] = v
        else:
            n_missing += 1
            out[cid] = U
    if n_missing:
        warn.append(f"답변 누락·불량 {n_missing}개 → 모르겠음")
    asked = len(criteria_of(task))
    if asked and n_missing >= asked:
        warn.insert(0, f"⚠️ 답변을 하나도 못 받았다({asked}개 전부) — 추출 실패로 봐야 한다")
    return out, warn


# ---------------------------------------------------------------- 판정
def _short(c: dict, n: int = 90) -> str:
    w = " ".join(str(c.get("when", "")).split())
    return w if len(w) <= n else w[:n] + "…"


def _pick(hits: list, extra: str = "") -> dict:
    c = hits[0]
    note = extra
    if len(hits) > 1:
        more = f"같은 등급의 다른 기준도 해당: {len(hits)-1}개"
        note = (note + " · " if note else "") + more
    return {"label": c["label"], "criterion_id": c["id"], "criterion": _short(c),
            "reason": _short(c), "note": note}


def evaluate(answers: dict, task: dict) -> dict:
    """정규화된 답변 → 판정.

    반환: {label, criterion_id, criterion, reason, note, step, matched, unknown}
      step: 어느 단계에서 정해졌는지 (보류 / 노이즈판단 / 이슈판단 / 유효)
    """
    items = criteria_of(task)
    if not items:
        raise RuleError("판정 기준(criteria)이 비어 있다")
    g = by_label(task)

    def hits(lab):
        return [c for c in g[lab] if answers.get(c["id"], U) == O]

    def unk(lab):
        return [c["id"] for c in g[lab] if answers.get(c["id"], U) == U]

    h_hold, h_noise, h_issue = hits("hold"), hits("noise"), hits("issue")
    u_hold, u_noise, u_issue = unk("hold"), unk("noise"), unk("issue")
    base = {"matched": {lab: [c["id"] for c in hits(lab)] for lab in LABELS if hits(lab)},
            "unknown": [c["id"] for c in items if answers.get(c["id"], U) == U]}

    # ① 보류 조건은 어느 단계에서든 먼저
    if h_hold:
        return {**base, "step": "보류", **_pick(h_hold)}

    # ② 노이즈와 이슈가 동시에 해당 — 버리지도 올리지도 않는다
    if h_noise and h_issue:
        return {**base, "step": "보류", "label": "hold", "criterion_id": "판단충돌",
                "criterion": f"노이즈 기준과 이슈 기준에 동시에 해당한다",
                "reason": f"노이즈 「{_short(h_noise[0], 60)}」와 "
                          f"이슈 「{_short(h_issue[0], 60)}」가 함께 해당해 판단이 서지 않는다.",
                "note": "사람이 확인해야 한다"}

    # ③ 1단계 — 노이즈인가
    if h_noise:
        if u_hold or u_issue:
            return {**base, "step": "보류", "label": "hold", "criterion_id": "판단불가",
                    "criterion": "노이즈로 볼 수 있으나 판단하지 못한 기준이 남아 있다",
                    "reason": f"「{_short(h_noise[0], 60)}」에 해당하나, "
                              f"판단 못 한 기준 {len(u_hold)+len(u_issue)}개가 있어 버리지 않는다.",
                    "note": "모르는 상태에서 버리는 것은 되돌릴 수 없다"}
        return {**base, "step": "노이즈판단", **_pick(h_noise)}

    # ④ 2단계 — 유효 중에 이슈인가
    if h_issue:
        return {**base, "step": "이슈판단", **_pick(h_issue)}

    # ⑤ 유효 기준에 해당 — '왜 유효인가'의 근거로 쓴다
    h_valid = hits("valid")
    if h_valid:
        return {**base, "step": "유효", **_pick(h_valid)}

    # ⑥ 어느 기준에도 해당하지 않음 → 보류. 판단이 서지 않은 것이므로 넘기지 않는다.
    if u_issue:
        return {**base, "step": "보류", "label": "hold", "criterion_id": "이슈판단불가",
                "criterion": "노이즈는 아니나 이슈 여부를 판단할 수 없다",
                "reason": f"이슈 기준 {len(u_issue)}개를 판단하지 못해 확정하지 않는다.",
                "note": "이슈를 놓치지 않기 위해 사람에게 넘긴다"}
    return {**base, "step": "보류", "label": "hold", "criterion_id": "판단없음",
            "criterion": "어느 기준에도 해당하지 않는다",
            "reason": "노이즈·이슈·유효 어느 기준에도 해당한다고 판단되지 않았다.",
            "note": "기준에 없는 유형인지 확인이 필요하다"}


def trace(answers: dict, task: dict) -> list[dict]:
    """판정 과정 — 단계별로 무엇에 해당했는지. 번호는 매기지 않는다."""
    v = evaluate(answers, task)
    g = by_label(task)
    steps = [("노이즈판단", "1단계 · 노이즈인가?", "noise"),
             ("이슈판단", "2단계 · 이슈인가?", "issue"),
             ("유효", "유효 근거", "valid"),
             ("보류", "판단이 안 서면 · 보류", "hold")]
    out = []
    for key, title, lab in steps:
        rows = []
        for c in g[lab]:
            a = answers.get(c["id"], U)
            rows.append({"id": c["id"], "answer": a, "when": _short(c, 150),
                         "decided": c["id"] == v.get("criterion_id")})
        if rows:
            out.append({"key": key, "title": title, "label": lab, "items": rows,
                        "n_hit": sum(1 for r in rows if r["answer"] == O),
                        "n_unknown": sum(1 for r in rows if r["answer"] == U),
                        "decided": v.get("step") == key})
    return out


def lint(task: dict) -> list[str]:
    """기준 정의를 검사한다(실행 전 점검)."""
    problems, seen = [], set()
    items = criteria_of(task)
    if not items:
        problems.append("판정 기준(criteria)이 비어 있다")
    for i, c in enumerate(items):
        cid = c.get("id") or f"(id없음 #{i+1})"
        if cid in seen:
            problems.append(f"{cid}: id 중복")
        seen.add(cid)
        if c.get("label") not in LABELS:
            problems.append(f"{cid}: label 이 {LABELS} 중 하나가 아님 → {c.get('label')!r}")
        if not str(c.get("when") or "").strip():
            problems.append(f"{cid}: 기준 문장이 비어 있다")
    g = by_label(task)
    if items and not g["noise"]:
        problems.append("노이즈 기준이 없다 — 아무것도 걸러지지 않는다")
    if items and not g["issue"]:
        problems.append("이슈 기준이 없다 — 이슈 등급이 절대 나오지 않는다")
    if items and not g["valid"]:
        problems.append("유효 기준이 없다 — 노이즈·이슈가 아닌 건이 전부 보류가 된다")
    return problems
