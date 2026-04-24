# Codebase Guide for AI-Assisted Development

This file gives an AI assistant the context needed to work on this project without re-reading the full conversation history.

---

## What this project does

Family Inbox Intelligence is a private family dashboard. A dedicated Gmail account (configured via `FAMILY_INBOX_EMAIL`) receives forwarded emails from schools and children's activity providers. A Python scanner reads those emails daily, sends them to Claude, and extracts:
- **Events:** upcoming dates, deadlines, and action items
- **Digest groups:** a weekly narrative summary grouped by sender

Results are stored in JSONBin.io. A React SPA reads JSONBin and displays everything. Both parents can view, add, edit, and dismiss events from their phones. Every Saturday a digest email is sent to both parents via Gmail SMTP. A day-before reminder fires on any day an event is coming up the next day.

**Email sources:** All emails in the dedicated Gmail inbox are scanned. Family context configured via `FAMILY_CONTEXT` in `backend/.env`.

---

## Scanner flow

```mermaid
flowchart TD
    Start([Scanner starts]) --> Auth["Authenticate Gmail\n(token.json · OAuth2)"]
    Auth --> ReadBin["Read JSONBin\n(get lastScanned + existing data)"]
    ReadBin --> Fetch["Fetch emails since lastScanned\n(1h overlap buffer · fallback: newer_than:7d)"]
    Fetch --> Empty{0 new emails?}
    Empty -->|yes| UpdateTS["Update lastScanned in JSONBin"]
    UpdateTS --> Reminder1["Send day-before reminder email\n(if events tomorrow)"]
    Reminder1 --> Done1([Done])
    Empty -->|no| Claude1["Claude pass 1: analyze emails\n(extract events + digest groups)"]
    Claude1 --> Merge["Merge into existing:\n① Add new events by ID\n② Auto-expire >2 days past date\n③ Never remove manually_added"]
    Merge --> Dedup["Claude pass 2: dedup\n(remove duplicate events)"]
    Dedup --> Write["Write merged data to JSONBin\n(30s timeout · 3 retries)"]
    Write --> Reminder2["Send day-before reminder email\n(if events tomorrow)"]
    Reminder2 --> Saturday{"Saturday or\n--send-digest?"}
    Saturday -->|yes| Email["Gmail SMTP → digest email to parents"]
    Saturday -->|no| Done2([Done])
    Email --> Done2
```

---

## Stack

| Layer | Technology |
|---|---|
| Backend language | Python 3.11+ |
| Email reading | Gmail API (OAuth2 via `google-auth-oauthlib`) |
| AI analysis | Anthropic Python SDK — model `claude-sonnet-4-6` |
| Data store | JSONBin.io REST API (no database, no server) |
| Digest email | Gmail SMTP via `smtplib` + App Password |
| Scheduler | Mac launchd (daily 7am) |
| Frontend | React 19 + Vite 8 |
| Frontend hosting | Firebase Hosting (static SPA) |
| Project management | Linear (team key: FAM) |

---

## Key files

### Backend

| File | Purpose |
|---|---|
| `backend/scanner.py` | Main entrypoint. Orchestrates all steps: auth → fetch → analyze → merge → dedup → write → email |
| `backend/config.py` | All user-configurable settings and category metadata. Loaded from `backend/.env`. |
| `backend/credentials.json` | Gmail OAuth2 app credentials (do not commit, do not modify) |
| `backend/token.json` | Gmail OAuth2 user token (generated on first `--test-auth` run, do not commit) |
| `backend/.env` | All secrets (do not commit) |
| `backend/.env.example` | Template with all required variable names |
| `backend/requirements.txt` | Python dependencies |
| `backend/linear_setup.py` | One-time script that created all Linear tickets. Not part of normal operation. |

### Frontend

| File | Purpose |
|---|---|
| `frontend/src/api.js` | All JSONBin read/write — `loadData`, `saveData`, `dismissEvent`, `deleteEvent`, `addEvent`, `updateEvent` |
| `frontend/src/App.jsx` | Root component. All state, all handlers, PIN gate logic, top-level layout. |
| `frontend/src/index.css` | Design system: CSS variables, typography, layout, animations, skeleton loader |
| `frontend/src/components/EventCard.jsx` | Single event card: display, inline edit, copy-subject button (⎘), "Open link →" action |
| `frontend/src/components/AddEventForm.jsx` | Modal bottom-sheet form for manually adding events |
| `frontend/src/components/DigestGroup.jsx` | Collapsible card showing weekly narrative bullets per sender |
| `frontend/src/components/FilterPills.jsx` | Category filter buttons (all / school / daycare / scouts / soccer / GFT / other) |

---

## Data shape (JSONBin record)

```json
{
  "lastScanned": "2026-04-18T07:00:00Z",
  "events": [
    {
      "id": "evt_001",
      "title": "Summer Camp — Register by May 25",
      "date": "2026-05-25",
      "category": "school",
      "priority": "medium",
      "source": "Springfield Elementary",
      "notes": "Camp runs June 26–July 2. Register by May 25 for the early-bird rate.",
      "link": "https://example.com/register",
      "source_message_id": "18f2b3c4d5e6f7a8",
      "source_thread_id": "18f2b3c4d5e6f7a8",
      "source_subject": "Summer Camp Registration Now Open",
      "dismissed": false,
      "manually_added": false
    }
  ],
  "digestGroups": [
    {
      "source": "Springfield Elementary",
      "category": "school",
      "week_of": "2026-04-14",
      "bullets": ["The class finished their weather unit and began ecosystems."]
    }
  ]
}
```

**Event fields:**
- `link` — URL if present in the source email (registration, survey, booking, etc.); `null` otherwise. Never set for informational or newsletter links. Displayed as "Open link →" on the EventCard.
- `source_message_id` — Gmail API message ID of the source email.
- `source_thread_id` — Gmail API thread ID of the source email (more reliable than message ID for lookups).
- `source_subject` — subject line of the source email. Shown as a tooltip on desktop; can be copied to clipboard via the ⎘ button on the EventCard to search Gmail manually.
- `link` and `source_*` fields are absent on manually-added events and on events extracted before these fields were introduced.

**Merge rules (applied on every scanner run):**
- Events: keep all existing; add new Claude events only if their `id` doesn't already exist; auto-expire events more than 2 days past their date unless `manually_added`.
- DigestGroups: always replace entirely with new Claude output.
- `lastScanned`: always update to current UTC timestamp.

---

## Scanner CLI flags

```bash
python scanner.py                    # Normal run
python scanner.py --dry-run          # All steps, no writes, prints final JSON to console
python scanner.py --send-digest      # Force send Saturday digest email regardless of day
python scanner.py --send-reminder    # Force send day-before reminder email regardless of schedule
python scanner.py --test-auth        # Test Gmail OAuth only
python scanner.py --test-fetch       # Test email fetching only (prints subjects)
python scanner.py --test-analyze     # Test Claude analysis only (prints raw JSON)
python scanner.py --test-jsonbin     # Test JSONBin read/write only
python scanner.py --test-dedup       # Test dedup pass on current JSONBin events (read-only)
python scanner.py --test-reminder    # Preview tomorrow's reminder events (read-only, no send)
python scanner.py --reset-last-scanned   # Clear lastScanned so next run fetches 7 days back
python scanner.py --wipe-and-rescan      # Clear all JSONBin data then run a fresh 7-day scan
python scanner.py --migrate-categories  # One-time: rename legacy category values in JSONBin
```

---

## Category metadata

Defined in `config.py`. The same keys are used in both backend (email body) and frontend (colors, icons).

| Key | Icon | Color |
|---|---|---|
| `school` | 🏫 | `#60a5fa` |
| `daycare` | 🌻 | `#4ade80` |
| `scouts` | 🎯 | `#f87171` |
| `soccer` | ⚽ | `#f0c040` |
| `GFT` | 🥋 | `#c084fc` |
| `other` | 📬 | `#9090a8` |

---

## PIN gate

All write actions on the dashboard (add event, dismiss, delete, edit) require a PIN set via `VITE_APP_PIN` in `frontend/.env`. The PIN is checked on every page load — it is stored in React state only, not in sessionStorage or localStorage, so refreshing or opening a new tab always requires re-entry.

---

## Design system (CSS variables)

```
--bg: #0c0c12          Dark background
--surface: #14141c     Header / elevated surfaces
--card: #1a1a24        Card backgrounds
--border: #26263a      Borders and dividers
--accent: #f0c040      Primary action color (yellow)
--text: #eaeaf4        Primary text
--sub: #9090a8         Secondary text / bullet markers
--muted: #55556a       Placeholder / label text
--green: #4ade80
--red: #f87171
--orange: #fb923c
--blue: #60a5fa
--purple: #c084fc
```

Fonts: DM Sans (400/600/700) for UI, DM Mono (500) for numbers. Loaded from Google Fonts CDN.
Mobile-first. All interactive elements min 44px touch target height.

---

## Environment variables

### `backend/.env`

| Variable | Description |
|---|---|
| `ANTHROPIC_API_KEY` | Anthropic API key |
| `FAMILY_INBOX_EMAIL` | Gmail address of the dedicated family forwarding inbox |
| `GMAIL_APP_PASSWORD` | Gmail App Password for SMTP sending |
| `JSONBIN_BIN_ID` | JSONBin bin ID |
| `JSONBIN_API_KEY` | JSONBin master key (literal `$` signs — Python dotenv reads fine) |
| `DIGEST_RECIPIENTS` | Comma-separated parent email addresses for Saturday digest |
| `FAMILY_CONTEXT` | Free-text description of children's schools/providers passed to Claude |
| `LINEAR_API_KEY` | Linear API key (only used by `linear_setup.py`) |
| `LINEAR_TEAM_ID` | Linear team key, e.g. `FAM` |

### `frontend/.env`

| Variable | Description |
|---|---|
| `VITE_JSONBIN_BIN_ID` | Same bin ID as backend |
| `VITE_JSONBIN_API_KEY` | Same key as backend — escape every `$` as `\$` (Vite runs dotenv-expand) |
| `VITE_APP_PIN` | PIN required to make any write action on the dashboard (React state only — no persistence) |

All actual values live in the `.env` files (gitignored). See `docs/SERVICES.md` for account details and infrastructure IDs.

---

## Infrastructure

All account details, project IDs, and live URLs are documented in `docs/SERVICES.md` (gitignored — contains private info).

Key paths on the local machine:
- launchd plist: `~/Library/LaunchAgents/com.familyinbox.scanner.plist`
- Scanner log: `~/Desktop/family-inbox/scanner.log`
- Firebase project: configured in `.firebaserc`

---

## Development conventions

- No stubs, no TODOs in shipped code. Every function is complete.
- Every secret lives in `.env`. Nothing hardcoded.
- Backend errors are logged with `logging` and raised explicitly — no silent failures.
- Frontend errors are caught by `api.js` functions and thrown as descriptive strings for the UI to display.
- The frontend reads/writes JSONBin directly from the browser — there is no backend API server.
- JSONBin requests use a 30s timeout with 3 automatic retries (3s delay between attempts).
- `firebase deploy --only hosting` is the only deploy step. No CI/CD pipeline.