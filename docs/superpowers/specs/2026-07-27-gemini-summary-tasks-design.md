# Gemini summary + Obsidian tasks (fase 1)

Date: 2026-07-27  
Revision: 2  
Status: approved for implementation planning

## Goal

After local Whisper transcription of a Telegram voice message, optionally enrich the daily note with:

1. A useful summary under `#### Riassunto` (only when worth it)
2. Obsidian checkboxes under `#### Task` (only when tasks exist)

Use two separate Gemini calls. Load prompts from Markdown files referenced in config. Split the monolithic `bot.py` into a small reusable package. Do not invent details. Omit empty sections.

## Non-goals (this phase)

- Structured JSON responses from Gemini
- Local/offline AI summary or task extraction
- Changes to image/text/document handlers beyond moving code into modules
- Auto-scripting of `ob login` / `ob sync-setup`

## Provider behavior

| `SUMMARY_PROVIDER` | Daily note content |
|---|---|
| `local` | Audio embed + `#### Trascrizione` only. No summary. No tasks. |
| `gemini` | Audio + transcription; then Call A (summary) and Call B (tasks); write each section only if that call returns usable content. |

## Architecture / data flow

```
Voice message
  → download OGG
  → Whisper (local) → transcript
  → if provider == gemini:
       Call A: summary prompt file + transcript → optional summary text
       Call B: task prompt file + transcript → optional task lines
  → append markdown to daily note
```

Calls A and B are independent: one failure must not block the other.

## Prompt files

Prompts live as well-written Markdown under `config/prompts/`:

| File | Purpose |
|---|---|
| `config/prompts/summary.md` | Instructions for Call A (summary) |
| `config/prompts/tasks.md` | Instructions for Call B (Obsidian tasks) |

Env points to file paths (not inline prompt text):

```env
GEMINI_SUMMARY_PROMPT_FILE=config/prompts/summary.md
GEMINI_TASK_PROMPT_FILE=config/prompts/tasks.md
```

- Paths are resolved relative to the app working directory (`/app` in the container) unless absolute.
- Prompt files are loaded at startup; missing/empty files fail fast.
- Remove `GEMINI_SUMMARY_PROMPT` from config (replaced by file reference).

Prompt content contract:

- Summary: practical Italian bullets only if useful; otherwise reply `NONE`; do not invent details.
- Tasks: concrete actions as `- [ ] ...`; explicit and clearly implied tasks; otherwise `NONE`; no commentary outside task lines.

## Package layout

Keep a thin `bot.py` stub so supervisord and healthcheck stay on `bot.py`. Move logic into package `bot/`:

```text
bot.py                      # stub → bot.app.main()
bot/
  __init__.py
  app.py                    # Application wiring / main()
  config.py                 # env loading + prompt file loading
  stt.py                    # ffmpeg + whisper
  gemini_enrichment.py      # two Gemini calls + NONE/task normalize
  notes.py                  # markdown entries + atomic daily append
  media.py                  # image compression helpers
  handlers.py               # Telegram handlers
config/
  prompts/
    summary.md
    tasks.md
```

Dockerfile must `COPY` `bot.py`, `bot/`, and `config/prompts/`.

`.cursorrules` preferred edit surface: `Dockerfile`, `bot.py`, `bot/`, and `config/`.

## Markdown format

```markdown
### Audio HH:MM:SS TZ

![[Media-folder/file.ogg]]

#### Trascrizione

<transcript>

#### Riassunto

- <bullet>
- <bullet>

#### Task

- [ ] <action>
- [ ] <action>
```

`#### Riassunto` and `#### Task` appear only when their respective call produced content.

## Error handling

- Network/API/exception on Call A or B: log the error; skip that section; continue.
- Both empty/failed: note still has audio + transcription.
- Invalid `SUMMARY_PROVIDER`, missing Gemini key (when provider is gemini), or missing prompt files: fail at startup.

## Documentation updates (this revision)

- README: features, mermaid flow, config table, structure, Gemini troubleshooting
- `config/.env.example`: prompt file vars; clarify `local` = transcript-only
- `.cursorrules`: include `bot/` and prompt files under `config/`
- Design spec: this revision 2

## Testing / verification

- Voice with `local`: daily note has transcript only.
- Voice with `gemini`, chatty note with no tasks: `#### Riassunto` present, no `#### Task`.
- Voice with explicit “metti un task …”: `#### Task` with `- [ ] ...`.
- Short trivial audio: may omit both optional sections.
- Simulate one Gemini call failure: other section still written when successful.
- Container starts with prompt files present; fails fast if a prompt path is wrong.
