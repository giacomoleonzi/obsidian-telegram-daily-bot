# Dropbox Sync Setup

This guide walks through configuring the bot to sync your vault to Dropbox instead of Obsidian Sync.

## 1. Create a Dropbox App

1. Go to https://www.dropbox.com/developers/apps
2. Click "Create app".
3. Choose "Scoped access".
4. Choose "Full Dropbox" (or "App folder" if you prefer isolation).
5. Name your app (e.g., "obsidian-telegram-bot").
6. Click "Create app".

## 2. Set permissions

In your app's settings page, go to the "Permissions" tab and enable:

- `files.content.write`
- `files.content.read`

Click "Submit" to save.

## 3. Copy credentials

In the "Settings" tab, copy:

- **App key** (listed as "App key")
- **App secret** (click "Show" next to "App secret")

## 4. Generate refresh token

On any machine with Python installed:

```bash
pip install dropbox
python scripts/dropbox_auth.py
```

The script will:
1. Ask for your App Key and App Secret (or read from env vars).
2. Print a URL to open in any browser (your PC, phone, etc.).
3. Ask you to paste the authorization code.
4. Print your `DROPBOX_REFRESH_TOKEN`.

This is a one-time operation. The refresh token does not expire unless you revoke the app.

## 5. Configure environment

Edit `config/.env`:

```ini
SYNC_PROVIDER=dropbox
OB_SYNC_AUTOSTART=false

DROPBOX_APP_KEY=your_app_key
DROPBOX_APP_SECRET=your_app_secret
DROPBOX_REFRESH_TOKEN=your_refresh_token
DROPBOX_BASE_PATH=/path/to/your/vault
```

`DROPBOX_BASE_PATH` is the full path to your Obsidian vault folder on Dropbox (e.g., `/plincode_works`).

## 6. Start the container

```bash
docker compose up -d --build
```

No `setup.sh` needed for Dropbox. The bot connects to Dropbox automatically on startup.

## 7. Verify

Check the logs for a successful Dropbox connection:

```bash
docker compose logs -f
```

You should see: `Dropbox provider active (account: your@email.com)`
