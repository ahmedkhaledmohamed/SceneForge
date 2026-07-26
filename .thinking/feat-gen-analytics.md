# Thinking Trail: feat/gen-analytics

## Problem Framing
Step 17 — cost, quality, and model performance dashboards computed from existing generation data.

## Approach
Created `analytics.py` module with `project_analytics()` and `profile_analytics()` functions that iterate all projects/scenes/clips to compute stats. Two API endpoints. New Analytics page with CSS-only horizontal bar charts and stats cards.

## Key Decisions
- Computed on-the-fly from existing `meta.cost_usd` fields — no new data storage needed.
- Key metric: cost-per-kept-clip (the real ROI metric, not cost-per-generation).
- Spend trend uses ISO week keys for aggregation.
- Best-value model auto-identified as lowest cost-per-kept.
- CSS-only bar charts — no chart library dependency.

## Outcome
2 API endpoints, 8 tests (242 total, all passing). Analytics page with model comparison table, spend trend, and summary cards.
