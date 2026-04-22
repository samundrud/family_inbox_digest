from __future__ import annotations

import os
from pathlib import Path

from dotenv import load_dotenv

load_dotenv(Path(__file__).parent / ".env")

# --- Scanner behaviour ---
SCAN_DAYS_BACK = 7
URGENCY_THRESHOLD_DAYS = 3
DIGEST_DAY = "Saturday"

# --- Loaded from .env ---
DIGEST_RECIPIENTS: list[str] = [
    addr.strip()
    for addr in os.environ["DIGEST_RECIPIENTS"].split(",")
    if addr.strip()
]
FAMILY_INBOX_EMAIL: str = os.environ["FAMILY_INBOX_EMAIL"]
GMAIL_APP_PASSWORD: str = os.environ["GMAIL_APP_PASSWORD"]
ANTHROPIC_API_KEY: str = os.environ["ANTHROPIC_API_KEY"]
JSONBIN_BIN_ID: str = os.environ["JSONBIN_BIN_ID"]
JSONBIN_API_KEY: str = os.environ["JSONBIN_API_KEY"]
ALLOWED_FORWARDERS: set[str] = {
    addr.strip().lower()
    for addr in os.environ["ALLOWED_FORWARDERS"].split(",")
    if addr.strip()
}
FAMILY_CONTEXT: str = os.environ["FAMILY_CONTEXT"]

# --- Category metadata (used by scanner email body and frontend) ---
CATEGORIES: dict[str, dict[str, str]] = {
    "school": {
        "color": "#60a5fa",
        "dot": "#60a5fa",
        "icon": "🏫",
        "bg": "#162340",
    },
    "daycare": {
        "color": "#4ade80",
        "dot": "#4ade80",
        "icon": "🌻",
        "bg": "#12301e",
    },
    "scouts": {
        "color": "#f87171",
        "dot": "#f87171",
        "icon": "🎯",
        "bg": "#261414",
    },
    "soccer": {
        "color": "#f0c040",
        "dot": "#f0c040",
        "icon": "⚽",
        "bg": "#2e1e00",
    },
    "GFT": {
        "color": "#c084fc",
        "dot": "#c084fc",
        "icon": "🥋",
        "bg": "#221230",
    },
    "other": {
        "color": "#9090a8",
        "dot": "#9090a8",
        "icon": "📬",
        "bg": "#222230",
    },
}