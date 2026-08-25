# 특허 판정 엔진

신규 공개 특허 리스트(엑셀)를 **원문 청구항 근거로** 판정해 연구원 1차검토를 돕는 범용 엔진.
출력은 4등급 — **노이즈 / 유효 / 이슈 / 보류**.

**AI는 등급을 정하지 않는다.** 기준마다 해당(`O`)·비해당(`X`)·모르겠음(`?`)만 답하고,
등급은 규칙 엔진이 결정한다. 같은 답이면 항상 같은 등급이 나온다.
판정 기준은 `tasks/*.yaml` 한 곳에만 있고 웹에서 코딩 없이 고친다.

판단이 안 서면 억지로 분류하지 않고 **보류**로 사람에게 넘긴다.
`?` 는 실패가 아니라 정확한 답이다.

## 파이프라인
```
엑셀 회차시트 ─ excel_loader ─▶ 레코드
   └ ON key(13자리) ─ wips_downloader ─▶ 원문 PDF ─ claims_extractor ─▶ 청구항
        ├ 텍스트 없음(스캔) ─ agent.read_claims_from_scan ─▶ 청구항 (캐시)
        └ 확보 실패 ─▶ 엑셀 대표청구항 → 보류
   └ agent.extract_facts ─▶ 기준별 O/X/? (등급 없음)
   └ rules.evaluate ─▶ 노이즈/유효/이슈/보류 + 해당 기준 + 판단 과정
   └ output/runs/<회차>_<시각>/  records.jsonl · 판정결과.xlsx · AI판단과정.md · 판정표.csv
```

판정 순서는 **① 노이즈인가 → ② 유효 중에 이슈인가**이고, 그 과정 어디서든 판단이 안 서면 보류다.

## 판정 기준 (`tasks/*.yaml`)
```yaml
version: 3
task: 과제 한 줄 설명
scope:     { definition: 무엇을 찾는 과제인지 }
own_tech:  { materials: [], application: '', ranges: '' }   # 참고용, 판정에 안 쓴다
synonyms:  [{ keyword: ..., terms: [...] }]                 # 특허마다 다른 표기를 흡수
criteria:  [{ id: c_n1, label: noise|valid|issue|hold, when: 기준 문장 }]
extract:   { collect: [원문에서 함께 뽑을 항목] }             # 판정과 별개
```
기준 문장에 근거 범위를 적으면(`독립청구항에`, `명세서 본문에`) 그 범위 밖은 근거가 되지 않는다.

`tasks/_템플릿.yaml` 을 복사해 새 과제를 만든다.

## 모듈
| 파일 | 역할 |
|---|---|
| `pipeline.py` | 오케스트레이션 — 근거 확보 · 건별 판정 · 체크포인트 실행 |
| **`rules.py`** | **규칙 엔진** — 기준별 답 → 등급. `evaluate` · `trace` · `lint` |
| `agent.py` | AI 추출(`extract_facts`) · 스캔 판독(`read_claims_from_scan`) |
| `criteria.py` | `tasks/*.yaml` 로더 · 프롬프트 렌더 · 기준 id 를 사람 말로(`humanize`) |
| `excel_export.py` | 원본 엑셀에 결과 열 + 상세 시트 추가 (원본 불변) |
| `run_output.py` | 실행 폴더에 엑셀 · 판단과정 · 판정표 저장 |
| `excel_loader.py` | 엑셀 로드 + 컬럼 정규화 |
| `wips_downloader.py` | ON key → 원문 PDF (캐시 재사용) |
| `claims_extractor.py` | PDF → 청구항 (CN/KR/JP/US/EP, 스캔 감지) |
| `ui_*.py` · `theme.py` | 웹 화면 (홈 · 판정 실행 · 판정기준 관리) |
| `config.yaml` / `config.py` | 모델·백엔드·경로·상한 설정 |
| `prompts/*.md` | 에이전트 지시문 (과제 무관) |
| `tests/test_rules.py` | 규칙 회귀 테스트 (케이스 23개) |

## 실행
```bash
pip install -r requirements.txt
streamlit run launch/app.py

# CLI (회차 하나)
python engine/pipeline.py "data/특허리스트.xlsx" 228회차 --task dod --limit 20 --excel

# 중단된 실행 이어가기
python engine/pipeline.py "data/특허리스트.xlsx" 228회차 --task dod --resume output/runs/<폴더>

# 기준을 고친 뒤에는 반드시
python tests/test_rules.py
```

## 실측 (2026-08-21)
- 청구항 추출 검증: **CN·JP·KR·US·EP 성공**. PCT는 스캔이미지 → 에이전트 판독으로 확보
- 스캔 판독: `231k~289k`토큰 · `68~87`초/건 → **캐시되어 특허당 1회만**
- `225~228`회차 812행: ON key 전건 정상, 스캔 예상 73건 이상(PCT 68 + EP 5 실측)
- 엑셀 원문키 상태: 정상=`218~220`·`225~228` / 형식오류=`221~224` / 컬럼없음=`214~217`
