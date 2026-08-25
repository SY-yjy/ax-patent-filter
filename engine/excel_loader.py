"""특허 리스트 엑셀 로더 — pandas/openpyxl.

회차별 시트 = 한 주치. 컬럼명이 회차마다 흔들려서(개행/공백, 예: '이슈특허\\n여부')
반드시 정규화 후 COLUMN_MAP으로 매핑한다. (위치 기준 매핑 금지)

입력 소스는 **파일 경로(str/Path)** 또는 **파일류 객체(BytesIO 등, 웹 업로드)** 둘 다 가능.
전제: 입력은 보안 해제된 .xlsx.
"""
import io
import pandas as pd
import config


def norm(s) -> str:
    """컬럼명/값 정규화: 개행·공백 제거."""
    if s is None:
        return ""
    return str(s).replace("\n", "").replace("\r", "").replace(" ", "").strip()


def _clean(v):
    """pandas 빈칸(NaN) → None."""
    if v is None:
        return None
    try:
        if isinstance(v, float) and pd.isna(v):
            return None
    except Exception:
        pass
    return v


def _map_headers(header_row):
    """헤더행 → {표준키: 열인덱스}. 규칙 정규화 매핑. 미매핑은 폴백 대상."""
    idx = {}
    unmapped = []
    for i, h in enumerate(header_row):
        key = config.COLUMN_MAP.get(norm(h))
        if key:
            idx.setdefault(key, i)   # 첫 매칭 우선
        elif norm(h):
            unmapped.append(norm(h))
    return idx, unmapped


def _rows_from_vals(vals):
    """[헤더행, 데이터행…] → (표준화 레코드 리스트, ON key 컬럼 존재여부)."""
    if not vals or len(vals) < 2:
        return [], False
    header, rows = vals[0], vals[1:]
    idx, _ = _map_headers(header)
    has_on_key = "on_key" in idx

    def cell(r, key):
        i = idx.get(key)
        return _clean(r[i]) if (i is not None and i < len(r)) else None

    records = []
    for r in rows:
        rec = {k: cell(r, k) for k in idx}
        # ON key는 숫자로 읽히면 소수점 붙으니 정수 문자열로
        if rec.get("on_key") is not None:
            rec["on_key"] = str(rec["on_key"]).split(".")[0]
        # 라벨 O/X 정규화
        for lab in ("valid", "issue"):
            if rec.get(lab) is not None:
                rec[lab] = norm(rec[lab]).upper()
        if any(v not in (None, "") for v in rec.values()):  # 빈 행 제외
            records.append(rec)
    return records, has_on_key


# ---------- 읽기 ----------
def _as_buffer(source):
    """file-like이면 매 재사용 안전하게 bytes 스냅샷을 뜬다. 경로면 그대로 반환."""
    if hasattr(source, "read"):
        try:
            source.seek(0)
        except Exception:
            pass
        return io.BytesIO(source.read())
    return source


def _sheet_vals(xl: "pd.ExcelFile", name: str):
    """한 시트를 [헤더행, 데이터행…] 원시 2차원 리스트로. header=None으로 헤더도 데이터로."""
    df = xl.parse(name, header=None)
    return df.where(pd.notna(df), None).values.tolist()


def _read_all_vals(source) -> dict:
    """소스 → {sheet_name: 원시 2차원 리스트}."""
    xl = pd.ExcelFile(_as_buffer(source), engine="openpyxl")
    return {name: _sheet_vals(xl, name) for name in xl.sheet_names}


# ---------- 공개 API (기존 시그니처 유지) ----------
def load_all_sheets(source) -> dict:
    """전 회차를 한 번에 읽는다.
    반환: {sheet_name: {"records": [...], "has_on_key": bool}} (순서 유지)."""
    raw = _read_all_vals(source)
    out = {}
    for name, vals in raw.items():
        recs, has_key = _rows_from_vals(vals)
        out[name] = {"records": recs, "has_on_key": has_key}
    return out


def load_sheet(source, sheet_name: str) -> list[dict]:
    """한 회차 시트 → 표준화 레코드 리스트."""
    raw = _read_all_vals(source)
    if sheet_name not in raw:
        raise KeyError(f"시트 없음: {sheet_name} (있는 시트: {list(raw)[:20]})")
    recs, _ = _rows_from_vals(raw[sheet_name])
    return recs


def list_sheets(source) -> list[str]:
    return list(_read_all_vals(source).keys())
