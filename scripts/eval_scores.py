"""2일차: 뉴스 점수 평가 — 내 채점(news_scored.jsonl)을 정답 20건(d2_news_answer.csv)과 견준다.

지표: MAE = mean(|내 점수 − 정답|) · ±2 이내 비율 · 라벨 일치율 (+ 치우침 = mean(내 점수 − 정답)).
차이가 큰 행은 |차이| 큰 순 → 라벨 불일치 먼저 → 정답 파일 순서로 고른다.
원본(data/checkpoints/)은 읽기만 하고, 결과는 workbench/day2/outputs/eval.md 에 쓴다.
실행: uv run python scripts/eval_scores.py
"""

import csv
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "data/checkpoints/d2_news.csv"
ANSWER = ROOT / "data/checkpoints/d2_news_answer.csv"
SCORED = ROOT / "workbench/day2/outputs/news_scored.jsonl"
OUT = ROOT / "workbench/day2/outputs/eval.md"
TOP_N = 2

# 차이 큰 행의 이유 — 원문과 news_score_v1.md를 사람이(AI가) 읽고 쓴 판단 메모. 숫자가 아니라 해석이다.
REASONS = {
    "N01343": "실제 매출 감소는 규칙 5의 '실적 둔화 전망'보다 무겁다고 보고 한 칸 내려 4를 줬지만, 정답은 매출 둔화를 경계(5)로 본다 — v1에 없는 '실적치면 한 칸 아래' 기준을 내가 덧붙였다.",
    "N01339": "마진 19포인트 하락이라는 크기를 보고 4를 줬지만, 정답은 원가 상승에 따른 마진 축소 '전망'으로 보아 규칙 5의 앵커 5에 둔다.",
}


def band(score: int) -> str:
    if score <= 2:
        return "severe"
    if score <= 4:
        return "high"
    if score == 5:
        return "watch"
    return "low"


def main() -> int:
    sys.stdout.reconfigure(encoding="utf-8")
    with open(SRC, encoding="utf-8-sig", newline="") as f:
        src = {r["news_id"]: r for r in csv.DictReader(f)}
    with open(ANSWER, encoding="utf-8-sig", newline="") as f:
        ans = list(csv.DictReader(f))
    mine = {o["news_id"]: o for o in map(json.loads, SCORED.read_text(encoding="utf-8").splitlines())}

    missing = [a["news_id"] for a in ans if a["news_id"] not in mine]
    if missing:
        sys.exit(f"내 채점에 없는 정답 행: {missing}")

    rows = []
    for order, a in enumerate(ans):
        m = mine[a["news_id"]]
        t = int(a["news_sent_0_10_true"])
        rows.append({
            "order": order, "news_id": a["news_id"], "buyer_id": m["buyer_id"],
            "pred": m["news_sent_0_10"], "true": t, "diff": m["news_sent_0_10"] - t,
            "label": m["label"], "label_true": a["label_true"], "note": a["note_ko"],
            "evidence": m["evidence"], "confidence": m["confidence"],
        })

    n = len(rows)
    mae = sum(abs(r["diff"]) for r in rows) / n
    within2 = sum(abs(r["diff"]) <= 2 for r in rows)
    label_ok = sum(r["label"] == r["label_true"] for r in rows)
    bias = sum(r["diff"] for r in rows) / n
    max_abs = max(abs(r["diff"]) for r in rows)
    tied = sum(abs(r["diff"]) == max_abs for r in rows)
    top = sorted(rows, key=lambda r: (-abs(r["diff"]), r["label"] == r["label_true"], r["order"]))[:TOP_N]

    md = [
        "# 2일차 뉴스 점수 평가 — news_score_v1",
        "",
        f"- 비교: `workbench/day2/outputs/news_scored.jsonl`(내 채점 100건) × `data/checkpoints/d2_news_answer.csv`(정답 {n}건), `news_id`로 맞춤",
        "- 계산 코드: `scripts/eval_scores.py` (`uv run python scripts/eval_scores.py`로 다시 만든다)",
        "",
        "## 지표",
        "",
        "| 지표 | 계산식 | 값 |",
        "|---|---|---|",
        f"| MAE | Σ\\|내 점수 − 정답\\| ÷ {n} = {sum(abs(r['diff']) for r in rows)} ÷ {n} | **{mae:.2f}** |",
        f"| ±2 이내 비율 | \\|차이\\| ≤ 2 인 건수 ÷ {n} = {within2} ÷ {n} | **{within2 / n:.0%}** |",
        f"| 라벨 일치율 | 라벨 같은 건수 ÷ {n} = {label_ok} ÷ {n} | **{label_ok / n:.0%}** |",
        f"| (참고) 치우침 | Σ(내 점수 − 정답) ÷ {n} = {sum(r['diff'] for r in rows)} ÷ {n} | {bias:+.2f} |",
        "",
        "## 차이가 가장 큰 2건",
        "",
        f"최대 \\|차이\\|는 {max_abs}점이고 {tied}건이 같다. 같으면 라벨이 어긋난 행을 먼저, 그다음 정답 파일 순서로 골랐다.",
        "",
        "| news_id | 원문 (headline \\| body_short) | 내 점수·라벨 | 정답 점수·라벨 | 이유 |",
        "|---|---|---|---|---|",
    ]
    for r in top:
        s = src[r["news_id"]]
        md.append(f"| {r['news_id']} | {s['headline']} \\| {s['body_short']} | {r['pred']} {r['label']} | "
                  f"{r['true']} {r['label_true']} | {REASONS.get(r['news_id'], '확인 필요')} |")
    md += [
        "",
        "## 20건 전체",
        "",
        "| news_id | buyer_id | 내 점수 | 정답 | 차이 | 내 라벨 | 정답 라벨 | 일치 | confidence |",
        "|---|---|---|---|---|---|---|---|---|",
    ]
    for r in rows:
        ok = "O" if r["label"] == r["label_true"] else "X"
        md.append(f"| {r['news_id']} | {r['buyer_id']} | {r['pred']} | {r['true']} | {r['diff']:+d} | "
                  f"{r['label']} | {r['label_true']} | {ok} | {r['confidence']} |")
    OUT.write_text("\n".join(md) + "\n", encoding="utf-8")

    print(f"MAE {mae:.2f} · ±2 이내 {within2}/{n} · 라벨 일치 {label_ok}/{n} · 치우침 {bias:+.2f}")
    print("차이 큰 행:", ", ".join(f"{r['news_id']}({r['diff']:+d})" for r in top), f"(최대 |차이| {max_abs}점 {tied}건 동률)")
    print("썼음:", OUT.relative_to(ROOT).as_posix())
    return 0


if __name__ == "__main__":
    sys.exit(main())
