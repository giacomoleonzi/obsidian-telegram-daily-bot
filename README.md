# Obsidian Telegram Daily Capture

Telegram bot + Obsidian Headless Sync running in a single Docker container (ARM64-ready for Raspberry Pi).

## Quick Start

1. Configure environment variables (strict mode: required values, no runtime fallbacks):
   - `cp config/.env.example config/.env`
   - edit `config/.env` and set `TELEGRAM_BOT_TOKEN`
2. Start the service:
   - `docker compose up -d --build`
3. Run one-time interactive Obsidian setup:
   - `docker compose exec obsidian-telegram bash`
   - `setup.sh`

## Features

- Receives Telegram voice messages (`.ogg`).
- Receives Telegram images (photos and image documents).
- Stores audio and images in the vault media subfolder (default: `999 - File Bucket`, configurable via `BOT_MEDIA_SUBDIR`).
- Writes and updates a single daily note in `000 - Daily` (or your custom `BOT_DAILY_SUBDIR`).
- Transcribes audio locally with `whisper.cpp` (CPU-only, ARM64-friendly).
- Generates a summary:
  - local (default, lightweight)
  - optional via Gemini API
- Appends to one daily note (e.g. `2026-03-27.md`) with:
  - audio/image embeds
  - audio transcription
  - audio summary
- Runs `ob sync --continuous` in parallel to keep the vault synced.
- Keeps both processes alive via Supervisor:
  - Python bot
  - Obsidian Headless continuous sync

## Architecture

The container runs two processes managed by `supervisord`:

- **Process 1:** `python /app/bot.py`
- **Process 2:** `ob sync --continuous --path /vault`

The Docker bind mount `./vault:/vault` persists notes/media and local `ob` state.

```mermaid
flowchart TD
  U[Telegram user] -->|Sends voice/image| TG[Telegram Bot API]
  TG -->|Voice update| BOT[bot.py]
  TG -->|Photo update| BOT
  BOT -->|Download media| MEDIA["Media (default: 999 - File Bucket)"]
  BOT -->|Local whisper.cpp| STT[Text transcription]
  STT --> SUM[Local or Gemini summary]
  BOT -->|Append daily note| DAILY[/vault/000 - Daily/YYYY-MM-DD.md]
  MEDIA --> VAULT[(Obsidian Vault)]
  STT --> DAILY
  SUM --> DAILY
  DAILY --> VAULT
  SUP[supervisord] --> BOT
  SUP --> OBS[ob sync --continuous]
  VAULT --> OBS
  OBS -->|Remote sync| OS[Obsidian Sync]
```

## Telegram Flow

1. The bot receives an update with `message.voice`.
2. It downloads the audio via `get_file(...).download_to_drive(...)`.
3. It saves the audio into the vault media folder (`BOT_MEDIA_SUBDIR`).
4. It transcribes and summarizes the content.
5. It appends the result to the daily note (`YYYY-MM-DD.md`).

For images:

1. The bot receives `message.photo` (or an image document).
2. It downloads the image into the vault media folder (`BOT_MEDIA_SUBDIR`).
3. It appends an embed to the same daily note using `![[image.ext]]`.

## Obsidian Flow

1. `ob login` (interactive) authenticates your Obsidian account.
2. `ob sync-setup` links local vault (`/vault`) to a remote Obsidian Sync vault.
3. `ob sync --continuous` watches local changes and syncs continuously.

## Configuration

All configuration files live in `config/`. The bot now runs in strict configuration mode: required variables must be explicitly set in `config/.env`.

| Variable | Description | Default |
|---|---|---|
| `TELEGRAM_BOT_TOKEN` | Bot token from BotFather | `replace_with_your_bot_token` |
| `OB_VAULT_PATH` | Vault path inside container | `/vault` |
| `OB_DEVICE_NAME` | Device name for Obsidian Sync | `raspberrypi` |
| `OB_EMAIL` | Optional Obsidian account email (used by `setup.sh`) | empty |
| `OB_PASSWORD` | Optional Obsidian password (never commit real credentials) | empty |
| `OB_MFA` | One-time 2FA code: export in shell only, do not store in files | — |
| `BOT_DAILY_SUBDIR` | Folder where the daily note is written | `000 - Daily` |
| `BOT_MEDIA_SUBDIR` | Folder where audio/images are stored | `999 - File Bucket` |
| `BOT_DAILY_NOTE_FORMAT` | Note name format (`strftime`; `.md` is auto-added if missing) | `%Y-%m-%d` |
| `BOT_LOG_LEVEL` | Python log level | `INFO` |
| `BOT_NOTE_TEMPLATE` | Audio note template (must include `{audio_file}`) | `![[{audio_file}]]` |
| `BOT_IMAGE_NOTE_TEMPLATE` | Image note template (must include `{image_file}`) | `![[{image_file}]]` |
| `IMAGE_COMPRESSION_ENABLED` | Enable image compression before saving | `true` |
| `IMAGE_MAX_BYTES` | Max target image size in bytes | `5242880` |
| `IMAGE_MAX_DIMENSION` | Max image side length during compression | `2560` |
| `IMAGE_JPEG_QUALITY_START` | Starting JPEG quality | `90` |
| `IMAGE_JPEG_QUALITY_MIN` | Minimum JPEG quality | `55` |
| `IMAGE_JPEG_QUALITY_STEP` | JPEG quality decrement step | `5` |
| `STT_PROVIDER` | Speech-to-text provider (`local`) | `local` |
| `STT_LANGUAGE` | whisper.cpp language | `it` |
| `WHISPER_CLI_PATH` | Path to `whisper-cli` binary | `/usr/local/bin/whisper-cli` |
| `WHISPER_MODEL_PATH` | Path to ggml model | `/models/ggml-base.bin` |
| `SUMMARY_PROVIDER` | Summary provider (`local` or `gemini`) | `local` |
| `GEMINI_API_KEY` | Gemini API key (required only with `SUMMARY_PROVIDER=gemini`) | empty |
| `GEMINI_MODEL` | Gemini model name for summaries | `gemini-2.5-flash` |
| `GEMINI_SUMMARY_PROMPT` | Custom summary prompt | `Summarize the text...` |

Main files:

- `docker-compose.yml`
- `Dockerfile`
- `bot.py`
- `config/supervisord.conf`
- `config/setup.sh`
- `config/.env.example` (copy to local `config/.env`; `.env` must not be committed)

## Security

- Never commit `config/.env`: it contains `TELEGRAM_BOT_TOKEN` and may include `GEMINI_API_KEY` and Obsidian credentials.
- Never post tokens, passwords, or API keys in issues or PRs. Rotate the token in BotFather immediately if exposed.
- The repository includes `.gitignore` rules for `config/.env` and `vault/`.

## Operational Notes

- Obsidian setup is one-time per environment/container.
- Do not automate `ob login`; it requires interactive input.
- If you use Obsidian 2FA:
  - keep interactive login (recommended), or
  - set `OB_EMAIL`/`OB_PASSWORD` and provide the one-time code when `setup.sh` asks.
- To view logs:
  - `docker compose logs -f`
- To use Gemini summaries:
  - set `SUMMARY_PROVIDER=gemini`
  - add `GEMINI_API_KEY` in `config/.env`

## License

MIT. See [LICENSE](LICENSE).
