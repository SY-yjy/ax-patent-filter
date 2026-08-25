# 특허 판정 엔진

매주 신규 공개 특허 리스트(엑셀)를 **원문 청구항 근거로** 판정해 연구원 1차검토를 돕는 **범용 엔진**.
출력은 4등급 — **노이즈 / 유효 / 이슈 / 보류**.

## 설계 원칙

**① 사전 게이트 없음 · 전 건 원문 판정**
값싼 초록 판정으로 미리 버리지 않는다. 모든 건의 원문 PDF 청구항을 읽는다.
스캔 이미지 PDF도 에이전트가 페이지를 이미지로 읽어 청구항을 전사한다(결과 캐시).

**② AI는 등급을 정하지 않는다 — 추출 + 규칙 엔진**
```
원문 청구항 → [AI 추출] 사실만 (flags/choices/물성/근거인용)
            → [규칙 엔진] tasks/*.yaml 의 rules 를 위에서부터 평가 → 등급 확정
```
같은 추출값이면 **항상 같은 등급**이다. 판정 규칙이 yaml에 있으니 과제 담당자가 코드를 안 건드리고 고칠 수 있다.

**③ 애매한 건 억지로 분류하지 않는다 — 보류(hold)**
모든 추출 flag는 `yes/no/unclear` 3값이다. `unclear` 는 실패가 아니라 정확한 답이고, 규칙이 그걸 보류로 보낸다.
구조식 이미지·청구범위 불명확·박리원인 불명·원문 미확보 등은 **보류 사유 코드**와 함께 사람에게 넘어간다.

**④ 신뢰 근거 = 근거등급 + 근거 청구항 + 적용 규칙**
정답 라벨(사람 O/X)은 정확도가 검증되지 않아 성능 지표로 쓰지 않는다. 대신 판정마다
무엇을 보고 판단했는지(`원문청구항` / `엑셀폴백:*`), 근거가 된 독립청구항 원문, 적용된 규칙 ID를 남긴다.

**⑤ 회차 단위 실행 · 중단 시 이어가기**
한 번에 한 회차(시트). 건별로 즉시 디스크에 append 하므로 rate limit·오류로 끊겨도 `--resume` 으로 이어간다.

**⑥ 결과는 원본 엑셀에 열로 붙는다**
연구원이 이미 쓰는 회차 시트 오른쪽에 12열 추가 + `<회차>_AI상세` 시트. 새 화면을 익힐 필요가 없다.

## 파이프라인
```
엑셀 회차시트 ─ excel_loader ─▶ 레코드
   └ ON key(13자리) ─ wips_downloader ─▶ 원문 PDF ─ claims_extractor ─▶ 청구항
        ├ 텍스트 없음(스캔) ─ agent.read_claims_from_scan ─▶ 청구항 (캐시)
        └ 확보 실패 ─▶ 엑셀 대표청구항 (근거등급 = 엑셀폴백:*)
   └ agent.extract_facts ─▶ 사실 (등급 없음)
   └ rules.normalize → rules.evaluate ─▶ 노이즈/유효/이슈/보류 + 적용규칙 + 보류사유
   └ output/runs/<회차>_<시각>/records.jsonl  +  판정결과.xlsx
```

## 근거등급 (evidence)
| 값 | 뜻 |
|---|---|
| `원문청구항` | 원문 PDF 청구항 (텍스트 추출 또는 스캔 판독) — 가장 신뢰 |
| `원문전체` | 청구항 구간 특정 실패 → PDF 전체 텍스트 |
| `엑셀폴백:ONkey없음` | 원문키 컬럼 없음 (`214~217`회차) |
| `엑셀폴백:ONkey형식오류` | 원문키 값이 13자리가 아님 (`221~224`회차) |
| `엑셀폴백:PDF실패` / `엑셀폴백:스캔판독실패` | 원문 확보 실패 |

> `엑셀폴백`은 규칙 `hold_원문미확보` 에 걸려 **무조건 보류**다. 대표청구항 1항만으로 최종 판정하지 않는다.

## 엑셀 출력
**회차 시트 오른쪽 12열** — AI판정 · AI신뢰도 · 보류/보류근거 · 노이즈/노이즈근거 · 유효/유효근거 · 이슈/이슈근거 · 근거청구항 · 검토필요사항
(등급은 배타적이라 O열 중 하나만 채워진다. 자동필터 범위가 새 열까지 확장된다.)

**`<회차>_AI상세` 시트** — 적용규칙 · 보류사유 · 기술요약 · 추출 flag/choice 전부 · 물성 10항목 · 근거인용 · 보정경고

## 모듈
| 파일 | 역할 |
|---|---|
| `pipeline.py` | 오케스트레이션 — 근거 확보 · 건별 판정 · 체크포인트 실행 · 리포트 |
| **`rules.py`** | **규칙 엔진** — 추출값 → 등급. `normalize`(추출값 보정) · `evaluate` · `lint` |
| `agent.py` | AI 추출(`extract_facts`) · 스캔 판독(`read_claims_from_scan`). 구독·API 분기 |
| `criteria.py` | `tasks/*.yaml`(v2) 로더 · 추출 프롬프트용 렌더 |
| `excel_export.py` | 원본 엑셀에 결과 열 + 상세 시트 추가 (원본 불변) |
| `excel_loader.py` | 엑셀 로드(pandas) + 컬럼 정규화 |
| `wips_downloader.py` | WIPS ON key → 원문 PDF (캐시 재사용) |
| `claims_extractor.py` | PDF → 청구항 (CN/KR/JP/US/EP, 스캔 감지) |
| `ui_common.py` | 두 앱 공유 UI |
| `config.yaml` / `config.py` | 모델·백엔드·경로·상한·스캔판독 설정 |
| `prompts/추출.md` · `prompts/스캔판독.md` | 에이전트 지시문 (과제 무관) |
| **`tasks/*.yaml`** | **과제별 판정기준 전부** — scope · own_composition · extract · disambiguation · rules |
| `tests/test_rules.py` | 규칙 회귀 테스트 (IP전략팀 피드백 케이스 19개) |

## 실행
```bash
pip install -r requirements.txt      # anaconda 환경 권장
streamlit run experiment/app.py      # 🧪 실험·검증
streamlit run launch/app.py          # 🚀 배포
# CLI (회차 하나):
python engine/pipeline.py "data/특허리스트.xlsx" 228회차 --task dod --limit 20 --excel
# 중단된 실행 이어가기:
python engine/pipeline.py "data/특허리스트.xlsx" 228회차 --task dod --resume output/runs/228회차_20260821_105653
# 규칙 회귀 테스트 (tasks/*.yaml 고친 뒤 반드시):
python tests/test_rules.py
```

## 실측 (2026-08-21)
- 청구항 추출 검증: **CN·JP·KR·US·EP 성공**. PCT는 스캔이미지 → 에이전트 판독으로 확보
- 스캔 판독: `231k~289k`토큰 · `68~87`초/건 → **캐시되어 특허당 1회만**
- `225~228`회차 812행: ON key 전건 정상, 스캔 예상 73건 이상(PCT 68 + EP 5 실측)
- 엑셀 원문키 상태: 정상=`218~220`·`225~228` / 형식오류=`221~224` / 컬럼없음=`214~217`
