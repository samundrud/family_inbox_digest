# Family Inbox Intelligence

A private family dashboard that reads a dedicated Gmail inbox where school and activity emails are forwarded. A Python scanner reads those emails, sends them to Claude, and extracts upcoming events and a weekly narrative digest. Results are stored in JSONBin and displayed in a React dashboard. Every Saturday morning a digest email is sent to both parents; a day-before reminder fires whenever an event is coming up the next day.

**Users:** Two parents and their children.
**Email sources:** All emails in the dedicated Gmail inbox are scanned. Family context configured via `FAMILY_CONTEXT` in `backend/.env`.

---

## Architecture

```mermaid
flowchart LR
    Scheduler["⏰ Cloud Scheduler\n(daily · 7am Pacific)"]
    Gmail["📧 Gmail inbox\n(family forwarding account)"]
    Scanner["☁️ scanner.py\n(Google Cloud Run Job)"]
    Claude["🤖 Claude Sonnet\n(Anthropic API · up to 3 passes)"]
    JSONBin["🗄️ JSONBin.io\n(data store)"]
    Frontend["📱 React SPA\n(Firebase Hosting · PIN-gated)"]
    ReminderEmail["📅 Reminder email\n(day before events)"]
    DigestEmail["📋 Digest email\n(Saturday)"]
    Parents["👨‍👩‍👧‍👦 Parents"]

    Scheduler -->|"trigger"| Scanner
    Gmail -->|"incremental fetch (daily)\nfull SCAN_DAYS_BACK fetch (Saturday)"| Scanner
    Scanner -->|"audit + events prompt (daily)\ndigest prompt (Saturday)"| Claude
    Claude -->|"events · dedup · digest groups"| Scanner
    Scanner -->|"PUT · 30s timeout · 3 retries"| JSONBin
    JSONBin -->|"GET · browser"| Frontend
    Frontend <-->|"view · add · edit · dismiss · delete\n(PIN-gated writes)"| Parents
    Scanner -->|"Gmail SMTP · daily"| ReminderEmail
    Scanner -->|"Gmail SMTP · Saturday"| DigestEmail
    ReminderEmail --> Parents
    DigestEmail --> Parents
```

The scanner runs as a Google Cloud Run Job triggered daily at 7am Pacific by Cloud Scheduler. The frontend is a static SPA — no server required.

---

## Prerequisites

- Python 3.11+
- Node.js 18+
- Firebase CLI (`npm install -g firebase-tools`)
- gcloud CLI (`brew install --cask google-cloud-sdk` on Mac)
- A Google Cloud project with the **Gmail API** enabled and an OAuth 2.0 Desktop credentials file (`credentials.json`)
- Accounts on: Anthropic, JSONBin.io, Firebase, Google Cloud (see [docs/SERVICES.md](docs/SERVICES.md))

---

## Backend setup

```bash
# 1. Create and activate virtualenv
python3 -m venv venv
source venv/bin/activate

# 2. Install dependencies
pip install -r backend/requirements.txt

# 3. Configure environment
cp backend/.env.example backend/.env
# Edit backend/.env — fill in all values (see .env.example for guidance)

# 4. Place Gmail OAuth credentials
# Copy credentials.json into backend/credentials.json
# (Download from Google Cloud Console → APIs & Services → Credentials)

# 5. Authenticate with Gmail (opens browser on first run)
cd backend
python scanner.py --test-auth
# Saves backend/token.json — subsequent runs skip the browser
```

---

## Frontend setup

```bash
cd frontend

# 1. Install dependencies
npm install

# 2. Configure environment
cp .env.example .env
# Edit frontend/.env — set VITE_JSONBIN_BIN_ID, VITE_JSONBIN_API_KEY, and VITE_APP_PIN
# NOTE: escape every $ in the API key with \$ (e.g. \$2a\$10\$...)

# 3. Run dev server
npm run dev
# Opens at http://localhost:5173
```

---

## Running the scanner locally

All commands run from the `backend/` directory with the virtualenv active.

```bash
# Full run: fetch emails → Claude → write JSONBin → send reminder → send digest if Saturday
python scanner.py

# Dry run: all steps but no writes, prints JSON to console
python scanner.py --dry-run

# Force send the weekly digest email right now
python scanner.py --send-digest

# Force send the day-before reminder email right now
python scanner.py --send-reminder

# Override the fetch window for this run only (default: SCAN_DAYS_BACK from config)
python scanner.py --days 14

# Smoke tests (run each independently to verify a step)
python scanner.py --test-auth
python scanner.py --test-fetch
python scanner.py --test-analyze
python scanner.py --test-jsonbin
python scanner.py --test-dedup
python scanner.py --test-reminder

# Maintenance
python scanner.py --reset-last-scanned        # Clear lastScanned so next run fetches SCAN_DAYS_BACK days
python scanner.py --wipe-and-rescan           # Clear all JSONBin data then run a fresh scan
python scanner.py --wipe-and-rescan --days 14 # Same but fetch 14 days
```

---

## Deploying the frontend

```bash
# 1. Build
cd frontend && npm run build

# 2. Deploy (run from project root)
cd .. && firebase deploy --only hosting
```

Live URL is printed by Firebase CLI after deploy (`Hosting URL: https://...`).
The project ID is configured in `.firebaserc`.

Refreshing any path does not 404 — SPA rewrites are configured in `firebase.json`.

---

## Cloud Run (production scheduler)

The scanner runs in production as a Google Cloud Run Job triggered daily at 7am Pacific by Cloud Scheduler. Secrets (API keys, Gmail token) are stored in GCP Secret Manager and injected at runtime — nothing sensitive is baked into the container image.

Key files:
- `backend/Dockerfile` — container definition (Python 3.11-slim, installs requirements, copies scanner)
- `backend/entrypoint.sh` — copies the read-only Gmail token secret to a writable path, then runs scanner.py
- `backend/.dockerignore` — excludes `.env`, `credentials.json`, `token.json`, and `venv/` from the image

**Manually trigger a run:**
```bash
gcloud run jobs execute family-inbox-scanner --region=us-west1 --wait
```

**Update the container after changing scanner.py:**
```bash
cd backend
gcloud builds submit . \
  --tag="us-west1-docker.pkg.dev/YOUR_PROJECT_ID/family-inbox/scanner:latest"
gcloud run jobs update family-inbox-scanner \
  --image="us-west1-docker.pkg.dev/YOUR_PROJECT_ID/family-inbox/scanner:latest" \
  --region=us-west1
```

**If token.json needs regeneration** (e.g. refresh token revoked):
```bash
cd backend && source venv/bin/activate
python scanner.py --test-auth
gcloud secrets versions add GMAIL_TOKEN_JSON --data-file=token.json
```

---

## Environment variables

### `backend/.env`

| Variable | Description |
|---|---|
| `ANTHROPIC_API_KEY` | Anthropic API key |
| `FAMILY_INBOX_EMAIL` | Gmail address of the family forwarding inbox |
| `GMAIL_APP_PASSWORD` | Gmail App Password for SMTP sending |
| `JSONBIN_BIN_ID` | JSONBin bin ID |
| `JSONBIN_API_KEY` | JSONBin master key |
| `DIGEST_RECIPIENTS` | Comma-separated list of digest email recipients |
| `FAMILY_CONTEXT` | Free-text description of children's schools/providers passed to Claude |

### `frontend/.env`

| Variable | Description |
|---|---|
| `VITE_JSONBIN_BIN_ID` | Same bin ID as backend |
| `VITE_JSONBIN_API_KEY` | Same master key as backend — escape `$` as `\$` (Vite runs dotenv-expand) |
| `VITE_APP_PIN` | PIN required to make any write action on the dashboard |

In production, all backend variables are stored in GCP Secret Manager and injected into the Cloud Run Job at runtime. The `.env` file is only used for local development.

---

## Folder structure

```
family_inbox_digest/
├── backend/
│   ├── scanner.py          # Main script: fetch → analyze → store → email
│   ├── config.py           # All user-configurable settings
│   ├── Dockerfile          # Cloud Run container definition
│   ├── entrypoint.sh       # Container startup: writes token.json, runs scanner.py
│   ├── requirements.txt
│   ├── .dockerignore
│   ├── credentials.json    # Gmail OAuth app credentials (do not commit)
│   ├── token.json          # Gmail OAuth user token (do not commit, generated on first auth)
│   ├── .env                # Secrets (do not commit)
│   └── .env.example
├── frontend/
│   ├── src/
│   │   ├── App.jsx
│   │   ├── api.js          # All JSONBin read/write functions
│   │   ├── index.css       # Design system (CSS variables, typography, layout)
│   │   └── components/
│   │       ├── EventCard.jsx
│   │       ├── AddEventForm.jsx
│   │       ├── DigestGroup.jsx
│   │       └── FilterPills.jsx
│   ├── .env
│   └── .env.example
├── docs/
│   ├── SERVICES.md         # All external services and account details (do not commit)
│   └── CLAUDE.md           # Codebase guide for AI-assisted development
├── firebase.json
└── .firebaserc
```