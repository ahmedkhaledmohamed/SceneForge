# Thinking Trail: feat/shop-links

## Problem Framing
Step 14 of the 20-step execution plan — generate visual product link cards from scene refs that have shop URLs, plus a plain-text link list and an SRT overlay for timed product callouts in video exports.

## Approach
Followed the established pattern: new module (`link_card.py`) for business logic, API endpoints in `api.py` matching existing URL structure, frontend section added to SequenceTab alongside captions, and a dedicated test file.

## Key Decisions
- Used PIL/Pillow (already a dependency) for card image generation — no new deps needed.
- Deduplicated product refs by URL across scenes to avoid duplicates on the card.
- SRT overlay times product labels to scene positions in the sequence, defaulting to 3s display.
- Added a `downloadFile` helper in the frontend API layer to handle binary file downloads cleanly, reusable by future features.

## Outcome
4 new API endpoints, 14 new tests (206 total, all passing). Link card section auto-hides when no product refs exist.
