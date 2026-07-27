# Gemini Summary + Tasks Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Split `bot.py` into a `bot/` package, load Gemini prompts from Markdown files, and enrich voice notes with two independent Gemini calls (optional `#### Riassunto` + optional `#### Task`).

**Architecture:** Package `bot/` with entrypoint `python -u -m bot`. Config loads prompt Markdown at startup. Voice handler calls summary then tasks Gemini helpers independently; notes builder omits empty sections. `SUMMARY_PROVIDER=local` writes transcript only.

**Tech Stack:** Python 3.11, python-telegram-bot, google-genai, whisper.cpp, Docker.

## Global Constraints

- Prefer edits to `Dockerfile`, `bot.py`, `bot/`, `config/` only.
- Do not auto-script `ob login` / `ob sync-setup`.
- Fail fast on missing required env / prompt files.
- Keep supervisord command `python -u -m bot`.

## File map

| Path | Responsibility |
|---|---|
| `bot.py` | Stub → `bot.app.main()` |
| `bot/__init__.py` | Package marker |
| `bot/config.py` | Env + prompt file loading |
| `bot/stt.py` | ffmpeg + whisper |
| `bot/gemini_enrichment.py` | Two Gemini calls + NONE/task normalize |
| `bot/notes.py` | Markdown entries + atomic append |
| `bot/media.py` | Image compression |
| `bot/handlers.py` | Telegram handlers |
| `bot/app.py` | Application wiring |
| `Dockerfile` | COPY `bot/`, `config/prompts/` |
| `tests/unit/test_notes.py` | Voice markdown optional sections |
| `tests/unit/test_gemini_enrichment.py` | NONE parsing + task normalize |

### Task 1: Pure helpers (notes + gemini parse) with tests

**Files:**
- Create: `bot/notes.py`, `bot/gemini_enrichment.py`, `tests/unit/test_notes.py`, `tests/unit/test_gemini_enrichment.py`, `tests/unit/conftest.py` (optional), `pytest.ini`

**Produces:**
- `voice_entry_markdown(message_dt, audio_embed, transcript, summary: str | None, tasks: str | None) -> str`
- `normalize_gemini_text(raw: str) -> str | None` (None if empty/NONE)
- `normalize_task_markdown(raw: str) -> str | None`
- `generate_summary(...)` / `generate_tasks(...)` wrapping genai (mocked in tests for parse only)

- [ ] Implement parse/normalize + voice markdown; write pytest; pass; commit

### Task 2: Split remaining modules + wiring

**Files:**
- Create: `bot/config.py`, `bot/stt.py`, `bot/media.py`, `bot/handlers.py`, `bot/app.py`, `bot/__init__.py`
- Replace: `bot.py` stub
- Modify: `Dockerfile`

- [ ] Move logic; load `GEMINI_SUMMARY_PROMPT_FILE` / `GEMINI_TASK_PROMPT_FILE`; voice: local=transcript only; gemini=two independent calls; update Dockerfile COPY; commit

### Task 3: Verify

- [ ] `python -m compileall bot bot.py`
- [ ] `pytest tests/unit -q` (install pytest if needed locally)
- [ ] Confirm README/env already match (no further doc drift)
