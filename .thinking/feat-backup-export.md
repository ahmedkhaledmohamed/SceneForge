# Thinking Trail: feat/backup-export

## Problem Framing
Step 20 (final) — full project zip export/import for portability and backup, including profile-wide backup.

## Approach
New `backup.py` module with `export_project_zip()`, `import_project_zip()`, and `export_all_projects_zip()`. Three API endpoints. Frontend: "backup zip" in project header, "Backup all" + "Import zip" in project list.

## Key Decisions
- Export includes project.json + scene refs + selected images + kept clips only — not all generated artifacts. Keeps zip sizes manageable.
- manifest.json with version, export date, and stats for validation.
- Import creates a new project with slug collision avoidance.
- Separate from existing `export.zip` (which exports final output files for sharing).

## Outcome
3 API endpoints, 12 tests (279 total, all passing). All 20 steps of the execution plan are now complete.
