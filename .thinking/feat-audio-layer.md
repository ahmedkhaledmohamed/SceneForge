# Thinking Trail: feat/audio-layer

## Problem Framing
Step 19 — add audio support to clips: upload audio files, attach to clips with type classification, and merge into video using ffmpeg.

## Approach
Added `audio_file` and `audio_type` fields to Clip dataclass. New `audio.py` module with ffmpeg-based merge/strip. Three API endpoints for add, merge, and remove. Frontend ClipAudioSection component on completed clip cards.

## Key Decisions
- Audio upload accepts any media file (mp3/wav/m4a/mp4) via the existing upload pipeline — no audio generation API yet, just user-uploaded files.
- Three-step workflow: upload → preview → merge. Merge replaces the clip's video file with an audio-merged version.
- Audio types (ambient/music/voiceover) are metadata — they don't affect processing but help with organization.
- `strip_audio` utility included for future "remove audio from merged clip" use.

## Outcome
3 API endpoints + 1 config endpoint, 10 tests (267 total, all passing). Audio section on clip cards with upload/merge/remove controls.
