# Thinking Trail: feat/style-scoring

## Problem Framing
Step 18 — CLIP-based visual similarity scoring across selected scene images to measure and flag style inconsistencies.

## Approach
New `clip_scorer.py` backend module with cosine similarity math, pairwise scoring, and outlier detection. One API endpoint. Frontend badge in project header with color coding + "Check consistency" button.

## Key Decisions
- Embeddings via Together AI's endpoint with the same API key pattern used everywhere else.
- Pure math functions (`_cosine_similarity`, `score_consistency`, `find_outliers`) are fully testable without external calls — embeddings can be injected.
- Outlier threshold defaults to 0.7 (average pairwise similarity to the group).
- Badge color: green >80%, yellow 60-80%, red <60%.

## Outcome
1 API endpoint, 15 tests (257 total, all passing). Consistency badge + outlier warnings in project header.
