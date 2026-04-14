#!/usr/bin/env bash
set -euo pipefail

# This script intentionally does *not* try to automate `ob login` or `ob sync-setup`.
# Those steps require interactive terminal input (and often a browser auth flow).
#
# Run it once after `docker compose up` and while tailing logs / watching the terminal.

VAULT_PATH="${OB_VAULT_PATH:?OB_VAULT_PATH is required}"
DEVICE_NAME="${OB_DEVICE_NAME:?OB_DEVICE_NAME is required}"
OB_EMAIL="${OB_EMAIL:-}"
OB_PASSWORD="${OB_PASSWORD:-}"
OB_MFA="${OB_MFA:-}"
SYNC_PROVIDER="${SYNC_PROVIDER:-obsidian}"

if [[ "${SYNC_PROVIDER}" == "dropbox" ]]; then
  echo "SYNC_PROVIDER=dropbox: skipping Obsidian headless setup."
  echo "See docs/dropbox-setup.md for Dropbox configuration."
  exit 0
fi

echo "Obsidian headless setup"
echo "Local vault path: ${VAULT_PATH}"
echo "Device name: ${DEVICE_NAME}"
echo

echo "Step 1/2: Obsidian headless login"
if [[ -n "${OB_EMAIL}" && -n "${OB_PASSWORD}" ]]; then
  echo "Using OB_EMAIL/OB_PASSWORD from environment."
  if [[ -n "${OB_MFA}" ]]; then
    echo "Using OB_MFA from environment."
    ob login --email "${OB_EMAIL}" --password "${OB_PASSWORD}" --mfa "${OB_MFA}"
  else
    read -rp "Enter current Obsidian MFA code (leave blank to continue interactively): " MFA_CODE
    if [[ -n "${MFA_CODE}" ]]; then
      ob login --email "${OB_EMAIL}" --password "${OB_PASSWORD}" --mfa "${MFA_CODE}"
    else
      ob login --email "${OB_EMAIL}" --password "${OB_PASSWORD}"
    fi
  fi
else
  echo "OB_EMAIL/OB_PASSWORD not set; falling back to fully interactive login."
  ob login
fi

echo
read -rp "Step 2/2: Remote vault id/name (from Obsidian Sync settings): " VAULT_ID

# `ob sync-setup` may prompt for encryption password and device confirmation interactively.
echo
echo "Starting sync-setup..."
ob sync-setup --vault "${VAULT_ID}" --path "${VAULT_PATH}" --device-name "${DEVICE_NAME}"

echo
echo "Setup complete."
