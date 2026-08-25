# CLAUDE.md — 특허 필터링 AI (AX 100일의 도전) 작업 컨텍스트

> Claude Code가 이 폴더(`~/dev/ax-patent-filter`)에서 세션을 열 때 자동으로 읽는 파일.
> 전역 개인 규칙(`~/.claude/CLAUDE.md` — 데이터 기반·추측 금지, 한국어·존댓말)은 여기서도 그대로 적용된다.
> **이건 코드 작업 폴더**다. 프로젝트의 회의·결정·이력 등 상위 맥락은 samyang 허브에 있다(아래 링크).

## 이 프로젝트가 뭔가 (한 줄)
매주 SDI 신규공개 특허 리스트(엑셀 ~200건)에서 **AI 에이전트가 노이즈를 걸러** 연구원 1차검토를 돕는 시스템. 시범 과제 = **DOD(전기박리 접착제)**. "AX 100일의 도전" 사내 프로그램 과제.

## 상위 맥락은 samyang 허브에 (이력·결정·데이터)
> 여기(dev)는 코드만. 아래는 OneDrive `samyang` 안 — **진짜 중요한 결정/이력/데이터 근거는 여기 있다.**
- **핵심 정리(Living Doc):** `~/Library/CloudStorage/OneDrive-samyang.com/samyang/03_duty/13_ax_100days/AX_핵심정리.md` — 과제개요·데이터현황·판정기준·설계결정·인프라·PDF파이프라인·실측·구조개편 전부 주제별 누적. **막히면 여기부터 본다.**
- 비개발자용 구조도: 같은 폴더 `특허필터링AI_구조도.md` / `.html`
- 발표 제안서: 같은 폴더 `presentation/특허검토AI_제안서.pptx` (2026-08-09)
- 회의록·메일: 같은 폴더 `meeting/`·`mail/`

## 코드 구조 (엔진 / 과제 / 앱 3층 분리, 2026-08-04 대개편)
자세한 파일 지도·처리흐름·Mermaid는 **`구조도.md`** 참조(정확·최신). 요지만:
- `engine/` — 공유 엔진(과제 무관, 한 벌): `agent · pipeline · excel_loader · wips_downloader · claims_extractor · criteria · config.py · config.yaml · ui_common` + `prompts/판정.md`
- `tasks/*.yaml` — 과제별 판정범위(노이즈/유효/이슈). `tasks/dod.yaml` = DOD
- `experiment/app.py` — 🧪 검증·튜닝 앱(정답라벨로 recall 측정, 과제 저장O)
- `launch/app.py` — 🚀 배포 앱(직접입력만, 저장X)
- 앱은 `sys.path`에 `engine/` 추가해 import하는 얇은 진입점. 엔진은 한 벌만 관리.

**"AI가 뭘 근거로 판단하나"는 딱 3곳:** `prompts/판정.md`(판단 방법, 과제 무관) + `tasks/*.yaml`(판정 범위, 과제별) + 특허 데이터. 엔진 코드엔 DOD 등 특정 과제 지식이 전혀 없다.
**자주 만지는 것:** `config.yaml`(모델·백엔드) · `tasks/dod.yaml`(판정범위) · `prompts/판정.md`(지침). 나머지는 로직.

## ⭐ 설계 (2026-08-21 대개편 — IP전략팀 피드백 반영)

**① 사전 게이트 없음 · 전 건 원문 판정.** 1차 노이즈 스크리닝(엑셀 요약 게이트)을 삭제했다. 모든 건의 원문 PDF 청구항을 읽는다. 스캔 이미지 PDF는 에이전트가 페이지를 이미지로 읽어 청구항을 전사하고 `.claims.txt` 에 캐시한다(특허당 1회만 비용).

**② AI는 등급을 정하지 않는다 — 추출 + 규칙 엔진.**
```
원문 → [AI 추출] 사실만(flags/choices/물성/근거인용) → [rules.py + tasks/*.yaml] 등급 확정
```
같은 추출값이면 항상 같은 등급. LLM 자유 판정의 비재현성 제거(피드백 10.1). **프롬프트에 판정 규칙을 넣지 마라** — 규칙은 `tasks/*.yaml` 의 `rules`.

**③ 4등급 — 노이즈 / 유효 / 이슈 / 보류.** 모든 flag는 `yes/no/unclear` 3값이고 `unclear` 는 규칙이 보류로 보낸다. 보류에는 **사유 코드**가 붙는다(구조식_이미지 · 청구범위_불명확 · 박리원인_불명 · 원문_미확보 · 제목초록_불일치 · 접착제_바인더_불명 · 규칙_미매칭).

**④ 정답 라벨을 성능 지표로 쓰지 않는다** (양정열 판단, 책임 인지). 라벨 정확도 미검증 + 이슈=O 사례가 2,826행 중 7건뿐(최근 6회차 0건). 신뢰 근거는 **근거등급 + 근거 청구항 + 적용 규칙 ID**.

**⑤ 회차 단위 실행 · 체크포인트.** 건별로 `output/runs/<회차>_<시각>/records.jsonl` 즉시 append → `--resume` 으로 이어가기. `meta.json` 에 프롬프트 전문 + **과제 yaml 전체** 스냅샷.

**⑥ 결과는 원본 엑셀에 열로 붙는다.** 회차 시트 오른쪽 12열(`AM`~`AX`: AI판정·AI신뢰도·보류/노이즈/유효/이슈 각 O·근거·근거청구항·검토필요사항) + `<회차>_AI상세` 시트 36열(추출 flag·choice·물성 10항목·근거인용). 원본 파일은 수정하지 않고 사본 생성.

**⑦ 실험 범위는 225~228회차** (ON key 전건 정상인 회차).

### 규칙 우선순위 (순서 바꿀 때 반드시 지킬 것)
1. 근거 부족(원문 미확보)은 무엇보다 먼저 → 초록·대표청구항만으로 최종 판정 금지
2. 명백히 무관한 기술은 보류보다 **노이즈 우선** (피드백 7장 단서)
3. 이슈 **제외** 규칙(6장)은 반드시 이슈 규칙보다 먼저
4. 범위 불명은 비이슈로 단정하지 않고 **보류** (5.3)

`tasks/*.yaml` 을 고친 뒤에는 **반드시** `python tests/test_rules.py` (피드백 케이스 19개).

## ⭐ 설계 전환 (2026-08-21) — 사전 게이트 제거, 전 건 원문 판정
- **1차 노이즈 스크리닝(엑셀 요약 기반 게이트)을 삭제했다.** 모든 건의 원문 PDF 청구항을 읽고 한 번에 판정한다.
- **정답 라벨(사람 O/X)을 성능 지표로 쓰지 않는다.** 라벨 정확도가 검증되지 않았다(양정열 판단, 책임 인지). recall 숫자를 시연 근거로 쓰지 않는다.
- 대신 신뢰 근거는 **① 근거등급(evidence)** = 무엇을 보고 판단했는지(`원문청구항`/`원문전체`/`엑셀폴백:*`) **② 청구항 인용(quote)** = 판단에 쓴 구절 원문. 연구원이 원문과 대조해 검증한다.
- 실행은 **회차 단위**, 건별로 `output/runs/<회차>_<시각>/records.jsonl` 에 즉시 append → `--resume`으로 이어가기.
- 실험 범위는 **225~228회차** (ON key 전건 정상인 회차).

## 실행 환경 (⚠️ 여기가 자주 발목 잡음)
- **파이썬 = conda `base`.** 의존성(streamlit·claude-agent-sdk·pypdf·anthropic·pyyaml)은 **anaconda base에만** 있다. 시스템 `python3` 아님.
  - 확인됨(2026-08-20): base에 streamlit 1.51.0 · claude-agent-sdk 0.2.128 · anthropic 0.120.0
- **실행:**
  ```bash
  cd ~/dev/ax-patent-filter
  streamlit run experiment/app.py      # 🧪 검증·튜닝 (localhost:8501)
  streamlit run launch/app.py          # 🚀 배포
  # CLI 배치(회차 하나, 과제 --task 필수):
  python engine/pipeline.py "<엑셀경로>" 226회차 --task dod --limit 5
  # 중단된 실행 이어가기:
  python engine/pipeline.py "<엑셀경로>" 226회차 --task dod --resume output/runs/<폴더>
  ```

## LLM 백엔드 = 구독 경로 (핵심 — 시연 성패가 여기 걸림)
- API 크레딧 소진 → **구독(Claude 구독)으로 돌린다.** `config.yaml`의 `backend.default: subscription` (환경변수 `AX_USE_API=1`이면 API 키 강제).
- 구조: **Streamlit 앱 → `claude-agent-sdk`(pip 패키지) → 로컬 `claude` CLI(=구독 로그인) → LLM.** API 키/크레딧 안 씀, 구독 사용량 소비.
  - `agent.py`의 `_ask`가 분기: 구독이면 `_ask_subscription`.
  - ⚠️ **옵션 4개(`allowed_tools=[] · tools=[] · setting_sources=[] · skills=[]`)를 절대 빼지 마라.** 하나라도 빠지면 CLI가 자기 시스템 프롬프트·도구 정의·스킬 목록·`CLAUDE.md`를 판정 프롬프트에 실어 보낸다. **실측(2026-08-21): 옵션 없음 29,162토큰 / `setting_sources`만 22,229 / 4개 전부 215.** 판정이 프롬프트 파일만의 함수가 아니게 되어 재현이 깨진다.
  - `config.py`가 구독모드일 때 `.env`의 `ANTHROPIC_API_KEY`를 `os.environ`에서 **일부러 제거**(안 그러면 SDK가 구독 대신 그 키를 씀).
- **전제:** `streamlit`을 띄우는 터미널에서 `claude` CLI가 실행돼야 한다 → **실행 전 `which claude` / `claude --version` 확인.**
- ⚠️ **구독은 rate limit 있음**(`RateLimitEvent` 관측) → 2,400행 전수는 throttle 위험. **데모는 소량(처리건수 제한)으로.** 비용($) 집계는 API 모드에서만 의미(구독은 quota 소비).

### `claude` CLI 고장났을 때 (2026-08-20 실제로 겪음)
- 증상: `claude --version` → `zsh: killed`(SIGKILL). 원인 = `~/.claude/downloads/claude-2.1.23-darwin-arm64`가 **잘린 불완전 파일(144MB)이고 코드서명이 아예 없음** → arm64 맥이 실행 즉시 죽임.
- **해결:** VS Code 확장의 정상 서명 바이너리를 복사해 PATH에 놓음(`~/.claude/bin`은 이미 PATH에 있음):
  ```bash
  cp ~/.vscode/extensions/anthropic.claude-code-<최신버전>-darwin-arm64/resources/native-binary/claude ~/.claude/bin/claude
  chmod +x ~/.claude/bin/claude
  hash -r && claude --version    # 새 터미널 또는 hash -r 후 확인
  ```
- ⚠️ 이 복사본은 특정 버전(2.1.235)에 고정 — 자동 업데이트 안 됨. 또 깨지면 최신 확장 폴더에서 재복사하거나 공식 설치.

## 지금 상태 (2026-08-21)
- ✅ 엔진/과제/앱 3층 분리 — 도메인 지식은 `tasks/dod.yaml` 에만 (규칙 18개 + default)
- ✅ **추출 + 규칙 엔진** (`rules.py`: normalize·evaluate·lint). `pipeline.run` 이 실행 전 lint 하고 규칙이 깨져 있으면 거부
- ✅ **4등급 + 보류 사유 코드**, 신뢰도(높음/중간/낮음) 결정적 계산
- ✅ **엑셀 결과 열 출력** (`excel_export.py`) — 회차 시트 +12열, 상세 시트 36열. 실측: 원본에 이미지·차트·병합셀 0개라 openpyxl 왕복 유실 없음
- ✅ **스캔 이미지 판독** — `claude` CLI Read 도구가 PDF를 이미지로 읽음. 별도 OCR 엔진 불필요. 캐시 `output/pdf/<on_key>.claims.txt`
- ✅ 청구항 추출 CN·JP·KR·US·**EP** 전부 실측 검증 (EP는 청구항이 명세서 **뒤**에 옴 — 실측 135,664자 중 129,270자 지점)
- ✅ 구독 프롬프트 오염 수정 (29,162 → 215토큰), `번호` 컬럼 YAML 불리언 버그 수정
- ✅ 규칙 회귀 테스트 19/19, 앱 2개 부팅 확인, 죽은 참조 0건
- 📊 실측: 추출 판정 건당 20~30초. 스캔 판독 231k~289k토큰·68~87초(캐시로 1회만)

## 남은 블로커 / 다음 할 일 (우선순위)
1. 🔴 **자사 개발 조성 확정** — `tasks/dod.yaml` 의 `own_composition.composition_ranges` 가 "미확정". 이슈 중첩 판단의 기준점이라 이게 없으면 이슈 규칙이 수지계만 보고 판정한다 → 임가현·IP전략팀 확인
2. 🔴 **로더 입구 검증** — 열이 밀려도 조용히 통과(221회차 `title='P'`). `title` 길이·`on_key` 형식 sanity check
3. 🔴 **엑셀 열구조 재추출 요청** — 임가현에 열구조 통일 + `WIPSONkey` 포함. 형식오류=221~224 / 컬럼없음=214~217
4. 🟠 **회차 1개 전수 실행** — 225~228 중 하나. 직렬 70~100분 추정 → 등급·보류사유 분포 실측
5. 🟠 **판정 병렬화** — 추출 호출만 병렬(PDF는 polite delay 유지)
6. 🟡 **판정기준 편집 UI** (피드백 10.2 화면 3) — 지금은 `tasks/*.yaml` 직접 수정
7. 🟡 **대시보드 + 연구원 최종 승인·수정 사유 누적** (피드백 10.2·10.3) — SQLite 필요
8. ⚪ `excel_loader`·`claims_extractor` 테스트 추가

## 작업 규칙
- 전역 규칙 최우선: **추측 금지, 데이터/실행결과로만.** 수치·원인은 실제로 돌려/열어 확인 후 말한다.
- 코드는 여기(dev)서 하고, **진행/결정/데이터는 samyang Living Doc(`AX_핵심정리.md`)에 반영.** 중요한 결정 생기면 거기 "변경 이력"에 한 줄.
- `.env`·`data/`·`output/`는 `.gitignore`(커밋 제외). GitHub엔 실데이터·키 안 올린다.
- ⚠️ **이 폴더는 git 저장소가 아니다** (양정열 결정: 스냅샷 안 뜸). 되돌릴 수 없는 변경은 미리 알린다.
