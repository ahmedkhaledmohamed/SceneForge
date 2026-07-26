# Thinking Trail: feat/asset-library

## Problem Framing
Step 16 — profile-level tagged assets reusable across projects, so garment/style/background photos can be uploaded once and used in any project's scenes.

## Approach
Added Asset dataclass to profile.py with CRUD helpers. Four API endpoints (list with tag/role filter, upload, delete, ref-from-asset). Frontend AssetPicker inline component in SceneCard for adding refs from the library.

## Key Decisions
- Assets stored at profile level (`assets/` dir), copied into project scene refs on use — no symlinks, so projects remain self-contained.
- `projects_used` tracks which projects have used each asset for analytics.
- ref-from-asset endpoint handles file collision avoidance and auto-populates role/label/url from the asset metadata.
- AssetPicker is inline in SceneCard rather than a separate page — faster workflow, one click to add.

## Outcome
4 new API endpoints, 14 new tests (234 total, all passing). Assets filterable by role and tag.
