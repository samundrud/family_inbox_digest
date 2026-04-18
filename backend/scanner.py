from __future__ import annotations

import base64
import email as email_lib
import html
import json
import logging
import re
import smtplib
import sys
from datetime import date, datetime, timedelta, timezone
from email.mime.text import MIMEText
from pathlib import Path

import anthropic
import requests

from google.auth.transport.requests import Request
from google.oauth2.credentials import Credentials
from google_auth_oauthlib.flow import InstalledAppFlow
from googleapiclient.discovery import build

from config import (
    ALLOWED_FORWARDERS,
    ANTHROPIC_API_KEY,
    CATEGORIES,
    DIGEST_DAY,
    DIGEST_RECIPIENTS,
    FAMILY_CONTEXT,
    FAMILY_INBOX_EMAIL,
    GMAIL_APP_PASSWORD,
    JSONBIN_API_KEY,
    JSONBIN_BIN_ID,
    SCAN_DAYS_BACK,
)

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s  %(levelname)-8s  %(message)s",
    datefmt="%H:%M:%S",
)
log = logging.getLogger(__name__)

_BASE = Path(__file__).parent
_CREDENTIALS_PATH = _BASE / "credentials.json"
_TOKEN_PATH = _BASE / "token.json"

SCOPES = [
    "https://www.googleapis.com/auth/gmail.readonly",
    "https://mail.google.com/",
]


# ---------------------------------------------------------------------------
# Gmail authentication
# ---------------------------------------------------------------------------

def get_gmail_service():
    """Return an authenticated Gmail API service object.

    Uses token.json if present and valid; otherwise runs the interactive
    OAuth browser flow and saves the resulting token to token.json.
    """
    creds: Credentials | None = None

    if _TOKEN_PATH.exists():
        creds = Credentials.from_authorized_user_file(str(_TOKEN_PATH), SCOPES)

    if not creds or not creds.valid:
        if creds and creds.expired and creds.refresh_token:
            log.info("Refreshing expired Gmail token...")
            creds.refresh(Request())
        else:
            log.info("No valid token found — launching browser OAuth flow...")
            flow = InstalledAppFlow.from_client_secrets_file(
                str(_CREDENTIALS_PATH), SCOPES
            )
            creds = flow.run_local_server(port=0)

        _TOKEN_PATH.write_text(creds.to_json())
        log.info("Token saved to %s", _TOKEN_PATH)

    service = build("gmail", "v1", credentials=creds)
    log.info("Gmail service ready (account: %s)", FAMILY_INBOX_EMAIL)
    return service


# ---------------------------------------------------------------------------
# Email fetching
# ---------------------------------------------------------------------------

# Loaded from config (ALLOWED_FORWARDERS env var) — filters to emails forwarded from parent accounts.

_MAX_EMAILS = 30


def _decode_body(data: str) -> str:
    """Decode a base64url-encoded Gmail message part."""
    return base64.urlsafe_b64decode(data + "==").decode("utf-8", errors="replace")


def _strip_html(raw: str) -> str:
    """Remove HTML tags and decode entities, returning plain text."""
    text = re.sub(r"<[^>]+>", " ", raw)
    text = html.unescape(text)
    return re.sub(r"\s+", " ", text).strip()


def _extract_body(payload: dict) -> str:
    """Walk the MIME tree and return the best available body text."""
    mime = payload.get("mimeType", "")

    # Single-part plain text
    if mime == "text/plain":
        data = payload.get("body", {}).get("data", "")
        return _decode_body(data) if data else ""

    # Single-part HTML — strip tags
    if mime == "text/html":
        data = payload.get("body", {}).get("data", "")
        return _strip_html(_decode_body(data)) if data else ""

    # Multipart — recurse; prefer text/plain over text/html
    if mime.startswith("multipart/"):
        parts = payload.get("parts", [])
        plain = next((p for p in parts if p.get("mimeType") == "text/plain"), None)
        if plain:
            return _extract_body(plain)
        html_part = next((p for p in parts if p.get("mimeType") == "text/html"), None)
        if html_part:
            return _extract_body(html_part)
        # Recurse into nested multipart
        for part in parts:
            result = _extract_body(part)
            if result:
                return result

    return ""


def _parse_sender(raw_from: str) -> tuple[str, str]:
    """Return (sender_name, sender_email) from a raw From header value."""
    parsed = email_lib.utils.parseaddr(raw_from)
    name = parsed[0] or parsed[1]
    addr = parsed[1].lower()
    return name, addr


def fetch_emails(service) -> list[dict]:
    """Fetch recent emails forwarded from the parent accounts.

    Returns a list of dicts with keys:
        message_id, subject, sender_name, sender_email, date_received, body_text
    """
    forwarder_query = " OR ".join(f"from:{addr}" for addr in sorted(ALLOWED_FORWARDERS))
    query = f"newer_than:{SCAN_DAYS_BACK}d ({forwarder_query})"

    result = (
        service.users()
        .messages()
        .list(userId="me", q=query, maxResults=_MAX_EMAILS)
        .execute()
    )

    messages = result.get("messages", [])
    if not messages:
        log.info("Fetched 0 emails from %s", FAMILY_INBOX_EMAIL)
        return []

    emails = []
    for msg_stub in messages:
        msg = (
            service.users()
            .messages()
            .get(userId="me", id=msg_stub["id"], format="full")
            .execute()
        )

        headers = {h["name"]: h["value"] for h in msg["payload"].get("headers", [])}
        subject = headers.get("Subject", "(no subject)")
        raw_from = headers.get("From", "")
        date_received = headers.get("Date", "")

        sender_name, sender_email = _parse_sender(raw_from)
        body_text = _extract_body(msg["payload"])

        emails.append(
            {
                "message_id": msg["id"],
                "subject": subject,
                "sender_name": sender_name,
                "sender_email": sender_email,
                "date_received": date_received,
                "body_text": body_text,
            }
        )

    log.info("Fetched %d emails from %s", len(emails), FAMILY_INBOX_EMAIL)
    return emails


# ---------------------------------------------------------------------------
# Claude API analysis
# ---------------------------------------------------------------------------

_SYSTEM_PROMPT = (
    "You are analyzing emails forwarded to a dedicated family inbox. "
    "All emails come from schools, daycares, and children's activity providers. "
    + FAMILY_CONTEXT
)

_USER_PROMPT_TEMPLATE = """\
Here are emails from the family inbox this week:

{formatted_emails}

Return ONLY a valid JSON object with exactly two keys:

"events": Array of important upcoming dates, deadlines, or required actions. For each:
  - id: unique string e.g. "evt_001"
  - title: concise name e.g. "Picture Day", "Belt Test — Yellow Belt", "Permission Slip Due"
  - date: YYYY-MM-DD. Infer year from context (current year unless clearly next year). If no specific date exists, omit this event entirely.
  - category: one of: school, daycare, soccer, martial arts, activities, other
  - priority: "high" if within 7 days OR requires immediate action (sign something, pay something, register for something). "medium" if within 30 days. "low" otherwise.
  - source: sender organization name only e.g. "Springfield Elementary"
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

Return ONLY valid JSON. No markdown fences. No preamble. No explanation.\
"""


def _format_emails_for_claude(emails: list[dict]) -> str:
    parts = []
    for i, e in enumerate(emails, 1):
        parts.append(
            f"--- Email {i} ---\n"
            f"From: {e['sender_name']} <{e['sender_email']}>\n"
            f"Date: {e['date_received']}\n"
            f"Subject: {e['subject']}\n"
            f"Body:\n{e['body_text']}\n"
        )
    return "\n".join(parts)


def _parse_claude_json(raw: str) -> dict:
    """Parse JSON from Claude's response, stripping markdown fences if needed."""
    try:
        return json.loads(raw)
    except json.JSONDecodeError:
        pass

    # Strip markdown code fences and retry
    cleaned = re.sub(r"^```(?:json)?\s*", "", raw.strip(), flags=re.MULTILINE)
    cleaned = re.sub(r"\s*```$", "", cleaned.strip(), flags=re.MULTILINE)
    try:
        return json.loads(cleaned)
    except json.JSONDecodeError:
        log.error("Claude returned invalid JSON:\n%s", raw)
        raise ValueError(
            "Claude response could not be parsed as JSON after stripping markdown fences. "
            "Raw response logged above."
        )


def analyze_emails(emails: list[dict]) -> dict:
    """Send emails to Claude and return structured events and digest groups.

    Returns a dict with keys "events" and "digestGroups", both lists.
    """
    client = anthropic.Anthropic(api_key=ANTHROPIC_API_KEY)

    formatted = _format_emails_for_claude(emails)
    user_prompt = _USER_PROMPT_TEMPLATE.format(formatted_emails=formatted)

    log.info("Sending %d email(s) to Claude for analysis...", len(emails))
    message = client.messages.create(
        model="claude-sonnet-4-6",
        max_tokens=8192,
        system=_SYSTEM_PROMPT,
        messages=[{"role": "user", "content": user_prompt}],
    )

    raw_response = message.content[0].text
    result = _parse_claude_json(raw_response)

    events = result.get("events", [])
    digest_groups = result.get("digestGroups", [])
    log.info(
        "Claude returned %d event(s) and %d digest group(s)",
        len(events),
        len(digest_groups),
    )
    return {"events": events, "digestGroups": digest_groups}


# ---------------------------------------------------------------------------
# JSONBin read / write / merge
# ---------------------------------------------------------------------------

_JSONBIN_BASE = "https://api.jsonbin.io/v3/b"
_JSONBIN_HEADERS_READ = {"X-Master-Key": JSONBIN_API_KEY}
_JSONBIN_HEADERS_WRITE = {
    "Content-Type": "application/json",
    "X-Master-Key": JSONBIN_API_KEY,
}

_EMPTY_BIN: dict = {"events": [], "digestGroups": [], "lastScanned": None}


def read_jsonbin() -> dict:
    """Fetch current data from JSONBin. Returns the stored record dict."""
    url = f"{_JSONBIN_BASE}/{JSONBIN_BIN_ID}/latest"
    resp = requests.get(url, headers=_JSONBIN_HEADERS_READ, timeout=15)
    if resp.status_code == 200:
        record = resp.json().get("record", _EMPTY_BIN)
        event_count = len(record.get("events", []))
        log.info("Read %d existing event(s) from JSONBin", event_count)
        return record
    # 404 means the bin exists but has never been written — treat as empty
    if resp.status_code == 404:
        log.info("JSONBin bin is empty — starting fresh")
        return dict(_EMPTY_BIN)
    resp.raise_for_status()


def write_jsonbin(data: dict) -> None:
    """Write the full data dict to JSONBin."""
    url = f"{_JSONBIN_BASE}/{JSONBIN_BIN_ID}"
    resp = requests.put(
        url,
        headers=_JSONBIN_HEADERS_WRITE,
        data=json.dumps(data),
        timeout=15,
    )
    resp.raise_for_status()
    event_count = len(data.get("events", []))
    group_count = len(data.get("digestGroups", []))
    log.info("Wrote %d event(s), %d digest group(s) to JSONBin", event_count, group_count)


def merge_data(existing: dict, new_events: list[dict], new_digest_groups: list[dict]) -> dict:
    """Merge new Claude results into existing JSONBin data.

    Merge rules:
    - Events: always keep dismissed/manually_added events; add new events
      whose id is not already present (no duplicates).
    - DigestGroups: replace entirely with new Claude results.
    - lastScanned: always updated to current UTC timestamp.
    """
    kept_events: list[dict] = [
        e for e in existing.get("events", [])
        if e.get("dismissed") or e.get("manually_added")
    ]

    existing_ids = {e["id"] for e in existing.get("events", [])}
    added_events: list[dict] = [e for e in new_events if e["id"] not in existing_ids]

    merged_events = kept_events + added_events

    return {
        "events": merged_events,
        "digestGroups": new_digest_groups,
        "lastScanned": datetime.now(timezone.utc).isoformat(),
    }


# ---------------------------------------------------------------------------
# Saturday digest email
# ---------------------------------------------------------------------------

def _monday_of_week(ref: date) -> date:
    """Return the Monday of the week containing ref."""
    return ref - timedelta(days=ref.weekday())


def _format_event_line(event: dict) -> str:
    """Format a single event as two lines for the digest body."""
    try:
        d = datetime.strptime(event["date"], "%Y-%m-%d").date()
        date_str = d.strftime("%A, %B %-d")
    except (ValueError, KeyError):
        date_str = event.get("date", "TBD")

    title = event.get("title", "")
    source = event.get("source", "")
    notes = event.get("notes", "")
    return f"• {title} — {date_str} | {source}\n  {notes}"


def _build_digest_body(events: list[dict], digest_groups: list[dict]) -> str:
    today = date.today()
    monday = _monday_of_week(today)
    lines: list[str] = []

    # --- Upcoming events section ---
    actionable = [
        e for e in events
        if not e.get("dismissed")
    ]
    actionable.sort(key=lambda e: e.get("date", "9999-99-99"))

    lines.append("COMING UP THIS WEEK")
    if actionable:
        for event in actionable:
            lines.append(_format_event_line(event))
    else:
        lines.append("  Nothing urgent on the calendar this week.")

    lines.append("")
    lines.append("─" * 48)
    lines.append("")
    lines.append("THIS WEEK'S UPDATES FROM YOUR INBOX")
    lines.append("")

    # --- Digest groups section ---
    for group in digest_groups:
        category = group.get("category", "other")
        icon = CATEGORIES.get(category, CATEGORIES["other"])["icon"]
        source = group.get("source", "").upper()
        lines.append(f"{icon} {source}")
        for bullet in group.get("bullets", []):
            lines.append(f"› {bullet}")
        lines.append("")

    lines.append("─" * 48)
    lines.append(f"Family Inbox Intelligence  •  Week of {monday.strftime('%B %-d, %Y')}")
    return "\n".join(lines)


def send_digest_email(events: list[dict], digest_groups: list[dict], force: bool = False) -> None:
    """Send the weekly digest email.

    Only sends if today is DIGEST_DAY (Saturday) or force=True.
    Uses Gmail SMTP with an app password.
    """
    today_name = date.today().strftime("%A")
    if not force and today_name != DIGEST_DAY:
        log.info(
            "Skipping digest email — today is %s, not %s (pass --send-digest to force)",
            today_name,
            DIGEST_DAY,
        )
        return

    monday = _monday_of_week(date.today())
    subject = f"📋 Family Inbox — Week of {monday.strftime('%B %-d, %Y')}"
    body = _build_digest_body(events, digest_groups)

    msg = MIMEText(body, "plain", "utf-8")
    msg["Subject"] = subject
    msg["From"] = FAMILY_INBOX_EMAIL
    msg["To"] = ", ".join(DIGEST_RECIPIENTS)

    log.info("Sending digest email to: %s", ", ".join(DIGEST_RECIPIENTS))
    with smtplib.SMTP("smtp.gmail.com", 587) as smtp:
        smtp.ehlo()
        smtp.starttls()
        smtp.login(FAMILY_INBOX_EMAIL, GMAIL_APP_PASSWORD)
        smtp.sendmail(FAMILY_INBOX_EMAIL, DIGEST_RECIPIENTS, msg.as_string())

    log.info("Digest email sent — subject: %s", subject)


# ---------------------------------------------------------------------------
# Standalone auth test
# ---------------------------------------------------------------------------

def _test_auth():
    """Quick smoke-test: authenticate and call users.getProfile to confirm access."""
    log.info("=== Auth test starting ===")
    service = get_gmail_service()
    profile = service.users().getProfile(userId="me").execute()
    log.info("Authenticated as: %s", profile["emailAddress"])
    log.info("Total messages in mailbox: %s", profile["messagesTotal"])
    log.info("=== Auth test passed ===")


def _test_fetch():
    """Smoke-test: authenticate, fetch emails, and print subjects."""
    log.info("=== Fetch test starting ===")
    service = get_gmail_service()
    emails = fetch_emails(service)
    if not emails:
        log.info("No emails found in the last %d days from allowed forwarders.", SCAN_DAYS_BACK)
    else:
        log.info("--- %d email(s) retrieved ---", len(emails))
        for i, e in enumerate(emails, 1):
            print(f"  [{i:02d}] {e['subject']}")
            print(f"        from: {e['sender_name']} <{e['sender_email']}>")
            print(f"        date: {e['date_received']}")
            print(f"        body: {e['body_text'][:120].replace(chr(10), ' ')}...")
            print()
    log.info("=== Fetch test passed ===")


def _test_analyze():
    """Smoke-test: auth + fetch + Claude analysis, print resulting JSON."""
    log.info("=== Analyze test starting ===")
    service = get_gmail_service()
    emails = fetch_emails(service)
    if not emails:
        log.info("No emails to analyze — forwarding a test email first is recommended.")
        return
    result = analyze_emails(emails)
    print(json.dumps(result, indent=2, ensure_ascii=False))
    log.info(
        "=== Analyze test passed: %d event(s), %d digest group(s) ===",
        len(result["events"]),
        len(result["digestGroups"]),
    )


def _test_jsonbin():
    """Smoke-test: read JSONBin, write a test event, read again to confirm persistence."""
    log.info("=== JSONBin test starting ===")

    log.info("--- Step 1: reading current contents ---")
    before = read_jsonbin()
    print(json.dumps(before, indent=2, ensure_ascii=False))

    test_event = {
        "id": "_test_jsonbin_event",
        "title": "JSONBin write test — safe to delete",
        "date": "2026-01-01",
        "category": "other",
        "priority": "low",
        "source": "scanner test",
        "notes": "This event was written by --test-jsonbin and can be deleted.",
        "dismissed": False,
        "manually_added": True,
    }

    log.info("--- Step 2: writing test event ---")
    data_to_write = {
        "events": before.get("events", []) + [test_event],
        "digestGroups": before.get("digestGroups", []),
        "lastScanned": datetime.now(timezone.utc).isoformat(),
    }
    write_jsonbin(data_to_write)

    log.info("--- Step 3: reading back to confirm persistence ---")
    after = read_jsonbin()
    found = any(e["id"] == "_test_jsonbin_event" for e in after.get("events", []))
    if found:
        log.info("Test event confirmed in JSONBin ✓")
    else:
        raise RuntimeError("Test event NOT found after write — something went wrong.")

    log.info("=== JSONBin test passed ===")


def main() -> None:
    args = set(sys.argv[1:])
    dry_run = "--dry-run" in args
    force_digest = "--send-digest" in args

    log.info("=== Family Inbox Scanner starting ===%s", " (DRY RUN)" if dry_run else "")

    # Step 2: authenticate
    service = get_gmail_service()

    # Step 3: fetch emails
    emails = fetch_emails(service)

    # Step 4: no emails — update lastScanned and exit
    if not emails:
        log.info("No emails found, exiting")
        if not dry_run:
            existing = read_jsonbin()
            existing["lastScanned"] = datetime.now(timezone.utc).isoformat()
            write_jsonbin(existing)
        log.info("=== Scan complete ===")
        return

    # Step 5: analyze with Claude
    analysis = analyze_emails(emails)
    new_events = analysis["events"]
    new_digest_groups = analysis["digestGroups"]

    # Step 6: read existing JSONBin data
    existing = read_jsonbin()

    # Step 7: merge
    merged = merge_data(existing, new_events, new_digest_groups)

    # Step 8: write (or dry-run print)
    if dry_run:
        log.info("DRY RUN — would write the following to JSONBin:")
        print(json.dumps(merged, indent=2, ensure_ascii=False))
    else:
        write_jsonbin(merged)

    # Step 9: digest email
    today_name = date.today().strftime("%A")
    if force_digest or today_name == DIGEST_DAY:
        send_digest_email(merged["events"], merged["digestGroups"], force=force_digest)

    log.info("=== Scan complete ===")


if __name__ == "__main__":
    if "--test-auth" in sys.argv:
        _test_auth()
    elif "--test-fetch" in sys.argv:
        _test_fetch()
    elif "--test-analyze" in sys.argv:
        _test_analyze()
    elif "--test-jsonbin" in sys.argv:
        _test_jsonbin()
    else:
        main()