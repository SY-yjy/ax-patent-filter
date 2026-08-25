"""추출 에이전트 — 원문에서 **사실만** 구조화해 뽑는다. 등급은 정하지 않는다.

  extract_facts        : 원문 청구항 → {tech_summary, answers(기준별 O/X/?), evidence,
                         collect, independent_claims, notes}
  read_claims_from_scan: 스캔 이미지 PDF → 청구항 원문 전사 (Read 도구가 페이지를 이미지로 읽음)

AI는 **판정 기준 하나하나에 O(해당)/X(비해당)/?(모르겠음)** 만 답한다. 등급은 rules.py 가
기준 순서대로(첫 O) 결정한다 → 같은 답변이면 항상 같은 등급.
"""
import re
import json
import asyncio
from pathlib import Path
import anthropic
import config
import rules

_client = None  # API 경로에서만 지연 생성 (구독 모드에선 키가 없어 생성 시 에러날 수 있음)


def _api_client():
    global _client
    if _client is None:
        _client = anthropic.Anthropic()  # ANTHROPIC_API_KEY 필요
    return _client


# --- 프롬프트는 prompts/*.md 로 외부화 (코드와 분리, 비개발자도 읽고 수정 가능) ---
# 파일 내용 = 에이전트가 받는 system 프롬프트 그대로. 수정하면 다음 실행부터 바로 반영.
_PROMPTS_DIR = Path(__file__).parent / "prompts"


def _load_prompt(fname: str) -> str:
    return (_PROMPTS_DIR / fname).read_text(encoding="utf-8").strip()


SYS_EXTRACT = _load_prompt("추출.md")
SYS_SCAN = _load_prompt("스캔판독.md")   # 스캔 이미지 PDF → 청구항 전사

# --- 실측 집계 ---
_PRICE = config.PRICES          # {model: (input, output)} — 단가는 config.yaml
USAGE = {}                      # model -> {"in":int, "out":int, "calls":int}
PARSE_FAILS = []                # JSON 파싱 실패 원문 (조용한 실패 방지 — 실행 리포트에 노출)


def reset_usage():
    USAGE.clear()
    PARSE_FAILS.clear()


def usage_report() -> dict:
    total = 0.0
    lines = {}
    for model, u in USAGE.items():
        pin, pout = _PRICE.get(model, (0.0, 0.0))
        cost = u["in"] / 1e6 * pin + u["out"] / 1e6 * pout
        total += cost
        lines[model] = {**u, "cost_usd": round(cost, 4)}
    return {"per_model": lines, "total_usd": round(total, 4), "parse_fails": len(PARSE_FAILS)}


def _track(model: str, tin: int, tout: int):
    u = USAGE.setdefault(model, {"in": 0, "out": 0, "calls": 0})
    u["in"] += tin or 0
    u["out"] += tout or 0
    u["calls"] += 1


def _run_async(coro):
    """Streamlit 등 이미 이벤트루프가 도는 환경에서도 안전하게 코루틴 실행."""
    try:
        asyncio.get_running_loop()
    except RuntimeError:
        return asyncio.run(coro)  # 실행 중 루프 없음 → 정상 경로
    import threading
    box = {}
    def _worker():
        try:
            box["v"] = asyncio.run(coro)
        except BaseException as e:      # 스레드 예외를 삼키지 말고 호출자에게 올린다
            box["e"] = e
    t = threading.Thread(target=_worker)
    t.start(); t.join()
    if "e" in box:
        raise box["e"]
    return box["v"]


def _usage_tokens(usage):
    """SDK usage(dict 또는 객체)에서 입력/출력 토큰 최대한 추출."""
    if not usage:
        return 0, 0
    def g(k):
        if isinstance(usage, dict):
            return usage.get(k, 0) or 0
        return getattr(usage, k, 0) or 0
    # 구독 경로는 프롬프트 캐시를 쓰므로 캐시 생성·조회분까지 입력으로 합산
    tin = g("input_tokens") + g("cache_creation_input_tokens") + g("cache_read_input_tokens")
    return tin, g("output_tokens")


def _ask_api(model: str, system: str, user: str) -> str:
    """API 경로: anthropic SDK + API 키(per-token 과금)."""
    msg = _api_client().messages.create(
        model=model, max_tokens=1000, system=system,
        messages=[{"role": "user", "content": user}],
    )
    _track(model, msg.usage.input_tokens, msg.usage.output_tokens)
    return msg.content[0].text.strip()


def _emit(on_event, kind: str, payload):
    """UI 등 외부에 진행 상황을 알린다. 콜백이 죽어도 판정은 계속한다."""
    if on_event:
        try:
            on_event(kind, payload)
        except Exception:
            pass


def _ask_subscription(model: str, system: str, user: str, on_event=None,
                      tools: list[str] | None = None, thinking: bool = False,
                      max_turns: int | None = None) -> str:
    """구독 경로: Claude Agent SDK → 로컬 Claude Code 인증(구독 사용량).

    ⚠️ 옵션 4개를 반드시 함께 넘긴다. 하나라도 빠지면 CLI가 자기 시스템 프롬프트·도구 정의·
    스킬 목록·CLAUDE.md 를 프롬프트에 실어 보낸다(실측 29,162토큰 → 4개 지정 시 215토큰).
    판정이 프롬프트 파일만의 함수가 아니게 되어 재현이 깨지고 구독 쿼터도 낭비된다.

    on_event(kind, payload) 로 진행을 흘려보낸다 — 발표 시연에서 에이전트의 사고 과정을
    실시간으로 보여주는 데 쓴다.
      kind: "thinking"(사고) · "text"(응답 조각) · "tool"(도구 호출) · "usage"(토큰)
    tools 를 주면 그 도구만 허용한다(스캔 판독의 Read). thinking=True 면 사고 블록을 받는다.
    """
    from claude_agent_sdk import query, ClaudeAgentOptions  # lazy import

    async def _run() -> str:
        parts = []
        opt = dict(model=model, system_prompt=system,
                   setting_sources=[], skills=[],      # 설정·CLAUDE.md·스킬 주입 차단
                   max_buffer_size=config.MAX_BUFFER_SIZE)   # 기본 1MB 는 스캔 판독에 부족
        if tools:
            opt.update(allowed_tools=list(tools), permission_mode="bypassPermissions")
        else:
            opt.update(allowed_tools=[], tools=[])     # 도구 정의를 프롬프트에서 제외
        if max_turns:
            opt["max_turns"] = max_turns
        if thinking:
            opt["thinking"] = {"type": "adaptive"}
        if on_event:
            opt["include_partial_messages"] = True   # 토큰 단위 델타 → 실시간 표시
        opts = ClaudeAgentOptions(**opt)

        async for m in query(prompt=user, options=opts):
            if type(m).__name__ == "StreamEvent":
                e = getattr(m, "event", {}) or {}
                if e.get("type") == "content_block_delta":
                    d = e.get("delta") or {}
                    frag = d.get("text") or d.get("partial_json") or d.get("thinking") or ""
                    if frag:
                        _emit(on_event, "delta", frag)
                continue
            for b in getattr(m, "content", []) or []:
                bt = type(b).__name__
                if bt == "ThinkingBlock":
                    _emit(on_event, "thinking", getattr(b, "thinking", "") or "")
                elif bt == "ToolUseBlock":
                    inp = getattr(b, "input", {}) or {}
                    brief = ", ".join(f"{k}={str(v)[:60]}" for k, v in list(inp.items())[:3])
                    _emit(on_event, "tool", f"{getattr(b,'name','?')}({brief})")
                else:
                    t = getattr(b, "text", None)
                    if t:
                        parts.append(t)
                        _emit(on_event, "text", t)
            if type(m).__name__ == "ResultMessage":
                tin, tout = _usage_tokens(getattr(m, "usage", None))
                _track(model, tin, tout)
                _emit(on_event, "usage", {"in": tin, "out": tout})
                if not parts:
                    parts.append(getattr(m, "result", "") or "")
        return "\n".join(parts)

    return (_run_async(_run()) or "").strip()


def _ask(model: str, system: str, user: str, on_event=None) -> dict:
    raw = _ask_subscription(model, system, user, on_event=on_event,
                            thinking=config.SHOW_THINKING) if config.USE_SUBSCRIPTION \
        else _ask_api(model, system, user)
    body = raw
    if "THINKING>>>" in body:                   # 판단 과정 서술은 잘라낸다(중괄호 오탐 방지)
        body = body.split("THINKING>>>", 1)[1]
    m = body[body.find("{"): body.rfind("}") + 1]  # JSON 블록만 (```json 펜스 대응)
    try:
        out = json.loads(m)
        out["_narration"] = narration_of(raw)   # 판단 과정 서술 (화면·기록용)
        return out
    except Exception as e:
        PARSE_FAILS.append(raw[:500])

        # 추출 실패 = 답을 못 얻은 것. answers 를 비워두면 전부 '모르겠음' → 보류.
        return {"_parse_failed": True, "tech_summary": "", "_narration": narration_of(raw),
                "answers": {}, "evidence": {}, "collect": {},
                "independent_claims": [],
                "notes": f"추출 JSON 파싱실패({type(e).__name__}): {raw[:150]}"}


_CLAIMS_BLOCK = re.compile(r"<<<CLAIMS(.*?)CLAIMS>>>", re.S)
_THINK_BLOCK = re.compile(r"<<<THINKING(.*?)THINKING>>>", re.S)


def narration_of(raw: str) -> str:
    """응답에서 판단 과정 서술만 뽑는다(있으면)."""
    m = _THINK_BLOCK.search(raw or "")
    return m.group(1).strip() if m else ""


def read_claims_from_scan(pdf_path: str, on_event=None) -> str:
    """스캔 이미지 PDF에서 청구항 섹션을 읽어 원문 그대로 돌려준다. 실패 시 "".

    `claude` CLI의 Read 도구가 PDF 페이지를 이미지로 읽으므로 **별도 OCR 엔진이 필요 없다.**
    ⚠️ 텍스트 PDF 판정 대비 토큰·시간이 60배 수준(실측 2026-08-21: 231,517토큰 · 68초 · Read 10회).
       → 호출자는 결과를 **반드시 캐시**해서 특허당 한 번만 지불해야 한다.
    ⚠️ 구독 경로 전용. API 모드는 PDF를 이미지로 렌더할 수단이 없어 지원하지 않는다.

    on_event 로 Read 호출이 실시간으로 흘러나온다 — 에이전트가 뒷페이지부터 훑어
    청구항을 찾아가는 과정이 시연의 핵심 장면이다.
    """
    if not config.USE_SUBSCRIPTION:
        return ""
    raw = _ask_subscription(
        config.MODEL_JUDGE, SYS_SCAN,
        f"파일: {pdf_path}\n이 PDF의 청구항 섹션을 지시대로 전사하라.",
        on_event=on_event, tools=["Read"], max_turns=config.SCAN_MAX_TURNS,
        thinking=config.SHOW_THINKING)
    m = _CLAIMS_BLOCK.search(raw or "")
    return m.group(1).strip() if m else ""


def extract_facts(rec: dict, claims_text: str, criteria_text: str, evidence: str,
                  on_event=None, task: dict | None = None) -> dict:
    """원문 → 구조화된 사실. **등급은 정하지 않는다**(rules.py 담당).

    criteria_text = criteria.render_for_extract(task) — 검토대상·판정기준·동의어.
    evidence(근거등급)를 알려줘 폴백 건은 unclear 를 적극적으로 쓰게 한다.
    지침(system)은 prompts/추출.md 에서 로드.
    """
    hint = ("원문 청구항 전체를 보고 있다." if str(evidence).startswith("원문")
            else "원문을 확보하지 못해 대표청구항(독립항 1항)만 보고 있다. "
                 "근거가 부족한 항목은 반드시 unclear 로 두어라.")
    user = (f"{criteria_text}\n\n"
            f"[특허]\n명칭: {rec.get('title')}\n국가: {rec.get('country')}\n"
            f"근거등급: {evidence} — {hint}\n\n"
            f"[청구항]\n{claims_text[:config.MAX_CLAIM_CHARS]}")
    out = _ask(config.MODEL_JUDGE, SYS_EXTRACT, user, on_event=on_event)

    # 답변 키가 기준 id 와 안 맞으면(모델이 번호 등으로 키잉) 1회 교정 재시도.
    # 이걸 안 하면 전 건이 조용히 보류로 떨어진다(2026-08-24 실측).
    if task is not None and not rules.answers_usable(out.get("answers"), task):
        ids = [c["id"] for c in (task.get("criteria") or [])]
        _emit(on_event, "stage", "답변 키가 기준과 맞지 않아 교정 재요청")
        fix = (user + "\n\n[교정 요청]\n직전 답변의 answers 키가 기준 id 와 맞지 않았다.\n"
               "아래 id 목록을 **그대로 키로 사용해** 다시 답하라. 번호나 문장을 키로 쓰지 마라.\n"
               + "\n".join(ids))
        retry = _ask(config.MODEL_JUDGE, SYS_EXTRACT, fix, on_event=on_event)
        if rules.answers_usable(retry.get("answers"), task):
            retry["_retried"] = True
            return retry
        out["_retry_failed"] = True
    return out
