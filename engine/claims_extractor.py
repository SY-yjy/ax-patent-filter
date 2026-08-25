"""PDF 원문 → 청구항 섹션 추출.

국가별 청구항 헤더가 다르다 (2026-07-27 실제 PDF 받아 확인):
  CN(중국 발명공보): 페이지 푸터 '权利要求书 N/M 页'          ← 검증
  KR: '청구범위' → '청구항 1', '청구항 2' …                    ← 검증
  JP: '特許請求の範囲' / '【請求項１】'(전각) …                ← 검증
  US: 'What is claimed is:' / 'We claim' / 'I claim' → 번호     ← 검증
  EP: 'Claims' 단독 줄 ~ 'REFERENCES CITED' (청구항이 명세서 **뒤**) ← 검증
  PCT(WO): ⚠️ WIPS 제공 PDF가 스캔 이미지(텍스트 레이어 없음).
           pypdf로 0자 → OCR 필요. 현재 추출 불가 → no_text 신호 반환.
           (2026-07-27 PCT 7건 전부 0자 실측)

텍스트 소량이면(스캔) extract_claims가 how="no_text"를 돌려주므로,
파이프라인이 엑셀 대표청구항(영어) 폴백 등으로 처리하게 한다.

200페이지 특허도 청구항 섹션만·상한 글자수로 잘라 토큰을 bound한다.
"""
import re
import pypdf
import config

MAX_CLAIM_CHARS = config.MAX_CLAIM_CHARS  # 청구항 섹션 상한(config.yaml limits)
_MIN_TEXT = 200                            # 이보다 적으면 스캔 이미지로 간주


def _pages(pdf_path: str) -> list[str]:
    return [(p.extract_text() or "") for p in pypdf.PdfReader(pdf_path).pages]


def _nospace(t: str) -> str:
    return re.sub(r"\s", "", t)


def _ws(pattern_chars: str) -> str:
    """CJK 글자 사이 공백/개행 허용 정규식으로 변환."""
    return r"\s*".join(re.escape(c) for c in pattern_chars)


def _clip(text: str) -> tuple[str, bool]:
    text = re.sub(r"[ \t]+", " ", text)
    text = re.sub(r"\n{2,}", "\n", text).strip()
    if len(text) > MAX_CLAIM_CHARS:
        return text[:MAX_CLAIM_CHARS], True
    return text, False


# ---------- CN: 페이지 푸터 기준 (검증 완료) ----------
def extract_claims_cn(pages: list[str]) -> str:
    claim_pages = [t for t in pages
                   if re.search(r"权利要求书\d+/\d+页", _nospace(t))]
    text = "\n".join(claim_pages)
    text = re.sub(r"权\s*利\s*要\s*求\s*书\s*\d+\s*/\s*\d+\s*页", "", text)
    text = re.sub(r"CN\s*\d+\s*[A-Z]", "", text)
    return _clip(text)[0]


def _between(full: str, start_pats: list[str], end_pats: list[str]) -> str:
    """start 마커 첫 위치 ~ (그 뒤 end 마커 or 문서끝) 사이 원문."""
    start = -1
    for p in start_pats:
        m = re.search(p, full)
        if m:
            start = m.start()
            break
    if start < 0:
        return ""
    rest = full[start:]
    end = len(rest)
    for p in end_pats:
        m = re.search(p, rest[10:])  # 시작 마커 자체는 건너뛰고 탐색
        if m:
            end = min(end, m.start() + 10)
    return rest[:end]


def extract_claims_kr(pages: list[str]) -> str:
    full = "\n".join(pages)
    seg = _between(
        full,
        start_pats=[_ws("청구범위")],
        end_pats=[_ws("발명의설명"), _ws("발명의상세한설명"), _ws("도면의간단한설명"), _ws("요약")],
    )
    return _clip(seg)[0]


def extract_claims_jp(pages: list[str]) -> str:
    full = "\n".join(pages)
    seg = _between(
        full,
        start_pats=[_ws("特許請求の範囲"), r"【\s*請\s*求\s*項"],
        end_pats=[_ws("発明の詳細な説明"), _ws("発明の概要"), _ws("技術分野")],
    )
    return _clip(seg)[0]


def extract_claims_us(pages: list[str]) -> str:
    full = "\n".join(pages)
    seg = _between(
        full,
        start_pats=[r"What\s+is\s+claimed\s+is", r"We\s+claim", r"I\s+claim", r"\bCLAIMS\b"],
        end_pats=[r"\bABSTRACT\b", r"\*\s*\*\s*\*"],
    )
    return _clip(seg)[0]


def extract_claims_ep(pages: list[str]) -> str:
    """EP: 청구항이 **명세서 뒤**에 온다 (Art.153(4) A1 등). 앞에서 자르면 서지·명세서만 잡힌다.
    실측(EP4773345A1, 34p): 'Claims' 단독 줄이 135,664자 중 129,270자 지점."""
    full = "\n".join(pages)
    seg = _between(
        full,
        start_pats=[r"(?m)^\s*Claims\s*$", r"(?m)^\s*CLAIMS\s*$"],
        end_pats=[r"REFERENCES\s+CITED\s+IN\s+THE\s+DESCRIPTION",
                  r"(?m)^\s*Patentansprüche\s*$", r"(?m)^\s*Revendications\s*$"],
    )
    # 페이지 가구 제거: 러닝헤더('EP 4 773 345 A1')와 여백 줄번호(5·10·…·55 단독 줄)
    seg = re.sub(r"EP\s+\d[\d\s]*A1", "", seg)
    seg = re.sub(r"(?m)^\s*(?:5|10|15|20|25|30|35|40|45|50|55)\s*$", "", seg)
    return _clip(seg)[0]


_EXTRACTORS = {
    "CN": extract_claims_cn,
    "KR": extract_claims_kr,
    "JP": extract_claims_jp,
    "US": extract_claims_us,
    "EP": extract_claims_ep,
}


def extract_claims(pdf_path: str, country: str = "CN") -> tuple[str, str]:
    """(청구항텍스트, how).
    how: 'claims:XX' 국가추출기 성공 / 'fulltext' 폴백 / 'no_text' 스캔이미지(추출불가).
    """
    pages = _pages(pdf_path)
    full = "\n".join(pages)
    if len(_nospace(full)) < _MIN_TEXT:
        return "", "no_text"  # PCT 등 스캔 이미지 → 파이프라인이 엑셀 청구항 폴백

    fn = _EXTRACTORS.get((country or "").upper())
    if fn:
        claims = fn(pages)
        if claims and len(_nospace(claims)) >= 30:
            return claims, f"claims:{country}"
    # 국가 미지원/추출 실패 → 전체 텍스트(상한 적용)
    clipped, _ = _clip(full)
    return clipped, "fulltext"
