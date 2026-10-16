"""3일차 실습 C: 한빛식당(가상) 밥 예보 페이지 — workbench/day3/outputs/hanbit_lunch.html 한 장을 쓴다.

입력: workbench/day3/outputs/lunch_clean.csv (깨끗한 표) · labs/day3/lab-c/nutritionist_memo.md (믿음 글, 읽기만)
구역: 머리 → 예보 성적표 → 영양사님 감 검증 (다음 단계에서 구역을 더한다)
같은 입력이면 같은 페이지가 나오도록 날짜 · 난수 같은 바뀌는 값은 넣지 않는다(LightGBM은 random_state 고정).
실행: uv run python scripts/lunch_page.py
"""

import html
import json
import math
import re
from pathlib import Path

import numpy as np
import pandas as pd
from lightgbm import LGBMRegressor
from sklearn.linear_model import LinearRegression

ROOT = Path(__file__).resolve().parents[1]
CLEAN = ROOT / "workbench/day3/outputs/lunch_clean.csv"
MEMO = ROOT / "labs/day3/lab-c/nutritionist_memo.md"
PLAN = ROOT / "labs/day3/lab-c/next_week_plan.csv"
OUT = ROOT / "workbench/day3/outputs/hanbit_lunch.html"

DIFF_LINE = 2.0   # 100명당 2명 이상 차이 나면 '차이 있음' (사람이 정한 선)
HOT = 31          # 믿음 4: 31도 이상 = 더운 날
WARM = 25         # 믿음 4: 25도 이상 31도 미만 = 비교할 날

TEST_START = "2026-09-14"  # 이 날 전 = 배우는 기간, 이 날부터 = 시험 기간
MARGIN = 10                # AI 준비 = 예보 + 10인분
COST = 4500                # 1인분 원가(가정)
MENU_MULT = {"돈가스": 1.1, "카레": 1.1, "샐러드": 0.9}  # 영양사님 공식 배수(나머지 1.0)
CAT_COLS = ["요일", "날씨", "메인메뉴", "행사"]
NUM_COLS = ["최고기온", "월급날", "출근예정"]
TEST_MARKS = {"2026-09-23": "추석 연휴 전날 · 돈가스", "2026-09-30": "비 오는 수요일 · 카레"}

CHART_JS = "https://cdnjs.cloudflare.com/ajax/libs/Chart.js/4.4.1/chart.umd.min.js"
FONT_CSS = "https://fonts.googleapis.com/css2?family=Noto+Sans+KR:wght@400;500;700&display=swap"


# ---------------------------------------------------------------- 데이터
def load_clean():
    df = pd.read_csv(CLEAN, encoding="utf-8-sig", dtype={"최고기온": float})
    df["행사"] = df["행사"].fillna("")
    df["per100"] = df["식수"] / df["출근예정"] * 100  # 출근 100명당 식수
    return df


def load_beliefs():
    """메모의 '제가 믿는 다섯 가지' 글 — 번호 → 글(굵은 표시만 떼고 그대로)."""
    text = MEMO.read_text(encoding="utf-8")
    beliefs = {}
    for m in re.finditer(r"^(\d)\. (.+)$", text, flags=re.M):
        beliefs[int(m[1])] = m[2].replace("**", "").strip()
    assert sorted(beliefs) == [1, 2, 3, 4, 5], beliefs
    return beliefs


# ---------------------------------------------------------------- 감 검증 계산
def judge(diff):
    """diff = (믿음대로라면 큰 쪽) − (작은 쪽). 2명 이상이면 맞음, 반대로 2명 이상이면 틀림, 그 사이 반만."""
    if diff >= DIFF_LINE:
        return "맞음"
    if diff <= -DIFF_LINE:
        return "틀림"
    return "반만"


def group(sub, label):
    return {"label": label, "value": round(float(sub["per100"].mean()), 1), "days": int(len(sub))}


def check_beliefs(df):
    base = df[(df["행사"] == "") & (df["월급날"] == 0)]  # 행사 없고 월급날 아닌 날
    memo = load_beliefs()
    cards = []

    # 믿음 1: 비 오는 날 > 맑은 날
    a, b = group(base[base["날씨"] == "비"], "비 오는 날"), group(base[base["날씨"] == "맑음"], "맑은 날")
    cards.append(two_group_card(1, memo[1], a, b, a["value"] - b["value"]))

    # 믿음 2: 금요일 < 월–목
    a, b = group(base[base["요일"] == "금"], "금요일"), group(base[base["요일"].isin(["월", "화", "수", "목"])], "월–목")
    cards.append(two_group_card(2, memo[2], a, b, b["value"] - a["value"]))

    # 믿음 3: 돈가스가 1등
    menus = sorted((group(g, name) for name, g in base.groupby("메인메뉴")),
                   key=lambda r: (-r["value"], r["label"]))
    top, second = menus[0], menus[1]
    donkatsu = next(r for r in menus if r["label"] == "돈가스")
    if top["label"] == "돈가스" and top["value"] - second["value"] >= DIFF_LINE:
        verdict = "맞음"
    elif top["value"] - donkatsu["value"] < DIFF_LINE:
        verdict = "반만"
    else:
        verdict = "틀림"
    rank = menus.index(donkatsu) + 1
    if top["label"] == "돈가스":
        note = f"돈가스가 1등, 2등({second['label']})보다 {top['value'] - second['value']:.1f}명 많음"
    else:
        note = f"1등은 {top['label']}, 돈가스는 {rank}등 — 1등보다 {top['value'] - donkatsu['value']:.1f}명 적음"
    cards.append({"id": 3, "memo": memo[3], "groups": menus, "highlight": ["돈가스"],
                  "verdict": verdict, "note": note})

    # 믿음 4: 31도 이상 < 25도 이상 31도 미만 (기온 빈칸은 뺌)
    t = base["최고기온"]
    a = group(base[t >= HOT], f"{HOT}도 이상")
    b = group(base[(t >= WARM) & (t < HOT)], f"{WARM}도 이상 {HOT}도 미만")
    card = two_group_card(4, memo[4], a, b, b["value"] - a["value"])
    card["note"] += f" · {HOT}도 이상인 날 {a['days']}일"
    cards.append(card)

    # 믿음 5: 월요일 < 화–목
    a, b = group(base[base["요일"] == "월"], "월요일"), group(base[base["요일"].isin(["화", "수", "목"])], "화–목")
    cards.append(two_group_card(5, memo[5], a, b, b["value"] - a["value"]))

    # 메모에 없던 규칙: 월급날(월급날인 날 모두) vs 보통 날
    a, b = group(df[df["월급날"] == 1], "월급날"), group(base, "보통 날")
    diff = a["value"] - b["value"]
    word = "많음" if diff > 0 else "적음"
    cards.append({"id": "pay", "memo": "월급날에는 식수가 달라질까? (메모에 없던 규칙)",
                  "groups": [a, b], "highlight": ["월급날"],
                  "verdict": "차이 있음" if abs(diff) >= DIFF_LINE else "차이 작음",
                  "note": f"월급날이 보통 날보다 100명당 {abs(diff):.1f}명 {word}"})
    return base, cards


def two_group_card(no, memo_text, a, b, diff):
    """a = 믿음이 말하는 쪽, b = 견주는 쪽. diff는 믿음 방향으로 잰 차이."""
    gap = a["value"] - b["value"]
    word = "많음" if gap > 0 else "적음"
    return {"id": no, "memo": memo_text, "groups": [a, b], "highlight": [a["label"]],
            "verdict": judge(diff),
            "note": f"{a['label']}이 {b['label']}보다 100명당 {abs(gap):.1f}명 {word}"}


# ---------------------------------------------------------------- 예보관 시험 계산
def round_half_up(x):
    return int(math.floor(x + 0.5))


def make_features(rows, temp_fill, columns=None):
    """재료: 요일 · 날씨 · 최고기온(빈칸 = 배우는 기간 가운데 값) · 메인메뉴 · 행사(빈칸 = 없음) · 월급날 · 출근예정.
    글자 열은 get_dummies(drop_first 없이). columns를 주면 배울 때와 같은 열로 맞추고 없는 열은 0."""
    X = rows[CAT_COLS + NUM_COLS].copy()
    X["최고기온"] = X["최고기온"].fillna(temp_fill)
    X["행사"] = X["행사"].replace("", "없음")
    X = pd.get_dummies(X, columns=CAT_COLS, dtype=float)
    if columns is not None:
        X = X.reindex(columns=columns, fill_value=0.0)
    return X


def nutritionist_formula(df, date, weekday, menu):
    """그날 전 같은 요일의 실제 식수 4개(가장 가까운 날부터)의 평균 × 메뉴 배수."""
    prev = df[(df["요일"] == weekday) & (df["날짜"] < date)].sort_values("날짜").tail(4)
    assert len(prev) == 4, (date, len(prev))
    return float(prev["식수"].mean()) * MENU_MULT.get(menu, 1.0)


def make_forecasters():
    return {
        "선형 회귀": LinearRegression(),
        "LightGBM": LGBMRegressor(n_estimators=300, learning_rate=0.05, num_leaves=15,
                                  min_child_samples=5, random_state=42, verbose=-1),
    }


def outcome(prep, actual):
    left = np.maximum(prep - actual, 0)
    short = np.maximum(actual - prep, 0)
    return {"left": int(left.sum()), "left_won": int(left.sum()) * COST,
            "short": int(short.sum()), "short_days": int((short > 0).sum())}


def forecast_test(df):
    train = df[df["날짜"] < TEST_START]
    test = df[df["날짜"] >= TEST_START]
    temp_fill = float(train["최고기온"].median())
    X_train = make_features(train, temp_fill)
    columns = list(X_train.columns)
    X_test = make_features(test, temp_fill, columns)
    y_train = train["식수"].to_numpy()
    actual = test["식수"].to_numpy()

    models, preds, scores = make_forecasters(), {}, {}
    for name, model in models.items():
        model.fit(X_train.to_numpy(), y_train)
        preds[name] = model.predict(X_test.to_numpy())
        scores[name] = float(np.mean(np.abs(preds[name] - actual)))  # 하루 평균 몇 인분 차이
    chosen = min(scores, key=scores.get)
    pred = preds[chosen]

    formula = np.array([nutritionist_formula(df, r["날짜"], r["요일"], r["메인메뉴"])
                        for _, r in test.iterrows()])
    ai_prep = np.array([round_half_up(p) + MARGIN for p in pred])
    f_prep = np.array([round_half_up(f) for f in formula])

    days = []
    for i, (_, r) in enumerate(test.iterrows()):
        d = pd.Timestamp(r["날짜"])
        days.append({"date": r["날짜"], "label": f"{d.month}/{d.day}", "weekday": r["요일"],
                     "menu": r["메인메뉴"], "actual": int(actual[i]),
                     "ai": round_half_up(pred[i]), "ai_prep": int(ai_prep[i]),
                     "formula": int(f_prep[i]), "mark": TEST_MARKS.get(r["날짜"], "")})

    return {
        "n_train": len(train), "n_test": len(test),
        "train_period": [train["날짜"].min(), train["날짜"].max()],
        "test_period": [test["날짜"].min(), test["날짜"].max()],
        "scores": {k: round(v, 1) for k, v in scores.items()},
        "chosen": chosen,
        "mae": {"ai": round(scores[chosen], 1),
                "formula": round(float(np.mean(np.abs(formula - actual))), 1)},
        "ai": outcome(ai_prep, actual), "formula": outcome(f_prep, actual),
        "days": days,
        # 아래는 페이지 JSON에 넣지 않는 값(다음 단계 '다음 주 예보'에서 다시 씀)
        "_model": models[chosen], "_columns": columns, "_temp_fill": temp_fill,
    }


# ---------------------------------------------------------------- 다음 주 예보 계산
def load_plan():
    """다음 주 계획 → 깨끗한 표와 같은 열 이름 · 같은 값 모양으로."""
    p = pd.read_csv(PLAN, encoding="utf-8-sig", dtype=str, keep_default_na=False)
    p = p.rename(columns={"날씨예보": "날씨", "최고기온예보": "최고기온"})
    p["최고기온"] = pd.to_numeric(p["최고기온"])
    p["월급날"] = (p["월급날"] == "Y").astype(int)
    p["출근예정"] = p["출근예정"].astype(int)
    return p


def comment_facts(df, base, cards):
    """코멘트에 끼워 넣을 근거 숫자 — 모두 감 검증과 같은 '출근 100명당 식수'."""
    by_id = {c["id"]: c for c in cards}
    g = lambda cid, i: by_id[cid]["groups"][i]["value"]
    events = {ev: round(float(sub["per100"].mean()), 1)
              for ev, sub in df[df["행사"] != ""].groupby("행사")}
    menus = {m["label"]: (m["value"], i + 1) for i, m in enumerate(by_id[3]["groups"])}
    return {"rain": g(1, 0), "sunny": g(1, 1), "fri": g(2, 0), "mon_thu": g(2, 1),
            "mon": g(5, 0), "tue_thu": g(5, 1), "pay": g("pay", 0), "normal": g("pay", 1),
            "events": events, "menus": menus, "n_menus": len(menus)}


def day_comment(r, prep, f_prep, F):
    """영양사님께 드리는 한 줄 — 그날 조건 하나를 근거로 + 공식과의 차이."""
    def more_less(a, b):
        return f"{abs(a - b):.1f}명 {'더' if a > b else '덜'}"

    if r["월급날"] == 1:
        why = f"월급날은 보통 날보다 100명당 {more_less(F['pay'], F['normal'])} 오셨어요"
        if r["요일"] == "금":
            why = "금요일에 월급날까지 겹쳐요. " + why
    elif r["행사"]:
        ev = F["events"].get(r["행사"])
        why = (f"{r['행사']} 날은 보통 날보다 100명당 {more_less(ev, F['normal'])} 오셨어요"
               if ev is not None else f"{r['행사']} 날은 지난 기록이 없어요(확인 필요)")
        if r["행사"] == "전사 교육":
            why += f"(출근예정도 {r['출근예정']}명으로 많아요)"
    elif r["날씨"] == "비":
        why = f"비 오는 날은 맑은 날보다 100명당 {more_less(F['rain'], F['sunny'])} 오셨어요"
    elif r["요일"] == "금":
        why = f"금요일은 월–목보다 100명당 {more_less(F['fri'], F['mon_thu'])} 오셨어요"
    elif r["요일"] == "월":
        why = f"월요일은 화–목보다 100명당 {more_less(F['mon'], F['tue_thu'])} 오셨어요"
    else:
        v, rank = F["menus"].get(r["메인메뉴"], (None, None))
        why = (f"{r['메인메뉴']} 날은 100명당 {v:.1f}명으로 메뉴 {F['n_menus']}개 중 {rank}위였어요"
               if v is not None else f"{r['메인메뉴']}은 지난 기록이 없어요(확인 필요)")

    gap = prep - f_prep
    if gap == 0:
        tail = "준비량은 영양사님 공식과 같아요."
    else:
        tail = f"AI 준비가 영양사님 공식보다 {abs(gap)}인분 {'많아요' if gap > 0 else '적어요'}."
    return f"{why}. {tail}"


def forecast_next(df, test, base, cards):
    plan = load_plan()
    X = make_features(plan, test["_temp_fill"], test["_columns"])  # 배울 때와 같은 열 · 같은 빈칸 처리
    pred = test["_model"].predict(X.to_numpy())
    F = comment_facts(df, base, cards)

    days = []
    for i, (_, r) in enumerate(plan.iterrows()):
        fc = round_half_up(pred[i])
        prep = fc + MARGIN
        f_prep = round_half_up(nutritionist_formula(df, r["날짜"], r["요일"], r["메인메뉴"]))
        d = pd.Timestamp(r["날짜"])
        days.append({"date": r["날짜"], "label": f"{d.month}/{d.day}", "weekday": r["요일"],
                     "forecast": fc, "prep": prep, "formula": f_prep,
                     "weather": r["날씨"], "menu": r["메인메뉴"], "event": r["행사"],
                     "payday": int(r["월급날"]), "staff": int(r["출근예정"]),
                     "comment": day_comment(r, prep, f_prep, F)})
    hi = max(days, key=lambda d: d["forecast"])
    lo = min(days, key=lambda d: d["forecast"])
    hi["mark"], lo["mark"] = "이번 주 가장 많은 날", "이번 주 가장 적은 날"
    return {"chosen": test["chosen"], "days": days, "max": hi["date"], "min": lo["date"]}


# ---------------------------------------------------------------- 페이지 조각
def esc(s):
    return html.escape(str(s))


def section_header(df):
    period = f"{df['날짜'].min()} – {df['날짜'].max()}"
    return f"""
<header class="head">
  <h1>한빛식당 밥 예보</h1>
  <p class="lead">(가상) 한빛정밀(주) 본사 구내식당 · 기록 기간 {period} · 만든 사람 총무팀 최 대리(가상)</p>
</header>"""


BADGE_CLASS = {"맞음": "ok", "반만": "half", "틀림": "bad", "차이 있음": "ok", "차이 작음": "half"}


def section_beliefs(df, base, cards):
    items = []
    for c in cards:
        is_pay = c["id"] == "pay"
        title = "메모에 없던 규칙" if is_pay else f"믿음 {c['id']}"
        if len(c["groups"]) == 2:
            nums = "".join(
                f'<div class="num"><span class="n">{g["value"]:.1f}</span>'
                f'<span class="l">{esc(g["label"])} · {g["days"]}일</span></div>'
                for g in c["groups"])
        else:  # 믿음 3: 1등과 돈가스
            top = c["groups"][0]
            dk = next(g for g in c["groups"] if g["label"] == "돈가스")
            pair = [top, dk] if top is not dk else c["groups"][:2]
            nums = "".join(
                f'<div class="num"><span class="n">{g["value"]:.1f}</span>'
                f'<span class="l">{esc(g["label"])} · {g["days"]}일</span></div>'
                for g in pair)
        height = 28 * len(c["groups"]) + 24
        items.append(f"""
  <article class="card{' extra' if is_pay else ''}">
    <div class="card-top">
      <span class="tag">{title}</span>
      <span class="badge {BADGE_CLASS[c['verdict']]}">{c['verdict']}</span>
    </div>
    <p class="memo">“{esc(c['memo'])}”</p>
    <div class="nums">{nums}</div>
    <div class="chart" style="height:{height}px"><canvas id="chart-{c['id']}" role="img" aria-label="{esc(title)} 출근 100명당 식수 막대"></canvas></div>
    <p class="note">{esc(c['note'])}</p>
  </article>""")
    return f"""
<section id="beliefs">
  <h2>영양사님 감 검증</h2>
  <p class="desc">출근 인원이 다른 날도 견줄 수 있게 <b>출근 100명당 식수</b>(식수 ÷ 출근예정 × 100)로 비교했습니다.
  행사가 없고 월급날이 아닌 {len(base)}일만 썼습니다(월급날 카드는 월급날인 날 모두).
  100명당 {DIFF_LINE:g}명 이상 차이 나면 '차이 있음'으로 봅니다 — 이 선은 사람이 정했습니다.</p>
  <div class="cards">{''.join(items)}
  </div>
</section>"""


def section_next_week(nw):
    cards = []
    for d in nw["days"]:
        badges = [d["weather"], d["menu"]] + ([d["event"]] if d["event"] else []) + (["월급날"] if d["payday"] else [])
        chips = "".join(f'<span class="chip">{esc(b)}</span>' for b in badges)
        mark = d.get("mark", "")
        mark_cls = " hi" if d["date"] == nw["max"] else (" lo" if d["date"] == nw["min"] else "")
        mark_html = f'<span class="day-mark{mark_cls}">{esc(mark)}</span>' if mark else ""
        cards.append(f"""
    <article class="card day{mark_cls}">
      <div class="day-top"><span class="day-date">{d["label"]}</span><span class="day-wd">{d["weekday"]}요일</span></div>
      {mark_html}
      <p class="day-n">{d["forecast"]}<small>명</small></p>
      <p class="day-prep">준비 {d["prep"]}인분</p>
      <p class="day-f">영양사님 공식이면 {d["formula"]}인분</p>
      <div class="chips">{chips}</div>
      <p class="note">{esc(d["comment"])}</p>
    </article>""")
    return f"""
<section id="nextweek">
  <h2>다음 주 예보</h2>
  <p class="desc">{nw["days"][0]["date"]} – {nw["days"][-1]["date"]}의 계획을 시험에서 고른 우리 예보관({esc(nw["chosen"])})에게 물었습니다.
  준비 = 예보 + {MARGIN}인분. 근거 숫자는 아래 '영양사님 감 검증'과 같은 출근 100명당 식수입니다.</p>
  <div class="week">{''.join(cards)}
  </div>
</section>"""


def section_scorecard(t):
    duel = "".join(
        f'<div class="fc{" chosen" if name == t["chosen"] else ""}">'
        f'<span class="fc-name">{esc(name)}</span>'
        f'<span class="fc-score">{score:.1f}<small>인분</small></span>'
        f'<span class="fc-sub">하루 평균 차이</span>'
        f'{"<span class=badge ok>우리 예보관</span>" if name == t["chosen"] else ""}</div>'
        for name, score in t["scores"].items())

    marks = "".join(
        f'<li><b>{d["label"]}({d["weekday"]})</b> {esc(d["mark"])} — 실제 {d["actual"]}명 · '
        f'우리 예보관 {d["ai"]}명(준비 {d["ai_prep"]}인분) · 영양사님 공식 {d["formula"]}인분</li>'
        for d in t["days"] if d["mark"])

    def better(ai, f):  # 작을수록 좋은 값 — 더 작은 쪽에 강조
        return ("good" if ai < f else "", "good" if f < ai else "")

    ai, fo = t["ai"], t["formula"]
    rows = [
        ("하루 평균 몇 인분 차이", f'{t["mae"]["ai"]:.1f}인분', f'{t["mae"]["formula"]:.1f}인분',
         better(t["mae"]["ai"], t["mae"]["formula"]), "예보와 실제의 차이를 크기만 재어 평균"),
        ("남은 밥", f'{ai["left"]:,}인분', f'{fo["left"]:,}인분', better(ai["left"], fo["left"]),
         f'AI {ai["left_won"]:,}원 · 공식 {fo["left_won"]:,}원 (1인분 {COST:,}원 가정)'),
        ("모자란 밥", f'{ai["short"]:,}인분', f'{fo["short"]:,}인분', better(ai["short"], fo["short"]),
         f'컵라면을 드신 분 · 모자란 날 AI {ai["short_days"]}일 · 공식 {fo["short_days"]}일'),
    ]
    cards = "".join(f"""
    <article class="card">
      <p class="tag">{title}</p>
      <div class="vs">
        <div><span class="vs-who">AI 준비</span><span class="vs-n {ca}">{a}</span></div>
        <div><span class="vs-who">영양사님 공식</span><span class="vs-n {cb}">{b}</span></div>
      </div>
      <p class="note">{esc(note)}</p>
    </article>""" for title, a, b, (ca, cb), note in rows)

    return f"""
<section id="scorecard">
  <h2>예보 성적표</h2>
  <p class="desc">{t["train_period"][0]} – {t["train_period"][1]}의 {t["n_train"]}일로 배우고,
  {t["test_period"][0]} – {t["test_period"][1]}의 {t["n_test"]}일(시험 기간)로 시험했습니다. 시험 기간은 배울 때 쓰지 않았습니다.</p>
  <div class="duel">{duel}</div>
  <p class="callout">복잡한 쪽이 늘 이기지는 않는다 — 시험으로 고른다</p>
  <p class="note">두 예보관의 설정은 모두 같은 결과를 보려고 고정했습니다.</p>

  <h3>시험 {t["n_test"]}일 — 실제와 예보</h3>
  <div class="card">
    <div class="chart line"><canvas id="chart-test" role="img" aria-label="시험 기간 실제 식수와 우리 예보관 · 영양사님 공식 선 그래프"></canvas></div>
    <ul class="marks">{marks}</ul>
  </div>

  <h3>AI 준비와 영양사님 공식, 나란히</h3>
  <p class="desc">AI 준비 = 우리 예보관({esc(t["chosen"])})의 예보 + {MARGIN}인분, 영양사님 준비 = 공식(그날 전 같은 요일 4번의 평균 × 돈가스 · 카레 1.1 · 샐러드 0.9).
  남은 밥 = 준비 − 실제, 모자란 밥 = 실제 − 준비(0보다 작으면 0).</p>
  <div class="cards">{cards}
  </div>
</section>"""


CSS = """
:root{--bg:#f4f5f7;--card:#ffffff;--ink:#1f2328;--sub:#5b6270;--line:#e3e6ea;
--accent:#1f6feb;--warn:#d1495b;--gray:#8b929c;--gray-soft:#c9ced6}
*{box-sizing:border-box}
html,body{margin:0;background:var(--bg);color:var(--ink)}
body{font-family:'Noto Sans KR',sans-serif;font-size:16px;line-height:1.6;word-break:keep-all;overflow-wrap:break-word}
main{max-width:1080px;margin:0 auto;padding:24px 16px 48px}
.head h1{margin:0 0 4px;font-size:28px}
.head .lead{margin:0;color:var(--sub);font-size:15px}
section{margin-top:32px}
h2{font-size:22px;margin:0 0 8px}
.desc{color:var(--sub);font-size:15px;margin:0 0 16px}
.cards{display:grid;grid-template-columns:repeat(auto-fill,minmax(min(100%,320px),1fr));gap:16px}
.card{background:var(--card);border:1px solid var(--line);border-radius:12px;padding:16px;min-width:0}
.card.extra{border-style:dashed}
.card-top{display:flex;justify-content:space-between;align-items:center;gap:8px}
.tag{font-size:14px;font-weight:700;color:var(--sub)}
.badge{font-size:14px;font-weight:700;padding:2px 12px;border-radius:999px;color:#fff}
.badge.ok{background:var(--accent)}
.badge.half{background:var(--gray)}
.badge.bad{background:var(--warn)}
.memo{margin:8px 0 12px;font-weight:500}
.nums{display:flex;gap:16px;flex-wrap:wrap}
.num{display:flex;flex-direction:column}
.num .n{font-size:26px;font-weight:700;line-height:1.2}
.num .l{font-size:14px;color:var(--sub)}
.chart{position:relative;width:100%;margin-top:8px}
.note{margin:8px 0 0;font-size:14px;color:var(--sub)}
h3{font-size:18px;margin:24px 0 8px}
.duel{display:grid;grid-template-columns:repeat(auto-fit,minmax(min(100%,220px),1fr));gap:12px}
.fc{background:var(--card);border:1px solid var(--line);border-radius:12px;padding:16px;display:flex;flex-direction:column;gap:4px;align-items:flex-start}
.fc.chosen{border:2px solid var(--accent)}
.fc-name{font-weight:700}
.fc-score{font-size:32px;font-weight:700;line-height:1.2}
.fc-score small{font-size:16px;font-weight:500;margin-left:4px}
.fc-sub{font-size:14px;color:var(--sub)}
.callout{margin:16px 0 0;font-weight:700}
.chart.line{height:300px;margin-top:0}
.marks{margin:12px 0 0;padding-left:20px;font-size:15px}
.marks li{margin-top:4px}
.vs{display:grid;grid-template-columns:1fr 1fr;gap:12px;margin-top:4px}
.vs > div{display:flex;flex-direction:column}
.vs-who{font-size:14px;color:var(--sub)}
.vs-n{font-size:24px;font-weight:700;line-height:1.3}
.vs-n.good{color:var(--accent)}
p.tag{margin:0}
.week{display:grid;grid-template-columns:1fr;gap:12px}
@media (min-width:600px){.week{grid-template-columns:repeat(2,1fr)}}
@media (min-width:960px){.week{grid-template-columns:repeat(5,1fr)}}
.day{display:flex;flex-direction:column;gap:4px}
.day.hi{border:2px solid var(--accent)}
.day.lo{border:2px solid var(--gray)}
.day-top{display:flex;justify-content:space-between;align-items:baseline;gap:8px}
.day-date{font-size:20px;font-weight:700}
.day-wd{font-size:15px;color:var(--sub)}
.day-mark{align-self:flex-start;font-size:14px;font-weight:700;padding:1px 10px;border-radius:999px;color:#fff;background:var(--gray)}
.day-mark.hi{background:var(--accent)}
.day-n{margin:4px 0 0;font-size:40px;font-weight:700;line-height:1.1}
.day-n small{font-size:18px;font-weight:500;margin-left:2px}
.day-prep{margin:0;font-size:17px;font-weight:700}
.day-f{margin:0;font-size:14px;color:var(--sub)}
.chips{display:flex;flex-wrap:wrap;gap:6px;margin-top:6px}
.chip{font-size:14px;padding:1px 10px;border-radius:999px;border:1px solid var(--line);background:var(--bg)}
"""

JS = """
const DATA = JSON.parse(document.getElementById('page-data').textContent);
const css = getComputedStyle(document.documentElement);
const ACCENT = css.getPropertyValue('--accent').trim();
const SOFT = css.getPropertyValue('--gray-soft').trim();
Chart.defaults.font.family = "'Noto Sans KR', sans-serif";
Chart.defaults.font.size = 14;
for (const c of DATA.beliefs) {
  const el = document.getElementById('chart-' + c.id);
  new Chart(el, {
    type: 'bar',
    data: {
      labels: c.groups.map(g => g.label),
      datasets: [{
        data: c.groups.map(g => g.value),
        backgroundColor: c.groups.map(g => c.highlight.includes(g.label) ? ACCENT : SOFT),
        borderRadius: 4, barThickness: 16
      }]
    },
    options: {
      indexAxis: 'y', maintainAspectRatio: false, animation: false,
      plugins: {legend: {display: false},
        tooltip: {callbacks: {label: ctx => `100명당 ${ctx.parsed.x.toFixed(1)}명 · ${c.groups[ctx.dataIndex].days}일`}}},
      scales: {x: {beginAtZero: true, grid: {color: '#eceef1'}},
               y: {grid: {display: false}}}
    }
  });
}

if (DATA.test) {
  const t = DATA.test;
  const INK = css.getPropertyValue('--ink').trim();
  const GRAY = css.getPropertyValue('--gray').trim();
  const markLines = {
    id: 'markLines',
    afterDatasetsDraw(chart) {
      const {ctx, chartArea, scales} = chart;
      ctx.save();
      t.days.forEach((d, i) => {
        if (!d.mark) return;
        const x = scales.x.getPixelForValue(i);
        ctx.strokeStyle = GRAY; ctx.setLineDash([4, 4]); ctx.lineWidth = 1;
        ctx.beginPath(); ctx.moveTo(x, chartArea.top); ctx.lineTo(x, chartArea.bottom); ctx.stroke();
        ctx.setLineDash([]); ctx.fillStyle = INK; ctx.textAlign = 'center';
        ctx.font = "700 14px 'Noto Sans KR', sans-serif";
        ctx.fillText(d.label, x, chartArea.top + 14);
      });
      ctx.restore();
    }
  };
  const pointR = t.days.map(d => d.mark ? 6 : 3);
  new Chart(document.getElementById('chart-test'), {
    type: 'line',
    data: {
      labels: t.days.map(d => d.label),
      datasets: [
        {label: '실제', data: t.days.map(d => d.actual), borderColor: INK, backgroundColor: INK,
         borderWidth: 2.5, pointRadius: pointR},
        {label: '우리 예보관(' + t.chosen + ')', data: t.days.map(d => d.ai), borderColor: ACCENT,
         backgroundColor: ACCENT, borderWidth: 2, pointRadius: 3},
        {label: '영양사님 공식', data: t.days.map(d => d.formula), borderColor: GRAY,
         backgroundColor: GRAY, borderWidth: 2, borderDash: [6, 4], pointRadius: 3}
      ]
    },
    options: {
      maintainAspectRatio: false, animation: false,
      interaction: {mode: 'index', intersect: false},
      plugins: {legend: {position: 'bottom', labels: {boxWidth: 14}},
        tooltip: {callbacks: {
          title: items => { const d = t.days[items[0].dataIndex]; return `${d.label}(${d.weekday}) ${d.menu}` + (d.mark ? ' — ' + d.mark : ''); },
          label: ctx => `${ctx.dataset.label} ${ctx.parsed.y}`}}},
      scales: {x: {grid: {display: false}}, y: {grid: {color: '#eceef1'}, title: {display: true, text: '명 · 인분'}}}
    },
    plugins: [markLines]
  });
}
"""


def render(sections, data):
    payload = json.dumps(data, ensure_ascii=False, sort_keys=True).replace("</", "<\\/")
    return f"""<!doctype html>
<html lang="ko">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>한빛식당 밥 예보</title>
<link rel="preconnect" href="https://fonts.googleapis.com">
<link rel="preconnect" href="https://fonts.gstatic.com" crossorigin>
<link rel="stylesheet" href="{FONT_CSS}">
<style>{CSS}</style>
</head>
<body>
<main>{''.join(sections)}
</main>
<script type="application/json" id="page-data">{payload}</script>
<script src="{CHART_JS}"></script>
<script>{JS}</script>
</body>
</html>
"""


def main():
    df = load_clean()
    base, cards = check_beliefs(df)
    test = forecast_test(df)
    nw = forecast_next(df, test, base, cards)
    sections = [section_header(df), section_next_week(nw), section_scorecard(test),
                section_beliefs(df, base, cards)]
    test_json = {k: v for k, v in test.items() if not k.startswith("_")}
    OUT.write_text(render(sections, {"beliefs": cards, "test": test_json, "next_week": nw}),
                   encoding="utf-8")

    print(f"[다음 주 예보] 우리 예보관 = {nw['chosen']}")
    for d in nw["days"]:
        print(f"  {d['date']}({d['weekday']}) 예보 {d['forecast']}명 · 준비 {d['prep']}인분 · 공식 {d['formula']}인분"
              + (f"  ← {d['mark']}" if d.get("mark") else "") + f"\n    코멘트: {d['comment']}")

    print(f"[예보관 시험] 배우는 기간 {test['n_train']}일 · 시험 기간 {test['n_test']}일 "
          f"({test['test_period'][0]} – {test['test_period'][1]})")
    for name, s in test["scores"].items():
        print(f"  {name}: 하루 평균 {s:.1f}인분 차이" + ("  ← 우리 예보관" if name == test["chosen"] else ""))
    for d in test["days"]:
        if d["mark"]:
            print(f"  {d['date']}({d['weekday']}) {d['mark']}: 실제 {d['actual']} · AI 예보 {d['ai']}"
                  f"(준비 {d['ai_prep']}) · 공식 {d['formula']}")
    for who in ("ai", "formula"):
        o = test[who]
        print(f"  {'AI 준비' if who == 'ai' else '영양사님 공식'}: 평균 차이 {test['mae'][who]:.1f} · "
              f"남은 밥 {o['left']}인분({o['left_won']:,}원) · 모자란 밥 {o['short']}인분 · 모자란 날 {o['short_days']}일")

    print(f"비교에 쓴 날(행사 없고 월급날 아님): {len(base)}일 / 깨끗한 표 {len(df)}일")
    for c in cards:
        name = "월급날" if c["id"] == "pay" else f"믿음 {c['id']}"
        shown = c["groups"] if len(c["groups"]) <= 2 else c["groups"]
        print(f"[{name}] {c['verdict']} — " + " · ".join(f"{g['label']} {g['value']:.1f}({g['days']}일)" for g in shown)
              + f" — {c['note']}")
    print(f"[저장] {OUT.relative_to(ROOT)}")


if __name__ == "__main__":
    main()
