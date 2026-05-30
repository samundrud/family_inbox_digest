# Codebase Guide for AI-Assisted Development

This file gives an AI assistant the context needed to work on this project without re-reading the full conversation history.

---

## What this project does

Family Inbox Intelligence is a private family dashboard. A dedicated Gmail account (configured via `FAMILY_INBOX_EMAIL`) receives forwarded emails from schools and children's activity providers. A Python scanner reads those emails daily, sends them to Claude, and extracts:
- **Events:** upcoming dates, deadlines, and action items (extracted daily from new emails)
- **Digest groups:** a weekly narrative summary grouped by category (generated once on Saturday from all emails of the past week)

Results are stored in JSONBin.io. A React SPA reads JSONBin and displays everything. Both parents can view, add, edit, and dismiss events from their phones. Every Saturday a digest email is sent to both parents via Gmail SMTP. A day-before reminder fires on any day an event is coming up the next day.

**Email sources:** All emails in the dedicated Gmail inbox are scanned. Family context configured via `FAMILY_CONTEXT` in `backend/.env`.

---

## Scanner flow

```mermaid
flowchart TD
    Start([Scanner starts]) --> Auth["Authenticate Gmail\n(token.json · OAuth2)"]
    Auth --> ReadBin["Read JSONBin\n(events + digestGroups + lastScanned)"]
    ReadBin --> Fetch["Fetch emails since lastScanned\n(incremental · 1h overlap buffer · cap 50\n--days N overrides window for this run)"]
    Fetch --> HasEmails{New emails?}
    HasEmails -->|yes| Claude1["Claude pass 1: extract events\n(two-step: per-email audit then JSON)"]
    HasEmails -->|no| DigestCheck
    Claude1 --> Merge["Merge into existing data:\n• New events added by composite key\n• Expire auto events >2 days past date\n• Expire deleted tombstones >30 days old\n• digestGroups: unchanged"]
    Merge --> Dedup["Claude pass 2: dedup events"]
    Dedup --> DigestCheck{Saturday or\n--send-digest?}
    DigestCheck -->|no| Write
    DigestCheck -->|yes| FullFetch["Full SCAN_DAYS_BACK email fetch\n(separate Gmail query)"]
    FullFetch --> Claude3["Claude pass 3: generate digest\n(digest-only prompt · one entry per category\nbullets are objects: {text, link})"]
    Claude3 --> Write["Write to JSONBin\n(30s timeout · 3 retries)"]
    Write --> Reminder["Day-before reminder email\n(if events tomorrow)"]
    Reminder --> DigestEmail{Saturday or\n--send-digest?}
    DigestEmail -->|no| Done([Done])
    DigestEmail -->|yes| Email["Gmail SMTP → weekly digest email\n(upcoming events + narrative digest)"]
    Email --> Done
```

**Two separate Claude calls:** The daily events prompt uses a two-step format — Claude writes a one-line audit for every email before outputting JSON, ensuring no email is silently skipped. On Saturday a second, independent call generates the digest from a full `SCAN_DAYS_BACK`-day email fetch, so the narrative always covers the complete window.

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
| `frontend/src/api.js` | All JSONBin read/write — `loadData`, `saveData`, `dismissEvent`, `deleteEvent`, `addEvent`, `updateEvent`. Guards every function with `IS_DEMO` so demo builds never call JSONBin. |
| `frontend/src/App.jsx` | Root component. All state, all handlers, PIN gate logic, top-level layout. Renders demo banner and passes `isDemo` prop when `VITE_DEMO_MODE=true`. |
| `frontend/src/index.css` | Design system: CSS variables, typography, layout, animations, skeleton loader |
| `frontend/src/components/EventCard.jsx` | Single event card: display, inline edit, copy-subject button (⎘), "Open link →" action. In demo mode, action buttons and links show a "Disabled in demo mode" popover instead of triggering. |
| `frontend/src/components/AddEventForm.jsx` | Modal bottom-sheet form for manually adding events |
| `frontend/src/components/DigestGroup.jsx` | Collapsible card showing weekly narrative bullets per sender. In demo mode, digest links show a "Disabled in demo mode" popover. |
| `frontend/src/components/FilterPills.jsx` | Category filter buttons (all / school / daycare / scouts / soccer / GFT / other) |
| `frontend/src/mockData.js` | Anonymized sample data for the demo build. Dates are hardcoded relative to 2026-05-30. Never bundled in production builds (tree-shaken). |
| `frontend/.env.mock` | Vite env file loaded by `build:mock`. Sets `VITE_DEMO_MODE=true` and `VITE_DEMO_TODAY=2026-05-30` to freeze urgency labels. Contains no secrets. |

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
      "deleted": false,
      "manually_added": false
    }
  ],
  "digestGroups": [
    {
      "source": "School",
      "category": "school",
      "week_of": "2026-04-21",
      "bullets": [
        { "text": "The class finished their weather unit and began ecosystems.", "link": null },
        { "text": "Student Led Conferences are coming up — sign up for a time slot.", "link": "https://example.com/signup" }
      ]
    }
  ]
}
```

**Event fields:**
- `link` — URL if present in the source email (registration, survey, booking, document sign-up, etc.); `null` otherwise. The link must be directly actionable and come from the same email as the event. Never set for informational or newsletter links. Displayed as "Open link →" on the EventCard.
- `dismissed` — `true` if a parent marked the event as done. Kept in storage (renders crossed out at bottom of list); never deleted from JSONBin so the scanner's dedup key remains intact.
- `deleted` — `true` if a parent deleted the event. Hidden from the UI entirely but kept in JSONBin as a tombstone for 30 days so the scanner cannot re-extract it from the same email. Expired automatically by `merge_data` after 30 days (using `deleted_at`).
- `deleted_at` — ISO timestamp set when `deleted` is set to `true`. Used by `merge_data` to expire tombstones after 30 days.
- `source_message_id` — Gmail API message ID of the source email. Used as part of the composite dedup key `(source_message_id, title)`.
- `source_thread_id` — Gmail API thread ID of the source email.
- `source_subject` — subject line of the source email. Shown as a tooltip on desktop; can be copied to clipboard via the ⎘ button on the EventCard to search Gmail manually.
- `link`, `source_*`, `deleted`, and `deleted_at` fields are absent on manually-added events and on events extracted before these fields were introduced.

**DigestGroup fields:**
- `source` — friendly category label (e.g. "School", "Soccer", "GFT After School", "Other"). One entry per category, not per organisation.
- `week_of` — Monday of the week being summarised (ISO date). Set by the digest generation pass.
- `bullets` — array of objects `{ text: string, link: string | null }`. `link` is included only when the bullet directly references something the parent should act on via that specific link. Frontend falls back gracefully to plain strings for bullets generated before this schema change.

**Merge rules (applied on every scanner run):**
- Events: keep all existing; add new Claude events only if their composite key `(source_message_id, title)` doesn't already exist; auto-expire auto-generated events more than 2 days past their date.
- Deleted tombstones (`deleted: true`): kept in storage so their dedup key blocks re-extraction; expired after 30 days from `deleted_at`.
- `manually_added` events: kept forever (never auto-expired) unless `deleted: true` (then tombstone rules apply).
- DigestGroups: unchanged on daily runs. Replaced entirely on Saturday from a dedicated full `SCAN_DAYS_BACK`-day Claude call.
- `lastScanned`: always updated to current UTC timestamp.

---

## Scanner CLI flags

```bash
python scanner.py                         # Normal run
python scanner.py --dry-run               # All steps, no writes, prints final JSON to console
python scanner.py --send-digest           # Force send Saturday digest email regardless of day
python scanner.py --send-reminder         # Force send day-before reminder email regardless of schedule
python scanner.py --days 14               # Override fetch window for this run only (default: SCAN_DAYS_BACK)
python scanner.py --test-auth             # Test Gmail OAuth only
python scanner.py --test-fetch            # Test email fetching only (prints subjects)
python scanner.py --test-analyze          # Test Claude analysis only (prints raw JSON)
python scanner.py --test-jsonbin          # Test JSONBin read/write only
python scanner.py --test-dedup            # Test dedup pass on current JSONBin events (read-only)
python scanner.py --test-reminder         # Preview tomorrow's reminder events (read-only, no send)
python scanner.py --reset-last-scanned    # Clear lastScanned so next run fetches SCAN_DAYS_BACK days
python scanner.py --wipe-and-rescan       # Clear all JSONBin data then run a fresh scan
python scanner.py --wipe-and-rescan --days 14  # Same but with a custom lookback window
python scanner.py --migrate-categories    # One-time: rename legacy category values in JSONBin
```

`--days N` can be combined with any command that triggers a scan. It overrides `SCAN_DAYS_BACK` for that run only — the config file is never modified.

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