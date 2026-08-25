"""정의되지 않은 이름 검사 — NameError 를 실행 전에 잡는다.

Streamlit은 화면을 눌러야 그 코드가 실행되므로, 함수 안의 NameError 가
사용자 클릭 시점에야 터진다(2026-08-24: BRAND_050 미정의로 실제 발생).
여기서 각 모듈의 **함수 본문까지** 훑어 모듈 전역에 없는 참조를 찾아낸다.

실행:  /opt/anaconda3/bin/python tests/test_names.py
"""
import sys, ast, builtins, pathlib

ROOT = pathlib.Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "engine"))

MODULES = ["theme", "config", "criteria", "rules", "excel_loader", "claims_extractor",
           "wips_downloader", "agent", "pipeline", "excel_export",
           "ui_common", "ui_task_editor", "ui_app"]


def _local_names(fn: ast.AST) -> set:
    """함수 안에서 새로 만들어지는 이름(인자·대입·for·with·except·comprehension)."""
    out = set()
    if isinstance(fn, (ast.FunctionDef, ast.AsyncFunctionDef, ast.Lambda)):
        a = fn.args
        for arg in list(a.posonlyargs) + list(a.args) + list(a.kwonlyargs):
            out.add(arg.arg)
        for x in (a.vararg, a.kwarg):
            if x:
                out.add(x.arg)
    for n in ast.walk(fn):
        if isinstance(n, ast.Name) and isinstance(n.ctx, (ast.Store, ast.Del)):
            out.add(n.id)
        elif isinstance(n, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef)):
            out.add(n.name)
        elif isinstance(n, ast.ExceptHandler) and n.name:
            out.add(n.name)
        elif isinstance(n, ast.alias):
            out.add((n.asname or n.name).split(".")[0])
        elif isinstance(n, ast.Global) or isinstance(n, ast.Nonlocal):
            out.update(n.names)
    return out


def _own_body(fn):
    """이 함수 자신의 본문 노드만 (중첩 함수 안으로는 들어가지 않는다).

    중첩 함수는 별도로 검사되므로, 그 인자를 바깥 함수의 미정의 참조로 세면 안 된다.
    """
    stack = list(ast.iter_child_nodes(fn))
    while stack:
        n = stack.pop()
        if isinstance(n, (ast.FunctionDef, ast.AsyncFunctionDef, ast.Lambda)):
            continue                      # 경계에서 멈춘다
        yield n
        stack.extend(ast.iter_child_nodes(n))


def check(name: str) -> list[str]:
    """함수마다 '자기 지역변수 + 바깥 함수들의 지역변수 + 모듈 전역 + 빌트인' 밖의 참조를 찾는다.

    중첩 함수(클로저)가 바깥 변수를 쓰는 것은 정상이므로 조상 함수의 지역변수를 함께 본다.
    """
    mod = __import__(name)
    src = (ROOT / "engine" / f"{name}.py").read_text(encoding="utf-8")
    tree = ast.parse(src)

    parent = {}
    for node in ast.walk(tree):
        for child in ast.iter_child_nodes(node):
            parent[child] = node

    def enclosing_locals(fn):
        names, cur = set(), fn
        while cur is not None:
            if isinstance(cur, (ast.FunctionDef, ast.AsyncFunctionDef, ast.Lambda)):
                names |= _local_names(cur)
            elif isinstance(cur, ast.ClassDef):
                names.add(cur.name)
            cur = parent.get(cur)
        return names

    problems = []
    for node in ast.walk(tree):
        if not isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
            continue
        scope = enclosing_locals(node)
        for n in _own_body(node):
            if not (isinstance(n, ast.Name) and isinstance(n.ctx, ast.Load)):
                continue
            nm = n.id
            if nm in scope or hasattr(mod, nm) or hasattr(builtins, nm):
                continue
            # 컴프리헨션 변수는 별도 스코프 — 해당 노드 안에서 선언됐는지 확인
            problems.append(f"{name}.{node.name}() 줄 {n.lineno}: '{nm}' 정의 없음")
    return sorted(set(problems))


def main() -> int:
    total = []
    for m in MODULES:
        try:
            probs = check(m)
        except Exception as e:
            probs = [f"{m}: 검사 실패 {type(e).__name__}: {e}"]
        print(f"{'✅' if not probs else '❌'} {m}"
              + ("" if not probs else f"  ({len(probs)}건)"))
        for p in probs:
            print(f"     {p}")
        total += probs
    print(f"\n모듈 {len(MODULES)}개 → {'전부 통과' if not total else f'미정의 {len(total)}건'}")
    return 1 if total else 0


if __name__ == "__main__":
    sys.exit(main())
