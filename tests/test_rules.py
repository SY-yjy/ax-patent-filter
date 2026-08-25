"""판정 엔진 회귀 테스트 — 2026-08-24 확정 흐름.

  1단계  노이즈인가?         → 노이즈 / 아니면 유효로 남김
  2단계  유효 중 이슈인가?    → 이슈 / 아니면 유효
  언제든 판단이 안 서면        → 보류

기준 하나하나에 순서는 없다. '기본 등급' 설정도 없다 — 판단이 안 되면 보류다.

실행:  /opt/anaconda3/bin/python tests/test_rules.py
"""
import sys, pathlib
ROOT = pathlib.Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "engine"))
import yaml
import rules as R

T = yaml.safe_load(open(ROOT / "tasks/dod.yaml", encoding="utf-8"))
ALL = [c["id"] for c in R.criteria_of(T)]
G = R.by_label(T)


def cid(label, frag):
    for c in G[label]:
        if frag in " ".join(str(c.get("when", "")).split()):
            return c["id"]
    raise AssertionError(f"{label} 기준에 '{frag}' 없음")


H_구조식 = cid("hold", "화학구조식")
H_광범위 = cid("hold", "지나치게 광범위")
H_불명확 = cid("hold", "의미가 불명확")
I_청구항 = cid("issue", "독립청구항에 이온성 액체")
I_실험 = cid("issue", "실험 데이터")
N_배터리 = cid("noise", "배터리·전해커패시터")
N_비접착 = cid("noise", "접착 관련 요소가 아예 없는")
N_이온없음 = cid("noise", "명세서 전문에 없음")
N_소자내부 = cid("noise", "전기화학 소자의 내부 구성요소")
V_관련 = cid("valid", "노이즈 기준에 해당하지 않는다")


def ans(**over):
    a = {c: R.X for c in ALL}
    for k, v in over.items():
        assert k in a, f"없는 기준 id: {k}"
        a[k] = v
    return a


CASES = [
    # 1단계 — 노이즈 판단
    ("1단계: 배터리 전용 → 노이즈", ans(**{N_배터리: R.O}), "noise", "노이즈판단"),
    ("1단계: 접착 요소 없음 → 노이즈", ans(**{N_비접착: R.O}), "noise", "노이즈판단"),
    ("1단계: 이온성 액체 없음 → 노이즈", ans(**{N_이온없음: R.O}), "noise", "노이즈판단"),

    # 2단계 — 유효 중 이슈 판단
    ("2단계: 청구항에 이온성액체+수지 → 이슈", ans(**{I_청구항: R.O}), "issue", "이슈판단"),
    ("2단계: 실험데이터에 이온성액체+수지 → 이슈", ans(**{I_실험: R.O}), "issue", "이슈판단"),
    ("1단계: 전기화학 소자 내부 구성요소 → 노이즈",
     ans(**{N_소자내부: R.O}), "noise", "노이즈판단"),
    ("소자 내부 구성요소인데 이슈 조성도 있음 → 판단충돌로 보류",
     ans(**{N_소자내부: R.O, I_청구항: R.O}), "hold", "보류"),
    ("소자 내부 구성요소 아님 + 이슈 조성 → 이슈",
     ans(**{N_소자내부: R.X, I_청구항: R.O}), "issue", "이슈판단"),
    ("2단계: 독립항에 이온성액체+수지 → 이슈", ans(**{I_청구항: R.O}), "issue", "이슈판단"),

    # 유효
    ("유효 기준 해당 → 유효", ans(**{V_관련: R.O}), "valid", "유효"),
    ("어느 기준에도 해당 없으면 → 보류", ans(), "hold", "보류"),
    ("이슈가 유효보다 먼저", ans(**{I_청구항: R.O, V_관련: R.O}), "issue", "이슈판단"),
    ("노이즈가 유효보다 먼저", ans(**{N_비접착: R.O, V_관련: R.O}), "noise", "노이즈판단"),

    # 보류 — 어느 단계에서든
    ("보류: 구조식·이미지만", ans(**{H_구조식: R.O}), "hold", "보류"),
    ("보류: 독립항 광범위", ans(**{H_광범위: R.O}), "hold", "보류"),
    ("보류: 청구항 의미 불명확", ans(**{H_불명확: R.O}), "hold", "보류"),
    ("보류가 노이즈보다 먼저", ans(**{H_구조식: R.O, N_비접착: R.O}), "hold", "보류"),
    ("보류가 이슈보다 먼저", ans(**{H_광범위: R.O, I_청구항: R.O}), "hold", "보류"),

    # 노이즈·이슈 동시 해당 → 모순이므로 보류
    ("노이즈와 이슈가 동시에 해당 → 보류(판단충돌)",
     ans(**{N_이온없음: R.O, I_청구항: R.O}), "hold", "보류"),

    # 모르겠음 — 버리지 않는다 / 이슈를 놓치지 않는다
    ("노이즈 해당 + 이슈 기준 모르겠음 → 보류(버리지 않음)",
     ans(**{N_비접착: R.O, I_청구항: R.U}), "hold", "보류"),
    ("노이즈 해당 + 보류 기준 모르겠음 → 보류",
     ans(**{N_비접착: R.O, H_구조식: R.U}), "hold", "보류"),
    ("아무것도 해당 없고 이슈 기준 모르겠음 → 보류(이슈 누락 방지)",
     ans(**{I_청구항: R.U}), "hold", "보류"),
    ("이슈 해당 + 노이즈 기준 모르겠음 → 이슈 (올리는 건 안전)",
     ans(**{I_청구항: R.O, N_이온없음: R.U}), "issue", "이슈판단"),
]


def test_scope_harness():
    """이슈 기준은 독립청구항을 근거로 한다 — 문장과 프롬프트 양쪽에 걸려 있어야 한다."""
    import sys, os
    sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "engine"))
    import agent
    bad = []
    for c in R.by_label(T)["issue"]:
        w = str(c.get("when") or "")
        if "명세서" in w:
            continue                      # 실험데이터 기준은 명세서 전체가 근거다
        if "독립청구항" not in w:
            bad.append(f'{c["id"]}: 근거 범위가 독립청구항으로 못박혀 있지 않다')
    for frag in ("기준이 근거 범위를 못박은 경우", "독립청구항 본문에서만"):
        if frag not in agent.SYS_EXTRACT:
            bad.append(f"추출 프롬프트에 '{frag}' 규칙이 없다")
    for b in bad:
        print("  ❌", b)
    print("✅ 근거 범위 하네스" if not bad else f"❌ 근거 범위 하네스 {len(bad)}건")
    return bad


def main() -> int:
    fails = []
    for p in R.lint(T):
        print(f"⚠️ 기준 정의: {p}")
        fails.append(f"lint: {p}")

    print("판정 흐름:  1단계 노이즈인가? → 2단계 이슈인가? → 아니면 유효 / 언제든 보류\n")
    for lab in ("noise", "valid", "issue", "hold"):
        for c in G[lab]:
            print(f"  {R.LABEL_KO[lab]:<4} · {' '.join(str(c['when']).split())[:64]}")
    print()

    for desc, a, exp_label, exp_step in CASES:
        v = R.evaluate(a, T)
        ok = v["label"] == exp_label and v["step"] == exp_step
        print(f"{'✅' if ok else '❌'} {exp_label:<6} {v['step']:<8} {v['criterion_id']:<12} {desc}")
        if not ok:
            fails.append(f"{desc}: 기대 {exp_label}/{exp_step} → 실제 {v['label']}/{v['step']}")

    ok = not R.answers_usable({str(i): "O" for i in range(1, len(ALL))}, T)
    print(f"{'✅' if ok else '❌'} 안전   —          {'':<12} 번호 키 응답 → 교정 재요청 유발")
    if not ok:
        fails.append("번호 키를 사용 가능으로 오판")

    fails += test_scope_harness()

    print(f"\n기준 {len(ALL)}개 · 케이스 {len(CASES)}개 → "
          f"{'전부 통과' if not fails else '실패 ' + str(len(fails)) + '건'}")
    for f in fails:
        print(f"   ❌ {f}")
    return 1 if fails else 0


if __name__ == "__main__":
    sys.exit(main())
