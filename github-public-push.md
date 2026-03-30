# Push su GitHub (repo pubblico)

## Goal

Pubblicare questo progetto su GitHub come repository pubblico senza esporre token, chiavi API o dati del vault.

## Tasks

- [ ] **Rimuovere segreti dal working tree** — Sostituisci `TELEGRAM_BOT_TOKEN` in `config/.env` con un placeholder (o elimina il file e usa solo `config/.env.example`). Rigenera il token su BotFather se è mai stato committato. → Verify: `git grep -i "AA[A-Za-z0-9_-]"` non trova token; `config/.env` non contiene segreti reali.
- [ ] **Confermare `.gitignore`** — `config/.env`, `vault/`, `__pycache__` sono ignorati (già presente in root). → Verify: `git check-ignore -v config/.env` mostra una regola.
- [ ] **Inizializzare Git** — `git init` nella root del progetto. → Verify: `git status` mostra file tracciabili senza `config/.env` né `vault/`.
- [ ] **Primo commit** — `git add` solo file sicuri; `git commit -m "Initial commit: Obsidian Telegram bot (Docker)"`. → Verify: `git log -1 --stat` non include `.env` né vault.
- [ ] **Creare repo su GitHub** — Su github.com: New repository → nome (es. `obsidian-telegram`) → Public → senza README se già hai commit locale. → Verify: pagina repo esiste e è vuota o con un solo branch.
- [ ] **Collegare remote e push** — `git remote add origin https://github.com/<user>/<repo>.git` (o SSH), poi `git branch -M main` e `git push -u origin main`. → Verify: su GitHub compaiono i file attesi; nessun segreto nei file.
- [ ] **Opzionale: README** — Se manca una sezione “Security”, aggiungi riga: non committare `config/.env`, copiare da `.env.example`. → Verify: README leggibile su GitHub.

## Done When

- [ ] Repo pubblico su GitHub con codice e `config/.env.example`, senza `config/.env` né dati sensibili in cronologia.
- [ ] Hai un token Telegram nuovo se il vecchio è mai finito in log o in chat.

## Notes

- Se in passato hai committato segreti, usa `git filter-repo` o supporto GitHub per rimuovere dati sensibili dalla cronologia prima di considerare il repo “pulito”.
- Il file `github-public-push.md` puoi tenerlo come checklist o rimuoverlo dopo il push se preferisci repo più snello.
