# Gemini summary + Obsidian tasks (fase 1)

Date: 2026-07-27  
Status: approved for implementation planning

## Goal

After local Whisper transcription of a Telegram voice message, optionally enrich the daily note with:

1. A useful summary under `#### Riassunto` (only when worth it)
2. Obsidian checkboxes under `#### Task` (only when tasks exist)

Use two separate Gemini calls. Do not invent details. Omit empty sections.

## Non-goals (this phase)

- Structured JSON responses from Gemini
- Local/offline AI summary or task extraction
- Changes to image/text/document handlers
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
       Call A: summary prompt + transcript → optional summary text
       Call B: task prompt + transcript → optional task lines
  → append markdown to daily note
```

Calls A and B are independent: one failure must not block the other.

## Components

### `bot.py`

- Replace single `_gemini_summary` usage with two Gemini helpers (or one shared caller with different prompts):
  - summary call
  - task call
- Parse/normalize responses:
  - empty / whitespace / `NONE` → treat as no content
  - task lines: prefer `- [ ] ...`; if Gemini returns plain bullets (`- ...`), normalize to `- [ ] ...` when reasonable; drop non-task lines
- Update `_voice_entry_markdown` to accept optional `summary` and `tasks` and omit missing sections
- When `SUMMARY_PROVIDER=local`, do not call `_local_extractive_summary` for voice entries (remove that path from voice handling)
- Keep existing startup guard: `GEMINI_API_KEY` required if provider is `gemini`

### `config/.env.example`

- Document two prompts:
  - `GEMINI_SUMMARY_PROMPT`
  - `GEMINI_TASK_PROMPT` (new)
- Keep `GEMINI_API_KEY`, `GEMINI_MODEL` shared by both calls
- Clarify that `local` means transcript-only for voice

### README (minimal)

- Update summary/task behavior to match this design

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

## Default prompts (Italian, editable via env)

**Summary**

- Summarize in practical Italian bullets only if the summary adds value beyond the raw transcript.
- If not worth summarizing, reply with exactly `NONE`.
- Do not invent details.

**Tasks**

- Extract concrete actionable items as Obsidian checkboxes: `- [ ] ...`
- Include explicit and clearly implied tasks (e.g. “metti un task di comprare il latte”).
- No commentary outside task lines.
- If there are no tasks, reply with exactly `NONE`.

## Error handling

- Network/API/exception on Call A or B: log the error; skip that section; continue.
- Both empty/failed: note still has audio + transcription.
- Invalid `SUMMARY_PROVIDER` or missing key for gemini: fail at startup (existing pattern).

## Testing / verification

- Voice with `local`: daily note has transcript only.
- Voice with `gemini`, chatty note with no tasks: `#### Riassunto` present, no `#### Task`.
- Voice with explicit “metti un task …”: `#### Task` with `- [ ] ...`.
- Short trivial audio: may omit both optional sections.
- Simulate one Gemini call failure: other section still written when successful.

## Out of scope follow-ups

JSON-structured Gemini responses can be considered later; not part of this design or implementation plan.
