"""전역 설정 로더 — 값은 config.yaml, 비밀(키)은 .env, 실행 로직만 여기.

다른 모듈은 config.MODEL_JUDGE / config.COLUMN_MAP 등으로 접근한다.
값을 바꾸려면 코드가 아니라 config.yaml 을 고친다.
"""
import os
from pathlib import Path
import yaml
from dotenv import load_dotenv

ENGINE_DIR = Path(__file__).parent        # engine/ (config.yaml·prompts 여기)
ROOT = ENGINE_DIR.parent                   # repo 루트 (.env·data·output·tasks 여기)
load_dotenv(ROOT / ".env")  # .env 로드 (ANTHROPIC_API_KEY) — 실행 위치(CWD) 무관

with open(ENGINE_DIR / "config.yaml", encoding="utf-8") as _f:
    _CFG = yaml.safe_load(_f)

# --- 모델 (전 건 원문 판정, 단일 단계) ---
MODEL_JUDGE = _CFG["models"]["judge"]

# --- 판정에 넣는 청구항 상한 (claims_extractor·agent 공용) ---
MAX_CLAIM_CHARS = _CFG["limits"]["max_claim_chars"]
SCAN_MAX_TURNS = _CFG["limits"]["scan_max_turns"]
# claude CLI ↔ SDK 사이 한 JSON 메시지의 최대 크기.
# SDK 기본값은 1MB 인데 스캔 PDF 판독 결과가 한 메시지로 넘어오면 넘친다
# (실측: "JSON message exceeded maximum buffer size of 1048576 bytes" 로 그 건이 보류 처리됨).
MAX_BUFFER_SIZE = int(_CFG.get("max_buffer_size", 64 * 1024 * 1024))

# 한 건의 판정 결과(기준별 해당 여부)를 다음 건으로 넘어가기 전에 화면에 붙잡아 두는 초.
# 답은 추출이 끝나야 한 번에 오므로, 붙잡지 않으면 채워지자마자 다음 건이 덮어써서
# 사람이 읽을 틈이 없다. 0 이면 붙잡지 않는다(대량 실행용).
TRACE_HOLD_SEC = float(_CFG.get("trace_hold_sec", 2.0))

# --- 스캔 이미지 PDF를 에이전트가 직접 판독할지 (결과는 캐시됨) ---
SCAN_READ = bool(_CFG.get("features", {}).get("scan_read", True))

# --- 에이전트 사고 과정(thinking)을 받아 화면에 표시할지 (시연용) ---
SHOW_THINKING = bool(_CFG.get("features", {}).get("show_thinking", False))

# --- 모델별 단가 ($/1M 토큰): {model: (input, output)} ---
PRICES = {m: (p["input"], p["output"]) for m, p in _CFG["prices"].items()}

# --- LLM 백엔드 ---
#   subscription = Claude Agent SDK → 로컬 Claude Code 구독 인증(API 크레딧 X, 구독 사용량 소비).
#                  ⚠️ 구독 rate limit 있음 → 대량 전수실행 시 throttle 주의.
#   api          = anthropic SDK + ANTHROPIC_API_KEY (per-token 과금).
# 환경변수 AX_USE_API=1 이면 yaml 기본값과 무관하게 api 로 강제.
USE_SUBSCRIPTION = (_CFG["backend"]["default"] == "subscription") and os.environ.get("AX_USE_API") != "1"

# 구독 경로에선 ANTHROPIC_API_KEY가 있으면 Agent SDK가 구독 대신 그 키를 써버림
# (claude.ai 로그인보다 우선). .env가 주입한 키를 제거해 구독 인증으로 폴백시킨다.
if USE_SUBSCRIPTION:
    os.environ.pop("ANTHROPIC_API_KEY", None)

# --- WIPS ---
_w = _CFG["wips"]
WIPS_BASE = _w["base"]
BIBLIO_EP = f"{WIPS_BASE}/{_w['biblio_ep']}"     # 서지 페이지 (skey)
PDF_EP    = f"{WIPS_BASE}/{_w['pdf_ep']}"         # 원문 PDF (POST skey) → 래퍼 HTML
USER_AGENT = _w["user_agent"]

# --- 경로 ---
DATA_DIR   = ROOT / _CFG["paths"]["data"]         # 입력 엑셀 (gitignore)
OUTPUT_DIR = ROOT / _CFG["paths"]["output"]       # 결과 (gitignore)
PDF_CACHE  = ROOT / _CFG["paths"]["pdf_cache"]     # 내려받은 PDF 캐시
RUNS_DIR   = ROOT / _CFG["paths"]["runs"]          # 실행별 결과(체크포인트)
for d in (DATA_DIR, OUTPUT_DIR, PDF_CACHE, RUNS_DIR):
    d.mkdir(parents=True, exist_ok=True)

# --- 엑셀 컬럼 표준화 매핑 (정규화된 이름 → 표준 키) ---
# 회차마다 표기가 흔들려서(개행/공백) 반드시 정규화 후 매핑. norm()은 excel_loader에.
COLUMN_MAP = dict(_CFG["column_map"])
