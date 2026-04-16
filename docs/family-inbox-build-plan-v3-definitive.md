# Family Inbox Intelligence — Definitive Build Plan
### Owner: Sarah | Stack: Python · React · JSONBin · Firebase · Linear | Version: 1.0

---

## How to Use This Document

This plan is written in strict chronological order. Every step tells you:
- **What** to do
- **Why** you are doing it
- **Who** does it (You or Claude Code)
- **Risks** where relevant

Do not skip steps or reorder them. Each step depends on the one before it.

**Conventions:**
- 🧑 YOU — something you do manually in a browser or app
- 💻 TERMINAL — something you type in Terminal (Mac)
- 🤖 CLAUDE CODE — a prompt you paste into Claude Code in VS Code
- 📋 LINEAR — a ticket Claude Code will create via the Linear API
- ⚠️ RISK — something that commonly goes wrong and how to handle it

**Time estimate:** 4–5 hours total for Phase 1. You can split across two sessions — a natural break point is marked.

---

## What We Are Building

A private family dashboard called **Family Inbox Intelligence**.

**The problem:** You receive 5–10 emails per week from Brandfort Elementary, Little Neighbourhood Daycare, GFT After School, and other activity providers. You regularly miss important dates — picture day, permission slips, belt tests, Pro-D Day closures — because the volume is overwhelming and sifting through it takes time you don't have.

**The solution:** A dedicated Gmail account (`family-inbox@gmail.com` or similar) receives forwarded copies of all school and activity emails. A Python script reads those emails, sends them to Claude AI, and extracts: (a) important upcoming dates and deadlines, and (b) a weekly narrative digest of what teachers and coaches communicated. Results are stored in a shared JSON store (JSONBin). A React dashboard hosted at a permanent URL displays everything. You and your husband both bookmark that URL on your phones. Either of you can add events manually, edit events, or dismiss events you don't care about — and the other person sees those changes immediately.

Every Saturday morning, the script also emails both of you a formatted weekly digest.

**Architecture:**
```
Your Gmail          ──forward rules──►
Husband's Gmail     ──forward rules──►  family-inbox@gmail.com
                                                │
                                        Python scanner.py
                                        (runs on your Mac daily at 7am
                                         via launchd scheduler)
                                                │
                                        Anthropic Claude API
                                        (your own API key, ~$0.20/month)
                                                │
                                        JSONBin.io (free JSON storage)
                                                │
                                    ┌───────────┴───────────┐
                              Your phone               Husband's phone
                           (Firebase URL,           (same Firebase URL,
                           bookmarked on             bookmarked on
                           home screen)              home screen)
```

**Privacy:** Your raw email content flows from Gmail → your Mac → Anthropic API. Anthropic processes the text to extract events but does not use API data for model training by default. JSONBin stores only the extracted events and digest summaries — not your raw email text. No Google Cloud backend is involved in Phase 1.

---

## Phase 1 — Local Build (Today)

---

### SECTION 1: Account Setup
*Everything in this section is done by you in a web browser. No code yet.*

---

#### STEP 1.1 — Create the dedicated Gmail account
**Who:** 🧑 You
**Time:** 5 minutes
**Why:** This is the inbox the scanner reads. By using a dedicated account instead of your personal Gmail, you control exactly what gets scanned. Only forwarded school/activity emails will ever be in this inbox — no personal emails, no work emails, no risk of accidentally exposing anything sensitive.

1. Go to accounts.google.com/signup
2. Create an account. Suggested username: `familyinbox.yourfamilyname@gmail.com` (use your actual family name or something memorable)
3. Set a strong password and save it in your password manager
4. Write down this email address — you will use it in many steps below. We will refer to it as `FAMILY_INBOX_EMAIL` throughout this document.
5. Do NOT set up Gmail forwarding yet — that comes in Step 1.6.

**⚠️ Risk:** Google sometimes flags new accounts for suspicious activity if you immediately start using the API. To avoid this, after creating the account, open Gmail in the browser and send one test email to yourself. This establishes the account as active.

---

#### STEP 1.2 — Create an Anthropic account and API key
**Who:** 🧑 You
**Time:** 5 minutes
**Why:** The scanner sends email text to Claude AI to extract events and write digest summaries. This requires your own API key — it means you pay directly for what you use (approximately $0.20/month), and Anthropic processes only what you explicitly send, under your account's terms.

1. Go to console.anthropic.com
2. Sign up with your personal email (not the family inbox account)
3. Once logged in, click **API Keys** in the left sidebar
4. Click **Create Key**
5. Name it `family-inbox-scanner`
6. Copy the key immediately — it starts with `sk-ant-` and is shown only once
7. Save it somewhere secure (your password manager, or a notes app on your phone). We will refer to it as `ANTHROPIC_API_KEY`.

**⚠️ Risk:** If you lose this key before saving it, you just generate a new one. No harm done.

---

#### STEP 1.3 — Create a JSONBin account and bin
**Who:** 🧑 You
**Time:** 5 minutes
**Why:** JSONBin is a free service that stores a JSON file at a permanent URL. Think of it as a tiny shared database that both your phone and your husband's phone read from. When the scanner runs, it writes updated data here. When either of you opens the dashboard, it reads from here. This is what makes the dashboard shared and always in sync — no traditional database needed.

1. Go to jsonbin.io
2. Click **Sign Up** — use your personal email
3. Once logged in, click **Create Bin** (the + button)
4. In the editor, paste this exact starter content:
   ```json
   {
     "lastScanned": null,
     "events": [],
     "digestGroups": []
   }
   ```
5. Click **Create Bin**
6. You will see a Bin ID in the URL — it looks like `64abc1234567890abc123456`. Copy it. We will refer to it as `JSONBIN_BIN_ID`.
7. Click your account icon (top right) → **API Keys** → copy your Master Key. We will refer to it as `JSONBIN_API_KEY`.

**⚠️ Risk:** JSONBin free tier allows up to 10,000 requests/month. At one scan per day plus normal dashboard usage, you will use approximately 100–200 requests/month. You are nowhere near the limit.

---

#### STEP 1.4 — Create a Linear account and project
**Who:** 🧑 You
**Time:** 10 minutes
**Why:** Linear is a project management tool where you will track every task in this build as a ticket. This is spec-based development: each piece of functionality is defined as a ticket before Claude Code builds it. This keeps the work organized, makes it easy to resume if you take a break, and gives Claude Code clear acceptance criteria for each task.

1. Go to linear.app
2. Click **Sign up** — use your personal email or sign in with Google
3. Create a new **Workspace** called `Personal Projects`
4. Create a new **Project** called `Family Inbox Intelligence`
5. Create a new **Team** called `Family App` (Linear requires a team)
6. In your Linear settings, go to **API** → **Personal API Keys** → **Create Key**
7. Name it `claude-code-integration`
8. Copy the key. We will refer to it as `LINEAR_API_KEY`.
9. Find your team ID: go to Settings → Teams → click your team → the ID is in the URL (looks like `abc12345-...`). We will refer to it as `LINEAR_TEAM_ID`.

---

#### STEP 1.5 — Set up GCP project and Gmail API credentials
**Who:** 🧑 You
**Time:** 15 minutes
**Why:** The scanner needs permission to read emails from your family inbox Gmail account. Google requires you to go through an authorization process (OAuth) to grant that permission. This step sets up the "app" that requests that permission. You do this once, and it never needs to be repeated.

**Why GCP and not just a password?** Google does not allow apps to log into Gmail with a username and password for security reasons. Instead, you create an "OAuth app" in Google Cloud Platform, download credentials for it, and the first time the scanner runs, a browser window opens asking you to click "Allow." After that, the permission is saved locally and the scanner never asks again.

1. Go to console.cloud.google.com
2. Sign in with the **family inbox Google account** (`FAMILY_INBOX_EMAIL`) — important: use the family inbox account, not your personal one
3. Click the project dropdown at the top → **New Project**
   - Project name: `family-inbox-scanner`
   - Click **Create**
   - Wait ~30 seconds for it to create, then select it from the dropdown
4. In the left sidebar, go to **APIs & Services** → **Enable APIs and Services**
   - Search for `Gmail API` → click it → click **Enable**
5. Go to **APIs & Services** → **OAuth consent screen**
   - User type: **External** → click Create
   - App name: `Family Inbox Scanner`
   - User support email: your `FAMILY_INBOX_EMAIL`
   - Developer contact email: your `FAMILY_INBOX_EMAIL`
   - Click **Save and Continue** through all steps (you don't need to fill in scopes manually)
   - On the final screen, click **Back to Dashboard**
   - Click **Publish App** → confirm. This allows the app to request Gmail access.
6. Go to **APIs & Services** → **Credentials** → **Create Credentials** → **OAuth client ID**
   - Application type: **Desktop app**
   - Name: `Family Inbox Scanner Desktop`
   - Click **Create**
7. A dialog appears. Click **Download JSON**
8. The file downloads with a long name like `client_secret_xyz.json`. Rename it to exactly `credentials.json`
9. Do not open or edit this file. Leave it in your Downloads folder for now — you will move it in Step 2.3.

**⚠️ Risk — most common stumbling block in this whole project:** If you see "Access blocked: app has not completed Google verification" when the browser OAuth window opens later, it means you did not click "Publish App" in step 5. Go back to OAuth consent screen and publish it. You do NOT need Google to verify your app — publishing it yourself is sufficient for personal use.

---

#### STEP 1.6 — Set up Gmail forwarding rules
**Who:** 🧑 You
**Time:** 10 minutes
**Why:** Instead of giving the scanner access to your personal Gmail (which contains everything), you forward only school and activity emails to the dedicated family inbox account. This means the scanner only ever sees emails you explicitly chose to include. You stay in full control.

**First, authorize the forwarding address:**
1. Log into your **personal Gmail** (not the family inbox)
2. Go to Settings (gear icon) → **See all settings** → **Forwarding and POP/IMAP**
3. Click **Add a forwarding address**
4. Enter your `FAMILY_INBOX_EMAIL`
5. Google will send a confirmation email to that address. Open the family inbox Gmail, find the confirmation email, and click the confirmation link.
6. Back in your personal Gmail settings, the forwarding address is now verified.

**Create forwarding filters — do this for each sender:**
1. In your personal Gmail, go to Settings → **Filters and Blocked Addresses** → **Create a new filter**
2. Create one filter for each of the following (repeat this process for each):

   | In the "From" field, enter: | Category |
   |---|---|
   | `brandfortelementary` | school |
   | `littleneighbourhood` | daycare |
   | `gftafterschool` | activities |
   | *(add more after checking your inbox)* | |

3. For each filter: click **Create filter** → check **Forward it to:** → select `FAMILY_INBOX_EMAIL` → click **Create filter**

**⚠️ Note:** You said you'll need to check your inbox for GFT and other senders' actual email domains. Do that now and add a filter for each one. The more precise the "From" filter (e.g. using the full domain like `@brandfortelementary.ca`), the better.

**Ask your husband** to do the same steps from his Gmail — forwarding rules for any school/activity emails he receives that you might not.

---

#### STEP 1.7 — Generate a Gmail App Password
**Who:** 🧑 You
**Time:** 3 minutes
**Why:** The scanner sends the Saturday digest email using Gmail's email-sending service (SMTP). Gmail does not allow apps to log in with your regular password — it requires a special 16-character "App Password" generated specifically for this purpose. This is separate from your Gmail login password and can be revoked at any time without changing your main password.

1. Go to myaccount.google.com — sign in with your `FAMILY_INBOX_EMAIL` account
2. Click **Security** in the left sidebar
3. Under "How you sign in to Google," click **2-Step Verification**
4. If 2-Step Verification is not already on, turn it on now (required before App Passwords work)
5. Scroll to the bottom of the 2-Step Verification page → click **App passwords**
6. In the "Select app" dropdown, choose **Mail**
7. In the "Select device" dropdown, choose **Mac**
8. Click **Generate**
9. A 16-character password appears (format: `xxxx xxxx xxxx xxxx`). Copy it including spaces, or copy without spaces — either works.
10. We will refer to this as `GMAIL_APP_PASSWORD`. Save it in your password manager.

**⚠️ Risk:** If you don't see the App Passwords option, 2-Step Verification is not enabled. Enable it first, then come back to this step.

---

#### STEP 1.8 — Create a Firebase project for hosting
**Who:** 🧑 You
**Time:** 5 minutes
**Why:** Firebase Hosting is a free service from Google that serves your React dashboard at a permanent public URL (like `family-inbox-abc.web.app`). It's fast, free, and requires no server — it just serves your files. This is the URL you and your husband will bookmark on your phones.

1. Go to console.firebase.google.com
2. Sign in with your **personal** Google account (not the family inbox account)
3. Click **Add project**
4. Enter project name: `family-inbox`
5. Disable Google Analytics (not needed) → click **Create project**
6. Once created, click **Hosting** in the left sidebar → **Get started**
7. Follow the setup wizard — you don't need to run any commands yet, just click through
8. Note the project ID shown (e.g. `family-inbox-abc`) — this is your `FIREBASE_PROJECT_ID`

---

*— NATURAL BREAK POINT — You have completed all account setup. Take a break if needed. The next section is where you open VS Code and start building. —*

---

### SECTION 2: Project Setup
*Setting up the codebase on your Mac before any real coding begins.*

---

#### STEP 2.1 — Install required tools
**Who:** 💻 TERMINAL
**Time:** 10 minutes
**Why:** These are the software tools Claude Code will use to build and deploy the app.

Open Terminal (find it in Applications → Utilities → Terminal, or Cmd+Space → "Terminal").

Run each of these commands one at a time. After each one, wait for it to finish before running the next.

```bash
# Check Node.js version (need 18 or higher)
node --version

# If it says v18 or higher, you're good. If lower or "command not found":
# Go to nodejs.org → download the LTS version → install it → reopen Terminal

# Install Firebase CLI (lets you deploy the frontend)
npm install -g firebase-tools

# Verify Firebase installed
firebase --version

# Check Python version (need 3.9 or higher)
python3 --version

# Log into Firebase
firebase login
# This opens a browser window — click Allow
```

---

#### STEP 2.2 — Create the project folder
**Who:** 💻 TERMINAL + 🧑 You
**Time:** 2 minutes
**Why:** All code lives in one folder. Keeping it organized from the start makes Claude Code more reliable — it always knows where things are.

```bash
# Create the project folder on your Desktop
mkdir ~/Desktop/family-inbox
cd ~/Desktop/family-inbox

# Open it in VS Code
code .
```

VS Code opens with the empty `family-inbox` folder.

---

#### STEP 2.3 — Move credentials file
**Who:** 🧑 You
**Time:** 1 minute
**Why:** The `credentials.json` file you downloaded in Step 1.5 needs to be inside the backend folder so the scanner can find it.

1. Create a `backend` folder inside `family-inbox`: in VS Code, click the new folder icon → name it `backend`
2. Move `credentials.json` from your Downloads folder into `~/Desktop/family-inbox/backend/`

You can drag and drop it, or run:
```bash
mv ~/Downloads/credentials.json ~/Desktop/family-inbox/backend/credentials.json
```

---

#### STEP 2.4 — Create your .env file
**Who:** 🧑 You
**Time:** 3 minutes
**Why:** The `.env` file stores all your secret credentials in one place. The scanner reads from this file at runtime. It is never committed to version control (Claude Code will add it to `.gitignore`), so your secrets stay on your machine only.

In VS Code, create a new file at `backend/.env` with this exact content, substituting your real values:

```
# Anthropic
ANTHROPIC_API_KEY=sk-ant-your-key-here

# Gmail (family inbox account)
FAMILY_INBOX_EMAIL=your-family-inbox@gmail.com
GMAIL_APP_PASSWORD=your-16-char-app-password

# JSONBin
JSONBIN_BIN_ID=your-bin-id-here
JSONBIN_API_KEY=your-master-key-here

# Weekly digest recipients
DIGEST_RECIPIENTS=your-personal-email@gmail.com,husbands-email@gmail.com

# Linear (for ticket creation)
LINEAR_API_KEY=your-linear-api-key
LINEAR_TEAM_ID=your-linear-team-id
```

Save the file. Do not share this file with anyone.

---

### SECTION 3: Linear Ticket Creation
*Claude Code reads the full spec and creates all Linear tickets before writing any code.*

---

#### STEP 3.1 — Open Claude Code and set context
**Who:** 🤖 CLAUDE CODE
**Time:** 5 minutes

In VS Code, open Claude Code (click the Claude icon in the sidebar or press Cmd+Shift+P → "Claude Code").

Paste this context-setting prompt first — before any task prompts:

---

**CONTEXT PROMPT — paste this first, before anything else:**
```
You are helping me build a web app called Family Inbox Intelligence. Here is the full context you need to keep in mind throughout this entire project:

WHAT THE APP DOES:
A private family dashboard that reads a dedicated Gmail account (family-inbox@gmail.com) where school and activity emails are forwarded. A Python script reads those emails, sends them to the Anthropic Claude API, and extracts: (a) important upcoming dates and action items, and (b) a weekly narrative digest grouped by sender. Results are stored in JSONBin (a free JSON REST store). A React dashboard at a Firebase Hosting URL displays everything. Both parents can view, add, edit, and dismiss events from their phones. Every Saturday morning, the script emails a digest to both parents.

FAMILY CONTEXT:
- Two children in Vancouver, BC
- Email sources: Brandfort Elementary (school), Little Neighbourhood Daycare (daycare), GFT After School (activities), plus other activity providers TBD
- Two users: Sarah (the builder) and her husband
- Dashboard used on iPhone home screens

TECHNICAL STACK:
- Backend: Python script running locally on Mac (Phase 1), later migrated to Google Cloud Run (Phase 2)
- Data store: JSONBin.io (free, REST API, shared between backend and frontend)
- Frontend: React with Vite, hosted on Firebase Hosting (static, no backend)
- Email sending: Gmail SMTP via Python smtplib
- Scheduler: Mac launchd (Phase 1), Cloud Scheduler (Phase 2)
- Project management: Linear (tickets created via Linear API)
- Claude model to use for email analysis: claude-sonnet-4-20250514

DEVELOPMENT APPROACH:
- Spec-based, not vibe-based. Each module is fully specified before implementation.
- Write complete, production-quality code. No stubs, no placeholders, no TODOs in shipped code.
- Every secret goes in .env files. Never hardcode credentials.
- Handle errors explicitly — the script must never crash silently.
- Log clearly at every step so Sarah can see what's happening.
- Mobile-first frontend. Minimum touch target size 44px.

PROJECT FOLDER STRUCTURE (you will create this):
family-inbox/
├── backend/
│   ├── scanner.py
│   ├── config.py
│   ├── linear_setup.py     ← creates all Linear tickets
│   ├── requirements.txt
│   ├── credentials.json    ← already exists, do not touch
│   ├── .env                ← already exists, do not touch
│   ├── .env.example
│   └── .gitignore
├── frontend/
│   ├── src/
│   │   ├── App.jsx
│   │   ├── components/
│   │   │   ├── EventCard.jsx
│   │   │   ├── AddEventForm.jsx
│   │   │   ├── DigestGroup.jsx
│   │   │   ├── StatsBar.jsx
│   │   │   └── FilterPills.jsx
│   │   ├── api.js
│   │   └── index.css
│   ├── public/
│   │   └── index.html
│   ├── .env
│   ├── .env.example
│   └── package.json
├── firebase.json
├── .firebaserc
└── README.md

Acknowledge you have understood this context and are ready for the first task.
```

---

#### STEP 3.2 — Claude Code creates all Linear tickets
**Who:** 🤖 CLAUDE CODE
**Time:** 10 minutes
**Why:** Before writing any application code, we create Linear tickets for every task. This is spec-based development — the specification exists as tickets before implementation begins. It also means you have a clear checklist and can track progress.

After Claude Code acknowledges the context, paste this prompt:

---

**PROMPT — Linear ticket creation:**
```
Your first task is to write and run a Python script called linear_setup.py that creates all project tickets in Linear via the Linear API.

Read the LINEAR_API_KEY and LINEAR_TEAM_ID from backend/.env using python-dotenv.

Create tickets in this exact order, in a project called "Family Inbox Intelligence". Each ticket should have a title, detailed description (the acceptance criteria), and a status of "Todo". Use the Linear GraphQL API at https://api.linear.app/graphql.

Here are all the tickets to create:

TICKET 1 — Project Scaffolding
Title: "Scaffold project folder structure and install dependencies"
Description:
- Create the full folder structure as specified in context
- Create frontend with: npm create vite@latest frontend -- --template react
- Create backend/requirements.txt with: google-auth google-auth-oauthlib google-api-python-client anthropic python-dotenv requests
- Create backend/.env.example with all required variables listed and commented
- Create backend/.gitignore excluding: .env, credentials.json, token.json, __pycache__, *.pyc
- Create frontend/.env.example
- Create firebase.json configured for single-page app hosting with public dir = frontend/dist
- Create .firebaserc with the Firebase project ID placeholder
- Install Python dependencies in a virtualenv
- Install frontend npm dependencies
- Acceptance criteria: `python3 -m venv venv && source venv/bin/activate && pip install -r requirements.txt` completes without error. `cd frontend && npm install` completes without error.

TICKET 2 — config.py
Title: "Write config.py with all user-configurable settings"
Description:
- All settings live in config.py. Nothing in scanner.py should need editing by the user.
- SCAN_DAYS_BACK = 7
- URGENCY_THRESHOLD_DAYS = 3
- DIGEST_DAY = "Saturday"
- DIGEST_RECIPIENTS loaded from .env
- FAMILY_INBOX_EMAIL loaded from .env
- GMAIL_APP_PASSWORD loaded from .env
- ANTHROPIC_API_KEY loaded from .env
- JSONBIN_BIN_ID loaded from .env
- JSONBIN_API_KEY loaded from .env
- No ALLOWED_SENDERS filter needed — the dedicated inbox only receives forwarded school/activity emails, so ALL emails in that inbox are relevant
- CATEGORIES dict mapping display names to colors and icons:
  school: { color: "#60a5fa", dot: "#60a5fa", icon: "🏫", bg: "#162340" }
  daycare: { color: "#4ade80", dot: "#4ade80", icon: "🌻", bg: "#12301e" }
  activities: { color: "#f87171", dot: "#f87171", icon: "🎯", bg: "#261414" }
  soccer: { color: "#f0c040", dot: "#f0c040", icon: "⚽", bg: "#2e1e00" }
  martial arts: { color: "#c084fc", dot: "#c084fc", icon: "🥋", bg: "#221230" }
  other: { color: "#9090a8", dot: "#9090a8", icon: "📬", bg: "#222230" }
- Acceptance criteria: `from config import *` runs without error. All values load correctly from .env.

TICKET 3 — Gmail authentication module
Title: "Implement Gmail OAuth2 authentication in scanner.py"
Description:
- Use google-auth-oauthlib to authenticate with the Gmail API
- Scopes: ["https://www.googleapis.com/auth/gmail.readonly", "https://mail.google.com/"]
- Look for token.json in the backend/ folder first. If found and valid, use it.
- If token.json is missing or expired, run the interactive OAuth flow using credentials.json — this opens a browser window asking the user to click Allow
- Save the resulting token to token.json after first auth
- Return an authenticated Gmail API service object
- Acceptance criteria: Running the auth function opens a browser on first run, saves token.json, and on subsequent runs uses the saved token without opening the browser.

TICKET 4 — Email fetching module
Title: "Implement Gmail email fetching in scanner.py"
Description:
- Use the authenticated Gmail service to search for emails newer than SCAN_DAYS_BACK days
- Query: f"newer_than:{SCAN_DAYS_BACK}d"
- For each email, extract: message_id, subject, sender_name, sender_email, date_received, body_text
- Body extraction: prefer plain text part. If not available, extract text from HTML by stripping all tags.
- Cap at 30 emails maximum
- Log: "Fetched X emails from [FAMILY_INBOX_EMAIL]"
- Return list of email dicts
- Acceptance criteria: Running the fetch function with valid auth returns a list of email dicts with all fields populated. Works on an inbox with 0 emails (returns empty list without crashing).

TICKET 5 — Claude API analysis module
Title: "Implement Claude API email analysis in scanner.py"
Description:
- Take the list of email dicts from Ticket 4
- Format them into a structured string for Claude
- Call Anthropic API using the anthropic Python library, model claude-sonnet-4-20250514, max_tokens 2000
- System prompt: "You are analyzing emails forwarded to a dedicated family inbox. All emails come from schools, daycares, and children's activity providers. The family has children at Brandfort Elementary, Little Neighbourhood Daycare, and GFT After School in Vancouver BC."
- User prompt: see full prompt text below
- Parse Claude's JSON response
- If JSON is invalid: strip markdown fences and retry parse. If still invalid, log the raw response and raise an exception with a clear message.
- Return dict with keys "events" and "digestGroups"

Full Claude prompt (embed this exactly in scanner.py):
"""
Here are emails from the family inbox this week:

{formatted_emails}

Return ONLY a valid JSON object with exactly two keys:

"events": Array of important upcoming dates, deadlines, or required actions. For each:
  - id: unique string e.g. "evt_001"
  - title: concise name e.g. "Picture Day", "Belt Test — Yellow Belt", "Permission Slip Due"
  - date: YYYY-MM-DD. Infer year from context (current year unless clearly next year). If no specific date exists, omit this event entirely.
  - category: one of: school, daycare, soccer, martial arts, activities, other
  - priority: "high" if within 7 days OR requires immediate action (sign something, pay something, register for something). "medium" if within 30 days. "low" otherwise.
  - source: sender organization name only e.g. "Brandfort Elementary"
  - notes: one sentence of actionable context for the parent e.g. "Wear class colour — blue for Grade 3" or "Registration link expires Friday at midnight"
  - dismissed: false
  - manually_added: false

Include: picture day, field trips, permission slip deadlines, signup/registration deadlines, belt tests, tournaments, Pro-D day closures, concerts, curriculum nights, fundraiser deadlines, any date requiring a parent to do something.
Omit: events with no specific date, purely informational content with no action required.

"digestGroups": Weekly narrative summary, one entry per sender. For each:
  - source: sender organization name
  - category: one of: school, daycare, soccer, martial arts, activities, other
  - week_of: ISO date of Monday of the current week (YYYY-MM-DD)
  - bullets: array of 3-5 strings. Each is a specific, useful update — what kids are learning, classroom news, coach updates, schedule changes, reminders, event recaps. Write as a parent would want to read. Be specific. BAD: "The teacher sent an update." GOOD: "Ms. Chen's class finished their weather unit and began ecosystems — ask your child about the terrarium they built."

Return ONLY valid JSON. No markdown fences. No preamble. No explanation.
"""

- Acceptance criteria: Given a list of sample emails, function returns a valid dict with "events" and "digestGroups" keys, both arrays, all fields present.

TICKET 6 — JSONBin read/write module
Title: "Implement JSONBin data persistence in scanner.py"
Description:
- Implement read_jsonbin() → fetches current data from JSONBin, returns dict
  GET https://api.jsonbin.io/v3/b/{JSONBIN_BIN_ID}/latest
  Header: X-Master-Key: {JSONBIN_API_KEY}
  Returns response.json()["record"]
- Implement write_jsonbin(data) → writes full data dict to JSONBin
  PUT https://api.jsonbin.io/v3/b/{JSONBIN_BIN_ID}
  Headers: Content-Type: application/json, X-Master-Key: {JSONBIN_API_KEY}
  Body: json.dumps(data)
- Implement merge_data(existing, new_events, new_digest_groups) → merging rules:
  Events: keep all existing events where dismissed=True OR manually_added=True. For new Claude events, add only if their id doesn't already exist in existing events. Never duplicate.
  DigestGroups: replace entirely with new Claude results.
  lastScanned: always set to current UTC timestamp in ISO format.
- Log: "Read X existing events from JSONBin" and "Wrote X events, Y digest groups to JSONBin"
- Acceptance criteria: read_jsonbin() returns a dict. write_jsonbin() returns HTTP 200. merge_data() correctly preserves dismissed and manually_added events while adding new ones without duplication. Running scanner twice in a row does not duplicate events.

TICKET 7 — Weekly digest email
Title: "Implement Saturday digest email in scanner.py"
Description:
- Implement send_digest_email(events, digest_groups) using smtplib + Gmail SMTP
- SMTP settings: host=smtp.gmail.com, port=587, TLS (starttls)
- Login: FAMILY_INBOX_EMAIL, GMAIL_APP_PASSWORD
- Send to all addresses in DIGEST_RECIPIENTS
- Subject: f"📋 Family Inbox — Week of {monday_date}"
- Body format (plain text):

---
COMING UP THIS WEEK
• [event title] — [weekday, Month Day] | [source]
  [notes]
(list only events with priority high or medium, sorted by date)

THIS WEEK'S UPDATES FROM YOUR INBOX

🏫 BRANDFORT ELEMENTARY
› [bullet 1]
› [bullet 2]
...

🌻 LITTLE NEIGHBOURHOOD DAYCARE
› [bullet 1]
...

(etc for each digest group, with appropriate icon from CATEGORIES)
---

- Only send if today is Saturday OR if --send-digest flag is passed at command line
- Acceptance criteria: Running python scanner.py --send-digest sends a correctly formatted email to all DIGEST_RECIPIENTS. Running on a non-Saturday without the flag does NOT send an email.

TICKET 8 — Main scanner orchestration
Title: "Wire all modules together in scanner.py main()"
Description:
- scanner.py main() runs all steps in sequence with clear logging:
  1. Log "=== Family Inbox Scanner starting ==="
  2. Authenticate with Gmail
  3. Fetch emails → log count
  4. If 0 emails: log "No emails found, exiting" and exit gracefully (still update lastScanned in JSONBin)
  5. Analyze with Claude → log event count and digest group count
  6. Read existing data from JSONBin
  7. Merge data
  8. Write merged data to JSONBin
  9. If Saturday or --send-digest: send digest email
  10. Log "=== Scan complete ==="
- Command line flags:
  --dry-run: run all steps but do NOT write to JSONBin and do NOT send email. Print what would be written to console instead.
  --send-digest: force send the digest email regardless of day
- Acceptance criteria: python scanner.py --dry-run runs end-to-end and prints valid JSON output to console. python scanner.py writes to JSONBin and exits with code 0.

TICKET 9 — Frontend: api.js (JSONBin integration)
Title: "Implement all JSONBin read/write functions in frontend api.js"
Description:
All JSONBin interaction lives in src/api.js. Uses VITE_JSONBIN_BIN_ID and VITE_JSONBIN_API_KEY from frontend .env.

Implement and export:
- loadData() → GET JSONBin, return { events, digestGroups, lastScanned }
- saveData(data) → PUT JSONBin with full data object
- dismissEvent(eventId) → load, find by id, set dismissed:true, save
- deleteEvent(eventId) → load, filter out by id, save (no confirm — confirm is in UI)
- addEvent(eventObj) → load, push new event with id:"manual_"+Date.now(), manually_added:true, dismissed:false, save
- updateEvent(eventId, fields) → load, find by id, merge fields, save

Each function must handle HTTP errors explicitly — throw a descriptive error that the UI can catch and display.
- Acceptance criteria: loadData() returns correct shape. saveData() returns HTTP 200. All mutation functions correctly update JSONBin and return the updated data.

TICKET 10 — Frontend: App.jsx and state management
Title: "Implement App.jsx with full state management and data loading"
Description:
- On mount: call loadData(), set state, set loading:false
- State: data, loading, error, activeTab ("events"|"digest"), filter ("all"|"school"|"daycare"|"soccer"|"martial arts"|"activities"|"other"), showAddForm, editingEventId
- Derived values (computed from state, not stored):
  visibleEvents: events where dismissed !== true, sorted by date asc, filtered by category
  upcomingEvents: visibleEvents where date >= today
  urgentCount: upcomingEvents where daysUntil <= 3
  thisWeekCount: upcomingEvents where daysUntil <= 7
- Handler functions: handleDismiss, handleDelete, handleAdd, handleUpdate, handleFilterChange, handleTabChange
- All handlers call the relevant api.js function then reload data from JSONBin
- Render: Header → StatsBar → TabBar → FilterPills → (EventsList or DigestList) → (AddEventForm modal if showAddForm)
- Acceptance criteria: App loads data on mount, displays correct counts in stats bar, filter changes update both tabs, all CRUD operations persist to JSONBin.

TICKET 11 — Frontend: EventCard component
Title: "Implement EventCard component with edit, dismiss, delete"
Description:
- Props: event, onDismiss, onDelete, onEdit
- Display mode (default):
  Left: date badge 60px wide, colored by urgency (red=today/tomorrow, orange=2-3 days, yellow=4-7 days, green=8+ days, gray=past)
  Badge label: TODAY | TOMORROW | IN Xd | PAST
  Right: title (bold) + URGENT badge if priority=high, category Tag + "via [source]", notes in muted text
  Action buttons (always visible on mobile, hover-only on desktop): Edit ✎, Dismiss ✓, Delete ✕
  Delete shows window.confirm() before calling onDelete
- Edit mode (when editingEventId matches this event):
  Inline form replacing card content: title (text), date (date input), category (select), notes (text)
  Save and Cancel buttons
  Save calls onEdit with updated fields
- Acceptance criteria: All three actions work. Edit mode toggles correctly. Urgency colors match spec. Mobile shows buttons always; desktop shows on hover.

TICKET 12 — Frontend: AddEventForm component
Title: "Implement AddEventForm modal for manually adding events"
Description:
- Modal overlay (fixed position, full screen, semi-transparent dark background #000000aa)
- Form fields: Title* (text, required), Date* (date input, required, min=today), Category* (select, options: school/daycare/soccer/martial arts/activities/other), Source (text, placeholder "e.g. Dentist"), Notes (text)
- Add Event button (accent colored) + Cancel button
- On submit: validate required fields, call onAdd(formData), close form
- Close on clicking the overlay background (not the form itself)
- On mobile: form appears as bottom sheet (slides up from bottom)
- Acceptance criteria: Form submits correctly formatted event object. Required field validation prevents empty submit. Closes on overlay click. New event appears in dashboard after submit.

TICKET 13 — Frontend: DigestGroup component
Title: "Implement DigestGroup collapsible card component"
Description:
- Props: group (source, category, week_of, bullets)
- Card with border-left 3px solid in category dot color
- Header (always visible, clickable): category icon + source name (bold) + category Tag pill + collapse chevron
- Body (collapsible): bullet list, each preceded by › in category dot color, text in var(--sub), 13px, line-height 1.6
- Default state: expanded if window.innerWidth > 768, collapsed if mobile
- Smooth collapse animation (max-height transition)
- Acceptance criteria: Collapses and expands on click. Default state correct per screen size. Bullet markers colored correctly per category.

TICKET 14 — Frontend: StatsBar and FilterPills components
Title: "Implement StatsBar and FilterPills components"
Description:
StatsBar:
- 3 equal-width cards: Upcoming (blue, var(--blue)), Urgent ≤3d (red, var(--red)), This Week (accent, var(--accent))
- Numbers in DM Mono font, 26px bold
- Labels in var(--muted), 11px

FilterPills:
- Buttons: all / school / daycare / soccer / martial arts / activities
- Active: var(--accent) background, black text, no border
- Inactive: var(--card) background, var(--muted) text, var(--border) border
- On mobile: horizontal scroll container, no visible scrollbar (overflow-x:auto, scrollbar-width:none)
- Applies to both tabs simultaneously
- Acceptance criteria: Active pill updates on click. Horizontal scroll works on mobile without visible scrollbar.

TICKET 15 — Full visual design and CSS
Title: "Implement complete CSS design system in index.css and component inline styles"
Description:
Apply this design system throughout the app:

CSS variables in :root:
  --bg: #0c0c12
  --surface: #14141c
  --card: #1a1a24
  --border: #26263a
  --accent: #f0c040
  --accent-dim: rgba(240,192,64,0.1)
  --text: #eaeaf4
  --sub: #9090a8
  --muted: #55556a
  --green: #4ade80
  --red: #f87171
  --orange: #fb923c
  --blue: #60a5fa
  --purple: #c084fc

body: background var(--bg), color var(--text), margin 0, font-family 'DM Sans'
Load from Google Fonts: DM Sans 400/600/700, DM Mono 500

Header: sticky, background var(--surface), border-bottom var(--border), padding 16px 24px
  Left: 🏫 + "Family Inbox Intelligence" with CSS gradient text (--text to --accent), below it "Last scanned: X" in var(--muted) 11px
  Right: urgency badge (red, shown only if urgentCount > 0) + "+ Add Event" button (accent bg, black text, bold)

Tab bar: two buttons side by side, active uses accent bg + black text, inactive transparent + var(--sub)

Max content width 820px, centered, padding 22px 16px

Loading state: 3 skeleton cards (gray rectangles, pulsing CSS animation using opacity keyframes)
Error state: red card with error message + Retry button
Empty events: centered text "You're all clear! No upcoming events." in var(--muted)
Empty digest: centered text "No digest yet. Run the scanner to generate summaries." in var(--muted)

Fade-in animation on content load: @keyframes fadein { from { opacity:0; transform:translateY(5px) } to { opacity:1; transform:none } }

All interactive elements: min touch target 44px height on mobile
- Acceptance criteria: App matches the design spec visually. No default browser blue links or form styling. Looks polished on both iPhone (390px) and desktop (1440px).

TICKET 16 — Mac launchd scheduler
Title: "Set up Mac launchd to run scanner daily at 7am"
Description:
- Write a launchd plist file that runs python scanner.py every day at 7:00 AM
- File location: ~/Library/LaunchAgents/com.familyinbox.scanner.plist
- Must activate the Python virtualenv before running the script
- Redirect stdout and stderr to a log file at ~/Desktop/family-inbox/scanner.log
- Include exact terminal commands to load, start, and verify the scheduler
- Include command to check if it's running: launchctl list | grep familyinbox
- Acceptance criteria: After loading the plist, the scanner runs at 7am without any manual intervention. Log file captures all output.

TICKET 17 — Firebase deployment
Title: "Deploy frontend to Firebase Hosting"
Description:
- Configure firebase.json for static hosting with SPA routing (all paths → index.html)
- Public directory: frontend/dist
- Write exact commands to build and deploy:
  cd frontend && npm run build
  firebase deploy --only hosting
- After deploy, output the live URL
- Acceptance criteria: Dashboard is accessible at the Firebase URL. Refreshing any path does not 404. JSONBin data loads correctly from the deployed URL.

TICKET 18 — End-to-end test and tuning
Title: "End-to-end test: real emails → dashboard"
Description:
- Run python scanner.py --dry-run → verify output contains real events from the family inbox
- Run python scanner.py → verify JSONBin is updated
- Open Firebase URL → verify dashboard shows correct data
- Test add event → verify it persists and is visible after page refresh
- Test dismiss event → verify it disappears and stays dismissed after page refresh
- Test delete event → verify it is removed from JSONBin
- Run python scanner.py again → verify dismissed and manual events are preserved
- Run python scanner.py --send-digest → verify both parents receive the email
- Add any remaining real sender names to config.py based on actual inbox contents
- Acceptance criteria: All above tests pass. Both parents can access the dashboard on their phones.

After creating all tickets, print the Linear ticket IDs and URLs for each ticket.
```

---

### SECTION 4: Implementation
*Claude Code builds the app, one ticket at a time.*

For each ticket below, the process is:
1. Tell Claude Code which ticket to implement (by Linear ticket ID)
2. Claude Code reads the ticket spec from Linear and implements it
3. You verify it works before moving to the next ticket

---

#### STEP 4.1 — Scaffold (Ticket 1)
**Who:** 🤖 CLAUDE CODE
**Time:** 15 minutes

```
Implement Linear ticket [TICKET-1-ID]: Project Scaffolding.
Read the full ticket description from Linear first, then implement it exactly.
After completing, confirm: "Scaffolding complete. Run these commands to verify: [commands]"
```

**You verify:**
```bash
cd ~/Desktop/family-inbox/backend
python3 -m venv venv
source venv/bin/activate
pip install -r requirements.txt
# Should complete without errors

cd ../frontend
npm install
npm run dev
# Should open a browser with a blank Vite React app
```

Press Ctrl+C to stop the dev server.

---

#### STEP 4.2 — Config (Ticket 2)
**Who:** 🤖 CLAUDE CODE
**Time:** 10 minutes

```
Implement Linear ticket [TICKET-2-ID]: config.py.
Read the full ticket description from Linear first, then implement it.
After completing, verify it works by running: cd backend && source venv/bin/activate && python3 -c "from config import *; print('Config loaded OK')"
```

---

#### STEP 4.3 — Gmail auth (Ticket 3)
**Who:** 🤖 CLAUDE CODE + 🧑 You
**Time:** 15 minutes

```
Implement Linear ticket [TICKET-3-ID]: Gmail OAuth2 authentication.
Read the full ticket description from Linear first, then implement it.
Write a standalone test function at the bottom of scanner.py that I can call to test just the auth step.
After completing, tell me exactly how to test it.
```

**You test it:**
```bash
cd ~/Desktop/family-inbox/backend
source venv/bin/activate
python3 scanner.py --test-auth
```

A browser window opens. Sign in with `FAMILY_INBOX_EMAIL`. Click Allow. You see "Authentication successful. token.json saved." in the terminal.

**⚠️ Risk:** If you see "Access blocked," go back to Step 1.5 and make sure you clicked "Publish App" on the OAuth consent screen.

---

#### STEP 4.4 — Email fetching (Ticket 4)
**Who:** 🤖 CLAUDE CODE
**Time:** 15 minutes

```
Implement Linear ticket [TICKET-4-ID]: Email fetching.
Read the full ticket description from Linear first, then implement it.
Add a --test-fetch flag that runs just auth + fetch and prints the email subjects to console.
```

**You test:**
```bash
python3 scanner.py --test-fetch
```

You should see a list of email subjects from the family inbox. If the inbox is empty (you haven't set up forwarding yet or no emails have arrived), it will print "No emails found" — that is correct behavior.

---

#### STEP 4.5 — Claude analysis (Ticket 5)
**Who:** 🤖 CLAUDE CODE
**Time:** 20 minutes

```
Implement Linear ticket [TICKET-5-ID]: Claude API analysis.
Read the full ticket description from Linear first, then implement it.
Add a --test-analyze flag that runs auth + fetch + Claude analysis and prints the resulting JSON to console.
```

**You test:**
```bash
python3 scanner.py --test-analyze
```

You should see a JSON object with "events" and "digestGroups" arrays printed to the terminal. If there are emails in the inbox, you should see real extracted events.

**⚠️ Risk:** If Claude returns invalid JSON, ask Claude Code: "The --test-analyze output shows Claude returning text that isn't valid JSON. Add a cleanup step that strips any markdown fences, leading/trailing text, or explanation before parsing."

---

#### STEP 4.6 — JSONBin persistence (Ticket 6)
**Who:** 🤖 CLAUDE CODE
**Time:** 15 minutes

```
Implement Linear ticket [TICKET-6-ID]: JSONBin read/write and merge logic.
Read the full ticket description from Linear first, then implement it.
Add a --test-jsonbin flag that reads from JSONBin and prints the current contents, then writes a test event and reads again to confirm it persisted.
```

**You test:**
```bash
python3 scanner.py --test-jsonbin
```

You should see your JSONBin contents (initially just the empty starter data), then see a test event written, then confirmed back.

---

#### STEP 4.7 — Digest email (Ticket 7)
**Who:** 🤖 CLAUDE CODE
**Time:** 15 minutes

```
Implement Linear ticket [TICKET-7-ID]: Saturday digest email.
Read the full ticket description from Linear first, then implement it.
```

**You test:**
```bash
python3 scanner.py --send-digest
```

Check both your email and your husband's email — you should each receive a formatted digest.

**⚠️ Risk:** If you get "SMTPAuthenticationError," your Gmail App Password is wrong. Go back to Step 1.7 and generate a new one.

---

#### STEP 4.8 — Main orchestration (Ticket 8)
**Who:** 🤖 CLAUDE CODE
**Time:** 15 minutes

```
Implement Linear ticket [TICKET-8-ID]: Main scanner orchestration.
Read the full ticket description from Linear first, then wire all the modules together in main().
```

**You test the dry run:**
```bash
python3 scanner.py --dry-run
```

You should see clean step-by-step log output and a JSON preview of what would be written. Nothing should be written to JSONBin.

**You test the real run:**
```bash
python3 scanner.py
```

Check JSONBin — go to jsonbin.io, open your bin, and verify events and digestGroups are populated.

---

*— BACKEND IS COMPLETE. Take a break if needed. The next section builds the dashboard. —*

---

#### STEP 4.9 — Frontend api.js (Ticket 9)
**Who:** 🤖 CLAUDE CODE
**Time:** 15 minutes

Before running this prompt, create `frontend/.env` with:
```
VITE_JSONBIN_BIN_ID=your-bin-id-here
VITE_JSONBIN_API_KEY=your-master-key-here
```

```
Implement Linear ticket [TICKET-9-ID]: frontend api.js.
Read the full ticket from Linear first, then implement it.
After implementing, add a quick test: in browser console I should be able to run:
  import { loadData } from './api.js'
  loadData().then(console.log)
and see the JSONBin data.
```

---

#### STEP 4.10 — App.jsx (Ticket 10)
**Who:** 🤖 CLAUDE CODE
**Time:** 20 minutes

```
Implement Linear ticket [TICKET-10-ID]: App.jsx and state management.
Read the full ticket from Linear first, then implement it.
Run npm run dev after implementing so I can verify it loads data and the basic structure works before we add individual components.
```

**You verify:** Open `http://localhost:5173` in your browser. The app should load and show a basic structure (even if unstyled) with the correct event counts from JSONBin.

---

#### STEP 4.11 — EventCard (Ticket 11)
**Who:** 🤖 CLAUDE CODE
**Time:** 20 minutes

```
Implement Linear ticket [TICKET-11-ID]: EventCard component.
Read the full ticket from Linear first, then implement it.
After implementing, I should be able to see event cards in the browser at localhost:5173 with working dismiss, delete, and edit functionality.
```

---

#### STEP 4.12 — AddEventForm (Ticket 12)
**Who:** 🤖 CLAUDE CODE
**Time:** 15 minutes

```
Implement Linear ticket [TICKET-12-ID]: AddEventForm modal.
Read the full ticket from Linear first, then implement it.
```

**You test:** Click "+ Add Event," fill in a test event, submit. Verify it appears in the events list and persists after page refresh.

---

#### STEP 4.13 — DigestGroup (Ticket 13)
**Who:** 🤖 CLAUDE CODE
**Time:** 15 minutes

```
Implement Linear ticket [TICKET-13-ID]: DigestGroup component.
Read the full ticket from Linear first, then implement it.
After implementing, switch to the Weekly Digest tab in the browser and verify digest groups appear and collapse/expand correctly.
```

---

#### STEP 4.14 — StatsBar and FilterPills (Ticket 14)
**Who:** 🤖 CLAUDE CODE
**Time:** 10 minutes

```
Implement Linear ticket [TICKET-14-ID]: StatsBar and FilterPills.
Read the full ticket from Linear first, then implement it.
```

---

#### STEP 4.15 — Full visual design (Ticket 15)
**Who:** 🤖 CLAUDE CODE
**Time:** 20 minutes

```
Implement Linear ticket [TICKET-15-ID]: Full CSS design system.
Read the full ticket from Linear first, then apply the complete design system across all components.
After implementing, the app should look polished and match the dark-themed design spec. Run npm run dev and confirm visually.
Key check: open Chrome DevTools, toggle device toolbar to iPhone 12 Pro (390px wide), and confirm the layout looks correct on mobile.
```

---

#### STEP 4.16 — Mac scheduler (Ticket 16)
**Who:** 🤖 CLAUDE CODE + 🧑 You
**Time:** 10 minutes

```
Implement Linear ticket [TICKET-16-ID]: Mac launchd scheduler.
Read the full ticket from Linear first.
Write the plist file content and the exact terminal commands to install it.
Make sure the plist uses the full absolute path to the Python virtualenv and to scanner.py.
Print the full path I should use — ask me to confirm my username first.
```

**You install it:**
```bash
# Claude Code gives you the exact commands. They will look something like:
cp com.familyinbox.scanner.plist ~/Library/LaunchAgents/
launchctl load ~/Library/LaunchAgents/com.familyinbox.scanner.plist
launchctl list | grep familyinbox
# Should show the job as loaded
```

---

#### STEP 4.17 — Deploy to Firebase (Ticket 17)
**Who:** 🤖 CLAUDE CODE + 🧑 You
**Time:** 15 minutes

```
Implement Linear ticket [TICKET-17-ID]: Firebase deployment.
Read the full ticket from Linear first.
Walk me through the exact commands to build and deploy. I have already run firebase login.
After deploying, tell me the live URL.
```

**After deploy:** Open the Firebase URL on your phone. Add it to your home screen (Safari → Share → Add to Home Screen).

Send the URL to your husband. Have him add it to his home screen on his phone.

---

#### STEP 4.18 — End-to-end test (Ticket 18)
**Who:** 🤖 CLAUDE CODE + 🧑 You
**Time:** 20 minutes

```
Guide me through the end-to-end test described in Linear ticket [TICKET-18-ID].
Read the ticket from Linear first, then walk me through each test step one at a time.
For each step, tell me what I should see if it's working correctly.
After all tests pass, update my config.py with any additional real sender names I identify during testing.
```

---

### SECTION 5: Phone Setup (Both of You)

#### STEP 5.1 — Add to iPhone home screen
**Who:** 🧑 You and your husband
**Time:** 2 minutes each

1. Open **Safari** on iPhone (must be Safari, not Chrome, for Add to Home Screen to work as a full-screen app)
2. Go to the Firebase URL
3. Tap the **Share** button at the bottom of the screen (box with an arrow pointing up)
4. Scroll down in the share sheet and tap **Add to Home Screen**
5. Edit the name to `Family Inbox` if desired
6. Tap **Add**

The app now appears on your home screen. Tapping it opens full-screen with no browser bar — it behaves like a native app.

---

## Phase 1 Complete ✓

At this point you have:
- A scanner running automatically every morning at 7am on your Mac
- A live dashboard at a Firebase URL, accessible on both your phones
- A weekly digest email arriving every Saturday morning
- Full ability to add, edit, and dismiss events from either phone
- All changes synced between both phones via JSONBin

---

## Phase 2 — Move Scanner to the Cloud
*Do this when you're happy with Phase 1 and want the scanner to run reliably without your laptop.*

This is a separate project. When you're ready, start a new Claude Code session and paste:

```
I have a working Family Inbox Intelligence app (Phase 1). The scanner (scanner.py) currently runs on my Mac via launchd. I want to migrate it to run automatically in the cloud so it doesn't depend on my laptop being on.

Target: Google Cloud Run Job triggered by Cloud Scheduler, running daily at 7am Pacific.

My Phase 1 tech: Python scanner, JSONBin for data storage, Firebase Hosting for frontend. No changes to the frontend or JSONBin — only the scanner execution environment changes.

Please plan and implement the migration. Keep scanner.py identical — we are only changing how it is executed and scheduled.
```

Cloud Run Job + Cloud Scheduler is the right approach for this — it runs a containerized Python script on a schedule, costs essentially $0 at this usage level, and requires no server management.

---

## Reference: Full .env Files

### backend/.env
```
ANTHROPIC_API_KEY=sk-ant-...
FAMILY_INBOX_EMAIL=your-family-inbox@gmail.com
GMAIL_APP_PASSWORD=xxxx xxxx xxxx xxxx
JSONBIN_BIN_ID=64abc...
JSONBIN_API_KEY=$2a$10$...
DIGEST_RECIPIENTS=sarah@gmail.com,husband@gmail.com
LINEAR_API_KEY=lin_api_...
LINEAR_TEAM_ID=abc12345-...
```

### frontend/.env
```
VITE_JSONBIN_BIN_ID=64abc...
VITE_JSONBIN_API_KEY=$2a$10$...
```

---

## Reference: Data Structure in JSONBin

```json
{
  "lastScanned": "2026-04-19T07:00:00Z",
  "events": [
    {
      "id": "evt_001",
      "title": "Picture Day",
      "date": "2026-04-20",
      "category": "school",
      "priority": "high",
      "source": "Brandfort Elementary",
      "notes": "Wear class colour — blue for Grade 3.",
      "dismissed": false,
      "manually_added": false
    },
    {
      "id": "manual_1713100000000",
      "title": "Dentist — both kids",
      "date": "2026-04-25",
      "category": "other",
      "priority": "medium",
      "source": "Manual",
      "notes": "Remember to call and confirm the day before.",
      "dismissed": false,
      "manually_added": true
    }
  ],
  "digestGroups": [
    {
      "source": "Brandfort Elementary",
      "category": "school",
      "week_of": "2026-04-13",
      "bullets": [
        "Ms. Chen's class finished weather systems and started ecosystems — ask your child about the terrarium they built.",
        "Library books are due back before the Science World field trip on April 28th.",
        "Spring concert is June 4th at 6:30pm in the gym — families welcome, kids arrive by 6pm."
      ]
    }
  ]
}
```

---

## Troubleshooting Reference

| Problem | Likely cause | Fix |
|---|---|---|
| "Access blocked" on Gmail OAuth | App not published | Go to GCP → OAuth consent screen → Publish App |
| SMTPAuthenticationError | Wrong App Password | Generate a new App Password in Google account settings |
| JSONBin 401 error | Wrong API key | Check JSONBIN_API_KEY — it's the X-Master-Key, not X-Access-Key |
| Claude returns invalid JSON | Preamble text in response | Ask Claude Code to add a cleanup step stripping markdown fences before JSON.parse() |
| Dashboard shows no data | Missing frontend .env | Check frontend/.env has both VITE_ variables; restart dev server after editing |
| Firebase deploy fails | Build not run first | Run `cd frontend && npm run build` before `firebase deploy` |
| Scheduler not running | plist not loaded | Run `launchctl load ~/Library/LaunchAgents/com.familyinbox.scanner.plist` |
| Scheduler runs but no output | Wrong Python path in plist | Use full absolute path to virtualenv python, not just `python3` |

---

*Family Inbox Intelligence — Build Plan v3 (Definitive)*
*Stack: Python · React (Vite) · JSONBin · Firebase Hosting · Anthropic Claude API · Linear*
*Phase 1: Local Mac scheduler | Phase 2: Google Cloud Run (future)*
*Built for Sarah — Vancouver, April 2026*
