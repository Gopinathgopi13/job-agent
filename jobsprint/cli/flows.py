"""The three things the CLI actually does: refresh the knowledge base,
run an auto-apply session, and review what the bot has learned.
"""

import json

from .. import paths
from ..automation.portals import PORTALS, create_bot, normalize_portal
from ..knowledge.store import KBStore
from ..preferences.profile import CONFIG_PATH, ProfileStore, job_roles
from ..preferences.store import PreferencesStore
from ..resume.parser import extract_skills_from_path
from ..tracker.excel_writer import ExcelTracker
from .credentials import resolve_email, resolve_password
from .prompts import ask_experience, ask_int, ask_required, ask_required_int, ask_text, choose
from .questions import TerminalQuestionPrompt
from .theme import (ACCENT, BAD, BRAND, MUTED, OK, WARN, alert, attach_rich_logging,
                    card, console, listing, note, result, step)

TOTAL_STEPS = 3

# The fields the pre-flight editor offers — the ones an answer most commonly
# goes stale between runs. The rest of config.json is still there to hand-edit,
# this just covers the common case without a bigger, generic JSON editor.
EDITABLE_CONFIG_FIELDS = ["Total experience", "Notice period", "Current CTC", "Expected salary"]


def _load_profile():
    return ProfileStore().load()


def _read_config_raw():
    try:
        with open(CONFIG_PATH, encoding="utf-8") as f:
            data = json.load(f)
    except (OSError, ValueError):
        return {}
    return data if isinstance(data, dict) else {}


def _edit_config_answers():
    """Let the user tweak config.json's most-likely-to-change fields in place,
    without leaving the terminal to hunt down the file."""
    done = "__done__"
    while True:
        data = _read_config_raw()
        options = [
            (f"{field}: {data.get(field) or '—'}", field) for field in EDITABLE_CONFIG_FIELDS
        ]
        options.append(("Done editing", done))

        field = choose("Edit config.json:", options)
        if field == done:
            return

        updated = ask_text(field, default=str(data.get(field, "")))
        data[field] = updated
        with open(CONFIG_PATH, "w", encoding="utf-8") as f:
            json.dump(data, f, indent=4)
        note(f"Saved {field} to config.json.", OK)


def refresh_knowledge_base(quiet=False):
    """Seed/refresh the deterministic question→answer store from the profile.

    Idempotent and offline — no Naukri login involved — so an apply run can
    just do it every time instead of asking whether to.
    """
    profile = _load_profile()
    store = KBStore(paths.DB_PATH, profile)
    try:
        total = len(store.list_entries())
    finally:
        store.close()

    if not quiet:
        result(
            f"{total} question → answer entries ready",
            "Knowledge base refreshed",
            border=OK,
            detail=str(paths.DB_PATH),
        )
    return total


# ── commands ───────────────────────────────────────────────────────

def run_train():
    step(1, 1, "Knowledge base", "🧠")
    with console.status(f"[{ACCENT}]Rebuilding from your profile…", spinner="dots"):
        total = refresh_knowledge_base(quiet=True)
    result(
        f"{total} question → answer entries ready",
        "Knowledge base refreshed",
        border=OK,
        detail=str(paths.DB_PATH),
    )


def run_apply(args):
    prefs_store = PreferencesStore()
    returning = prefs_store.exists()
    prefs = prefs_store.load()

    with console.status(f"[{ACCENT}]Refreshing the knowledge base…", spinner="dots"):
        entries = refresh_knowledge_base(quiet=True)
    note(f"  Knowledge base ready — {entries} answers on file.")

    # ── 1. who ─────────────────────────────────────────────────────
    step(1, TOTAL_STEPS, "Sign in", "👤")
    portal = normalize_portal(
        args.portal or choose("Job portal:", [(info["label"], key) for key, info in PORTALS.items()])
    )
    email = resolve_email(args.email, portal)
    password = resolve_password(portal)

    # ── 2. what ────────────────────────────────────────────────────
    step(2, TOTAL_STEPS, "What to search for", "🎯")

    # Roles come from config.json's "Job roles" when set; the prompt is only
    # the fallback for an install that hasn't filled that in yet.
    roles = job_roles(_load_profile())
    if roles:
        note(f"  Roles from config.json: {', '.join(roles)}")
    else:
        roles = [
            ask_text("Job role", default=prefs["role"]) if returning else ask_required("Job role")
        ]
    role = roles[0]
    experience = ask_experience(default_years=prefs["experience"])

    location_default = prefs["location"] or "Any"
    location_input = ask_text("Location", default=location_default, hint="'Any' searches everywhere")
    location = "" if location_input.strip().lower() in ("", "any") else location_input.strip()

    target = args.jobs or (
        ask_int("Jobs to apply to", default=prefs["jobs_target"]) if returning
        else ask_required_int("Jobs to apply to")
    )

    prefs_store.save({
        "role": role, "experience": experience,
        "location": location, "jobs_target": target,
    })

    profile = _load_profile()
    resume = args.resume or profile.get("Resume path", "")

    # ── 3. go ──────────────────────────────────────────────────────
    step(3, TOTAL_STEPS, "Applying", "🚀")
    while True:
        rows = [
            ("Roles" if len(roles) > 1 else "Role", ", ".join(roles)),
            ("Experience", "Fresher" if experience == 0 else f"{experience} year{'s' if experience > 1 else ''}"),
            ("Location", location or "Anywhere"),
            ("Target", f"{target} application{'s' if target != 1 else ''}"),
            ("Portal", PORTALS[portal]["label"]),
            ("Account", email),
            ("", ""),
            ("Total experience", f"{profile.get('Total experience') or '—'} yrs"),
            ("Notice period", f"{profile.get('Notice period') or '—'} days"),
            ("Current CTC", profile.get("Current CTC") or "—"),
            ("Expected CTC", profile.get("Expected salary") or "—"),
        ]
        card(
            rows,
            title="This session",
            border=BRAND,
            footer=(
                "Total experience, Notice period, Current CTC and Expected salary come from "
                "config.json — please change them there (or via ↓ Edit config.json below) if "
                "anything looks stale. Unknown questions are asked once, then remembered."
            ),
        )

        action = choose("Ready to apply?", [
            ("Continue", "continue"),
            ("↓ Edit config.json", "edit"),
        ])
        if action == "continue":
            break
        _edit_config_answers()
        profile = _load_profile()
        resume = args.resume or profile.get("Resume path", "")

    tracker = ExcelTracker(paths.EXCEL_PATH)
    label = PORTALS[portal]["label"]
    bot = create_bot(
        portal,
        email=email,
        password=password,
        username=email,
        number=target,
        user_info=profile,
        resume_path=resume,
        pending_registry=TerminalQuestionPrompt(),
        on_application_recorded=tracker.append_row,
    )
    bot.candidate_skills |= set(extract_skills_from_path(resume))
    attach_rich_logging(bot.logger)

    bot.init_browser()
    if not bot.login():
        alert(
            f"Couldn't confirm the sign-in. Check the password, and whether {label} asked for "
            "an OTP or captcha in the browser, then try again.",
            "Login failed",
        )
        bot.shutdown()
        return

    try:
        # Roles run one after another in the same browser session; the target
        # is shared, so later roles only run if earlier ones fell short.
        for role in roles:
            if bot.applied_count >= target or bot.quota_exceeded or bot.stop_event.is_set():
                break
            if len(roles) > 1:
                note(f"  Searching: {role}", ACCENT)
            bot.apply_for_role(role, experience, location, prefs["job_age_days"])
    finally:
        bot.shutdown()
        try:
            tracker.add_daily_summary(bot)
        except Exception as e:
            note(f"Couldn't update the Daily Summary sheet: {e}")

    applied = bot.applied_count
    needs_input = getattr(bot, "needs_input_count", 0)
    company_site = sum(1 for r in bot.records if r["application_type"] == "external")

    _print_session_report(bot.records)

    if bot.quota_exceeded:
        alert(
            f"{label} stopped the session early — the apply-click cap was hit "
            "or the site refused further applications. Try again later.",
            "Daily apply limit reached",
            border=WARN,
        )

    details = [f"{company_site} were company-site jobs — opened only, NOT applied"] if company_site else []
    if needs_input:
        details.append(f"{needs_input} skipped needing an answer")
    if bot.ignored_count:
        details.append(f"{bot.ignored_count} ignored by your skip lists in config.json")
    result(
        f"{applied} of {target} applications submitted on {label}",
        "Session complete" if applied else "Nothing applied to",
        border=OK if applied else WARN,
        detail="\n".join(details) or None,
    )


def _print_session_report(records):
    """One row per job this session touched, so it's clear which ones were
    really applied to on Naukri and which only had their careers page opened."""
    if not records:
        return

    def kind(r):
        if r["application_type"] == "external":
            return f"[{BAD}]✗ Company site[/{BAD}]"
        if r["status"] == "Submitted":
            return f"[{OK}]✓ Applied[/{OK}]"
        return f"[{WARN}]? Apply (unconfirmed)[/{WARN}]"

    rows = [
        (
            i,
            kind(r),
            r["company"] or "—",
            (r["job_role"] or "—")[:40],
            r["external_url"] if r["application_type"] == "external" and r["external_url"] else r["naukri_url"],
        )
        for i, r in enumerate(records, start=1)
    ]
    console.print()
    listing(
        [("#", "right"), ("Result", "left"), ("Company", "left"), ("Role", "left"), ("Link", "left")],
        rows,
        title="Session report",
    )
    note("✓ applied on the portal · ? submitted but no confirmation seen · ✗ careers page only, NOT applied")
    note(f"Also saved to {paths.EXCEL_PATH}")


def run_edit_answers():
    step(1, 1, "Learned answers", "📚")

    store = KBStore(paths.DB_PATH, _load_profile())
    done = "__done__"
    try:
        while True:
            entries = store.list_entries(source="user_taught")
            if not entries:
                note("Nothing learned yet — answers you give during a run show up here.")
                return

            def label(entry):
                question = entry["canonical_question"]
                answer = entry["answer"]
                question = question if len(question) <= 55 else question[:52] + "…"
                answer = answer if len(answer) <= 28 else answer[:25] + "…"
                return f"{question}   →   {answer}"

            options = [(label(e), e["id"]) for e in entries]
            options.append(("Done", done))

            entry_id = choose(f"{len(entries)} learned answer(s):", options)
            if entry_id == done:
                return

            entry = store.get_entry(entry_id)
            card(
                [("Question", entry["canonical_question"]), ("Answer", entry["answer"])],
                title="Learned answer",
                border=ACCENT,
            )

            action = choose("What would you like to do?", [
                ("Edit the answer", "edit"),
                ("Delete it", "delete"),
                ("Back", "back"),
            ])

            if action == "edit":
                updated = ask_text("New answer", default=entry["answer"])
                if updated and updated != entry["answer"]:
                    store.update_entry(entry_id, answer=updated)
                    note("Updated — used from your next application onward.", OK)
            elif action == "delete":
                store.delete_entry(entry_id)
                note("Deleted.", WARN)
    finally:
        store.close()


def show_usage():
    listing(
        [("Command", "left"), ("What it does", "left")],
        [
            ("jobsprint.bat  /  ./jobsprint.sh", "One click: refresh, sign in, apply"),
            ("python -m jobsprint --apply", "Same thing, from an activated venv"),
            ("python -m jobsprint --apply --portal hirist", "Apply on Hirist instead of Naukri"),
            ("python -m jobsprint --apply --jobs 25", "Skip the 'how many' question"),
            ("python -m jobsprint --train", "Rebuild answers from config.json"),
            ("python -m jobsprint --edit-answers", "Review or fix what it has learned"),
        ],
        title="What you can run",
    )
    console.print()
    note("Edit config.json to change the answers it fills forms with.")
    note("Add -h for the full option list.")
    console.print()
