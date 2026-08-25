"""WIPS 원문 PDF 다운로더 — 2026-07-26 실측 검증한 5단계 파이프라인.

  1. 엑셀 WIPS ON key(skey)
  2. POST dwn_pdf_dsdirect.wips (skey)     → "원문보기" 래퍼 HTML
  3. 래퍼 <iframe id="ifrm" src=...> 파싱   → 실제 PDF URL (img4.wipson.com/*.pdf)
  4. PDF URL GET (referer sd.wips.co.kr)   → application/pdf
  (5. 텍스트 추출은 claims_extractor 담당)

⚠️ WIPS 자동수집은 내부 승인 확인됨(2026-07-26). 예의상 요청 간 지연을 둔다.
"""
import re
import time
from pathlib import Path
import requests
import config

_IFRAME_SRC = re.compile(r'<iframe[^>]*id="ifrm"[^>]*src="([^"#]+)', re.I)


def _session() -> requests.Session:
    s = requests.Session()
    s.headers.update({"User-Agent": config.USER_AGENT})
    return s


def resolve_pdf_url(on_key: str, session: requests.Session | None = None) -> str | None:
    """skey → 실제 PDF URL. 못 찾으면 None."""
    s = session or _session()
    r = s.post(config.PDF_EP, data={"skey": on_key},
               headers={"Referer": f"{config.BIBLIO_EP}?skey={on_key}"}, timeout=30)
    r.raise_for_status()
    m = _IFRAME_SRC.search(r.text)
    return m.group(1) if m else None


def download_pdf(on_key: str, out_path=None, session: requests.Session | None = None,
                 polite_delay: float = 1.0, use_cache: bool = True) -> str | None:
    """skey → PDF 파일 저장. 성공 시 경로, 실패 시 None.
    이미 받아둔 PDF가 있으면 재다운로드하지 않는다(전 건 처리·재실행 시 필수)."""
    cached = out_path or (config.PDF_CACHE / f"{on_key}.pdf")
    if use_cache and Path(cached).is_file() and Path(cached).stat().st_size > 0:
        return str(cached)
    s = session or _session()
    pdf_url = resolve_pdf_url(on_key, s)
    if not pdf_url:
        print(f"[download_pdf] iframe src 못 찾음 (skey={on_key})")
        return None
    time.sleep(polite_delay)
    r = s.get(pdf_url, headers={"Referer": "https://sd.wips.co.kr/"}, timeout=60)
    ctype = r.headers.get("content-type", "")
    if not ctype.startswith("application/pdf"):
        print(f"[download_pdf] PDF 아님 (skey={on_key}, type={ctype})")
        return None
    out_path = str(out_path or (config.PDF_CACHE / f"{on_key}.pdf"))
    with open(out_path, "wb") as f:
        f.write(r.content)
    return out_path
