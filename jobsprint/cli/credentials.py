"""Naukri sign-in details.

Only the email is ever persisted, to `.env`'s NAUKRI_EMAILS (comma-separated,
most-recently-used last). The password is prompted every run and never
written anywhere — not to .env, not to the profile, not to the logs.
"""

import os
from getpass import getpass

from dotenv import find_dotenv, load_dotenv, set_key

from .prompts import ask_required, choose
from .theme import console

_ENV_PATH = find_dotenv(usecwd=True)
if _ENV_PATH:
    load_dotenv(_ENV_PATH)

_NEW_EMAIL = "__new_email__"


def saved_emails():
    raw = os.getenv("NAUKRI_EMAILS", "")
    emails = []
    for part in raw.split(","):
        part = part.strip()
        if part and part not in emails:
            emails.append(part)
    return emails


def remember_email(email):
    global _ENV_PATH
    emails = saved_emails()
    if email in emails:
        emails.remove(email)
    emails.append(email)

    if not _ENV_PATH:
        _ENV_PATH = os.path.join(os.getcwd(), ".env")
    if not os.path.exists(_ENV_PATH):
        open(_ENV_PATH, "a", encoding="utf-8").close()

    joined = ",".join(emails)
    set_key(_ENV_PATH, "NAUKRI_EMAILS", joined, quote_mode="never")
    os.environ["NAUKRI_EMAILS"] = joined


def _prompt_new_email():
    email = ask_required("Naukri email")
    remember_email(email)
    return email


def resolve_email(cli_email=None):
    if cli_email:
        remember_email(cli_email)
        return cli_email

    known = saved_emails()
    if not known:
        return _prompt_new_email()

    options = [(email, email) for email in known]
    options.append(("＋ Use a different email", _NEW_EMAIL))

    picked = choose("Naukri account:", options)
    return _prompt_new_email() if picked == _NEW_EMAIL else picked


def resolve_password():
    console.print("[gold1]🔑 Naukri password[/gold1] [grey50](never saved)[/grey50]: ", end="")
    return getpass("")
