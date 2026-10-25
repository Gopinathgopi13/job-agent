"""Portal sign-in details.

Only the email is ever persisted, to `.env` (comma-separated,
most-recently-used last): NAUKRI_EMAILS or HIRIST_EMAILS.
The password is prompted every run and never written anywhere — not to
.env, not to the profile, not to the logs.
"""

import os
from getpass import getpass

from dotenv import find_dotenv, load_dotenv, set_key

from ..automation.portals import PORTALS, normalize_portal
from .prompts import ask_required, choose
from .theme import console

_ENV_PATH = find_dotenv(usecwd=True)
if _ENV_PATH:
    load_dotenv(_ENV_PATH)

_NEW_EMAIL = "__new_email__"


def _email_env(portal):
    return PORTALS[normalize_portal(portal)]["email_env"]


def _label(portal):
    return PORTALS[normalize_portal(portal)]["label"]


def saved_emails(portal="naukri"):
    raw = os.getenv(_email_env(portal), "")
    emails = []
    for part in raw.split(","):
        part = part.strip()
        if part and part not in emails:
            emails.append(part)
    return emails


def remember_email(email, portal="naukri"):
    global _ENV_PATH
    emails = saved_emails(portal)
    if email in emails:
        emails.remove(email)
    emails.append(email)

    if not _ENV_PATH:
        _ENV_PATH = os.path.join(os.getcwd(), ".env")
    if not os.path.exists(_ENV_PATH):
        open(_ENV_PATH, "a", encoding="utf-8").close()

    key = _email_env(portal)
    joined = ",".join(emails)
    set_key(_ENV_PATH, key, joined, quote_mode="never")
    os.environ[key] = joined


def _prompt_new_email(portal="naukri"):
    email = ask_required(f"{_label(portal)} email")
    remember_email(email, portal)
    return email


def resolve_email(cli_email=None, portal="naukri"):
    if cli_email:
        remember_email(cli_email, portal)
        return cli_email

    known = saved_emails(portal)
    if not known:
        return _prompt_new_email(portal)

    options = [(email, email) for email in known]
    options.append(("＋ Use a different email", _NEW_EMAIL))

    picked = choose(f"{_label(portal)} account:", options)
    return _prompt_new_email(portal) if picked == _NEW_EMAIL else picked


def resolve_password(portal="naukri"):
    console.print(
        f"[gold1]🔑 {_label(portal)} password[/gold1] [grey50](never saved)[/grey50]: ",
        end="",
    )
    return getpass("")
