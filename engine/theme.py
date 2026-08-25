"""디자인 토큰 — 색·간격·깊이·라운드 한 벌. UI 모듈은 여기서만 가져온다.

Pantone 2756 C = #151F6D (RGB 21,31,109) 기준.
색을 파일마다 선언하면 하나 빠뜨려 NameError 가 난다(2026-08-24 실제 발생).
"""

# ── 브랜드 ───────────────────────────────────────────────────────────────
BRAND = "#151F6D"      # 본색 (Pantone 2756 C)
LEGACY_BLUE = "#2C2170"  # 삼양 Legacy Blue — 로고 파일 배경 실측값
BRAND_800 = "#101743"
BRAND_700 = "#1B2670"
BRAND_600 = "#2A3A9E"  # 링크·강조
BRAND_400 = "#5C6AC4"
BRAND_300 = "#939DDC"
BRAND_100 = "#D6DCF2"
BRAND_050 = "#E9ECF8"  # 테두리·강조 면
BRAND_025 = "#F5F7FD"  # 옅은 면

# ── 중성 ─────────────────────────────────────────────────────────────────
GROUND = "#EDF0F8"     # 페이지 바깥 바탕
SHEET = "#FFFFFF"      # 본문 시트
LINE = "#E2E7F4"       # 기본 경계선
LINE_STRONG = "#CBD3EA"
INK = "#141A35"        # 본문
INK_SUB = "#454D74"    # 보조 본문
INK_MUTED = "#79809F"  # 캡션

# ── 판정 등급 (의미색 — 브랜드와 조화되도록 채도 낮춤) ────────────────────
LABEL_COLOR = {"noise": "#79809F", "valid": "#1B7A46", "issue": "#C0342C", "hold": "#A96A12"}
LABEL_BG = {"noise": "#F3F4F9", "valid": "#EDF7F1", "issue": "#FDF1F0", "hold": "#FDF6EA"}
LABEL_LINE = {"noise": "#DDE0EC", "valid": "#C8E6D4", "issue": "#F3CFCC", "hold": "#F0DFBE"}
LABEL_ICON = {"noise": "🔘", "valid": "🟢", "issue": "🔴", "hold": "🟠"}

# ── 라운드 ───────────────────────────────────────────────────────────────
R_SM = "8px"
R_MD = "12px"
R_LG = "16px"
R_PILL = "999px"

# ── 깊이 (2단만 쓴다 — 많아지면 정리가 안 된다) ──────────────────────────
SHADOW_1 = "0 1px 2px rgba(20,26,53,.05), 0 1px 3px rgba(20,26,53,.04)"
SHADOW_2 = "0 2px 4px rgba(20,26,53,.05), 0 12px 32px rgba(20,26,53,.08)"
SHADOW_BRAND = "0 2px 10px rgba(21,31,109,.22)"

# ── 간격 리듬 (4의 배수) ─────────────────────────────────────────────────
S1, S2, S3, S4, S5, S6 = "4px", "8px", "12px", "16px", "24px", "32px"
