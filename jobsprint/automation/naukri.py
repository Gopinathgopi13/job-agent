import time
import re
import os
import random
import json
import logging
import threading
from datetime import datetime, timedelta
from urllib.parse import urlencode
from playwright.sync_api import sync_playwright, expect, TimeoutError as PlaywrightTimeoutError
from rapidfuzz import fuzz, process

from .. import paths
from .common import build_record, skip_reason
from ..knowledge import skills
from ..knowledge.store import KBStore
from ..knowledge.matcher import KBMatcher, AUTO, CONFIRM, ASK
from ..resume.matcher import score_job, parse_candidate_years, parse_experience_years

# ─────────────────────────── helpers ────────────────────────────

class _EventBusLogHandler(logging.Handler):
    """Forwards every log record onto the EventBus as a `log_line` event,
    so the desktop dashboard's live log gets everything the session log
    file gets, with no need to duplicate every self.logger.info() call."""

    def __init__(self, event_bus):
        super().__init__()
        self.event_bus = event_bus

    def emit(self, record):
        try:
            self.event_bus.publish("log_line", text=self.format(record))
        except Exception:
            pass


def setup_logger(name, log_file=None, level=logging.INFO, event_bus=None):
    logger = logging.getLogger(name)
    logger.setLevel(level)
    if logger.handlers:
        return logger
    fmt = logging.Formatter('[%(asctime)s] %(levelname)s - %(message)s', datefmt='%Y-%m-%d %H:%M:%S')
    ch = logging.StreamHandler()
    ch.setFormatter(fmt)
    logger.addHandler(ch)
    if log_file:
        os.makedirs(os.path.dirname(log_file), exist_ok=True)
        fh = logging.FileHandler(log_file, encoding="utf-8")
        fh.setFormatter(fmt)
        logger.addHandler(fh)
    if event_bus:
        ebh = _EventBusLogHandler(event_bus)
        ebh.setFormatter(fmt)
        logger.addHandler(ebh)
    return logger


def human_delay(min_ms=500, max_ms=2000):
    time.sleep(random.uniform(min_ms / 1000, max_ms / 1000))


_YES_WORDS = {"yes", "y", "yeah", "yep", "true", "yes.", "sure"}
_NO_WORDS = {"no", "n", "nope", "false", "no.", "none"}

# Yes/No screening questions where the honest default is No: history with
# the hiring company, conflicts of interest, legal/disciplinary records.
# Defaulting these to Yes misrepresents the candidate.
_NO_DEFAULT_PATTERNS = [re.compile(p, re.I) for p in (
    r"\b(previously|formerly|ever|already)\b.{0,40}\b(employed|worked|work|interviewed|applied)\b",
    r"\b(employed|worked)\b.{0,30}\b(by|for|with|at)\b.{0,40}\b(before|previously|in the past)\b",
    r"\b(received|had|got)\b.{0,20}\boffer\b",
    r"\b(former|ex[- ]?)\s*employee\b",
    r"\b(relative|family member|related to|friend)s?\b.{0,40}\b(work|employ|employee)",
    r"\bconflict of interest\b",
    r"\bnon[- ]?(compete|solicit)",
    r"\b(convicted|criminal|arrested|felony|pending (case|litigation))\b",
    r"\b(terminated|dismissed|fired|blacklisted)\b",
    r"\b(government|public) (official|employee|servant)\b",
)]


# ─────────────────────── chatbot agent ──────────────────────────

class ChatbotAgent:
    def __init__(self, page, username, user_info=None, logger=None,
                 pending_registry=None, event_bus=None):
        self.page = page
        self.username = username
        self.user_info = user_info or {}
        self.logger = logger or setup_logger('ChatbotAgent')
        self.store = KBStore(paths.DB_PATH, self.user_info)
        self.matcher = KBMatcher(self.store, self.user_info)
        # Wired in once pause/resume plumbing exists (workers/pending_question.py).
        # Until then, CONFIRM/ASK decisions are logged and the job is skipped —
        # the bot must never guess an answer it isn't confident about.
        self.pending_registry = pending_registry
        self.event_bus = event_bus

    # ── matching helpers ──────────────────────────────────────

    @staticmethod
    def _is_boolean_pool(pool):
        """True when the options are just some spelling of Yes and No."""
        words = {o.strip().lower() for o in pool}
        return bool(words) and words <= (_YES_WORDS | _NO_WORDS)

    def _best_match(self, target, options):
        # Filter out null-like options when we have a meaningful answer
        _null = {'none', 'n/a', 'not applicable', 'nil', 'na', '-'}
        valid = [o for o in options if o.strip().lower() not in _null]
        pool = valid if valid else options

        # An exact option wins outright. Matters most for Yes/No: fuzzy
        # scoring on two-to-three letter strings is noisy enough that "No"
        # could out-score "Yes" against an option list containing both.
        t = target.strip()
        for opt in pool:
            if opt.strip().lower() == t.lower():
                return opt

        # A number offered a Yes/No choice. Stripping question-frame words
        # makes "Do you have experience in Docker?" and "Experience in Docker"
        # normalise to the same text, so the knowledge base can legitimately
        # return a year count for what is really a yes/no question. The option
        # list is what disambiguates: any experience at all means Yes.
        number = re.match(r"^\s*(\d+(?:\.\d+)?)", t)
        if number and self._is_boolean_pool(pool):
            wanted = _YES_WORDS if float(number.group(1)) > 0 else _NO_WORDS
            for opt in pool:
                if opt.strip().lower() in wanted:
                    return opt

        # Numeric answers ("4", "15", "9 LPA") against numeric options, which
        # are usually buckets rather than exact values: "3-5 years", "5+",
        # "5-10 LPA". Match the bucket that actually contains the number
        # instead of fuzzy-matching the text, which would score every "… LPA"
        # option alike and pick whichever came first.
        if number:
            value = float(number.group(1))

            for opt in pool:
                if opt.strip() == t or number.group(1) in opt.split():
                    return opt

            containing, nearest = [], []
            for opt in pool:
                found = [float(n) for n in re.findall(r"\d+(?:\.\d+)?", opt)]
                if not found:
                    continue
                low = found[0]
                if len(found) >= 2 and low <= value <= found[1]:
                    containing.append((low, opt))
                elif ("+" in opt or "above" in opt.lower()) and value >= low:
                    containing.append((low, opt))
                nearest.append((min(abs(n - value) for n in found), opt))

            if containing:
                # Highest lower bound = the tightest bucket around the value,
                # so 5 prefers "5+ years" over "3-5 years".
                return max(containing, key=lambda pair: pair[0])[1]
            if nearest:
                return min(nearest, key=lambda pair: pair[0])[1]

        best = process.extractOne(target, pool, scorer=fuzz.token_set_ratio)
        return best[0] if best else pool[0]

    def _resolve_question(self, question, job_ctx=None, options=None):
        """Returns an answer string, or None if the bot must not guess.

        `options` is the actual on-page choice list (radio/checkbox labels,
        or a dropdown's option text) when the widget offers one, so a
        human asked to answer can pick from real options instead of typing
        free text, and a Yes/No widget can be defaulted without asking.

        Logs every attempt to kb_question_log regardless of outcome — this
        log *is* the learned-Q&A history surfaced in the UI.
        """
        # "Years of experience in <tool>" is asked about whatever the job spec
        # happens to list, so it's resolved from the question itself rather
        # than hoping a per-tool entry exists. This runs ahead of the fuzzy
        # matcher on purpose: matching alone would answer "Experience in
        # Golang" with an unrelated skill's number at CONFIRM confidence.
        skill_years = skills.answer_for(question, self.user_info)
        if skill_years is not None:
            self.logger.info(f"  A: {skill_years}  (experience)")
            self.store.log_question(question, None, 100.0, 'auto_skill', skill_years, job_ctx)
            return skill_years

        result = self.matcher.match(question)

        if result.decision == AUTO:
            self.store.log_question(question, result.entry["id"], result.score,
                                     'auto', result.answer, job_ctx)
            return result.answer

        # A Yes/No widget the knowledge base isn't confident about is
        # answered Yes by default instead of pausing for a human — these
        # are almost always screening questions ("Are you ok with a C2H
        # role?") that a job seeker answers Yes to anyway, and pausing
        # every application on one defeats the point of auto-apply. This
        # only kicks in when nothing better is already known (AUTO above
        # already returned); it never overrides a taught or matched answer.
        # Questions about prior history with the employer, conflicts or
        # records flip the default to No — "Yes" there is a false claim.
        if options and self._is_boolean_pool(options):
            negative = any(p.search(question) for p in _NO_DEFAULT_PATTERNS)
            wanted = _NO_WORDS if negative else _YES_WORDS
            answer = next((o for o in options if o.strip().lower() in wanted), options[0])
            self.logger.info(f"  Yes/No question, no confident match — defaulting to {answer!r}")
            self.store.log_question(question, result.entry["id"] if result.entry else None,
                                     result.score, 'auto_default', answer, job_ctx)
            return answer

        if self.pending_registry is not None:
            answer = self.pending_registry.submit(
                question=question, candidates=result.candidates,
                suggested_answer=result.answer, job_ctx=job_ctx, options=options,
            )
            if answer is not None:
                if result.decision == CONFIRM and answer == result.answer:
                    self.matcher.accept_confirm(result)
                    self.store.log_question(question, result.entry["id"], result.score,
                                             'confirmed', answer, job_ctx)
                else:
                    entry = self.matcher.teach(question, answer)
                    self.store.log_question(question, entry["id"], result.score,
                                             'user_taught', answer, job_ctx)
                    if self.event_bus:
                        self.event_bus.publish("question_learned", tag=entry["tag"], question=question)
                return answer
            self.store.log_question(question, result.entry["id"] if result.entry else None,
                                     result.score, 'timeout', None, job_ctx)
            return None

        # No pause/resume channel wired yet — never guess, just log + bail.
        self.logger.warning(
            f"  Unknown/uncertain question with no pause channel wired — skipping: {question!r}"
        )
        self.store.log_question(question, result.entry["id"] if result.entry else None,
                                 result.score, 'skipped', None, job_ctx)
        return None

    # ── human-like typing ─────────────────────────────────────

    def _type(self, locator, text):
        for ch in text:
            locator.type(ch, delay=random.randint(70, 180))

    # ── option handling ───────────────────────────────────────

    @staticmethod
    def _option_label(element):
        """The text a human reads next to a radio/checkbox.

        Tries, in order: the <label for=...> that points at it, an enclosing
        <label>, the element's own value/aria-label, and finally its id — so
        there is always something meaningful to match an answer against.
        """
        try:
            label = element.evaluate(
                """el => {
                    const byFor = el.id
                        ? document.querySelector('label[for="' + CSS.escape(el.id) + '"]')
                        : null;
                    const wrapping = el.closest('label');
                    return (
                        (byFor && byFor.innerText) ||
                        (wrapping && wrapping.innerText) ||
                        el.getAttribute('aria-label') ||
                        el.value ||
                        el.id ||
                        ''
                    ).trim();
                }"""
            )
        except Exception:
            label = ""
        if label:
            return label
        try:
            return element.evaluate("el => el.id") or ""
        except Exception:
            return ""

    def _click_option(self, element):
        """Click a radio/checkbox via its label where possible — Naukri hides
        the real input behind a styled label, so clicking the input itself is
        often intercepted."""
        try:
            element_id = element.evaluate("el => el.id")
        except Exception:
            element_id = None
        if element_id:
            label = self.page.locator(f'label[for="{element_id}"]')
            try:
                if label.count() > 0:
                    label.first.click(force=True, timeout=5000)
                    return
            except Exception:
                pass
        element.click(force=True)

    # ── chatbot form handler ──────────────────────────────────

    def classify_new_question(self, job_ctx=None):
        page = self.page
        try:
            cbcn = page.wait_for_selector(".chatbot_MessageContainer", timeout=4000)
            human_delay(1500, 2500)

            while cbcn:
                q_el = page.locator(".botMsg").last
                page.wait_for_timeout(800)
                question = q_el.inner_text().strip()
                self.logger.info(f"  Q: {question}")

                # Once the chatbot's closing message lands ("Thank you for your
                # responses."), Naukri tears the form down and navigates on.
                # `cbcn` is an ElementHandle into that now-destroyed frame, so
                # probing it raises "Protocol error (DOM.describeNode): Cannot
                # find context with specified id". That's the flow finishing
                # normally, not a failure — treat it as completion.
                try:
                    checkboxes   = cbcn.query_selector_all('input[type="checkbox"]')
                    radios       = cbcn.query_selector_all('input[type="radio"]')
                    text_input   = page.locator('.chatbot_MessageContainer .textArea')
                    chip         = page.query_selector('.chatbot_MessageContainer .chipsContainer .chatbot_Chip')
                    suggs        = cbcn.query_selector_all('.ssc__heading')
                    dob          = cbcn.query_selector(".dob__container")
                    dropdown     = cbcn.query_selector("select")
                    text_visible = text_input.is_visible()
                except Exception:
                    self.logger.info("  Chatbot form closed — flow complete")
                    return {"response": "chatbot_complete"}

                if not (checkboxes or radios or chip or suggs or dob or dropdown or text_visible):
                    # A closing statement with nothing left to fill in — the
                    # chatbot flow is done, not a question needing an answer.
                    self.logger.info("  Chatbot flow complete — nothing further to fill in")
                    return {"response": "chatbot_complete"}

                option_labels = None
                if radios or checkboxes:
                    option_labels = [self._option_label(el) for el in (radios or checkboxes)]
                elif dropdown:
                    option_labels = page.eval_on_selector_all(
                        '.chatbot_MessageContainer select option',
                        'els => els.map(e => e.innerText)'
                    )

                answer = self._resolve_question(question, job_ctx=job_ctx, options=option_labels)
                if answer is None:
                    self.logger.warning("  No safe answer available — aborting this application")
                    return {"response": "needs_input", "question": question}
                self.logger.info(f"  A: {answer}")

                if chip:
                    chip.click()
                    human_delay(400, 800)
                    continue

                if radios or checkboxes:
                    buttons = radios or checkboxes
                    # Match on what the option *says*, not on its element id.
                    # Naukri's ids are not the human labels, so scoring an
                    # answer like "4" against them was meaningless and kept
                    # landing on the first option — which is how every skill
                    # question ended up answered "No experience".
                    best = self._best_match(answer, option_labels)
                    element = next(el for el, label in zip(buttons, option_labels) if label == best)
                    self.logger.info(f"  Selected: {best}")
                    self._click_option(element)

                elif text_visible:
                    text_input.click()
                    text_input.fill('')
                    self._type(text_input, answer)

                elif dropdown:
                    best = self._best_match(answer, option_labels)
                    page.select_option('.chatbot_MessageContainer select', label=best)
                    self.logger.info(f"  Dropdown → {best}")

                elif suggs:
                    options = [el.evaluate('el => el.innerText') for el in suggs]
                    best = self._best_match(answer, options)
                    self.logger.info(f"  Suggestion → {best}")
                    page.click(f'text="{best}"')

                elif dob:
                    parts = answer.strip().split("/")
                    if len(parts) == 3:
                        page.locator("input[name='day']").fill(parts[0])
                        page.locator("input[name='month']").fill(parts[1])
                        page.locator("input[name='year']").fill(parts[2])

                else:
                    self.logger.warning("  No recognised input – exiting chatbot loop")
                    return

                send = page.locator('.sendMsg')
                try:
                    expect(send).to_be_enabled(timeout=3000)
                    human_delay(350, 700)
                    send.click(timeout=3000)
                except Exception:
                    return
                human_delay(800, 1500)

        except Exception as e:
            self.logger.error(f"classify_new_question: {e}")
            return {"response": "error", "error": str(e)}

    # ── standard (non-chatbot) form filler ───────────────────

    def fill_standard_form(self):
        page = self.page
        ui = self.user_info
        self.logger.info("Filling standard form fields...")

        field_map = [
            (["full name", "name"],               ui.get("Full name", "")),
            (["first name", "given name"],        ui.get("First name", "")),
            (["last name", "surname"],             ui.get("Last name", "")),
            (["email"],                            ui.get("Email", "")),
            (["phone", "mobile", "contact"],       ui.get("Mobile", "")),
            (["total experience", "experience"],   ui.get("Total experience", "")),
            (["current salary", "ctc"],            ui.get("Salary", "")),
            (["expected salary", "desired"],       ui.get("Expected salary", "")),
            (["notice period"],                    ui.get("Notice period", "")),
            (["location", "city", "current city"], ui.get("Location", "")),
        ]

        for labels, value in field_map:
            if not value:
                continue
            for lbl in labels:
                filled = False
                for strategy in [
                    f'input[aria-label*="{lbl}" i]',
                    f'input[placeholder*="{lbl}" i]',
                    f'input[name*="{lbl}" i]',
                ]:
                    try:
                        el = page.locator(strategy).first
                        if el.count() > 0 and el.is_visible():
                            el.fill(value)
                            self.logger.info(f"  Filled '{lbl}' → {value}")
                            filled = True
                            break
                    except Exception:
                        continue
                if filled:
                    break

        # Resume upload
        resume = ui.get("Resume path", "")
        if resume and os.path.exists(resume):
            try:
                fi = page.locator('input[type="file"]').first
                if fi.count() > 0:
                    fi.set_input_files(resume)
                    self.logger.info(f"  Resume uploaded: {resume}")
            except Exception as e:
                self.logger.warning(f"  Resume upload failed: {e}")

        # Cover letter
        cover = ui.get("Cover letter", "")
        if cover:
            try:
                ta = page.locator('textarea').first
                if ta.count() > 0 and ta.is_visible():
                    ta.fill(cover)
                    self.logger.info("  Cover letter filled")
            except Exception:
                pass

        human_delay(400, 800)


# ─────────────────────────── main bot ───────────────────────────

class NaukriBot:
    _APPLY_SELECTORS = [
        '#apply-button',
        'button:has-text("Apply")',
        'a:has-text("Apply Now")',
        '.apply-button',
        'button[id*="apply" i]',
        '[data-ga-track*="apply" i]',
    ]
    _SUCCESS_PHRASES = [
        "successfully applied", "application submitted",
        "application sent", "thank you for applying", "applied successfully",
    ]
    _ALREADY_APPLIED = ["already applied", "application submitted", "applied on"]

    def __init__(self, email, password, username, number=10, user_info=None, resume_path="",
                 log_file=None, pending_registry=None, event_bus=None, on_application_recorded=None,
                 resume_skills=None):
        self.usr = [email, password]
        self.username = username
        self.applno = number
        self.applied_count = 0
        self.skipped_count = 0
        self.needs_input_count = 0
        self.ignored_count = 0  # ruled out by config.json's skip lists
        self.failed_count = 0  # an apply attempt that errored or had no button
        self.records = []  # every job recorded this session, for the end-of-run report
        self.page_no = 1
        self.base_page_url = ""
        self.tabs = ["profile", "apply", "preference", "similar_jobs"]
        self.tabIndex = 0
        self.tab = "profile"
        self.pattern = re.compile(r'https://.*/myapply/saveApply\?strJobsarr=')
        self.browser = None
        self.page = None
        self.cba = None
        self.pending_registry = pending_registry
        self.event_bus = event_bus
        self.on_application_recorded = on_application_recorded
        self.stop_event = threading.Event()
        self.quota_exceeded = False
        # Every Easy Apply click spends one of Naukri's daily applications,
        # whether or not it ends in a submit (a chatbot question nobody
        # answered, a form that failed). Cap the clicks, not just the
        # successes, so a target of N can't quietly burn far more than N.
        self.apply_clicks = 0
        self.max_apply_clicks = number * 2
        self._job_api_apply_url = ""

        self.user_info = user_info or {}
        if resume_path:
            self.user_info["Resume path"] = resume_path

        # Job/resume match scoring (jobsprint/resume/matcher.py). The score is
        # informational only — it's logged and surfaced in the dashboard so you
        # can see how well each listing lines up, but it never gates whether an
        # application is submitted.
        self.candidate_skills = set(self.user_info.get("Skills", {}).keys()) | set(resume_skills or [])
        self.candidate_years = parse_candidate_years(self.user_info.get("Total experience"))

        self.pw = None  # playwright instance reused across sessions to avoid asyncio-loop conflicts

        log_path = log_file or os.path.join(
            paths.LOGS_DIR, f"session_{datetime.now().strftime('%Y%m%d_%H%M%S')}.log"
        )
        # Logger name is the (timestamped) log path, not a fixed string — a long-lived
        # desktop app process runs many sessions, and a fixed name would make every
        # session after the first reuse the first one's handlers (and log file).
        self.logger = setup_logger(log_path, log_path, event_bus=event_bus)
        self.logger.info(f"NaukriBot ready — user: {username}, target: {number} jobs")

    def _emit(self, event_type, **data):
        if self.event_bus:
            self.event_bus.publish(event_type, **data)

    # ── browser ────────────────────────────────────────────────

    def init_browser(self):
        if self.pw is None:
            self.pw = sync_playwright().start()
        args = [
            "--disable-blink-features=AutomationControlled",
            "--disable-dev-shm-usage",
        ]
        # Playwright passes --no-sandbox unless chromium_sandbox=True, so ask
        # for the sandbox explicitly. Some Linux setups (Ubuntu 23.10+ blocks
        # unprivileged user namespaces via AppArmor) can't provide one —
        # only then fall back, and say so loudly rather than silently.
        try:
            self.browser = self.pw.chromium.launch(headless=False, args=args, chromium_sandbox=True)
        except Exception as e:
            if "sandbox" not in str(e).lower():
                raise
            self.logger.warning(
                "Chromium's sandbox is unavailable on this system — running WITHOUT it. "
                "On Ubuntu, allow it with an AppArmor profile for Playwright's Chromium "
                "(see README → Troubleshooting)."
            )
            self.browser = self.pw.chromium.launch(headless=False, args=args, chromium_sandbox=False)
        ctx = self.browser.new_context(
            user_agent=(
                "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                "AppleWebKit/537.36 (KHTML, like Gecko) "
                "Chrome/122.0.0.0 Safari/537.36"
            ),
            viewport={"width": 1366, "height": 768},
        )
        self.page = ctx.new_page()
        self.page.on("response", self._watch_for_quota)
        self.page.on("response", self._watch_for_job_api)
        self.cba = ChatbotAgent(self.page, self.username, self.user_info, self.logger,
                                 pending_registry=self.pending_registry, event_bus=self.event_bus)
        self.logger.info("Browser launched")

    # ── login ──────────────────────────────────────────────────

    # Any signed-in page lives under /mnjuser/ (homepage, profile, …); a
    # signed-out visit to one redirects back to the login page instead.
    _LOGGED_IN_URL = re.compile(r"https://www\.naukri\.com/mnjuser/")

    def _is_logged_in(self):
        try:
            return bool(self._LOGGED_IN_URL.match(self.page.url))
        except Exception:
            return False

    def login(self, retries=3):
        for attempt in range(1, retries + 1):
            try:
                self.logger.info(f"Login attempt {attempt}/{retries}")

                # A previous attempt may have signed in and only timed out
                # waiting afterwards — check before looking for a login button
                # that a signed-in page doesn't have.
                if attempt > 1:
                    self.page.goto("https://www.naukri.com/mnjuser/homepage",
                                   timeout=40000, wait_until="domcontentloaded")
                    human_delay(1000, 2000)
                    if self._is_logged_in():
                        self.logger.info("Logged in successfully")
                        return True

                self.page.goto("https://www.naukri.com", timeout=40000)
                human_delay(1000, 2000)
                self.page.click('//*[@id="login_Layer"]')
                human_delay(600, 1000)
                self.page.fill('input[type="text"]', self.usr[0])
                human_delay(300, 600)
                self.page.fill('input[type="password"]', self.usr[1])
                human_delay(300, 600)
                self.page.click('button[type="submit"]')
                # Not "networkidle": Naukri's pages keep polling/tracking
                # requests going, so the network never goes quiet and a
                # successful sign-in was reported as a timeout.
                self.page.wait_for_url(
                    self._LOGGED_IN_URL, timeout=30000, wait_until="domcontentloaded"
                )
                self.logger.info("Logged in successfully")
                return True
            except Exception as e:
                if self._is_logged_in():
                    self.logger.info("Logged in successfully")
                    return True
                self.logger.warning(f"Login attempt {attempt} failed: {e}")
                human_delay(2000, 4000)
        self.logger.error("All login attempts failed")
        return False

    # ── helpers ────────────────────────────────────────────────

    def _find_apply_btn(self):
        """The job's apply button as (locator, selector, text), or None —
        found without clicking it, so the kind of apply can be told apart
        first."""
        for sel in self._APPLY_SELECTORS:
            try:
                btn = self.page.locator(sel).first
                if btn.count() > 0 and btn.is_visible():
                    return btn, sel, (btn.inner_text(timeout=1000) or "").strip()
            except Exception:
                continue
        return None

    def _is_company_site_btn(self, btn, text):
        if "company site" in text.lower():
            return True
        try:
            return "company-site" in (btn.get_attribute("id", timeout=1000) or "")
        except Exception:
            return False

    def _click_apply_btn(self, btn, sel, text):
        """Clicks the apply button and returns (button_text, pages_open_before_click)
        — both needed by _company_site_url to catch a button that turned out
        to lead off naukri.com after all."""
        pages_before = len(self.page.context.pages)
        btn.click()
        self.apply_clicks += 1
        self.logger.info(f"Apply button clicked via: {sel} ({text!r})")
        return text, pages_before

    # Naukri's job page loads its details from /jobapi/…; for a company-site
    # job that JSON carries the employer's apply link, so the link can be
    # captured without ever clicking the button.
    _REDIRECT_KEY = re.compile(r"redirect|companyapply|applyurl", re.I)

    def _watch_for_job_api(self, response):
        if "/jobapi/" not in response.url or response.status != 200:
            return
        try:
            data = response.json()
        except Exception:
            return
        url = self._find_redirect_url(data)
        if url:
            self._job_api_apply_url = url

    def _find_redirect_url(self, node):
        if isinstance(node, dict):
            for key, value in node.items():
                if (isinstance(value, str) and self._REDIRECT_KEY.search(key)
                        and value.startswith("http") and "naukri.com" not in value):
                    return value
                found = self._find_redirect_url(value)
                if found:
                    return found
        elif isinstance(node, list):
            for item in node:
                found = self._find_redirect_url(item)
                if found:
                    return found
        return ""

    def _company_site_url(self, button_text, pages_before):
        """If the apply click went to the employer's own site, close any tab
        it opened and return that site's URL ("" if it couldn't be read);
        None means it's a Naukri Easy Apply."""
        pages = self.page.context.pages
        if len(pages) > pages_before:
            url = ""
            for tab in pages[pages_before:]:
                try:
                    tab.wait_for_load_state("domcontentloaded", timeout=10000)
                except Exception:
                    pass
                url = url or tab.url
                try:
                    tab.close()
                except Exception:
                    pass
            self.page.bring_to_front()
            return url
        if self._is_external():
            url = self.page.url
            self.page.go_back()
            human_delay(1000, 1500)
            return url
        if "company site" in button_text.lower():
            return ""
        return None

    # Naukri caps applications per day. Its apply API then answers 403 with
    # {"message": "Daily quota of jobs exceeded", customErrorCode: 403009};
    # every further attempt would fail the same way, so the session stops.
    _QUOTA_TEXT = "daily quota of jobs exceeded"
    _QUOTA_ERROR_CODE = "403009"

    def _watch_for_quota(self, response):
        if self.quota_exceeded or response.status != 403 or "naukri.com" not in response.url:
            return
        try:
            body = response.text().lower()
        except Exception:
            return
        if self._QUOTA_TEXT in body or self._QUOTA_ERROR_CODE in body:
            self._hit_quota()

    def _hit_quota(self):
        if self.quota_exceeded:
            return
        self.quota_exceeded = True
        self.stop_event.set()
        self.logger.error("Naukri's daily apply quota is exhausted — stopping. Try again tomorrow.")
        self._emit("activity_update", text="Naukri daily apply quota reached — stopped.")

    def _check_quota(self):
        """True once the daily quota has been hit — seen either in the API
        response above or shown as text on the page."""
        if not self.quota_exceeded:
            try:
                if self._QUOTA_TEXT in self.page.inner_text("body").lower():
                    self._hit_quota()
            except Exception:
                pass
        return self.quota_exceeded

    def _already_applied(self):
        try:
            txt = self.page.inner_text('body').lower()
            return any(p in txt for p in self._ALREADY_APPLIED)
        except Exception:
            return False

    def _is_external(self):
        try:
            return 'naukri.com' not in self.page.url
        except Exception:
            return False

    def _scrape_job_meta(self):
        """Best-effort scrape of job-detail fields before applying, for the
        Excel tracker / dashboard / question-modal job context. Naukri's
        markup drifts across UI versions, so every selector here is
        speculative and independently optional — a failed scrape must never
        block the apply flow, it just leaves that field blank."""
        meta = {"title": "", "company": "", "experience": "", "salary": "", "posted_date": ""}
        selectors = {
            "title": ['h1.jd-header-title', 'h1[class*="title" i]'],
            "company": ['.jd-header-comp-name a', 'a[class*="comp-name" i]', '[class*="companyName" i]'],
            "experience": ['.exp', '[class*="experience" i]'],
            "salary": ['.salary', '[class*="salary" i]'],
            "posted_date": ['[class*="posted" i]', '.jd-stats span'],
        }
        for field, sels in selectors.items():
            for sel in sels:
                try:
                    el = self.page.locator(sel).first
                    if el.count() > 0:
                        text = el.inner_text(timeout=1000).strip()
                        if text:
                            meta[field] = text
                            break
                except Exception:
                    continue
        return meta

    def _record_application(self, meta, job_url, application_type, status, external_url=""):
        record = build_record(meta, job_url, application_type, status, external_url, site="Naukri")
        self.records.append(record)
        if self.on_application_recorded:
            try:
                self.on_application_recorded(record)
            except Exception as e:
                self.logger.warning(f"  on_application_recorded hook failed: {e}")
        return record

    def _abort_needs_input(self, job_url, question):
        """A chatbot question couldn't be answered confidently and no one
        answered it in time (or no pause channel is wired up yet). Never
        guess — bail out of this one job cleanly and let the session move on."""
        self.logger.info(f"  Needs input — skipping this job: {question!r}")
        self.needs_input_count += 1
        self.skipped_count += 1
        self._emit("application_needs_input", naukri_url=job_url, question=question)
        try:
            self.page.go_back(timeout=10000)
            self.page.wait_for_load_state('domcontentloaded', timeout=10000)
        except Exception:
            pass
        return False

    def _save_screenshot(self, label="error"):
        try:
            path = os.path.join(paths.SCREENSHOTS_DIR, f"{label}_{datetime.now().strftime('%H%M%S')}.png")
            self.page.screenshot(path=path)
            self.logger.debug(f"Screenshot: {path}")
        except Exception:
            pass

    # ── single-job application ─────────────────────────────────

    def apply_to_job(self, job_url):
        try:
            self.logger.info(f"→ {job_url}")
            self._job_api_apply_url = ""
            self.page.goto(job_url, timeout=30000)
            self.page.wait_for_load_state('networkidle', timeout=15000)
            human_delay(700, 1400)

            meta = self._scrape_job_meta()

            # Second check with the job page's own company/title — the search
            # results card doesn't always expose them.
            reason = self._skip_reason(job_url, meta.get("title"), meta.get("company"))
            if reason:
                self.logger.info(f"  Ignored ({reason}) — not applying")
                self.ignored_count += 1
                return False

            if self._already_applied():
                self.logger.info("  Already applied — skipping")
                self.skipped_count += 1
                return False

            found = self._find_apply_btn()
            if not found:
                self.logger.warning("  No apply button found — skipping")
                self.failed_count += 1
                return False

            # Naukri counts every apply click against its daily quota — an
            # "Apply on company site" click included, even though nothing gets
            # submitted. So company-site jobs are recognised by the button
            # itself and recorded without clicking it.
            if self._is_company_site_btn(found[0], found[2]):
                external_url = self._job_api_apply_url
                self.logger.info(
                    f"  Company-site apply — not clicked (would use up Naukri's daily quota), "
                    f"NOT applied: {external_url or '(link not captured — open the job page)'}"
                )
                self.skipped_count += 1
                self._record_application(meta, job_url, application_type="external",
                                          status="Captured - Not Applied", external_url=external_url)
                return False

            if self.apply_clicks >= self.max_apply_clicks:
                self.logger.warning(
                    f"  {self.apply_clicks} apply clicks used this session (limit "
                    f"{self.max_apply_clicks}) — stopping to save Naukri's daily quota"
                )
                self.stop_event.set()
                return False

            clicked = self._click_apply_btn(*found)
            human_delay(1500, 2500)

            if self._check_quota():
                return False

            external_url = self._company_site_url(*clicked)
            if external_url is not None:
                self.logger.info(
                    f"  Company-site apply — only opened the careers page, NOT applied: "
                    f"{external_url or '(link not captured)'}"
                )
                self.skipped_count += 1
                self._record_application(meta, job_url, application_type="external",
                                          status="Captured - Not Applied", external_url=external_url)
                return False

            job_ctx = {"url": job_url, **meta}

            # Handle chatbot form
            try:
                self.page.wait_for_selector(".chatbot_MessageContainer", timeout=3000)
                self.logger.info("  Chatbot form detected")
                result = self.cba.classify_new_question(job_ctx=job_ctx)
                if isinstance(result, dict) and result.get("response") == "needs_input":
                    return self._abort_needs_input(job_url, result.get("question"))
                human_delay(800, 1500)
            except PlaywrightTimeoutError:
                pass

            # Handle standard application form pages (multi-step)
            max_steps = 5
            for step in range(max_steps):
                try:
                    form = self.page.locator('form').first
                    if form.count() > 0 and form.is_visible():
                        self.logger.info(f"  Standard form step {step + 1}")
                        self.cba.fill_standard_form()
                        # Also handle any chatbot widget inside this page
                        try:
                            self.page.wait_for_selector(".chatbot_MessageContainer", timeout=1500)
                            result = self.cba.classify_new_question(job_ctx=job_ctx)
                            if isinstance(result, dict) and result.get("response") == "needs_input":
                                return self._abort_needs_input(job_url, result.get("question"))
                        except PlaywrightTimeoutError:
                            pass
                        # Click next/submit button
                        advanced = False
                        for btn_text in ["Submit", "Apply", "Save & Apply", "Continue", "Next"]:
                            try:
                                btn = self.page.locator(f'button:has-text("{btn_text}")').last
                                if btn.count() > 0 and btn.is_visible():
                                    btn.click()
                                    self.logger.info(f"  Clicked '{btn_text}'")
                                    human_delay(1200, 2000)
                                    advanced = True
                                    break
                            except Exception:
                                continue
                        if not advanced:
                            break
                    else:
                        break
                except Exception:
                    break

            # The quota can also be hit on the final submit of a multi-step
            # form — never count that attempt as applied.
            if self._check_quota():
                return False

            # Confirm success
            success_reason = None
            try:
                expect(self.page).to_have_url(self.pattern, timeout=4000)
                success_reason = "URL pattern"
            except Exception:
                pass

            if not success_reason:
                try:
                    body = self.page.inner_text('body').lower()
                    if any(p in body for p in self._SUCCESS_PHRASES):
                        success_reason = "success text"
                except Exception:
                    pass

            if success_reason:
                self.logger.info(f"  ✓ Applied ({success_reason})")
                status = "Submitted"
            else:
                # Naukri showed neither its confirmation URL nor any success
                # text — still counted, but flagged so the report doesn't
                # claim more than was actually seen.
                self.logger.warning("  ✓ Applied (unconfirmed — no success message seen)")
                status = "Submitted (unconfirmed)"
            self._record_application(meta, job_url, application_type="direct", status=status)
            return True

        except Exception as e:
            self.logger.error(f"  apply_to_job error: {e}")
            self._save_screenshot("apply_error")
            self.failed_count += 1
            return False

    # ── job listing extraction ─────────────────────────────────

    def get_job_cards(self):
        """Scrapes title/experience/skill-tags straight off the search
        results page — cheap enough to do for every listing, so match
        scoring (jobsprint/resume/matcher.py) can decide whether a job is worth
        opening at all *before* paying for a full page load.

        Naukri's listing markup drifts across UI versions like everything
        else scraped in this file, so every field here is best-effort and
        independently optional. A job with a resolvable URL but blank
        title/experience/tags still gets a (neutral) match score rather
        than being dropped."""
        try:
            self.page.wait_for_load_state('networkidle', timeout=15000)
            for pct in [0.3, 0.6, 1.0]:
                self.page.evaluate(f"window.scrollTo(0, document.body.scrollHeight * {pct})")
                human_delay(400, 700)

            cards = self.page.evaluate("""
                () => {
                    const rowSelectors = ['.jobTuple', '.srp-jobtuple-wrapper', '[class*="jobTuple" i]'];
                    let rows = [];
                    for (const sel of rowSelectors) {
                        rows = Array.from(document.querySelectorAll(sel));
                        if (rows.length) break;
                    }
                    if (!rows.length) {
                        const links = Array.from(document.querySelectorAll(
                            '.title, .jobTitle, [class*="job-title" i] a'
                        )).filter(a => a.href && a.href.includes('naukri.com'));
                        return links.map(a => ({ url: a.href, title: a.innerText.trim(), experience: '', tags: [] }));
                    }
                    return rows.map(row => {
                        const titleEl = row.querySelector(
                            '.title, .jobTitle, [class*="job-title" i] a, a[class*="title" i]'
                        );
                        const expEl = row.querySelector('.exp, [class*="experience" i]');
                        const compEl = row.querySelector('.comp-name, [class*="comp-name" i], .subTitle');
                        const tagEls = row.querySelectorAll('.tags-gt li, .tags li, [class*="skill" i] li, .chip');
                        return {
                            url: titleEl ? titleEl.href : '',
                            title: titleEl ? titleEl.innerText.trim() : '',
                            company: compEl ? compEl.innerText.trim() : '',
                            experience: expEl ? expEl.innerText.trim() : '',
                            tags: Array.from(tagEls).map(t => t.innerText.trim()).filter(Boolean),
                        };
                    }).filter(c => c.url && c.url.includes('naukri.com'));
                }
            """)
            self.logger.info(f"Found {len(cards)} jobs on page {self.page_no}")
            return cards
        except Exception as e:
            self.logger.error(f"get_job_cards: {e}")
            return []

    def _skip_reason(self, url="", title="", company=""):
        return skip_reason(self.user_info, url, title, company)

    def _role_terms(self):
        """The searched role(s) as a list — match scoring compares a listing's
        title against these."""
        return self.search if isinstance(self.search, list) else [self.search]

    # ── paginated apply loop ───────────────────────────────────

    def apply_(self):
        cards = self.get_job_cards()

        for card in cards:
            if self.stop_event.is_set():
                if not self.quota_exceeded:
                    self.logger.info("Stop requested — ending session")
                return
            if self.applied_count >= self.applno:
                self.logger.info(f"Target reached ({self.applied_count}/{self.applno})")
                return
            human_delay(1500, 3000)
            self._emit("job_scanned")

            jl = card.get("url")
            if not jl:
                continue

            reason = self._skip_reason(jl, card.get("title"), card.get("company"))
            if reason:
                self.logger.info(f"  Ignored ({reason}): {card.get('title') or jl}")
                self.ignored_count += 1
                continue

            # Informational only — every listing the search returned gets an
            # application attempt; the score just annotates how close a fit it is.
            score = score_job(card, self.candidate_skills, self.candidate_years, self._role_terms())
            self._emit("job_matched", score=score, title=card.get("title"))

            self._emit("activity_update", text=f"Applying: {card.get('title') or jl} ({score:.0f}% match)")
            if self.apply_to_job(jl):
                self.applied_count += 1
                self._emit("application_submitted", naukri_url=jl)
                self.logger.info(f"Progress: {self.applied_count}/{self.applno}")
            # Return to search results
            try:
                self.page.go_back(timeout=10000)
                self.page.wait_for_load_state('domcontentloaded', timeout=10000)
                human_delay(600, 1000)
            except Exception:
                try:
                    self.page.goto(self.base_page_url)
                    self.page.wait_for_load_state('domcontentloaded')
                except Exception:
                    pass

        # Paginate. Rebuilt from the search terms rather than by patching the
        # current URL: Naukri answers a paginated path that still carries the
        # ?k=/?experience= query by bouncing back to page 1, which would make
        # this loop re-scan the same twenty listings forever.
        if self.applied_count < self.applno and not self.stop_event.is_set():
            self.page_no += 1
            next_url = self.search_url(self.page_no)
            self.logger.info(f"Page {self.page_no}")
            try:
                self.page.goto(next_url, timeout=20000)
                self.page.wait_for_load_state('domcontentloaded', timeout=15000)
                human_delay(600, 1000)
                if self.page_no > 1 and not self.get_job_cards():
                    self.logger.info("No more results")
                    return
                self.apply_()
            except Exception as e:
                self.logger.warning(f"Pagination stopped: {e}")

    # ── single-role session apply ─────────────────────────────

    def apply_for_role(self, role, experience=None, location='', job_age='3'):
        """Search one job role and work through the results in a single browser
        session (no re-login).

        `experience` is a single number of years (e.g. 3), matching Naukri's own
        search bar, which offers one value rather than a range.

        Caller is responsible for init_browser() + login() before calling this,
        and shutdown() after.
        """
        self.search = role
        self.page_no = 1   # each role starts from its own first results page
        self.experience = experience
        self.location = location
        self.jobage = job_age
        human_delay(800, 1500)
        self.filter_()
        self.base_page_url = self.page.url
        self.apply_()
        result = {
            "response": "done",
            "applied": self.applied_count,
            "skipped": self.skipped_count,
        }
        self.logger.info(f"Session complete: {result}")
        return result

    # ── search ─────────────────────────────────────────────────

    @staticmethod
    def _slug(text):
        """'AWS DevOps' -> 'aws-devops' (Naukri's own URL wording)."""
        return re.sub(r"-+", "-", re.sub(r"[^a-z0-9]+", "-", str(text).lower())).strip("-")

    def search_url(self, page_no=1):
        """Build the results URL directly instead of driving the search widget.

        Typing into the header search bar turned out to be the single biggest
        source of failures: the input is a different element on the logged-out
        homepage, the results page and the logged-in dashboard, it is often
        present-but-not-visible (30s click timeouts), and Enter submits on some
        pages but is a no-op on others. Navigating straight to the results URL
        skips every one of those failure modes.

        The path slug matters: Naukri only honours ?experience= / ?jobAge= when
        the path is the role-specific slug. On the generic /jobs-in-india path
        it silently drops them (verified: experience=15 returned the same 3170
        results as no filter at all, while the slug form returned 165).
        """
        location = (self.location or "").strip()
        slug = f"{self._slug(self.search)}-jobs-in-{self._slug(location) if location else 'india'}"

        if page_no > 1:
            # Page 2 onward takes the bare path, exactly like Naukri's own
            # "Next" link. Keeping the query string on a paginated path makes
            # Naukri redirect back to page 1 (verified), so the filters have to
            # be dropped here — their own pagination discards them too.
            return f"https://www.naukri.com/{slug}-{page_no}"

        params = {"k": self.search}
        if location:
            params["l"] = location
        years = parse_experience_years(self.experience)
        if years is not None:
            params["experience"] = years
        if self.jobage:
            params["jobAge"] = self.jobage

        return f"https://www.naukri.com/{slug}?{urlencode(params)}"

    def filter_(self):
        url = self.search_url()
        try:
            self.page.goto(url, timeout=30000)
            self.page.wait_for_load_state("domcontentloaded", timeout=20000)
            human_delay(800, 1400)
            self.logger.info(f"Search: {self.page.url}")
        except Exception as e:
            self.logger.error(f"Could not open the search results: {e}")

    # ── checkbox / tab mode ────────────────────────────────────

    def checkbox_apply(self):
        try:
            cbs = self.page.locator('.naukicon-ot-checkbox').element_handles()
            self.logger.info(f"Checkboxes found: {len(cbs)}")
            if not cbs:
                return {"status": "finished", "found": 0, "clicked": 0}

            clicked = 0
            for cb in cbs[:5]:
                try:
                    cb.click()
                    clicked += 1
                    human_delay(200, 500)
                except Exception:
                    continue

            self.page.locator('.multi-apply-button').click()
            human_delay(1500, 2500)

            try:
                expect(self.page.locator(".chatbot_MessageContainer")).to_be_visible(timeout=3000)
                return {"status": "underway", "found": len(cbs), "clicked": clicked}
            except Exception:
                try:
                    expect(self.page).to_have_url(self.pattern, timeout=3000)
                    return {"status": "done", "clicked": clicked}
                except Exception:
                    raise
        except Exception:
            return {"status": "failed"}

    def start_apply(self, tab):
        self.tabIndex = 0
        self.tab = tab
        self.init_browser()
        if self.login():
            return self.bot_actions()

    def bot_actions(self):
        try:
            human_delay(2000, 3000)
            self.page.click('.nI-gNb-menuItems__anchorDropdown')
            if self.tab != "profile":
                self.page.click(f"#{self.tab}")
            self.page.wait_for_load_state("networkidle")

            if self.applied_count >= self.applno:
                self.logger.info(f"Target reached: {self.applied_count} jobs")
                return {"response": "done", "applied": self.applied_count}

            cbapl = self.checkbox_apply()

            if cbapl["status"] == 'failed':
                self.logger.info("Daily quota exhausted")
                self.close()
                return {"response": "quota finished", "applied": self.applied_count}

            if cbapl["status"] == 'done':
                self.applied_count += cbapl["clicked"]
                return self.bot_actions()

            if cbapl["status"] == 'underway':
                self.cba.classify_new_question()
                try:
                    expect(self.page).to_have_url(self.pattern, timeout=5000)
                    self.applied_count += cbapl["clicked"]
                    return self.bot_actions()
                except Exception as e:
                    self.logger.error(f"bot_actions underway error: {e}")
                    self.close()
                    return {"response": "error", "error": str(e)}

            if cbapl['status'] == "finished":
                if self.tabIndex + 1 < len(self.tabs):
                    self.tabIndex += 1
                    self.tab = self.tabs[self.tabIndex]
                    return self.bot_actions()
                else:
                    self.logger.info("All tabs exhausted")
                    self.close()
                    return {"response": "all tabs done", "applied": self.applied_count}

        except Exception as e:
            self.close()
            self.logger.error(f"bot_actions error (applied {self.applied_count}): {e}")
            return {"response": "error", "error": str(e)}

    def close(self):
        if self.browser:
            self.browser.close()
            self.browser = None
            self.logger.info("Browser closed")

    def shutdown(self):
        """Call once after all roles are done to fully stop playwright."""
        self.close()
        if self.pw:
            self.pw.stop()
            self.pw = None
