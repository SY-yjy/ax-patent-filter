"""과제 판정기준 로더 — tasks/*.yaml 이 과제별 단일 출처. 엔진은 과제에 무관하다.

과제 yaml(v2) 구조:
    scope            검토 대상 정의 · 대상 신호 · 메커니즘 · 접착요소 · 명백노이즈 유형
    criteria         **순서 있는 판정 기준 목록** — 각 줄이 하나의 기준, 첫 '해당'이 등급을 정한다
    default          어느 기준에도 해당하지 않을 때의 등급
    extract.collect  수집 항목 (판정에 쓰지 않고 값만 뽑는다)
    synonyms         동의어 — 키워드와 같은 뜻으로 쓰이는 표현 목록

이 모듈은 그걸 읽어 **추출 프롬프트에 넣는 텍스트**로 렌더링한다.
DOD 등 특정 과제 지식은 여기 없다 — 전부 tasks/ 안에 있다.
"""
from pathlib import Path
import yaml

TASKS_DIR = Path(__file__).parent.parent / "tasks"   # repo 루트/tasks (engine 밖)


TEMPLATE_NAME = "_템플릿"


def list_tasks() -> list[str]:
    """과제 목록. `_` 로 시작하는 파일은 템플릿이라 제외한다."""
    return sorted(p.stem for p in TASKS_DIR.glob("*.yaml") if not p.stem.startswith("_"))


def load_template() -> dict:
    """새 과제의 출발점. 없으면 최소 골격을 만들어 돌려준다."""
    p = TASKS_DIR / f"{TEMPLATE_NAME}.yaml"
    if p.is_file():
        with open(p, encoding="utf-8") as f:
            return yaml.safe_load(f) or {}
    return {"version": 3, "task": "", "sample_data": "",
            "scope": {"definition": "", "target_signals": [], "mechanisms": [],
                      "target_elements": [], "include_even_if_vague": ""},
            "criteria": [], "synonyms": [],
            "extract": {"collect": []}}


def delete_task(name: str) -> bool:
    p = TASKS_DIR / f"{name}.yaml"
    if p.is_file() and not name.startswith("_"):
        p.unlink()
        return True
    return False


def load_task(name: str) -> dict:
    p = Path(name) if str(name).endswith(".yaml") else TASKS_DIR / f"{name}.yaml"
    with open(p, encoding="utf-8") as f:
        t = yaml.safe_load(f) or {}
    if t.get("version") != 3:
        raise ValueError(f"과제 스키마 v3가 아니다: {p} (version={t.get('version')}). "
                         f"v2 파일은 criteria 를 순서 목록으로 바꿔야 한다.")
    return t


def _bullets(items, indent="  ") -> str:
    return "\n".join(f"{indent}· {x}" for x in (items or [])) or f"{indent}· (없음)"


LABEL_KO = {"noise": "노이즈", "valid": "유효", "issue": "이슈", "hold": "보류"}


def render_scope(task: dict) -> str:
    """[검토대상] — 과제 이름과 정의만.

    자사 기술 목록은 두지 않는다(2026-08-24). 자사 소재·조성은 이미 이슈 기준 문장에
    들어 있어서 두 군데에 적으면 어긋난다. 판정에 쓰이는 것은 `criteria` 뿐이다.
    """
    s = task.get("scope") or {}
    parts = [f"[과제] {str(task.get('task','')).strip()}"]
    if s.get("definition"):
        parts.append("검토 대상 기술의 정의:\n  " + " ".join(str(s["definition"]).split()))
    return "\n\n".join(parts)


def render_criteria(task: dict) -> str:
    """[판정기준] — AI가 하나씩 O/X/? 로 답할 목록.

    ⚠️ 표시용 번호를 붙이지 않는다. 번호를 붙였더니 모델이 answers 의 키를 **번호로**
       넣어 전부 미스매치가 났다(2026-08-24 실측: 37개 누락 + 미정의 키 1건).
       각 줄의 유일한 식별자는 `id` 이고, 그 문자열만 키로 쓰게 한다.
    """
    lines = []
    for c in task.get("criteria") or []:
        when = " ".join(str(c.get("when", "")).split())
        lines.append(f'  id="{c["id"]}"  ({LABEL_KO.get(c["label"], c["label"])})  {when}')
    return "\n".join(lines)


def render_info_spec(task: dict) -> str:
    """[수집항목] — 판정에 쓰지 않고 값만 뽑는 항목."""
    items = collect_names(task)
    if not items:
        return ""
    return ("[수집항목] (판정에 쓰지 않음. 원문에 있으면 값만 뽑고, 없으면 생략)\n"
            + _bullets(items))


def synonym_terms(row: dict) -> list[str]:
    """동의어 행 → 표현 목록. 옛 형식(detail 문자열, 줄바꿈·쉼표 구분)도 읽는다."""
    if isinstance(row.get("terms"), list):
        return [str(x).strip() for x in row["terms"] if str(x).strip()]
    raw = str(row.get("detail") or "")
    out = []
    for line in raw.replace(",", "\n").splitlines():
        v = line.strip()
        if v:
            out.append(v)
    return out


def render_synonyms(task: dict) -> str:
    """[동의어] — 같은 개념으로 쓰이는 다른 표현을 AI에게 알려준다."""
    rows = task.get("synonyms") or []
    if not rows:
        return ""
    out = ["아래 표현들은 같은 개념으로 본다. 원문에 어떤 표현으로 적혀 있든 같은 개념으로 읽어라."]
    for r in rows:
        kw = str(r.get("keyword") or "").strip()
        terms = synonym_terms(r)
        if not kw:
            continue
        field = str(r.get("field") or "").strip()
        head = f"· {kw}" + (f" (찾는 곳: {field})" if field else "")
        out.append(head)
        if terms:
            out.append("    = " + ", ".join(terms))
    return "\n".join(out)


def render_for_extract(task: dict) -> str:
    """추출 프롬프트의 user 메시지 전문."""
    blocks = [f"[검토대상]\n{render_scope(task)}",
              "[판정기준] — 각 항목에 O(해당)/X(비해당)/?(모르겠음) 으로 답하라. "
              "등급은 정하지 말 것.\n" + render_criteria(task)]
    info = render_info_spec(task)
    if info:
        blocks.append(info)
    syn = render_synonyms(task)
    if syn:
        blocks.append(f"[동의어]\n{syn}")
    return "\n\n".join(blocks)


def criteria_ids(task: dict) -> list[str]:
    return [c["id"] for c in (task.get("criteria") or [])]


_ID_TOKEN = None


def humanize(text: str, task: dict) -> str:
    """서술문에 섞인 기준 id 를 기준 문장으로 바꾼다.

    모델에게 서술에는 id 를 쓰지 말라고 지시하지만 지시는 어겨질 수 있다.
    화면·엑셀·마크다운에 `c_i1` 같은 내부 식별자가 새어나가면 안 되므로
    저장 직전에 한 번 더 결정적으로 치환한다(하네스).
    """
    if not text:
        return text
    import re
    items = task.get("criteria") or []
    if not items:
        return text
    by_id = {str(c.get("id")): c for c in items if c.get("id")}
    if not by_id:
        return text
    # 긴 id 를 먼저 — c_i1 이 c_i10 의 앞부분을 먹지 않게
    pat = re.compile(r"(?<![0-9A-Za-z_])(" +
                     "|".join(re.escape(k) for k in sorted(by_id, key=len, reverse=True)) +
                     r")(?![0-9A-Za-z_])")

    def _rep(m):
        c = by_id[m.group(1)]
        txt = " ".join(str(c.get("when") or "").split())
        return f"「{txt[:70]}」" if txt else m.group(1)

    text = pat.sub(_rep, text)

    # 지금은 없는 기준(삭제·이름변경된 id)도 화면에 내보내지 않는다.
    # 예전 실행 기록에는 그때 존재하던 id 가 남아 있다.
    return re.sub(r"(?<![0-9A-Za-z_])c_[A-Za-z]{1,4}\d{1,3}(?![0-9A-Za-z_])",
                  "「지금은 없는 기준」", text)


def collect_names(task: dict) -> list[str]:
    """수집 항목 목록. 옛 구조(fields + properties)도 읽어 합친다."""
    e = task.get("extract") or {}
    if e.get("collect"):
        return list(e["collect"])
    return list((e.get("fields") or {}).keys()) + list(e.get("properties") or [])


def save_task(name: str, task: dict) -> Path:
    TASKS_DIR.mkdir(exist_ok=True)
    path = TASKS_DIR / f"{name}.yaml"
    with open(path, "w", encoding="utf-8") as f:
        yaml.safe_dump(task, f, allow_unicode=True, sort_keys=False)
    return path
