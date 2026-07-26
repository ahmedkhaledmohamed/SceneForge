# Thinking Trail: feat/prompt-library

## Problem Framing
Step 15 of the execution plan — save, tag, and reuse successful prompts at the profile level so they carry across projects.

## Approach
Added `SavedPrompt` dataclass to `profile.py` with CRUD helpers. Four API endpoints (list, save, delete, use). Frontend PromptLibrary component in ProjectBoard with tag filtering, usage tracking, and copy-to-clipboard on "Use".

## Key Decisions
- Profile-level storage (not project-level) so prompts are reusable across all projects in a brand.
- "Use" copies to clipboard rather than DOM injection — more reliable across different scene creation flows.
- Tags can be passed as either a list or comma-separated string for flexibility.
- Usage counter increments server-side on each "Use" action for tracking which prompts are most valuable.

## Outcome
4 new API endpoints, 14 new tests (220 total, all passing). Prompt library panel toggles in the scenes toolbar.
