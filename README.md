# 특허 판정 엔진

신규 공개 특허 리스트를 **원문 청구항까지 읽어** 네 등급으로 나누는 웹 도구.

연구원은 매 회차 200건 안팎의 특허 목록을 한 건씩 훑어 "볼 것"과 "안 볼 것"을 가른다.
이 도구가 그 1차 검토를 대신한다. 특허마다 원문 PDF 를 받아 청구항을 읽고,
담당자가 정한 기준에 맞춰 **노이즈 · 유효 · 이슈 · 보류** 로 나눈다.
판정마다 근거가 된 청구항과 판단 과정이 함께 남는다.

결과는 **원본 엑셀 오른쪽에 열로 붙어** 돌아온다. 쓰던 파일에서 그대로 이어 작업하면 된다.

기준은 웹에서 문장으로 적는다. 코드를 고칠 일이 없어서, 과제가 바뀌면
기준만 새로 쓰면 그대로 쓸 수 있다.

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
```
과제 선택 · 엑셀 업로드 · 판정 실행 · 결과 내려받기 · 기준 편집까지 웹에서 한다.
