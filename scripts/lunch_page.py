"""3일차 실습 C: 한빛식당(가상) 밥 예보 페이지 — workbench/day3/outputs/hanbit_lunch.html 한 장을 쓴다.

입력: workbench/day3/outputs/lunch_clean.csv (깨끗한 표) · labs/day3/lab-c/nutritionist_memo.md (믿음 글, 읽기만)
구역: 머리 → 영양사님 감 검증 (다음 단계에서 구역을 더한다)
같은 입력이면 같은 페이지가 나오도록 날짜 · 난수 같은 바뀌는 값은 넣지 않는다.
실행: uv run python scripts/lunch_page.py
"""

import html
import json
import re
from pathlib import Path

import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
CLEAN = ROOT / "workbench/day3/outputs/lunch_clean.csv"
MEMO = ROOT / "labs/day3/lab-c/nutritionist_memo.md"
OUT = ROOT / "workbench/day3/outputs/hanbit_lunch.html"

DIFF_LINE = 2.0   # 100명당 2명 이상 차이 나면 '차이 있음' (사람이 정한 선)
HOT = 31          # 믿음 4: 31도 이상 = 더운 날
WARM = 25         # 믿음 4: 25도 이상 31도 미만 = 비교할 날

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
    sections = [section_header(df), section_beliefs(df, base, cards)]
    OUT.write_text(render(sections, {"beliefs": cards}), encoding="utf-8")

    print(f"비교에 쓴 날(행사 없고 월급날 아님): {len(base)}일 / 깨끗한 표 {len(df)}일")
    for c in cards:
        name = "월급날" if c["id"] == "pay" else f"믿음 {c['id']}"
        shown = c["groups"] if len(c["groups"]) <= 2 else c["groups"]
        print(f"[{name}] {c['verdict']} — " + " · ".join(f"{g['label']} {g['value']:.1f}({g['days']}일)" for g in shown)
              + f" — {c['note']}")
    print(f"[저장] {OUT.relative_to(ROOT)}")


if __name__ == "__main__":
    main()
