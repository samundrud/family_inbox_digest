from __future__ import annotations

import base64
import email as email_lib
import html
import json
import logging
import re
import smtplib
import sys
import time
import uuid
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

_MAX_EMAILS = 50
_MAX_LOOKBACK_DAYS = 30
_DIGEST_WINDOW_DAYS = 14


def _decode_body(data: str) -> str:
    """Decode a base64url-encoded Gmail message part."""
    return base64.urlsafe_b64decode(data + "==").decode("utf-8", errors="replace")


def _strip_html(raw: str) -> str:
    """Remove HTML tags and decode entities, returning plain text.

    Anchor hrefs are preserved inline as 'text (url)' so Claude can see links.
    """
    # Preserve anchor hrefs: <a href="URL">text</a> → text (URL)
    def _expand_anchor(m: re.Match) -> str:
        href = m.group(1).strip()
        text = re.sub(r"<[^>]+>", " ", m.group(2)).strip()
        if href and not href.startswith(("mailto:", "javascript:")):
            return f"{text} ({href})" if text else href
        return text

    text = re.sub(
        r'<a[^>]+href=["\']([^"\']*)["\'][^>]*>(.*?)</a>',
        _expand_anchor,
        raw,
        flags=re.IGNORECASE | re.DOTALL,
    )
    text = re.sub(r"<[^>]+>", " ", text)
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


def _build_time_query(last_scanned: datetime | None, days_back: int = SCAN_DAYS_BACK) -> str:
    """Return the Gmail time-range clause for the search query.

    Uses last_scanned with a 1-hour overlap buffer and caps lookback at
    _MAX_LOOKBACK_DAYS. Falls back to days_back if no timestamp stored.
    """
    if last_scanned is None:
        return f"newer_than:{days_back}d"

    max_lookback = datetime.now(timezone.utc) - timedelta(days=_MAX_LOOKBACK_DAYS)
    cutoff = max(last_scanned - timedelta(hours=1), max_lookback)
    after_ts = int(cutoff.timestamp())
    return f"after:{after_ts}"


def fetch_emails(service, last_scanned: datetime | None = None, days_back: int = SCAN_DAYS_BACK) -> list[dict]:
    """Fetch emails forwarded from the parent accounts.

    Uses last_scanned as the Gmail after: cutoff (with a 1-hour overlap buffer),
    falling back to days_back days if no timestamp is stored.
    Returns a list of dicts with keys:
        message_id, subject, sender_name, sender_email, date_received, body_text
    """
    time_clause = _build_time_query(last_scanned, days_back=days_back)
    query = f"{time_clause} -in:sent"
    log.info("Fetching emails — time filter: %s", time_clause)

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
                "thread_id": msg["threadId"],
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
    "You are analyzing emails in a dedicated family inbox. "
    "Most emails are forwarded from schools, daycares, and children's activity providers. "
    "Some emails are sent directly by a parent as a personal reminder or family event "
    "(e.g. a doctor appointment, a birthday party, a camp they found). "
    "Extract events from all of these. "
    + FAMILY_CONTEXT
)

_USER_PROMPT_TEMPLATE = """\
Here are emails from the family inbox:

{formatted_emails}

Work in two steps. Write both steps in your response.

STEP 1 — AUDIT (write this first, before any JSON):
Go through every numbered email one by one — Email 1, Email 2, Email 3, and so on.
For each, write exactly one line:
  Email N: [title of event(s) extracted]
  Email N: no events — [one-word reason: newsletter / recap / duplicate / other]
You MUST write a line for every email. Missing any email is an error.
If a single email contains multiple distinct events, list all of them on that line.
A $9 school payment request is just as required as a field trip form — do not filter by importance.

STEP 2 — JSON (write this immediately after the audit, no separator):
Output a valid JSON object with exactly one key "events" containing every event identified in Step 1.

"events": Array of ALL upcoming dates, deadlines, and required actions. For each:
  - id: unique string e.g. "evt_001"
  - title: concise name. When the actionable date is a deadline rather than the event itself, reflect that in the title e.g. "Summer BJJ Camp — Register by May 25" rather than just "Summer BJJ Camp".
  - date: YYYY-MM-DD, chosen by this priority order:
      1. Registration or sign-up deadline — use this if the email is a reminder to register, pay, or sign up
      2. Permission slip or payment due date — use this if the email requires returning something
      3. Event start date — only use this if there is no prior action required (e.g. a school concert you just attend)
    Infer year from context (current year unless clearly next year).
    If the actionable date differs from the event start date, set date to the actionable date and include the actual event date in notes.
    If no date can be determined at all, set date to null.
  - category: one of: school, daycare, scouts, soccer, GFT, other
    Use "scouts" for Scouts Canada, Beavers, Cubs, or any scouting organisation.
    For emails sent directly by a parent, use "other" unless the event clearly fits another category.
  - priority: "high" if within 7 days OR requires immediate action (sign something, pay something, register for something). "medium" if within 30 days. "low" otherwise.
  - source: for forwarded school/activity emails, use the sender organisation name only e.g. "Springfield Elementary".
    For emails sent directly by a parent, use the sender's first name e.g. "Sarah", or "Family" if the name is unclear.
  - source_email_index: the 1-based index of the email this event was extracted from, matching the "--- Email N ---" labels above
  - notes: one sentence of actionable context for the parent e.g. "Wear class colour — blue for Grade 3". If the actionable date differs from the actual event date, always include the event date here e.g. "Camp runs June 26–July 2 in Burnaby. Register by May 25 for the early-bird rate."
  - link: URL if the source email for this event (matching source_email_index) contains a link the parent needs to follow to take a required action — sign up, register, book, pay, view a form, or respond. The link MUST come from the same email as the event — never use a link from a different email. Include it regardless of how the link is labelled or what file type it points to; a shared Google Doc, Word document (.docx), or spreadsheet used as a sign-up sheet is just as valid as a web form. If the email says "sign up via the link below", "use this link to book", or "add your name to the document", that counts. Set to null if no actionable link exists. Never include general school or club website homepages, newsletter archive links, unsubscribe links, or tracking/redirect URLs.
  - dismissed: false
  - manually_added: false

Rules:
- Every event listed in Step 1 MUST appear in the JSON. The audit and JSON must match.
- If a single email mentions multiple distinct dates or events, extract EACH as its own entry. Never collapse two dates into one event.
- Include everything that has a date OR requires any action: picture day, field trips, permission slip deadlines, signup/registration deadlines, belt tests, tournaments, Pro-D day closures, early dismissals, concerts, curriculum nights, fundraiser deadlines, school fees or payments, scheduled meetings, practices, library pickups, personal reminders or family events sent directly by a parent, actionable items with no date (use date: null).
- Omit ONLY content that has both no action required AND no specific date — e.g. a general newsletter with no deadlines, a photo recap with nothing to do.
- Do not filter by perceived importance or dollar amount.

No markdown fences around the JSON.\
"""


_DIGEST_PROMPT_TEMPLATE = """\
Here are all emails received by the family inbox over the past week:

{formatted_emails}

Return ONLY a valid JSON object with exactly one key:

"digestGroups": A narrative summary of what happened this week, grouped by CATEGORY — not by individual organisation. Use the same six categories as the events list: school, daycare, scouts, soccer, GFT, other. Include one entry per category that had at least one email. If multiple organisations fall under the same category (e.g. MVPs and South Burnaby Metro Club are both "soccer"), combine their updates into a single entry. Do NOT include an entry for emails sent directly by a parent. For each entry:
  - source: a short friendly label for the category, e.g. "School", "Daycare", "Scouts", "Soccer", "GFT After School", "Other"
  - category: one of: school, daycare, scouts, soccer, GFT, other
    Use "scouts" for Scouts Canada, Beavers, Cubs, or any scouting organisation.
  - week_of: ISO date of the Monday of the week being summarised (YYYY-MM-DD)
  - bullets: array of 3-5 objects, each with:
    - text: the narrative bullet string. Tell the story of what happened — what kids are learning, what activities took place, what is coming up and why it matters, anything a parent would want to know beyond the bare dates. Do NOT list specific dates or deadlines (those appear separately in the parents' events list). Be concrete and specific.
      BAD: "There is a Pro-D Day on April 27." GOOD: "A professional development day this week means the school building is closed — a good moment to plan an outing or arrange alternate care."
      BAD: "The teacher sent an update." GOOD: "Ms. Chen's class finished their weather unit and started ecosystems — ask your child about the terrarium they built."
      BAD: "There was an email about soccer." GOOD: "Both soccer clubs had activity this week — the spring season is in full swing with practices underway and a merchandise sale at Byrne Creek Secondary."
    - link: a URL only if this specific bullet directly references an action the parent needs to take via that link (sign up, register, pay, complete a survey, view a form). The link must be relevant to the content described in this bullet — never attach a link from a different topic or a different part of the email. If the bullet is about seasonal reminders and the link is for a survey about something else, they do not belong together. Shared documents used as sign-up sheets count. Do not include general homepages, newsletter archives, or unsubscribe links. If no link is directly relevant to this bullet's content, set to null.

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
    """Parse JSON from Claude's response.

    Handles three formats:
    - Pure JSON
    - JSON wrapped in markdown fences
    - Audit text followed by JSON (two-step prompt format)
    """
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
        pass

    # Extract JSON object that follows audit/preamble text
    idx = raw.find('{')
    if idx > 0:
        try:
            return json.loads(raw[idx:])
        except json.JSONDecodeError:
            pass

    log.error("Claude returned invalid JSON:\n%s", raw)
    raise ValueError(
        "Claude response could not be parsed as JSON. Raw response logged above."
    )


def analyze_emails(emails: list[dict]) -> list[dict]:
    """Send emails to Claude and return a list of extracted events."""
    client = anthropic.Anthropic(api_key=ANTHROPIC_API_KEY)

    formatted = _format_emails_for_claude(emails)
    user_prompt = _USER_PROMPT_TEMPLATE.format(formatted_emails=formatted)

    log.info("Sending %d email(s) to Claude for event extraction...", len(emails))
    message = client.messages.create(
        model="claude-sonnet-4-6",
        max_tokens=8192,
        system=_SYSTEM_PROMPT,
        messages=[{"role": "user", "content": user_prompt}],
    )

    raw_response = message.content[0].text
    # Log the audit section so we can verify every email was processed
    json_start = raw_response.find('{')
    if json_start > 0:
        log.info("Claude audit:\n%s", raw_response[:json_start].strip())
    result = _parse_claude_json(raw_response)
    events = result.get("events", [])

    for event in events:
        # Replace Claude's sequential IDs (evt_001, evt_002, ...) with unique IDs.
        # Claude always starts at evt_001, which collides with IDs already in JSONBin.
        event["id"] = f"evt_{uuid.uuid4().hex[:10]}"

        idx = event.pop("source_email_index", None)
        if idx is not None:
            try:
                src = emails[int(idx) - 1]
                event["source_message_id"] = src["message_id"]
                event["source_thread_id"] = src["thread_id"]
                event["source_subject"] = src["subject"]
            except (IndexError, ValueError, TypeError):
                pass

    log.info("Claude returned %d event(s)", len(events))
    return events


def generate_digest_groups(emails: list[dict]) -> list[dict]:
    """Generate weekly narrative digest groups from a full week of emails.

    Called once on Saturday with all emails from the past 7 days.
    Returns a list of digest group dicts.
    """
    if not emails:
        log.info("No emails for digest generation — returning empty list")
        return []

    client = anthropic.Anthropic(api_key=ANTHROPIC_API_KEY)
    formatted = _format_emails_for_claude(emails)
    user_prompt = _DIGEST_PROMPT_TEMPLATE.format(formatted_emails=formatted)

    log.info("Generating weekly digest from %d email(s)...", len(emails))
    message = client.messages.create(
        model="claude-sonnet-4-6",
        max_tokens=4096,
        system=_SYSTEM_PROMPT,
        messages=[{"role": "user", "content": user_prompt}],
    )

    raw_response = message.content[0].text
    result = _parse_claude_json(raw_response)
    groups = result.get("digestGroups", [])
    log.info("Claude returned %d digest group(s)", len(groups))
    return groups


# ---------------------------------------------------------------------------
# JSONBin read / write / merge
# ---------------------------------------------------------------------------

_JSONBIN_BASE = "https://api.jsonbin.io/v3/b"
_JSONBIN_HEADERS_READ = {"X-Master-Key": JSONBIN_API_KEY}
_JSONBIN_HEADERS_WRITE = {
    "Content-Type": "application/json",
    "X-Master-Key": JSONBIN_API_KEY,
}
_JSONBIN_TIMEOUT = 30
_JSONBIN_RETRIES = 3
_JSONBIN_RETRY_DELAY = 3  # seconds between attempts

_EMPTY_BIN: dict = {"events": [], "digestGroups": [], "lastScanned": None}


def _jsonbin_request(method: str, url: str, **kwargs) -> requests.Response:
    """Call requests with retries on timeout or connection error."""
    kwargs.setdefault("timeout", _JSONBIN_TIMEOUT)
    last_exc: Exception | None = None
    for attempt in range(1, _JSONBIN_RETRIES + 1):
        try:
            resp = requests.request(method, url, **kwargs)
            return resp
        except (requests.exceptions.Timeout, requests.exceptions.ConnectionError) as exc:
            last_exc = exc
            if attempt < _JSONBIN_RETRIES:
                log.warning(
                    "JSONBin %s timed out (attempt %d/%d) — retrying in %ds...",
                    method.upper(), attempt, _JSONBIN_RETRIES, _JSONBIN_RETRY_DELAY,
                )
                time.sleep(_JSONBIN_RETRY_DELAY)
    raise last_exc


def read_jsonbin() -> dict:
    """Fetch current data from JSONBin. Returns the stored record dict."""
    url = f"{_JSONBIN_BASE}/{JSONBIN_BIN_ID}/latest"
    resp = _jsonbin_request("get", url, headers=_JSONBIN_HEADERS_READ)
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
    resp = _jsonbin_request(
        "put", url,
        headers=_JSONBIN_HEADERS_WRITE,
        data=json.dumps(data),
    )
    resp.raise_for_status()
    event_count = len(data.get("events", []))
    group_count = len(data.get("digestGroups", []))
    log.info("Wrote %d event(s), %d digest group(s) to JSONBin", event_count, group_count)


_TOMBSTONE_DAYS = 30


def merge_data(existing: dict, new_events: list[dict], new_digest_groups: list[dict] | None) -> dict:
    """Merge new Claude results into existing JSONBin data.

    Merge rules:
    - Events: keep ALL existing events; add new events not already present by id;
      auto-expire events more than 2 days past their date unless manually_added.
    - Deleted tombstones (deleted:true): kept for 30 days so the dedup key blocks
      re-extraction from the same email, then expired.
    - DigestGroups: replaced only when new_digest_groups is not None (Saturday digest run);
      on all other days, existing groups are preserved unchanged.
    - lastScanned: always updated to current UTC timestamp.
    """
    cutoff = date.today() - timedelta(days=2)
    tombstone_cutoff = datetime.now(timezone.utc) - timedelta(days=_TOMBSTONE_DAYS)

    # Keep all existing events, expiring only old auto-generated ones.
    kept_events: list[dict] = []
    expired = 0
    for e in existing.get("events", []):
        # Deleted tombstones: keep for 30 days so dedup blocks re-extraction, then drop.
        if e.get("deleted"):
            try:
                deleted_at = datetime.fromisoformat(e.get("deleted_at", ""))
                if deleted_at < tombstone_cutoff:
                    expired += 1
                    continue
            except (ValueError, TypeError):
                expired += 1
                continue
            kept_events.append(e)
            continue
        if e.get("manually_added"):
            kept_events.append(e)
            continue
        event_date_str = e.get("date", "")
        try:
            event_date = date.fromisoformat(event_date_str)
            if event_date < cutoff:
                expired += 1
                continue
        except (ValueError, TypeError):
            pass
        kept_events.append(e)

    if expired:
        log.info("Auto-expired %d event(s) more than 2 days past their date", expired)

    # Composite key: (source_message_id, title) prevents re-adding events from emails
    # re-fetched by the 1-hour overlap buffer on consecutive scanner runs.
    existing_keys = {
        (e["source_message_id"], e["title"])
        for e in kept_events
        if e.get("source_message_id") and e.get("title")
    }
    existing_ids = {e["id"] for e in kept_events}

    added_events: list[dict] = []
    for e in new_events:
        msg_id = e.get("source_message_id")
        title = e.get("title")
        if msg_id and title and (msg_id, title) in existing_keys:
            continue
        if e["id"] in existing_ids:
            continue
        if e.get("manually_added"):
            added_events.append(e)
            continue
        event_date_str = e.get("date", "")
        try:
            event_date = date.fromisoformat(event_date_str)
            if event_date < cutoff:
                expired += 1
                continue
        except (ValueError, TypeError):
            pass
        added_events.append(e)

    return {
        "events": kept_events + added_events,
        "digestGroups": new_digest_groups if new_digest_groups is not None else existing.get("digestGroups", []),
        "lastScanned": datetime.now(timezone.utc).isoformat(),
    }


# ---------------------------------------------------------------------------
# Claude dedup pass
# ---------------------------------------------------------------------------

_DEDUP_PROMPT = """\
You are reviewing a list of family calendar events extracted from emails.
Some may be duplicates — the same event extracted from multiple emails, or the same
event mentioned in different school communications.

Two events are duplicates if they describe the same real-world event with:
- Similar title (same activity or event name)
- Same or very close date (within 3 days)
- Same or related source

For each group of duplicates, keep the BEST version:
1. Prefer undismissed over dismissed
2. Then highest priority
3. Then most complete notes and most specific title
Remove the rest.

Events:
{events_json}

Return ONLY a valid JSON object: {{"remove": ["id1", "id2", ...]}}
If there are no duplicates, return {{"remove": []}}
No explanation. No markdown.\
"""


def dedup_events(events: list[dict]) -> list[dict]:
    """Run a second Claude pass to remove duplicate events from the merged list.

    Manually added events are excluded and always kept. If the pass fails for
    any reason, returns the original list unchanged.
    """
    immune = [e for e in events if e.get("manually_added")]
    candidates = [e for e in events if not e.get("manually_added")]

    if len(candidates) < 2:
        log.info("Dedup pass skipped — fewer than 2 non-manual events")
        return events

    client = anthropic.Anthropic(api_key=ANTHROPIC_API_KEY)
    events_json = json.dumps(candidates, indent=2, ensure_ascii=False)
    prompt = _DEDUP_PROMPT.format(events_json=events_json)

    log.info("Running Claude dedup pass on %d event(s)...", len(candidates))
    try:
        message = client.messages.create(
            model="claude-sonnet-4-6",
            max_tokens=1024,
            messages=[{"role": "user", "content": prompt}],
        )
        raw = message.content[0].text
        result = _parse_claude_json(raw)

        valid_ids = {e["id"] for e in candidates}
        ids_to_remove = set(result.get("remove", [])) & valid_ids

        if not ids_to_remove:
            log.info("Dedup pass: no duplicates found")
            return events

        if len(ids_to_remove) >= len(candidates):
            log.warning(
                "Dedup pass wants to remove all %d candidates — skipping (safety check)",
                len(candidates),
            )
            return events

        kept = [e for e in candidates if e["id"] not in ids_to_remove]
        log.info("Dedup pass: removed %d duplicate(s)", len(candidates) - len(kept))
        return kept + immune

    except Exception as exc:
        log.warning("Dedup pass failed (%s) — keeping original event list", exc)
        return events


# ---------------------------------------------------------------------------
# Saturday digest email
# ---------------------------------------------------------------------------

def _monday_of_week(ref: date) -> date:
    """Return the Monday of the week containing ref."""
    return ref - timedelta(days=ref.weekday())


def _build_digest_html(events: list[dict], digest_groups: list[dict]) -> str:
    today = date.today()
    monday = _monday_of_week(today)
    cutoff = today + timedelta(days=_DIGEST_WINDOW_DAYS)
    week_str = monday.strftime("%B %-d, %Y")

    # --- Upcoming events: next 14 days, dateless always included ---
    upcoming: list[dict] = []
    for e in events:
        if e.get("dismissed"):
            continue
        event_date = e.get("date")
        if event_date:
            try:
                if date.fromisoformat(event_date) <= cutoff:
                    upcoming.append(e)
            except ValueError:
                pass
        else:
            upcoming.append(e)
    upcoming.sort(key=lambda e: e.get("date") or "9999-99-99")

    by_category: dict[str, list[dict]] = {}
    for e in upcoming:
        by_category.setdefault(e.get("category", "other"), []).append(e)

    events_parts: list[str] = []
    for cat in CATEGORIES:
        if cat not in by_category:
            continue
        meta = CATEGORIES[cat]
        color = meta["color"]
        icon = meta["icon"]
        cards = ""
        for ev in by_category[cat]:
            try:
                d = datetime.strptime(ev["date"], "%Y-%m-%d").date()
                date_str = d.strftime("%A, %B %-d")
            except (ValueError, KeyError, TypeError):
                date_str = ev.get("date") or "No date set"
            title = html.escape(ev.get("title", ""))
            source = html.escape(ev.get("source", ""))
            notes = ev.get("notes", "")
            notes_html = (
                f'<div style="font-size:13px;color:#555;margin-top:6px;">{html.escape(notes)}</div>'
                if notes else ""
            )
            cards += f"""
              <div style="border-left:3px solid {color};padding:10px 14px;margin-bottom:8px;background:#f8f9ff;border-radius:0 6px 6px 0;">
                <div style="font-weight:600;font-size:14px;color:#111;">{title}</div>
                <div style="font-size:12px;color:#888;margin-top:3px;">{date_str} &middot; {source}</div>
                {notes_html}
              </div>"""
        events_parts.append(f"""
          <div style="margin-bottom:20px;">
            <div style="margin-bottom:10px;">
              <span style="font-size:14px;">{icon}</span>
              <span style="font-size:11px;font-weight:700;letter-spacing:0.8px;color:{color};text-transform:uppercase;vertical-align:middle;margin-left:4px;">{cat}</span>
            </div>
            {cards}
          </div>""")

    events_section = "\n".join(events_parts) if events_parts else (
        f'<p style="color:#999;font-size:13px;margin:0;">Nothing on the calendar in the next {_DIGEST_WINDOW_DAYS} days.</p>'
    )

    # --- Digest groups ---
    groups_parts: list[str] = []
    for group in digest_groups:
        cat = group.get("category", "other")
        meta = CATEGORIES.get(cat, CATEGORIES["other"])
        color = meta["color"]
        icon = meta["icon"]
        source = html.escape(group.get("source", ""))
        bullets = "".join(
            f'<li style="margin-bottom:6px;">{html.escape(b["text"] if isinstance(b, dict) else b)}'
            + (f' <a href="{html.escape(b["link"])}" style="color:#6c8ebf;">↗</a>' if isinstance(b, dict) and b.get("link") else "")
            + "</li>"
            for b in group.get("bullets", [])
        )
        groups_parts.append(f"""
          <div style="margin-bottom:24px;">
            <div style="margin-bottom:10px;">
              <span style="font-size:14px;">{icon}</span>
              <span style="font-size:11px;font-weight:700;letter-spacing:0.8px;color:{color};text-transform:uppercase;vertical-align:middle;margin-left:4px;">{source}</span>
            </div>
            <ul style="margin:0;padding-left:18px;color:#333;font-size:13px;line-height:1.7;">
              {bullets}
            </ul>
          </div>""")

    groups_section = "\n".join(groups_parts) if groups_parts else (
        '<p style="color:#999;font-size:13px;margin:0;">No updates from your inbox this week.</p>'
    )

    return f"""<!DOCTYPE html>
<html lang="en">
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width,initial-scale=1">
</head>
<body style="margin:0;padding:0;background:#f0f2f5;font-family:-apple-system,BlinkMacSystemFont,'Segoe UI',Helvetica,Arial,sans-serif;">
  <div style="max-width:600px;margin:0 auto;padding:24px 16px;">

    <div style="background:#1a1a2e;border-radius:12px;padding:24px;margin-bottom:16px;text-align:center;">
      <div style="color:#fff;font-size:20px;font-weight:700;">&#x1F4CB; Family Inbox</div>
      <div style="color:#9090a8;font-size:13px;margin-top:6px;">Week of {week_str}</div>
    </div>

    <div style="background:#fff;border-radius:12px;padding:24px;margin-bottom:16px;">
      <div style="font-size:11px;font-weight:700;letter-spacing:1px;color:#bbb;text-transform:uppercase;margin-bottom:20px;">Coming Up &mdash; Next {_DIGEST_WINDOW_DAYS} Days</div>
      {events_section}
    </div>

    <div style="background:#fff;border-radius:12px;padding:24px;margin-bottom:16px;">
      <div style="font-size:11px;font-weight:700;letter-spacing:1px;color:#bbb;text-transform:uppercase;margin-bottom:20px;">This Week&#x2019;s Updates From Your Inbox</div>
      {groups_section}
    </div>

    <div style="text-align:center;color:#bbb;font-size:11px;padding:8px;">
      Family Inbox Intelligence &middot; Week of {week_str}
    </div>

  </div>
</body>
</html>"""


def _build_reminder_html(tomorrow_events: list[dict], tomorrow: date) -> str:
    tomorrow_str = tomorrow.strftime("%A, %B %-d")
    cards = ""
    for ev in tomorrow_events:
        cat = ev.get("category", "other")
        meta = CATEGORIES.get(cat, CATEGORIES["other"])
        color = meta["color"]
        icon = meta["icon"]
        title = html.escape(ev.get("title", ""))
        source = html.escape(ev.get("source", ""))
        notes = ev.get("notes", "")
        notes_html = (
            f'<div style="font-size:13px;color:#555;margin-top:8px;">{html.escape(notes)}</div>'
            if notes else ""
        )
        cards += f"""
      <div style="border-left:3px solid {color};padding:12px 16px;margin-bottom:12px;background:#f8f9ff;border-radius:0 8px 8px 0;">
        <div style="margin-bottom:4px;">
          <span style="font-size:13px;">{icon}</span>
          <span style="font-size:11px;font-weight:700;letter-spacing:0.5px;color:{color};text-transform:uppercase;vertical-align:middle;margin-left:4px;">{cat}</span>
        </div>
        <div style="font-weight:600;font-size:15px;color:#111;">{title}</div>
        <div style="font-size:12px;color:#888;margin-top:3px;">{source}</div>
        {notes_html}
      </div>"""

    return f"""<!DOCTYPE html>
<html lang="en">
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width,initial-scale=1">
</head>
<body style="margin:0;padding:0;background:#f0f2f5;font-family:-apple-system,BlinkMacSystemFont,'Segoe UI',Helvetica,Arial,sans-serif;">
  <div style="max-width:600px;margin:0 auto;padding:24px 16px;">

    <div style="background:#1a1a2e;border-radius:12px;padding:24px;margin-bottom:16px;text-align:center;">
      <div style="color:#9090a8;font-size:12px;font-weight:700;letter-spacing:1px;text-transform:uppercase;margin-bottom:8px;">Heads Up</div>
      <div style="color:#fff;font-size:20px;font-weight:700;">&#x1F4C5; Tomorrow &mdash; {tomorrow_str}</div>
    </div>

    <div style="background:#fff;border-radius:12px;padding:24px;margin-bottom:16px;">
      {cards}
    </div>

    <div style="text-align:center;color:#bbb;font-size:11px;padding:8px;">
      Family Inbox Intelligence
    </div>

  </div>
</body>
</html>"""


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
    body = _build_digest_html(events, digest_groups)

    msg = MIMEText(body, "html", "utf-8")
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


def send_reminder_email(events: list[dict], force: bool = False) -> None:
    """Send a day-before reminder for events happening tomorrow.

    Fires every day a scan runs. Skipped silently if nothing is tomorrow,
    unless force=True (sends even when empty, for SMTP testing).
    """
    tomorrow = date.today() + timedelta(days=1)
    tomorrow_events = [
        e for e in events
        if not e.get("dismissed") and e.get("date") == tomorrow.isoformat()
    ]

    if not tomorrow_events and not force:
        log.info("No events tomorrow (%s) — skipping reminder email", tomorrow.isoformat())
        return

    if not tomorrow_events:
        log.info("Force-sending reminder with no tomorrow events (SMTP test)")
        subject = f"📅 Tomorrow: nothing scheduled ({tomorrow.strftime('%B %-d')})"
        tomorrow_str = tomorrow.strftime("%A, %B %-d")
        body = f"""<!DOCTYPE html>
<html lang="en"><head><meta charset="utf-8"></head>
<body style="margin:0;padding:0;background:#f0f2f5;font-family:-apple-system,BlinkMacSystemFont,'Segoe UI',Helvetica,Arial,sans-serif;">
  <div style="max-width:600px;margin:0 auto;padding:24px 16px;">
    <div style="background:#1a1a2e;border-radius:12px;padding:24px;margin-bottom:16px;text-align:center;">
      <div style="color:#9090a8;font-size:12px;font-weight:700;letter-spacing:1px;text-transform:uppercase;margin-bottom:8px;">Heads Up</div>
      <div style="color:#fff;font-size:20px;font-weight:700;">&#x1F4C5; Tomorrow &mdash; {tomorrow_str}</div>
    </div>
    <div style="background:#fff;border-radius:12px;padding:24px;margin-bottom:16px;text-align:center;">
      <p style="color:#999;font-size:13px;margin:0;">Nothing scheduled for tomorrow.</p>
    </div>
    <div style="text-align:center;color:#bbb;font-size:11px;padding:8px;">Family Inbox Intelligence</div>
  </div>
</body></html>"""
    else:
        subject = (
            f"📅 Tomorrow: {tomorrow_events[0]['title']}"
            if len(tomorrow_events) == 1
            else f"📅 Tomorrow: {len(tomorrow_events)} events"
        )
        body = _build_reminder_html(tomorrow_events, tomorrow)

    msg = MIMEText(body, "html", "utf-8")
    msg["Subject"] = subject
    msg["From"] = FAMILY_INBOX_EMAIL
    msg["To"] = ", ".join(DIGEST_RECIPIENTS)

    log.info(
        "Sending reminder email (%d event(s) tomorrow) to: %s",
        len(tomorrow_events),
        ", ".join(DIGEST_RECIPIENTS),
    )
    with smtplib.SMTP("smtp.gmail.com", 587) as smtp:
        smtp.ehlo()
        smtp.starttls()
        smtp.login(FAMILY_INBOX_EMAIL, GMAIL_APP_PASSWORD)
        smtp.sendmail(FAMILY_INBOX_EMAIL, DIGEST_RECIPIENTS, msg.as_string())

    log.info("Reminder email sent — subject: %s", subject)


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
    """Smoke-test: authenticate, fetch emails using lastScanned, and print subjects."""
    log.info("=== Fetch test starting ===")
    service = get_gmail_service()
    data = read_jsonbin()
    last_scanned_str = data.get("lastScanned")
    last_scanned: datetime | None = None
    if last_scanned_str:
        try:
            last_scanned = datetime.fromisoformat(last_scanned_str)
            log.info("Using lastScanned cutoff: %s (with 1h overlap buffer)", last_scanned)
        except ValueError:
            log.warning("Could not parse lastScanned %r — using fallback window", last_scanned_str)
    else:
        log.info("No lastScanned found — using newer_than:%dd fallback", SCAN_DAYS_BACK)
    emails = fetch_emails(service, last_scanned=last_scanned)
    if not emails:
        log.info("No emails found in the current fetch window.")
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
    """Smoke-test: auth + fetch + Claude event extraction, print resulting JSON."""
    log.info("=== Analyze test starting ===")
    service = get_gmail_service()
    emails = fetch_emails(service)
    if not emails:
        log.info("No emails to analyze — forwarding a test email first is recommended.")
        return
    events = analyze_emails(emails)
    print(json.dumps(events, indent=2, ensure_ascii=False))
    log.info("=== Analyze test passed: %d event(s) ===", len(events))


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


_SENTINEL_PATH = Path.home() / "Desktop" / "family-inbox" / "last-run-date"


def main(days_back: int = SCAN_DAYS_BACK) -> None:
    args = set(sys.argv[1:])
    dry_run = "--dry-run" in args
    force_digest = "--send-digest" in args
    force_reminder = "--send-reminder" in args
    auto_mode = "--auto" in args

    # --auto: skip if already ran today (used by launchd RunAtLoad trigger)
    if auto_mode:
        today = date.today().isoformat()
        if _SENTINEL_PATH.exists() and _SENTINEL_PATH.read_text().strip() == today:
            log.info("Already ran today — skipping (--auto mode)")
            return

    log.info("=== Family Inbox Scanner starting ===%s", " (DRY RUN)" if dry_run else "")

    # Step 2: authenticate
    service = get_gmail_service()

    # Step 3: read existing JSONBin data (needed for lastScanned cutoff)
    existing = read_jsonbin()
    last_scanned: datetime | None = None
    last_scanned_str = existing.get("lastScanned")
    if last_scanned_str:
        try:
            last_scanned = datetime.fromisoformat(last_scanned_str)
        except ValueError:
            log.warning(
                "Could not parse lastScanned %r — falling back to %dd window",
                last_scanned_str,
                SCAN_DAYS_BACK,
            )

    # Step 4: fetch incremental emails (since last scan)
    emails = fetch_emails(service, last_scanned=last_scanned, days_back=days_back)

    # Step 5: extract events from new emails
    new_events: list[dict] = []
    if emails:
        new_events = analyze_emails(emails)
    else:
        log.info("No new emails found")

    # Step 5b: on Saturday, fetch the full week and generate a fresh digest
    today_name = date.today().strftime("%A")
    is_digest_day = force_digest or today_name == DIGEST_DAY
    new_digest_groups: list[dict] | None = None
    if is_digest_day:
        log.info("Digest day — fetching full week of emails for digest generation...")
        weekly_emails = fetch_emails(service, last_scanned=None, days_back=days_back)
        new_digest_groups = generate_digest_groups(weekly_emails)

    # Step 6: merge into existing data (digest groups unchanged on non-Saturday days)
    final_data = merge_data(existing, new_events, new_digest_groups)
    if new_events:
        final_data["events"] = dedup_events(final_data["events"])

    # Step 7: write (or dry-run print)
    if dry_run:
        log.info("DRY RUN — would write the following to JSONBin:")
        print(json.dumps(final_data, indent=2, ensure_ascii=False))
        log.info("=== Scan complete ===")
        return

    write_jsonbin(final_data)

    # Step 8: day-before reminder (fires every run)
    send_reminder_email(final_data["events"], force=force_reminder)

    # Step 9: Saturday digest email
    if is_digest_day:
        send_digest_email(
            final_data["events"],
            final_data.get("digestGroups", []),
            force=force_digest,
        )

    if auto_mode and not dry_run:
        _SENTINEL_PATH.parent.mkdir(parents=True, exist_ok=True)
        _SENTINEL_PATH.write_text(date.today().isoformat())

    log.info("=== Scan complete ===")


_SCOUTS_KEYWORDS = {"scout", "scouts", "beaver", "beavers", "cub", "cubs"}


def _reset_last_scanned():
    """Clear lastScanned in JSONBin so the next run falls back to SCAN_DAYS_BACK."""
    log.info("=== Resetting lastScanned ===")
    data = read_jsonbin()
    data["lastScanned"] = None
    write_jsonbin(data)
    log.info("lastScanned cleared — next run will use newer_than:%dd fallback", SCAN_DAYS_BACK)


def _wipe_and_rescan(days: int = SCAN_DAYS_BACK):
    """Wipe all events from JSONBin, then run a full scan over the past `days` days."""
    log.info("=== Wiping JSONBin ===")
    write_jsonbin(dict(_EMPTY_BIN))
    log.info("JSONBin cleared — running fresh scan (last %d days)", days)
    main(days_back=days)


def _test_dedup():
    """Smoke-test: read current events from JSONBin and run the dedup pass (read-only)."""
    log.info("=== Dedup test starting ===")
    data = read_jsonbin()
    events = data.get("events", [])
    log.info("Read %d event(s) from JSONBin", len(events))
    deduped = dedup_events(events)
    removed = len(events) - len(deduped)
    log.info("Dedup pass complete — %d duplicate(s) removed, %d kept", removed, len(deduped))
    print(json.dumps(deduped, indent=2, ensure_ascii=False))
    log.info("=== Dedup test passed ===")


def _test_reminder():
    """Preview tomorrow's reminder email body without sending (read-only)."""
    log.info("=== Reminder test starting ===")
    data = read_jsonbin()
    events = data.get("events", [])
    tomorrow = date.today() + timedelta(days=1)
    tomorrow_events = [
        e for e in events
        if not e.get("dismissed") and e.get("date") == tomorrow.isoformat()
    ]
    log.info(
        "Tomorrow (%s): %d event(s) would trigger a reminder",
        tomorrow.isoformat(),
        len(tomorrow_events),
    )
    for ev in tomorrow_events:
        log.info("  • %s (%s) — %s", ev.get("title"), ev.get("source"), ev.get("notes", ""))
    if not tomorrow_events:
        log.info("No reminder would fire tomorrow — use --send-reminder to force-send")
    log.info("=== Reminder test passed ===")


def _migrate_categories() -> None:
    """One-time migration: rename legacy categories in JSONBin.

    martial arts → GFT
    activities   → scouts  (if source mentions scouts/beavers/cubs)
    activities   → other   (everything else)
    """
    log.info("=== Category migration starting ===")
    data = read_jsonbin()
    events = data.get("events", [])
    changed = 0

    for event in events:
        cat = event.get("category", "")
        if cat == "martial arts":
            event["category"] = "GFT"
            changed += 1
            log.info("  %s → GFT  (%s)", event.get("title", "?"), event.get("source", ""))
        elif cat == "activities":
            source_words = set(re.split(r"\W+", event.get("source", "").lower()))
            new_cat = "scouts" if source_words & _SCOUTS_KEYWORDS else "other"
            event["category"] = new_cat
            changed += 1
            log.info("  %s → %s  (%s)", event.get("title", "?"), new_cat, event.get("source", ""))

    if changed:
        write_jsonbin(data)
        log.info("Migration complete — updated %d event(s)", changed)
    else:
        log.info("Migration complete — nothing to update")
    log.info("=== Category migration done ===")


if __name__ == "__main__":
    # Parse optional --days N argument
    _days_back = SCAN_DAYS_BACK
    if "--days" in sys.argv:
        _idx = sys.argv.index("--days")
        try:
            _days_back = int(sys.argv[_idx + 1])
        except (IndexError, ValueError):
            log.error("--days requires an integer argument e.g. --days 14")
            sys.exit(1)

    if "--test-auth" in sys.argv:
        _test_auth()
    elif "--test-fetch" in sys.argv:
        _test_fetch()
    elif "--test-analyze" in sys.argv:
        _test_analyze()
    elif "--test-jsonbin" in sys.argv:
        _test_jsonbin()
    elif "--reset-last-scanned" in sys.argv:
        _reset_last_scanned()
    elif "--wipe-and-rescan" in sys.argv:
        _wipe_and_rescan(days=_days_back)
    elif "--test-dedup" in sys.argv:
        _test_dedup()
    elif "--test-reminder" in sys.argv:
        _test_reminder()
    elif "--migrate-categories" in sys.argv:
        _migrate_categories()
    else:
        main(days_back=_days_back)