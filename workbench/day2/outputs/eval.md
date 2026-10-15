# 2일차 뉴스 점수 평가 — news_score_v1

- 비교: `workbench/day2/outputs/news_scored.jsonl`(내 채점 100건) × `data/checkpoints/d2_news_answer.csv`(정답 20건), `news_id`로 맞춤
- 계산 코드: `scripts/eval_scores.py` (`uv run python scripts/eval_scores.py`로 다시 만든다)

## 지표

| 지표 | 계산식 | 값 |
|---|---|---|
| MAE | Σ\|내 점수 − 정답\| ÷ 20 = 9 ÷ 20 | **0.45** |
| ±2 이내 비율 | \|차이\| ≤ 2 인 건수 ÷ 20 = 20 ÷ 20 | **100%** |
| 라벨 일치율 | 라벨 같은 건수 ÷ 20 = 18 ÷ 20 | **90%** |
| (참고) 치우침 | Σ(내 점수 − 정답) ÷ 20 = -5 ÷ 20 | -0.25 |

## 차이가 가장 큰 2건

최대 \|차이\|는 1점이고 9건이 같다. 같으면 라벨이 어긋난 행을 먼저, 그다음 정답 파일 순서로 골랐다.

| news_id | 원문 (headline \| body_short) | 내 점수·라벨 | 정답 점수·라벨 | 이유 |
|---|---|---|---|---|
| N01343 | Ralora Kogyo K.K., 분기 매출 12% 감소 \| 수요 둔화와 프로젝트 지연이 원인으로 꼽혔다. | 4 high | 5 watch | 실제 매출 감소는 규칙 5의 '실적 둔화 전망'보다 무겁다고 보고 한 칸 내려 4를 줬지만, 정답은 매출 둔화를 경계(5)로 본다 — v1에 없는 '실적치면 한 칸 아래' 기준을 내가 덧붙였다. |
| N01339 | Nilora Water & Wastewater Authority warns margins will narrow on higher input costs \| Management expects operating margin to fall by about 19 points this year. | 4 high | 5 watch | 마진 19포인트 하락이라는 크기를 보고 4를 줬지만, 정답은 원가 상승에 따른 마진 축소 '전망'으로 보아 규칙 5의 앵커 5에 둔다. |

## 20건 전체

| news_id | buyer_id | 내 점수 | 정답 | 차이 | 내 라벨 | 정답 라벨 | 일치 | confidence |
|---|---|---|---|---|---|---|---|---|
| N01383 | B034 | 7 | 7 | +0 | low | low | O | 0.9 |
| N01381 | B141 | 9 | 9 | +0 | low | low | O | 0.9 |
| N01374 | B085 | 2 | 2 | +0 | severe | severe | O | 0.8 |
| N01371 | B066 | 4 | 3 | +1 | high | high | O | 0.6 |
| N01361 | B002 | 7 | 8 | -1 | low | low | O | 0.9 |
| N01360 | B086 | 8 | 9 | -1 | low | low | O | 0.6 |
| N01357 | B018 | 7 | 7 | +0 | low | low | O | 0.6 |
| N01356 | B065 | 7 | 8 | -1 | low | low | O | 0.8 |
| N01354 | B048 | 0 | 0 | +0 | severe | severe | O | 0.85 |
| N01351 | B134 | 9 | 9 | +0 | low | low | O | 0.7 |
| N01347 | B077 | 9 | 10 | -1 | low | low | O | 0.8 |
| N01343 | B113 | 4 | 5 | -1 | high | watch | X | 0.5 |
| N01339 | B032 | 4 | 5 | -1 | high | watch | X | 0.6 |
| N01334 | B053 | 5 | 5 | +0 | watch | watch | O | 0.8 |
| N01327 | B053 | 7 | 7 | +0 | low | low | O | 0.5 |
| N01321 | B140 | 7 | 8 | -1 | low | low | O | 0.9 |
| N01311 | B013 | 0 | 0 | +0 | severe | severe | O | 0.9 |
| N01312 | B081 | 7 | 7 | +0 | low | low | O | 0.5 |
| N01314 | B088 | 4 | 3 | +1 | high | high | O | 0.6 |
| N01295 | B128 | 7 | 7 | +0 | low | low | O | 0.6 |
