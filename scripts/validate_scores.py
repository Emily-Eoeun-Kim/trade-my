"""2일차: 뉴스 점수 검사 — workbench/day2/outputs/news_scored.jsonl 이 news_score_v1.md [출력] 규칙을 지키는지 본다.

원본(data/checkpoints/d2_news.csv)은 읽기만 하고, 점수는 고치지 않는다(위반 행만 알려 준다).
검사: 줄 수 · 점수 0–10 정수 · 라벨 = 점수 대역 · evidence가 원문 headline · body_short 안에 글자 그대로 있는지.
실행: uv run python scripts/validate_scores.py
"""

import csv
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "data/checkpoints/d2_news.csv"
SCORED = ROOT / "workbench/day2/outputs/news_scored.jsonl"
N_ROWS = 100  # 채점한 범위: d2_news.csv 1–100행


def band(score: int) -> str:
    """news_score_v1.md 규칙 5: 0–2 severe, 3–4 high, 5 watch, 6–10 low."""
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
    lines = SCORED.read_text(encoding="utf-8").splitlines()

    problems: list[str] = []
    if len(lines) != N_ROWS:
        problems.append(f"줄 수: {len(lines)}줄 (기대 {N_ROWS}줄)")

    for i, line in enumerate(lines, 1):
        try:
            o = json.loads(line)
        except json.JSONDecodeError as e:
            problems.append(f"{i}행: JSON 오류 ({e})")
            continue
        nid = o.get("news_id")
        tag = f"{i}행 {nid}"
        s = o.get("news_sent_0_10")
        # bool은 int의 하위형이라 따로 막는다
        if not isinstance(s, int) or isinstance(s, bool) or not 0 <= s <= 10:
            problems.append(f"{tag}: 점수가 0–10 정수가 아님 ({s!r})")
        elif o.get("label") != band(s):
            problems.append(f"{tag}: 라벨 {o.get('label')!r} ≠ 점수 {s}의 대역 {band(s)!r}")
        row = src.get(nid)
        if row is None:
            problems.append(f"{tag}: 원문에 없는 news_id")
            continue
        ev = o.get("evidence") or ""
        if not ev or (ev not in row["headline"] and ev not in row["body_short"]):
            problems.append(f"{tag}: evidence가 원문 headline · body_short에 그대로 없음 ({ev!r})")

    if problems:
        print(f"위반 {len(problems)}건")
        for p in problems:
            print(" -", p)
        return 1
    print(f"통과: {len(lines)}줄 · 점수 0–10 정수 · 라벨 대역 일치 · evidence 원문 그대로")
    return 0


if __name__ == "__main__":
    sys.exit(main())
