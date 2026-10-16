"""3일차 실습 C: 한빛식당(가상) 점심 기록 정제 — workbench/day3/outputs/lunch_rules.md 표를 그대로 옮긴 스크립트.

원본(labs/day3/lab-c/hanbit_lunch_log.csv)은 읽기만 하고, 결과는 workbench/day3/outputs/에 씁니다.
적용 순서: R1 → R2 → R3 → R4 → R5 → R10 → R6 → R7 → R8 → R9
실행: uv run python scripts/lunch_clean.py
"""

import math
import re
from pathlib import Path

import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "labs/day3/lab-c/hanbit_lunch_log.csv"
OUT_DIR = ROOT / "workbench/day3/outputs"
OUT_CSV = OUT_DIR / "lunch_clean.csv"
OUT_LOG = OUT_DIR / "lunch_clean_log.md"

COLS = ["날짜", "요일", "날씨", "최고기온", "메인메뉴", "행사", "월급날", "출근예정", "식수", "비고"]
HANDWRITTEN = "뺀다"  # R6 '수기 집계' 줄 — 수강생 결정(뺀다 / ×10 보정)
LOW_RATIO = 0.2       # R6: 출근예정의 20% 미만이면 뺀다

WEEKDAYS = ["월", "화", "수", "목", "금", "토", "일"]
WEEKDAY_MAP = {
    **{w: w for w in WEEKDAYS},
    **{w + "요일": w for w in WEEKDAYS},
    **dict(zip(["Mon", "Tue", "Wed", "Thu", "Fri", "Sat", "Sun"], WEEKDAYS)),
}
WEATHER_MAP = {
    "맑음": "맑음", "맑": "맑음", "sunny": "맑음",
    "흐림": "흐림", "구름많음": "흐림", "cloudy": "흐림",
    "비": "비", "rain": "비", "우천": "비", "소나기": "비", "흐리고 비": "비",
    "눈": "눈", "snow": "눈",
    "": "모름",
}
MENU_MAP = {"돈까스": "돈가스", "카레라이스": "카레", "제육": "제육볶음",
            "치킨마요덮밥": "치킨마요", "김치 찌개": "김치찌개"}
EVENT_MAP = {"외부손님": "외부 손님 방문", "전사교육": "전사 교육"}


def to_iso(s):
    """R1: 날짜 글자 → 'YYYY-MM-DD'."""
    s = s.strip()
    if re.fullmatch(r"\d{4}-\d{2}-\d{2}", s):
        return s
    m = re.fullmatch(r"(\d{4})[/.](\d{1,2})[/.](\d{1,2})", s)
    if m:
        y, mo, d = int(m[1]), int(m[2]), int(m[3])
    else:
        m = re.fullmatch(r"(\d{1,2})월 (\d{1,2})일", s)
        if not m:
            raise ValueError(f"날짜를 읽을 수 없음: {s!r}")
        mo, d = int(m[1]), int(m[2])
        y = 2025 if mo >= 10 else 2026
    return f"{y:04d}-{mo:02d}-{d:02d}"


def round_half_up(x):
    return int(math.floor(x + 0.5))


def main():
    df = pd.read_csv(SRC, dtype=str, keep_default_na=False, encoding="utf-8-sig")
    assert list(df.columns) == COLS, df.columns
    df["_order"] = range(len(df))  # 원본에서의 순서('나중 줄' 판단용)
    n_start = len(df)
    log = []  # (번호, 규칙, 고친/뺀 줄 수, 남은 줄 수, 자세히)

    # R1 날짜 형식
    new_date = df["날짜"].map(to_iso)
    n = int((new_date != df["날짜"]).sum())
    df["날짜"] = new_date
    log.append(("R1", "날짜를 YYYY-MM-DD로", n, len(df), "형식이 달랐던 줄을 고침"))

    # R2 요일 다시 계산 — 실제 요일과 달랐던 줄만 센다
    real = pd.to_datetime(df["날짜"]).dt.weekday.map(lambda i: WEEKDAYS[i])
    written = df["요일"].map(WEEKDAY_MAP)
    wrong = df[written != real]
    n = len(wrong)
    detail = " · ".join(f"{r['날짜']} 적힘 {r['요일']} → {real[i]}" for i, r in wrong.iterrows())
    df["요일"] = real
    log.append(("R2", "요일을 날짜에서 다시 계산", n, len(df), detail or "-"))

    # R3 휴무 줄 빼기
    mask = df["비고"] == "휴무"
    n = int(mask.sum())
    df = df[~mask]
    log.append(("R3", "휴무 줄 빼기", n, len(df), "-"))

    # R4 같은 날짜 두 줄 — 재집계 줄, 없으면 나중 줄을 남김
    keep_idx = []
    dup_dates = []
    for d, g in df.groupby("날짜", sort=False):
        if len(g) == 1:
            keep_idx.append(g.index[0])
            continue
        dup_dates.append(d)
        re_rows = g[g["비고"].str.contains("재집계")]
        pick = re_rows if len(re_rows) else g
        keep_idx.append(pick.sort_values("_order").index[-1])
    n = len(df) - len(keep_idx)
    df = df.loc[sorted(keep_idx)]
    log.append(("R4", "같은 날짜 두 줄 정리", n, len(df), "날짜 " + " · ".join(dup_dates)))

    # R5 식수 빈칸 빼기
    mask = df["식수"] == ""
    n = int(mask.sum())
    detail = " · ".join(df.loc[mask, "날짜"])
    df = df[~mask]
    log.append(("R5", "식수 빈칸 줄 빼기", n, len(df), detail or "-"))

    # R10 출근예정 빈칸 — 같은 요일 바로 앞 기록 4개(출근예정 있는 줄)의 median, 반올림
    df = df.sort_values(["날짜", "_order"]).copy()
    has = df["출근예정"] != ""
    filled = []
    for i, r in df[~has].iterrows():
        prev = df[has & (df["요일"] == r["요일"]) & (df["날짜"] < r["날짜"])].tail(4)
        if len(prev) < 4:
            raise ValueError(f"{r['날짜']}: 같은 요일 앞 기록이 4개보다 적음({len(prev)}개)")
        med = pd.to_numeric(prev["출근예정"]).median()
        val = round_half_up(med)
        df.at[i, "출근예정"] = str(val)
        filled.append(f"{r['날짜']}({r['요일']}) ← {'/'.join(prev['출근예정'])}의 가운데 값 {med:g} → {val}")
    log.append(("R10", "출근예정 빈칸 채우기", len(filled), len(df), " · ".join(filled) or "-"))

    # R6 불가능한 식수 · 수기 집계
    chul = pd.to_numeric(df["출근예정"])
    sik = pd.to_numeric(df["식수"])
    hand = df["비고"] == "수기 집계"
    bad = ~hand & ((sik > chul) | (sik < chul * LOW_RATIO))
    details = [f"{d} 출근예정 {c} 식수 {s}"
               for d, c, s in zip(df.loc[bad, "날짜"], df.loc[bad, "출근예정"], df.loc[bad, "식수"])]
    if HANDWRITTEN == "뺀다":
        drop = bad | hand
        details += [f"{d} 수기 집계 식수 {s} → 뺌" for d, s in zip(df.loc[hand, "날짜"], df.loc[hand, "식수"])]
        n = int(drop.sum())
    elif HANDWRITTEN == "×10 보정":
        df.loc[hand, "식수"] = (sik[hand] * 10).astype(int).astype(str)
        drop = bad
        details += [f"{d} 수기 집계 식수 {s} → ×10" for d, s in zip(df.loc[hand, "날짜"], df.loc[hand, "식수"])]
        n = int(drop.sum() + hand.sum())
    else:
        raise ValueError("R6 '수기 집계' 결정이 없음 — 수강생에게 물어볼 것")
    df = df[~drop]
    log.append(("R6", f"불가능한 식수 빼기 · 수기 집계 = {HANDWRITTEN}", n, len(df), " · ".join(details)))

    # R7 날씨 넷으로
    unknown = set(df["날씨"]) - set(WEATHER_MAP)
    if unknown:
        raise ValueError(f"R7 표에 없는 날씨: {unknown}")
    new = df["날씨"].map(WEATHER_MAP)
    n = int((new != df["날씨"]).sum())
    df["날씨"] = new
    log.append(("R7", "날씨 넷으로(빈칸 → 모름)", n, len(df), f"모름 {int((new == '모름').sum())}줄"))

    # R8 최고기온 숫자만
    new = df["최고기온"].str.replace("℃", "", regex=False).str.replace("°C", "", regex=False).str.replace(" ", "", regex=False)
    n = int((new != df["최고기온"]).sum())
    df["최고기온"] = new
    pd.to_numeric(df.loc[df["최고기온"] != "", "최고기온"])  # 숫자로 안 읽히면 여기서 멈춤
    log.append(("R8", "최고기온 단위 떼기", n, len(df), f"빈칸으로 둔 줄 {int((new == '').sum())}"))

    # R9 메뉴 · 행사 이름 통일 — 따로 세어 더함
    n_menu = int(df["메인메뉴"].isin(MENU_MAP).sum())
    n_event = int(df["행사"].isin(EVENT_MAP).sum())
    df["메인메뉴"] = df["메인메뉴"].replace(MENU_MAP)
    df["행사"] = df["행사"].replace(EVENT_MAP)
    log.append(("R9", "메뉴 · 행사 이름 통일", n_menu + n_event, len(df), f"메뉴 {n_menu} + 행사 {n_event}"))

    # 마지막 정리
    df["월급날"] = (df["월급날"] == "Y").astype(int)
    df["출근예정"] = df["출근예정"].astype(int)
    df["식수"] = df["식수"].astype(int)
    df = df.sort_values("날짜")[COLS].reset_index(drop=True)
    assert df["날짜"].is_unique

    OUT_DIR.mkdir(parents=True, exist_ok=True)
    df.to_csv(OUT_CSV, index=False, encoding="utf-8-sig")

    L = ["# 한빛식당(가상) 점심 기록 정제 기록 — lunch_clean_log.md\n",
         "- 규칙: `workbench/day3/outputs/lunch_rules.md` · 코드: `scripts/lunch_clean.py`",
         "- 세는 법: 그 규칙을 적용할 때 남아 있는 줄에서 셈. R2는 실제 요일과 달랐던 줄만. R9는 메뉴 + 행사.",
         f"- 처음 줄 수 **{n_start}** → 남은 줄 수 **{len(df)}** · 기간 {df['날짜'].min()} – {df['날짜'].max()}\n",
         "| 순서 | 규칙 | 할 일 | 고친(뺀) 줄 수 | 적용 뒤 남은 줄 | 자세히 |",
         "|---:|---|---|---:|---:|---|"]
    for k, (rid, name, cnt, left, det) in enumerate(log, 1):
        L.append(f"| {k} | {rid} | {name} | {cnt} | {left} | {det} |")
    L.append("")
    OUT_LOG.write_text("\n".join(L), encoding="utf-8")

    print("\n".join(L))
    print(f"[저장] {OUT_CSV.relative_to(ROOT)} ({len(df)}줄) · {OUT_LOG.relative_to(ROOT)}")


if __name__ == "__main__":
    main()
