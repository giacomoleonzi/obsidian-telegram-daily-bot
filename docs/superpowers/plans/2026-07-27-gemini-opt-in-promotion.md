# Piano: promozione opt-in Gemini (local-first)

Date: 2026-07-27  
Branch: `feature/gemini-opt-in-promotion`  
Status: in implementazione — decisioni bloccate sotto

### Decisioni bloccate (2026-07-27)

| ID | Scelta |
|---|---|
| D1 | **A** — solo opt-in; niente auto-enrichment a cattura |
| D2 | **A** — trascrizione intatta; aggiungi Riassunto/Task |
| D3 | **A+B** — `<!-- entry:id -->` + `processing:: local\|cloud` |
| D4 | **A** — default `{vault}/.bot/state.sqlite3` (override `BOT_STATE_DB_PATH`) |
| D5 | **A** — reply = trascrizione + keyboard |
| D6 | **B** — su errore → `failed` (riprovabile) |
| D7 | Solo vocali |
| D8 | Modifiche Dockerfile/model restano sul branch |

---

## 1. Ricognizione

### Dispatcher Telegram

| Voce | Dettaglio |
|---|---|
| Libreria | `python-telegram-bot` v21 (`requirements.txt`: `>=21.0,<22.0`) |
| Transport | **Long polling** — `application.run_polling(timeout=60)` in `bot/app.py` (`main`) |
| Webhook | Assente |
| Wiring | `Application.builder().token(...).build()`; config in `application.bot_data`; `asyncio.Lock` in `bot_data["note_lock"]` |

Handler registrati in `bot/app.py`:

| Handler | Funzione | File |
|---|---|---|
| `CommandHandler("whoami", ...)` | `cmd_whoami` | `bot/handlers.py` |
| `MessageHandler(filters.VOICE, ...)` | `handle_voice` | `bot/handlers.py` |
| `MessageHandler(PHOTO \| Document.IMAGE, ...)` | `handle_image` | `bot/handlers.py` |
| `MessageHandler(Document.ALL & ~IMAGE, ...)` | `handle_document` | `bot/handlers.py` |
| `MessageHandler(TEXT & ~COMMAND, ...)` | `handle_text` | `bot/handlers.py` |
| `add_error_handler(...)` | `handle_application_error` | `bot/handlers.py` |

**Assenti oggi:** `CallbackQueryHandler`, comandi `/g` e `/pending`, qualsiasi inline keyboard.

Autorizzazione: `is_authorized_chat` controlla solo `update.message` — **non gestisce `update.callback_query`**. Va estesa.

### Scrittura nel vault

| Voce | Dettaglio |
|---|---|
| Path nota | `daily_note_path()` in `bot/notes.py` → `{vault}/{BOT_DAILY_SUBDIR}/{strftime(BOT_DAILY_NOTE_FORMAT)}.md` |
| Append | `append_to_daily_note` → `append_to_daily_note_sync` (I/O in thread sotto `note_lock`) |
| Frontmatter YAML | **Nessuno**. Se la nota non esiste: header `# Daily YYYY-MM-DD` |
| Formato blocco | `---\n{timestamp}\n\n{entry}\n\n` |
| Entry vocale | `voice_entry_markdown()`: `### Audio HH:MM:SS TZ` + embed + `#### Trascrizione` + opz. `#### Riassunto` / `#### Task` |

Esempio blocco scritto oggi:

```markdown
---
2026-07-27 13:00:00 UTC

### Audio 13:00:00 UTC

![[Media-folder/....ogg]]

#### Trascrizione

<testo whisper>

```

**Nessun id stabile nell’entry.** Nessuna funzione di update/replace. Solo append.

### Whisper.cpp

| Voce | Dettaglio |
|---|---|
| Invocazione | `subprocess` (non binding) in `bot/stt.py` |
| Conversione | `run_ffmpeg_convert()` → WAV 16 kHz mono |
| Trascrizione | `transcribe_local_whisper()` → `whisper-cli -m … -f … -l … -otxt -of … -np` |
| OGG persistente | `{media_dir}/{YYYYMMDD_HHMMSS}_{file_unique_id}.ogg` (vault) |
| WAV temporaneo | `{tempfile.gettempdir()}/{stem}.wav` — cancellato in `finally` di `handle_voice` |
| Output txt | `{stem}.txt` accanto al WAV — letto e cancellato subito |

### Configurazione e stato persistente

| Voce | Dettaglio |
|---|---|
| Config | Solo env via `load_bot_config()` in `bot/config.py`; Compose `env_file: ./config/.env` |
| Prompt | File Markdown caricati a startup (`GEMINI_*_PROMPT_FILE`) |
| Gemini oggi | Se `SUMMARY_PROVIDER=gemini`, **chiamata automatica a cattura** in `handle_voice` (due call sync in thread: `generate_summary` / `generate_tasks`) |
| Bottone / opt-in | Assente — confligge col requisito local-first di questa feature |
| Store persistente bot | **Nessuno** (no SQLite, no JSON state) |
| Persistenza reale | Solo file vault (`./vault:/vault`); `HOME=/vault` per auth `ob` |
| Runtime in-memory | `bot_data` + `note_lock` — perso al restart |

Moduli rilevanti già presenti (fase 1): `bot/gemini_enrichment.py` (client `google.genai`, normalizzazione NONE/task), prompt in `config/prompts/`.

---

## 2. Punti di innesto

### Cosa agganciarci

| Punto | Azione |
|---|---|
| `handle_voice` | Dopo Whisper: **sempre** append locale (senza Gemini a cattura). Reply con trascrizione + inline keyboard `🧠 Gemini` solo se `GEMINI_API_KEY` non vuota. Persistere entry nello store SQLite. |
| `bot/app.py` | Registrare `CallbackQueryHandler`, `CommandHandler("g")`, `CommandHandler("pending")`; aprire/chiudere DB a startup/shutdown. |
| `is_authorized_chat` | Accettare anche `callback_query.message.chat_id`. |
| `bot/gemini_enrichment.py` | Riusare le call; eventualmente unificare in un job di promozione che marca stato prima della call. |
| `bot/config.py` | Opt-in guidato dalla sola presenza di `GEMINI_API_KEY` (bottone assente se manca). Decidere destino di `SUMMARY_PROVIDER` (vedi §7). |
| Volume / path DB | SQLite su path persistente sotto vault o volume dedicato (vedi §7). |

### Accoppiamento scrittura vault — problema centrale

**Oggi la scrittura è troppo accoppiata all’append-only** per una riscrittura successiva della stessa riga/blocco:

1. Nessun anchor/id nel markdown.
2. `append_to_daily_note_sync` non restituisce offset né range del blocco scritto.
3. Un secondo append di Riassunto/Task creerebbe un duplicato senza legame all’entry originale.
4. Sostituire testo cercando solo per timestamp `### Audio HH:MM:SS` è fragile (collisioni nello stesso secondo).

**Refactor obbligatorio (minimo):**

1. Introdurre un **entry id opaco** (es. `a3f9`) generato alla cattura.
2. Scriverlo in modo stabile nel blocco markdown (proposta meno invasiva in §7 — default consigliato: HTML comment `<!-- entry:a3f9 -->` subito sotto il separatore, invisibile in reading view Obsidian).
3. Far restituire da `append_to_daily_note*` metadati utili: `note_path`, `entry_id`, eventualmente `byte_offset`/`char_offset` di inizio blocco (offset come hint; **source of truth = entry_id nel file**).
4. Aggiungere `update_voice_entry_cloud(...)` (o equivalente) che, sotto `note_lock`:
   - legge la nota
   - trova il blocco via `entry_id`
   - inserisce/sostituisce sezioni cloud **senza toccare** trascrizione/audio
   - scrittura atomica (write temp + rename) per non corrompere la nota se il processo muore a metà

Senza questo refactor, bottone differito e `/g` non possono aggiornare “la stessa nota” in modo affidabile.

### Flusso target (alto livello)

```
Vocale
  → Whisper locale
  → append vault (solo locale) + INSERT store status=local
  → reply: trascrizione + [🧠 Gemini]  (se key presente)
         callback_data = "g:{id}"

Tap / /g
  → answerCallbackQuery immediato
  → CAS store: local → processing (se già processing/cloud → stop idempotente)
  → Gemini in background (create_task / to_thread)
  → success: update markdown + store=cloud + editMessageText (no button)
  → fail: store=local (o failed→local) + notifica; bottone resta o viene ripristinato
```

---

## 3. Schema store SQLite

Path proposto: `{OB_VAULT_PATH}/.bot/state.sqlite3` (persiste col volume `./vault`; fuori dal sync Obsidian se ignorato — vedi §7).

### Tabella `entries`

| Campo | Tipo | Note |
|---|---|---|
| `id` | `TEXT PRIMARY KEY` | Opaco corto (4–8 hex), usato in `callback_data` come `g:{id}` |
| `status` | `TEXT NOT NULL` | `local` \| `processing` \| `cloud` \| `failed` |
| `note_path` | `TEXT NOT NULL` | Path assoluto o relativo al vault della daily note |
| `entry_anchor` | `TEXT NOT NULL` | Stesso id scritto nel markdown (`<!-- entry:{id} -->`) |
| `transcript` | `TEXT NOT NULL` | Copia per Gemini / `/pending` senza rileggere il file |
| `chat_id` | `INTEGER NOT NULL` | |
| `telegram_message_id` | `INTEGER` | Messaggio reply del bot (per `editMessageText`) nullable |
| `telegram_user_message_id` | `INTEGER` | Messaggio vocale originale (debug / contesto) |
| `created_at` | `TEXT NOT NULL` | ISO8601 |
| `updated_at` | `TEXT NOT NULL` | ISO8601 |
| `processed_at` | `TEXT` | Valorizzato a promozione riuscita |
| `last_error` | `TEXT` | Ultimo errore Gemini (se `failed`) |
| `cloud_summary` | `TEXT` | Opzionale, cache risultato |
| `cloud_tasks` | `TEXT` | Opzionale, cache risultato |

Indici:

- `INDEX idx_entries_status_created ON entries(status, created_at)` — per `/g` (ultimo `local`) e `/pending`
- `INDEX idx_entries_chat_status ON entries(chat_id, status)`

### Idempotenza (contratto DB)

Transizione atomica:

```sql
UPDATE entries
SET status = 'processing', updated_at = ?
WHERE id = ? AND status IN ('local', 'failed');
```

Se `rowcount == 0` → già in corso o già cloud: niente API, feedback “già elaborato / in corso”.

Solo dopo successo Gemini + scrittura file: `status = 'cloud'`.  
Su fallimento: `status = 'failed'` (o ritorno a `local` — vedi §7) + `last_error`.

`callback_data`: `g:` + id ≤ 64 byte totali (es. `g:a3f9c2` = 8 byte).

---

## 4. Macchina a stati

```
        cattura vocale
              │
              ▼
          ┌───────┐
          │ local │◄────────────────────────┐
          └───┬───┘                         │
              │ tap / /g (CAS OK)             │ errore Gemini
              ▼                             │ (ripristino)
        ┌────────────┐                      │
        │ processing │──────────────────────┘
          └───┬──────┘
              │ successo (file + DB)
              ▼
          ┌───────┐
          │ cloud │  (terminale)
          └───────┘

  (opzionale esplicito)
          failed ──tap──► processing  (come local)
```

### Transizioni

| Transizione | Store | File vault | Telegram |
|---|---|---|---|
| → `local` (cattura) | INSERT `local`, transcript, path, anchor | Append blocco audio+trascrizione (+ marker id). **Nessuna** sezione cloud | Reply testo trascrizione; se key: InlineKeyboard `🧠 Gemini` (`g:{id}`); salva `telegram_message_id` |
| `local`/`failed` → `processing` | CAS UPDATE **prima** della call API | Nessuna modifica | `answerCallbackQuery` (“Elaboro…”); opz. edit testo “⏳ …”; bottone disabilitato/rimosso durante processing |
| `processing` → `cloud` | UPDATE `cloud`, cache summary/tasks, `processed_at` | Update blocco via anchor: aggiungi/sostituisci Riassunto/Task; marker stato interrogabile (vedi §7) | `editMessageText` con risultato; **rimuovi** keyboard |
| `processing` → `failed`/`local` | UPDATE + `last_error` | **Invariato** (solo locale) | Notifica errore; ripristina bottone sul messaggio (o nuovo reply) |
| Tap su `cloud` / secondo tap `processing` | Nessun cambio | Nessun cambio | `answerCallbackQuery` informativa; no API |

Stati interrogabili da Obsidian/Dataview: vedi decisione marker in §7. Il DB resta source of truth operativa; il markdown espone uno **specchio** per Dataview.

Concorrenza vocale vs Gemini: Gemini **sempre** in `asyncio.create_task` / `application.create_task` + `asyncio.to_thread` per I/O/API; il polling e `handle_voice` non restano bloccati sulla rete. Scritture file serializzate da `note_lock`.

---

## 5. File nuovi e modificati

### Nuovi

| File | Descrizione |
|---|---|
| `bot/store.py` | SQLite: schema, CAS status, query pending/ultimo local, CRUD entry |
| `bot/promotion.py` | Orchestrazione promozione: CAS → Gemini → update note → edit TG; rollback stato su errore |
| `bot/callbacks.py` | Handler `CallbackQuery` per `g:{id}` (+ auth) |
| `tests/unit/test_store.py` | Test CAS, idempotenza, pending |
| `tests/unit/test_notes_update.py` | Test find-by-anchor + update sezioni cloud atomico |
| `docs/superpowers/plans/2026-07-27-gemini-opt-in-promotion.md` | Questo piano |

### Modificati

| File | Descrizione |
|---|---|
| `bot/notes.py` | Marker entry id; append restituisce metadati; nuova API update blocco per promozione |
| `bot/handlers.py` | `handle_voice` local-only + keyboard; `/g`, `/pending`; auth anche per callback |
| `bot/app.py` | Handler callback/comandi; init store; lifecycle DB |
| `bot/config.py` | Path DB; regole key/provider; non fallire startup se key assente |
| `bot/gemini_enrichment.py` | Adattare a job promozione (errori tipizzati: timeout, rate limit, network) |
| `config/.env.example` | Documentare comportamento opt-in; path store; chiarire `SUMMARY_PROVIDER` |
| `docker-compose.yml` | Solo se serve volume/path esplicito per DB (probabilmente no se sotto `/vault`) |
| `README.md` | Flusso local-first, bottoni, `/g`, `/pending`, Dataview |
| `tests/unit/test_notes.py` | Adeguare a marker id / nuovi builder |
| `Dockerfile` | Solo se servono dipendenze extra (SQLite è stdlib) |

---

## 6. Sequenza di implementazione

Step piccoli, ciascuno verificabile da solo.

1. **Store SQLite** — `bot/store.py` + test: create schema, insert, CAS `local→processing`, reject doppio CAS, list pending, get latest local.
2. **Anchor + append metadati** — refactor `notes.py`: ogni entry vocale include marker id; test snapshot markdown; append continua a funzionare come oggi per il resto del blocco.
3. **Update blocco** — `update_voice_entry_cloud(note_path, entry_id, summary, tasks)` con write atomico + test (file con più entry, aggiorna solo quella giusta; trascrizione intatta).
4. **Voice local-only + keyboard** — togliere (o disaccoppiare) Gemini a cattura; reply con testo+bottone se key; INSERT store; senza key: comportamento identico a oggi con `SUMMARY_PROVIDER=local` (solo ✅ o trascrizione — vedi §7 sul testo reply).
5. **Callback handler** — `answerCallbackQuery` + task background; happy path fino a mock Gemini; idempotenza doppio tap.
6. **Promozione reale** — collegare `gemini_enrichment`; errori → rollback stato + notifica; edit messaggio finale senza bottone.
7. **`/g` e `/pending`** — ultimo `local`/`failed`; lista con bottoni riusando stessi `callback_data`.
8. **Marker Dataview** — implementare la forma scelta in §7; query di esempio in README.
9. **Hardening Pi** — timeout Gemini, rate limit message, verify restart container (DB e bottoni differiti ancora validi).
10. **Docs + `.env.example`** — allineare README; deprecare/ridefinire `SUMMARY_PROVIDER=gemini` auto.

---

## 7. Rischi e decisioni aperte

Rispondi pure punto per punto; non assumevo risposte.

### D1 — Destino di `SUMMARY_PROVIDER=gemini` (auto a cattura)

Oggi esiste già enrichment automatico. Questa feature lo contraddice.

- **A)** Rimuovere l’auto-enrichment: cloud **solo** via bottone/`/g` (key assente ⇒ niente bottone). `SUMMARY_PROVIDER` deprecato o ridotto a no-op.
- **B)** Tenere entrambi: `SUMMARY_PROVIDER=gemini` = auto; se `local` + key = opt-in bottone.
- **C)** Altro.

**Raccomandazione:** A (allineata ai vincoli “mai cloud senza tap”).

### D2 — Sostituire vs affiancare il testo locale

Al tap, Gemini produce Riassunto/Task. La trascrizione resta?

- **A)** Trascrizione intatta; si **aggiungono** `#### Riassunto` / `#### Task` (come fase 1).
- **B)** Si **sostituisce** la trascrizione col testo riformulato.
- **C)** Si affianca una sezione `#### Gemini` con il testo intero riformulato, oltre a summary/tasks.

**Raccomandazione:** A (minimo rischio perdita dati; riusa prompt esistenti).

### D3 — Marker stato per Dataview (forma meno invasiva)

Oggi le daily **non** hanno frontmatter. Opzioni:

- **A)** HTML comment per entry: `<!-- entry:a3f9 status:local -->` (aggiornato a `cloud`). Dataview puro su YAML non lo vede; utile a grep/script. Poco invasivo in reading view.
- **B)** Inline field Obsidian sotto l’heading: `processing:: local` (Dataview-friendly per entry).
- **C)** Frontmatter della daily come lista: `voice_entries: [{id, status}]` — invasivo, conflitti merge sync.
- **D)** Tag nel titolo: `### Audio … #stt/local` → `#stt/cloud`.

**Raccomandazione:** B se Dataview è requisito forte; A+B se vuoi anche id nascosto stabile.

### D4 — Path e sync del DB SQLite

- **A)** `/vault/.bot/state.sqlite3` + aggiungere `.bot/` a qualcosa che Obsidian Sync ignora se possibile.
- **B)** Volume Docker separato (es. `./data:/data`) fuori dal vault.
- **C)** Altro path.

**Raccomandazione:** B se sync cloud del vault è attivo (evita conflitti file DB); A se vault è solo locale sul Pi.

### D5 — Testo del reply Telegram a cattura

Oggi: solo `✅`. Target: “risponde con la trascrizione + bottone”.

- **A)** Reply = trascrizione (troncata se lunga) + keyboard.
- **B)** Reply = `✅` + anteprima corta + keyboard; trascrizione solo in nota.
- **C)** Due messaggi: conferma, poi trascrizione+bottone.

### D6 — Stato dopo errore Gemini

- **A)** Torna `local` (riprovabile, identico a pre-tap).
- **B)** Va in `failed` (visibile in `/pending`, stesso bottone).
- **C)** `failed` con cooldown.

**Raccomandazione:** B.

### D7 — Scope promozione

Solo vocali, o anche testo/immagine in seguito? (Piano attuale: **solo voice**.)

### D8 — Working tree sporco su questo branch

Su `main` c’erano modifiche non committate portate sul branch:

- `Dockerfile` (GGML_NATIVE=OFF per build ARM)
- `GEMINI_MODEL=gemini-3.5-flash-lite` in `.env.example` / README

Le lasciamo su questo branch, le committiamo a parte, o le scorporiamo?

---

## Nota sul rapporto con la fase 1

La fase 1 (`docs/superpowers/specs/2026-07-27-gemini-summary-tasks-design.md`) ha introdotto package `bot/`, prompt file, e enrichment **sincrono a cattura**. Questo piano la **ridefinisce**: stesso output markdown (Riassunto/Task), ma **trigger esplicito**, store persistente, callback differibili, idempotenza. Il codice `gemini_enrichment.py` e i prompt restano asset riutilizzabili.
