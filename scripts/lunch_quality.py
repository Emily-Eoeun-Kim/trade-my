"""3일차 실습 C: 한빛식당(가상) 점심 기록 진단 — 안내서 「3. 데이터 진단」 1–4를 그대로 센다.

원본(labs/day3/lab-c/hanbit_lunch_log.csv)은 읽기만 하고, 보고서는 workbench/day3/outputs/에 씁니다.
실행: uv run python scripts/lunch_quality.py
"""

import re
from pathlib import Path

import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "labs/day3/lab-c/hanbit_lunch_log.csv"
OUT_DIR = ROOT / "workbench/day3/outputs"
OUT_MD = OUT_DIR / "lunch_quality.md"

LOW_RATIO = 0.2  # 출근예정의 20% 미만이면 '너무 적음' (R6와 같은 선)

WEEKDAY_STD = ["월", "화", "수", "목", "금", "토", "일"]
WEEKDAY_MAP = {
    **{w: w for w in WEEKDAY_STD},
    **{w + "요일": w for w in WEEKDAY_STD},
    **dict(zip(["Mon", "Tue", "Wed", "Thu", "Fri", "Sat", "Sun"], WEEKDAY_STD)),
}
WEATHER_STD = {"맑음", "흐림", "비", "눈"}
MENU_VARIANTS = ["돈까스", "카레라이스", "제육", "치킨마요덮밥", "김치 찌개"]
EVENT_VARIANTS = ["외부손님", "전사교육"]


def parse_date(s):
    """원본 날짜 글자 → (Timestamp, 형식 이름). 해석 못 하면 (NaT, '알 수 없음')."""
    s = s.strip()
    if re.fullmatch(r"\d{4}-\d{2}-\d{2}", s):
        return pd.Timestamp(s), "YYYY-MM-DD"
    m = re.fullmatch(r"(\d{4})/(\d{1,2})/(\d{1,2})", s)
    if m:
        return pd.Timestamp(int(m[1]), int(m[2]), int(m[3])), "YYYY/MM/DD"
    m = re.fullmatch(r"(\d{4})\.(\d{1,2})\.(\d{1,2})", s)
    if m:
        return pd.Timestamp(int(m[1]), int(m[2]), int(m[3])), "YYYY.M.D"
    m = re.fullmatch(r"(\d{1,2})월 (\d{1,2})일", s)
    if m:
        month = int(m[1])
        year = 2025 if month >= 10 else 2026  # 연도 없음: 10–12월은 2025, 1–9월은 2026
        return pd.Timestamp(year, month, int(m[2])), "M월 D일(연도 없음)"
    return pd.NaT, "알 수 없음"


def to_num(s):
    return pd.to_numeric(s, errors="coerce")


def examples(sub, col, n=2):
    """예시 n개 — 원본 글자 그대로, 어느 줄인지 보이게 날짜를 함께."""
    out = []
    for _, r in sub.head(n).iterrows():
        val = r[col]
        shown = f"`{val}`" if val != "" else "(빈칸)"
        out.append(shown if col == "날짜" else f"{r['날짜']} → {shown}")
    return " · ".join(out) if out else "-"


def main():
    df = pd.read_csv(SRC, dtype=str, keep_default_na=False, encoding="utf-8-sig")
    df.insert(0, "원본줄", range(2, len(df) + 2))  # 파일의 줄 번호(머리 줄 = 1)

    parsed = df["날짜"].map(parse_date)
    df["_date"] = parsed.map(lambda t: t[0])
    df["_fmt"] = parsed.map(lambda t: t[1])
    df["_wd_std"] = df["요일"].map(WEEKDAY_MAP)
    df["_wd_real"] = df["_date"].map(lambda d: WEEKDAY_STD[d.weekday()] if pd.notna(d) else None)
    df["_chul"] = to_num(df["출근예정"])
    df["_sik"] = to_num(df["식수"])

    holiday = df["비고"] == "휴무"
    work = df[~holiday]

    # ---- 1. 기본 정보
    n_rows = len(df)
    d_min, d_max = df["_date"].min(), df["_date"].max()
    n_unparsed = int(df["_date"].isna().sum())

    # ---- 2. 엉망 종류별
    rows = []

    bad_date = df[df["_fmt"] != "YYYY-MM-DD"]
    fmt_counts = bad_date["_fmt"].value_counts()
    fmt_note = " · ".join(f"{k} {v}" for k, v in fmt_counts.items())
    rows.append(("날짜 형식 섞임", len(bad_date), examples(bad_date, "날짜"), fmt_note))

    bad_wd = df[~df["요일"].isin(WEEKDAY_STD)]
    wd_long = int(bad_wd["요일"].str.endswith("요일").sum())
    wd_eng = int(bad_wd["요일"].str.fullmatch(r"[A-Za-z]+").sum())
    rows.append(("요일 표기 섞임", len(bad_wd), examples(bad_wd, "요일"),
                 f"`○요일` {wd_long} · 영어 {wd_eng}"))

    wd_wrong = df[df["_wd_std"].notna() & (df["_wd_std"] != df["_wd_real"])]
    rows.append(("(덧붙임) 적힌 요일 ≠ 날짜의 실제 요일", len(wd_wrong), examples(wd_wrong, "요일"),
                 " · ".join(f"{r['날짜']}: 적힘 {r['요일']} / 실제 {r['_wd_real']}"
                            for _, r in wd_wrong.iterrows())))

    dup_mask = df["_date"].duplicated(keep=False) & df["_date"].notna()
    dup = df[dup_mask]
    raw_cols = ["날짜", "요일", "날씨", "최고기온", "메인메뉴", "행사", "월급날", "출근예정", "식수", "비고"]
    dup_notes = []
    for d, g in dup.groupby("_date"):
        if g["비고"].str.contains("재집계").any():
            kind = "재집계 줄 있음"
        elif g[raw_cols].duplicated(keep=False).all():
            kind = "완전히 같은 줄"
        else:
            kind = "값이 다름 · 재집계 표시 없음"
        dup_notes.append(f"{d.date()} {len(g)}줄({kind})")
    rows.append(("같은 날짜가 두 줄", len(dup),
                 examples(dup.drop_duplicates("_date"), "날짜"),
                 f"날짜 {dup['_date'].nunique()}개 — " + " · ".join(dup_notes)))

    hol = df[holiday]
    rows.append(("휴무 줄", len(hol), examples(hol, "날짜"), "출근예정 · 식수가 0"))

    sik_blank = df[df["식수"] == ""]
    rows.append(("식수 빈칸", len(sik_blank), examples(sik_blank, "식수"),
                 " · ".join(sorted(set(sik_blank["비고"]))) or "-"))

    has_both = work["_chul"].notna() & work["_sik"].notna()
    over = work[has_both & (work["_sik"] > work["_chul"])]
    under = work[has_both & (work["_sik"] < work["_chul"] * LOW_RATIO)]
    impossible = pd.concat([over, under]).sort_values("원본줄")
    imp_ex = " · ".join(f"{r['날짜']} → 출근예정 `{r['출근예정']}` 식수 `{r['식수']}`"
                        for _, r in impossible.head(2).iterrows())
    rows.append(("불가능해 보이는 식수", len(impossible), imp_ex or "-",
                 f"출근예정보다 많음 {len(over)} · 출근예정의 {LOW_RATIO:.0%} 미만 {len(under)} (휴무 줄 제외)"))

    weather_bad = work[~work["날씨"].isin(WEATHER_STD)]
    w_counts = weather_bad["날씨"].replace("", "(빈칸)").value_counts()
    rows.append(("날씨 표기 섞임", len(weather_bad), examples(weather_bad[weather_bad["날씨"] != ""], "날씨"),
                 " · ".join(f"`{k}` {v}" for k, v in w_counts.items()) + " (휴무 줄 제외)"))

    t_c1 = work[work["최고기온"].str.contains("℃")]
    t_c2 = work[work["최고기온"].str.contains("°C")]
    t_blank = work[work["최고기온"] == ""]
    t_all = pd.concat([t_c1, t_c2, t_blank]).sort_values("원본줄")
    rows.append(("최고기온의 단위(℃ · °C)와 빈칸", len(t_all),
                 examples(pd.concat([t_c1.head(1), t_c2.head(1)]), "최고기온"),
                 f"`℃` {len(t_c1)} · `°C` {len(t_c2)} · 빈칸 {len(t_blank)} (휴무 줄 제외)"))

    menu_bad = df[df["메인메뉴"].isin(MENU_VARIANTS)]
    event_bad = df[df["행사"].isin(EVENT_VARIANTS)]
    m_counts = menu_bad["메인메뉴"].value_counts()
    e_counts = event_bad["행사"].value_counts()
    rows.append(("메뉴 · 행사 이름 섞임", len(menu_bad) + len(event_bad),
                 examples(menu_bad, "메인메뉴", 1) + " · " + examples(event_bad, "행사", 1),
                 "메뉴 " + " · ".join(f"`{k}` {v}" for k, v in m_counts.items())
                 + f" (소계 {len(menu_bad)}) / 행사 "
                 + " · ".join(f"`{k}` {v}" for k, v in e_counts.items())
                 + f" (소계 {len(event_bad)})"))

    chul_blank = df[df["출근예정"] == ""]
    rows.append(("출근예정 빈칸", len(chul_blank), examples(chul_blank, "출근예정"), "-"))

    # ---- 3. 비고 열
    bigo = df.loc[df["비고"] != "", "비고"].value_counts()

    # ---- 4. 사람이 정할 줄
    decide = []
    for _, r in impossible.iterrows():
        why = "식수가 출근예정보다 많음" if r["_sik"] > r["_chul"] else f"식수가 출근예정의 {LOW_RATIO:.0%} 미만"
        if r["비고"] == "수기 집계":
            why += " · 수기 집계(빼기 또는 ×10 보정 — R6에서 결정)"
        decide.append((r["원본줄"], r["날짜"], r["출근예정"], r["식수"], r["비고"], why))
    for _, r in wd_wrong.iterrows():
        decide.append((r["원본줄"], r["날짜"], r["출근예정"], r["식수"], r["비고"],
                       f"적힌 요일 {r['요일']} ≠ 실제 {r['_wd_real']} — 날짜가 틀렸는지 요일이 틀렸는지 확인 필요"))
    decide.sort(key=lambda t: t[0])

    # ---- 보고서
    L = []
    L.append("# 한빛식당(가상) 점심 기록 진단 — lunch_quality.md\n")
    L.append(f"- 원본: `labs/day3/lab-c/hanbit_lunch_log.csv` (읽기만 함, 고치지 않음)")
    L.append(f"- 만든 코드: `scripts/lunch_quality.py` · 숫자는 모두 이 코드가 센 값\n")

    L.append("## 1. 줄 수 · 열 이름 · 날짜 범위\n")
    L.append("| 항목 | 값 |\n|---|---|")
    L.append(f"| 줄 수(머리 줄 제외) | {n_rows} |")
    L.append(f"| 열 이름({len(raw_cols)}개) | {' · '.join(df.columns[1:11])} |")
    L.append(f"| 날짜 범위 | {d_min.date()} – {d_max.date()} (형식을 맞춰 읽은 값, 연도 없는 날짜는 10–12월 2025 · 1–9월 2026) |")
    L.append(f"| 날짜를 읽지 못한 줄 | {n_unparsed} |\n")

    L.append("## 2. 엉망인 곳 — 종류별\n")
    L.append("| 종류 | 줄 수 | 예시 2개(원본 글자 그대로) | 자세히 |\n|---|---:|---|---|")
    for kind, n, ex, note in rows:
        L.append(f"| {kind} | {n} | {ex} | {note} |")
    L.append("")

    L.append("## 3. 비고 열에 나오는 글\n")
    L.append("| 비고 | 줄 수 |\n|---|---:|")
    for k, v in bigo.items():
        L.append(f"| {k} | {v} |")
    L.append(f"| (빈칸) | {int((df['비고'] == '').sum())} |\n")

    L.append("## 4. 사람이 정해야 할 줄\n")
    if decide:
        L.append("| 원본 줄 | 날짜 | 출근예정 | 식수 | 비고 | 왜 사람이 정하나 |\n|---:|---|---|---|---|---|")
        for ln, d, c, s, b, why in decide:
            L.append(f"| {ln} | {d} | {c or '(빈칸)'} | {s or '(빈칸)'} | {b or '-'} | {why} |")
    else:
        L.append("없음")
    L.append("")

    OUT_DIR.mkdir(parents=True, exist_ok=True)
    OUT_MD.write_text("\n".join(L), encoding="utf-8")
    print("\n".join(L))
    print(f"\n[저장] {OUT_MD.relative_to(ROOT)}")


if __name__ == "__main__":
    main()
