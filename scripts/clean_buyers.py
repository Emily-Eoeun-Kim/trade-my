"""2일차: buyers 시트 정제 — workbench/day2/rules/정제규칙.md 1–7칸을 그대로 옮긴 스크립트.

원본(data/checkpoints/d2_start.xlsx)은 읽기만 하고, 결과는 workbench/day2/outputs/에 씁니다.
실행: uv run python scripts/clean_buyers.py
"""

import hashlib
import re
import sys
from pathlib import Path

import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "data/checkpoints/d2_start.xlsx"
OUT_DIR = ROOT / "workbench/day2/outputs"
OUT_CSV = OUT_DIR / "d2_buyers_clean.csv"
OUT_REPORT = OUT_DIR / "dq_report.md"
REF_DATE = "2026-08-31"

AR_COLS = ["ar_balance", "ar_current", "ar_1_30", "ar_31_60", "ar_61_90", "ar_91p"]
FIN_COLS = ["current_assets", "current_liabilities", "total_liabilities", "equity",
            "accounts_receivable", "revenue", "operating_income"]
FIN_MISSING_COLS = ["current_assets", "current_liabilities", "total_liabilities", "equity", "revenue"]
BEHAV_COLS = ["avg_days_late_12m", "avg_dpd_last3m", "avg_dpd_prev3m"]
UNIT_MULT = 10  # 4칸: 잔액 > 한도 × 10 (교육용 가정)

# 1칸: 통화 표기 → 표준 4종 (map_ccy 시트가 비어 있어 규칙 문서의 대응표를 씀)
CCY_MAP = {"USD": "USD", "US$": "USD", "EUR": "EUR", "EURO": "EUR",
           "JPY": "JPY", "YEN": "JPY", "CNY": "CNY", "RMB": "CNY"}

OUT_COLS = ["buyer_id", "payment_method", "ccy_clean", "amt_num", "ar_balance_usd",
            "pct_current", "pct_ar_31p", "pct_91plus", "max_dpd", "avg_days_late",
            "late_ratio", "dpd_trend", "dispute_ratio", "current_ratio", "debt_to_equity",
            "dso_buyer", "op_margin", "fin_missing", "neg_equity", "country_risk",
            "crc_unclassified", "unit_flag", "fx_chg_30d", "fx_chg_30d_lag30", "late_30d"]


def sha256(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def to_num(v):
    """2칸: 공백·콤마·통화 글자(앞/뒤) 제거, 끝이 k면 ×1000. 실패하면 ValueError."""
    if not isinstance(v, str):
        return float(v)
    t = v.strip().replace(",", "")
    t = re.sub(r"^[A-Za-z$]{3,4}\s*|\s*[A-Za-z$]{3,4}$", "", t).strip()
    if t.lower().endswith("k"):
        return float(t[:-1]) * 1000
    return float(t)


def kind(v):
    if pd.isna(v):
        return "결측"
    if isinstance(v, str):
        return "문자"
    return "숫자"


def main():
    hash_before = sha256(SRC)
    xl = pd.ExcelFile(SRC)
    raw = pd.read_excel(xl, "buyers", dtype=object)
    fx = pd.read_excel(xl, "fx_at_ref")
    xl.close()
    df = raw.copy()

    # 1칸: 통화
    ccy_key = df["currency"].astype(str).str.strip().str.upper()
    unknown = sorted(set(ccy_key) - set(CCY_MAP))
    if unknown:
        sys.exit(f"[중단] map에 없는 통화 표기: {unknown}")
    df["ccy_clean"] = ccy_key.map(CCY_MAP)

    # 2칸: 숫자 변환 (*_num)
    for c in AR_COLS:
        try:
            df[f"{c}_num"] = df[c].map(to_num)
        except ValueError as e:
            bad = [v for v in df[c] if isinstance(v, str)]
            sys.exit(f"[중단] {c} 변환 실패: {e} / 문자 값: {bad}")
    df["amt_num"] = df["ar_balance_num"]
    bucket_cols = [f"{c}_num" for c in AR_COLS[1:]]
    df["aging_sum"] = df[bucket_cols].sum(axis=1)

    # 숫자 열 (원천이 object로 읽혀서)
    num_cols = ["max_dpd", "invoices_12m", "late_invoices_12m", "dispute_cnt_12m",
                "credit_limit_usd", "late_30d"] + FIN_COLS + BEHAV_COLS
    for c in num_cols:
        df[c] = pd.to_numeric(df[c])

    # 5칸: 자본잠식 — 채우기 전 원값으로 판정
    df["neg_equity"] = (df["equity"] <= 0).astype(int)

    # 3칸: 결측 — 플래그 먼저, 그다음 150개사 중위수
    df["fin_missing"] = df[FIN_MISSING_COLS].isna().any(axis=1).astype(int)
    medians = {}
    for c in FIN_COLS + BEHAV_COLS:
        df[f"{c}_missing"] = df[c].isna().astype(int)
        medians[c] = df[c].median()
        df[c] = df[c].fillna(medians[c])

    # 6칸: 국가위험
    crc = df["oecd_crc"].astype(str).str.strip()
    df["crc_unclassified"] = (crc == "-").astype(int)
    df["country_risk"] = pd.to_numeric(crc.where(crc != "-", "0")).astype(int)

    # 7칸: 환율 (기준일 행만 사용 — 9/30 행은 미래 정보)
    ref = fx[fx["ref_date"].astype(str).str[:10] == REF_DATE].set_index("ccy")
    per_unit = {"USD": 1, "EUR": 1, "CNY": 1, "JPY100": 100}
    krw = {("JPY" if k == "JPY100" else k): ref.loc[k, "krw_close"] / per_unit[k] for k in per_unit}
    usd_krw = krw["USD"]
    chg30 = {("JPY" if k == "JPY100" else k): ref.loc[k, "chg_30d"] for k in per_unit}
    chg60 = {("JPY" if k == "JPY100" else k): ref.loc[k, "chg_60d"] for k in per_unit}
    df["ar_balance_usd"] = df["amt_num"] * df["ccy_clean"].map(krw) / usd_krw
    df["fx_chg_30d"] = df["ccy_clean"].map(chg30)
    df["fx_chg_30d_lag30"] = (1 + df["ccy_clean"].map(chg60)) / (1 + df["ccy_clean"].map(chg30)) - 1

    # 4칸: 단위 의심 — 플래그만, 값은 그대로
    df["unit_flag"] = (df["ar_balance_usd"] > df["credit_limit_usd"] * UNIT_MULT).astype(int)

    # 파생 특성 (과정 공통 사전 data/data_dictionary.xlsx 정의)
    denom = df["aging_sum"].replace(0, np.nan)  # 잔액이 0이면 빈칸
    df["pct_current"] = df["ar_current_num"] / denom
    df["pct_ar_31p"] = df[["ar_31_60_num", "ar_61_90_num", "ar_91p_num"]].sum(axis=1) / denom
    df["pct_91plus"] = df["ar_91p_num"] / denom
    df["avg_days_late"] = df["avg_days_late_12m"]
    inv = df["invoices_12m"].replace(0, np.nan)  # 인보이스 0건이면 빈칸
    df["late_ratio"] = df["late_invoices_12m"] / inv
    df["dispute_ratio"] = df["dispute_cnt_12m"] / inv
    df["dpd_trend"] = df["avg_dpd_last3m"] - df["avg_dpd_prev3m"]
    df["current_ratio"] = df["current_assets"] / df["current_liabilities"]
    df["debt_to_equity"] = (df["total_liabilities"] / df["equity"]).where(df["neg_equity"] == 0)
    df["dso_buyer"] = df["accounts_receivable"] / df["revenue"] * 365
    df["op_margin"] = df["operating_income"] / df["revenue"]

    out = df[OUT_COLS].copy()
    out["late_30d"] = out["late_30d"].astype(int)
    assert len(out) == 150 and out["buyer_id"].is_unique
    assert list(out.columns) == OUT_COLS

    OUT_DIR.mkdir(parents=True, exist_ok=True)
    out.to_csv(OUT_CSV, index=False, encoding="utf-8-sig")

    hash_after = sha256(SRC)
    assert hash_before == hash_after, "원본 파일이 바뀌었습니다"
    write_report(raw, df, out, medians, krw, usd_krw, hash_before, hash_after)
    print(f"저장: {OUT_CSV.relative_to(ROOT)} ({out.shape[0]}행 × {out.shape[1]}열)")
    print(f"저장: {OUT_REPORT.relative_to(ROOT)}")


def write_report(raw, df, out, medians, krw, usd_krw, hash_before, hash_after):
    L = []
    L.append("# 데이터 품질 보고서 — buyers 정제 전·후\n")
    L.append(f"- 입력: `{SRC.relative_to(ROOT).as_posix()}` 시트 `buyers` (읽기만)")
    L.append(f"- 규칙: `workbench/day2/rules/정제규칙.md` 1–7칸 · 코드: `scripts/clean_buyers.py`")
    L.append(f"- 출력: `{OUT_CSV.relative_to(ROOT).as_posix()}` ({out.shape[0]}행 × {out.shape[1]}열)")
    L.append(f"- 원본 SHA-256 실행 전 `{hash_before[:16]}…` / 후 `{hash_after[:16]}…` → "
             f"{'같음(수정 없음)' if hash_before == hash_after else '**다름**'}\n")

    L.append("## 1. 통화 (1칸)\n")
    L.append("| 원천 표기 | 건수 | 정제 후 |")
    L.append("|---|---|---|")
    for v, n in raw["currency"].value_counts().items():
        L.append(f"| `{v}` | {n} | {CCY_MAP[str(v).strip().upper()]} |")
    L.append(f"\n정제 후: " + " · ".join(f"{k} {v}" for k, v in out['ccy_clean'].value_counts().items()) + "\n")

    L.append("## 2. 숫자 변환 (2칸)\n")
    L.append("| 열 | 전: 숫자 | 전: 문자 | 후: 숫자 | 후: 변환 실패 |")
    L.append("|---|---|---|---|---|")
    for c in AR_COLS:
        k = raw[c].map(kind).value_counts()
        L.append(f"| {c} | {k.get('숫자', 0)} | {k.get('문자', 0)} | {df[f'{c}_num'].notna().sum()} | 0 |")
    L.append("\n문자였던 값과 변환 결과:\n")
    L.append("| buyer_id | 열 | 원문 | 변환 값 |")
    L.append("|---|---|---|---|")
    for c in AR_COLS:
        for i in raw.index[raw[c].map(lambda v: isinstance(v, str))]:
            L.append(f"| {raw.at[i, 'buyer_id']} | {c} | `{raw.at[i, c]!r}` | {df.at[i, f'{c}_num']:,.0f} |")
    gap = df[(df["amt_num"] - df["aging_sum"]).abs() > 1]
    L.append("\n잔액(`amt_num`)과 연령대 합이 다른 행:\n")
    L.append("| buyer_id | 통화 | amt_num | 연령대 합 | 차이 |")
    L.append("|---|---|---|---|---|")
    for _, r in gap.iterrows():
        L.append(f"| {r.buyer_id} | {r.ccy_clean} | {r.amt_num:,.0f} | {r.aging_sum:,.0f} | {r.amt_num - r.aging_sum:,.0f} |")
    L.append("")

    L.append("## 3. 결측 (3칸) — 중위수 + 결측 플래그\n")
    L.append("| 열 | 전: 결측 | 채운 중위수 | 후: 결측 |")
    L.append("|---|---|---|---|")
    for c in FIN_COLS + BEHAV_COLS:
        L.append(f"| {c} | {df[f'{c}_missing'].sum()} | {medians[c]:,.2f} | {df[c].isna().sum()} |")
    L.append(f"\n- `fin_missing = 1`: {out['fin_missing'].sum()}행 (유동자산·유동부채·총부채·자기자본·매출 중 하나라도 빈칸)")
    L.append("- 행동 열 `{열}_missing` 플래그는 계산했지만, 요청한 출력 열 목록에 없어 CSV에는 넣지 않았습니다.\n")

    L.append("## 4. 단위 의심 (4칸)\n")
    L.append(f"환산: `금액 × krw_close(통화) ÷ krw_close(USD)`, {REF_DATE} 행. "
             + " · ".join(f"{k} {v:,.4f}원" for k, v in krw.items()) + "\n")
    L.append(f"`unit_flag = 1` (USD 환산 잔액 > 한도 × {UNIT_MULT}): {out['unit_flag'].sum()}건\n")
    L.append("| buyer_id | 통화 | amt_num | ar_balance_usd | 한도(USD) | 연령대 합 |")
    L.append("|---|---|---|---|---|---|")
    for _, r in df[df["unit_flag"] == 1].iterrows():
        L.append(f"| {r.buyer_id} | {r.ccy_clean} | {r.amt_num:,.0f} | {r.ar_balance_usd:,.0f} | {r.credit_limit_usd:,.0f} | {r.aging_sum:,.0f} |")
    L.append("\n값은 고치지 않았습니다. 원천 확인 후 정제규칙.md 9칸에 기록합니다.\n")

    L.append("## 5. 자본잠식 (5칸)\n")
    L.append("| buyer_id | equity(원값) | debt_to_equity |")
    L.append("|---|---|---|")
    for _, r in df[df["neg_equity"] == 1].iterrows():
        L.append(f"| {r.buyer_id} | {r.equity:,.0f} | 빈칸 |")
    L.append("")

    L.append("## 6. 국가위험 (6칸)\n")
    L.append("| oecd_crc 원천 | 건수 | country_risk | crc_unclassified |")
    L.append("|---|---|---|---|")
    for v, n in raw["oecd_crc"].map(str).value_counts().sort_index().items():
        L.append(f"| `{v}` | {n} | {0 if v == '-' else v} | {1 if v == '-' else 0} |")
    L.append("")

    L.append("## 7. 출력 열 결측 (정제 후)\n")
    L.append("| 열 | 결측 | 이유 |")
    L.append("|---|---|---|")
    reasons = {"pct_current": "잔액(연령대 합) 0 → 빈칸", "pct_ar_31p": "잔액(연령대 합) 0 → 빈칸",
               "pct_91plus": "잔액(연령대 합) 0 → 빈칸", "late_ratio": "invoices_12m = 0 → 빈칸",
               "dispute_ratio": "invoices_12m = 0 → 빈칸", "debt_to_equity": "자본잠식(5칸) → 빈칸"}
    for c in OUT_COLS:
        n = out[c].isna().sum()
        if n:
            L.append(f"| {c} | {n} | {reasons.get(c, '확인 필요')} |")
    L.append("")
    OUT_REPORT.write_text("\n".join(L), encoding="utf-8")


if __name__ == "__main__":
    main()
