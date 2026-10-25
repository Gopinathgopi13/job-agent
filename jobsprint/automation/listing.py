"""Shared search → open → apply loop for portals other than Naukri.

Each portal subclass owns login, the results URL, and how a listing card is
read. Applying one job at a time (never a bulk "apply all") keeps the skip
lists, the daily click cap, and the question prompts the same as Naukri.
"""

import os
import re
import threading
from datetime import datetime
from urllib.parse import urlparse

from playwright.sync_api import sync_playwright

from .. import paths
from ..resume.matcher import parse_candidate_years, score_job
from .common import build_record, skip_reason
from .naukri import ChatbotAgent, human_delay, setup_logger

_SUCCESS_PHRASES = (
    "successfully applied", "application submitted", "application sent",
    "thank you for applying", "applied successfully", "you have applied",
    "your application has been",
)
_ALREADY_PHRASES = ("already applied", "you have already applied", "applied on")
_EXTERNAL_BUTTON = re.compile(r"company site|company website|employer site|apply on website", re.I)


def _slug(text):
    return re.sub(r"-+", "-", re.sub(r"[^a-z0-9]+", "-", str(text or "").lower())).strip("-")


class ListingBot:
    site_name = ""
    home_url = ""

    def __init__(self, email, password, username, number=10, user_info=None, resume_path="",
                 log_file=None, pending_registry=None, event_bus=None, on_application_recorded=None,
                 resume_skills=None):
        self.usr = [email, password]
        self.username = username
        self.applno = number
        self.applied_count = 0
        self.skipped_count = 0
        self.needs_input_count = 0
        self.ignored_count = 0
        self.failed_count = 0
        self.records = []
        self.page_no = 1
        self.browser = None
        self.page = None
        self.pending_registry = pending_registry
        self.event_bus = event_bus
        self.on_application_recorded = on_application_recorded
        self.stop_event = threading.Event()
        self.quota_exceeded = False
        self.apply_clicks = 0
        self.max_apply_clicks = number * 2
        self.user_info = user_info or {}
        if resume_path:
            self.user_info["Resume path"] = resume_path
        self.candidate_skills = set(self.user_info.get("Skills", {}).keys()) | set(resume_skills or [])
        self.candidate_years = parse_candidate_years(self.user_info.get("Total experience"))
        self.pw = None
        self.search = ""
        self.experience = None
        self.location = ""
        self.jobage = ""
        self._seen_urls = set()

        log_path = log_file or os.path.join(
            paths.LOGS_DIR, f"session_{datetime.now().strftime('%Y%m%d_%H%M%S')}.log"
        )
        self.logger = setup_logger(log_path, log_path, event_bus=event_bus)
        self.agent = None
        self.logger.info(f"{self.site_name} bot ready — user: {username}, target: {number} jobs")

    def _emit(self, event_type, **data):
        if self.event_bus:
            self.event_bus.publish(event_type, **data)

    def init_browser(self):
        if self.pw is None:
            self.pw = sync_playwright().start()
        args = ["--disable-blink-features=AutomationControlled", "--disable-dev-shm-usage"]
        try:
            self.browser = self.pw.chromium.launch(headless=False, args=args, chromium_sandbox=True)
        except Exception as e:
            if "sandbox" not in str(e).lower():
                raise
            self.logger.warning(
                "Chromium's sandbox is unavailable on this system — running WITHOUT it."
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
        self.agent = ChatbotAgent(
            self.page, self.username, self.user_info, self.logger,
            pending_registry=self.pending_registry, event_bus=self.event_bus,
        )
        self.logger.info("Browser launched")

    def close(self):
        if self.browser:
            self.browser.close()
            self.browser = None
            self.logger.info("Browser closed")

    def shutdown(self):
        self.close()
        if self.pw:
            self.pw.stop()
            self.pw = None

    def login(self, retries=3):
        raise NotImplementedError

    def search_url(self, page_no=1):
        raise NotImplementedError

    def collect_cards(self):
        raise NotImplementedError

    def apply_to_job(self, job_url, card):
        raise NotImplementedError

    def _host(self):
        return urlparse(self.home_url).netloc

    def _on_site(self):
        try:
            return self._host() in (urlparse(self.page.url).netloc or "")
        except Exception:
            return False

    def _body_text(self):
        try:
            return self.page.locator("body").inner_text(timeout=4000).lower()
        except Exception:
            return ""

    def _saw_success(self):
        text = self._body_text()
        if any(phrase in text for phrase in _SUCCESS_PHRASES):
            return True
        try:
            applied = self.page.get_by_role("button", name=re.compile(r"^Applied$", re.I))
            return bool(applied.count() and applied.first.is_visible())
        except Exception:
            return False

    def _already_applied(self):
        text = self._body_text()
        return any(phrase in text for phrase in _ALREADY_PHRASES)

    def _record(self, meta, job_url, application_type, status, external_url=""):
        record = build_record(meta, job_url, application_type, status, external_url, site=self.site_name)
        self.records.append(record)
        if self.on_application_recorded:
            try:
                self.on_application_recorded(record)
            except Exception as e:
                self.logger.warning(f"  on_application_recorded hook failed: {e}")
        return record

    def _meta_from_card(self, card, job_url):
        return {
            "title": card.get("title") or "",
            "company": card.get("company") or "",
            "experience": card.get("experience") or "",
            "salary": card.get("salary") or "",
            "posted_date": card.get("posted_date") or "",
            "url": job_url,
        }

    def _click_apply(self):
        """Click the on-site apply control. Returns 'external' when the only
        apply path leaves the portal, or None when no button was found."""
        external = self.page.get_by_role("button", name=_EXTERNAL_BUTTON)
        try:
            if external.count() and external.first.is_visible():
                return "external"
        except Exception:
            pass
        external_link = self.page.get_by_role("link", name=_EXTERNAL_BUTTON)
        try:
            if external_link.count() and external_link.first.is_visible():
                return "external"
        except Exception:
            pass

        for pattern in (r"^Quick Apply$", r"^Apply Now$", r"^Apply$"):
            button = self.page.get_by_role("button", name=re.compile(pattern, re.I))
            try:
                if button.count() and button.first.is_visible():
                    button.first.click(timeout=8000)
                    return "clicked"
            except Exception:
                continue
        return None

    def _application_fields(self):
        """Empty inputs inside an apply form or dialog, ignoring the site's
        own search bar. Radios and checkboxes that share a name are one field."""
        try:
            raw = self.page.evaluate(
                """() => {
                    const visible = (el) => {
                        const rect = el.getBoundingClientRect();
                        const style = getComputedStyle(el);
                        return rect.width > 0 && rect.height > 0
                            && style.visibility !== 'hidden' && style.display !== 'none';
                    };
                    const labelFor = (el) => {
                        if (el.id) {
                            const byFor = document.querySelector('label[for="' + CSS.escape(el.id) + '"]');
                            if (byFor && byFor.innerText.trim()) return byFor.innerText.trim();
                        }
                        const wrap = el.closest('label');
                        if (wrap && wrap.innerText.trim()) return wrap.innerText.trim();
                        const aria = el.getAttribute('aria-label') || el.getAttribute('placeholder') || '';
                        if (aria.trim()) return aria.trim();
                        let node = el.parentElement;
                        for (let i = 0; i < 4 && node; i++) {
                            const caption = [...node.children].find(child =>
                                child !== el && /^(LABEL|P|SPAN|H3|H4|DIV)$/.test(child.tagName)
                                && child.innerText && child.innerText.trim().length < 180
                            );
                            if (caption) return caption.innerText.trim();
                            node = node.parentElement;
                        }
                        return el.name || '';
                    };
                    const headerNames = new Set(['query', 'loc', 'experience']);
                    const candidates = [...document.querySelectorAll('input, textarea, select')].filter(el => {
                        if (!visible(el)) return false;
                        const type = (el.getAttribute('type') || '').toLowerCase();
                        if (['hidden', 'submit', 'button', 'password', 'search'].includes(type)) return false;
                        if (headerNames.has((el.name || '').toLowerCase())) return false;
                        const placeholder = el.getAttribute('placeholder') || '';
                        if (placeholder === 'Search Jobs' || /job title|skill to search/i.test(placeholder)) return false;
                        return true;
                    });
                    const roots = [...document.querySelectorAll('[role="dialog"], form, [class*="Modal"], [class*="modal"], [class*="Drawer"]')]
                        .filter(visible);
                    const root = roots.find(node => candidates.some(el => node.contains(el))) || document.body;
                    const fields = [];
                    const groups = new Map();
                    for (const el of candidates.filter(el => root.contains(el))) {
                        const type = (el.getAttribute('type') || el.tagName).toLowerCase();
                        const label = labelFor(el).replace(/\\s+/g, ' ').slice(0, 180);
                        if (type === 'radio' || type === 'checkbox') {
                            const key = (el.name || label) + ':' + type;
                            if (!groups.has(key)) {
                                groups.set(key, {type, name: el.name || '', label, options: []});
                                fields.push(groups.get(key));
                            }
                            const option = labelFor(el).replace(/\\s+/g, ' ').slice(0, 120);
                            if (option) groups.get(key).options.push(option);
                            continue;
                        }
                        if (type !== 'file' && (el.value || '').trim()) continue;
                        fields.push({
                            type, tag: el.tagName.toLowerCase(),
                            name: el.name || '', id: el.id || '', label,
                            options: el.tagName === 'SELECT'
                                ? [...el.options].map(option => option.text.trim()).filter(Boolean) : [],
                        });
                    }
                    return fields;
                }"""
            )
        except Exception as e:
            self.logger.info(f"  Could not read the application form: {e}")
            return []
        return raw or []

    def _locator_for(self, field):
        if field.get("id"):
            return self.page.locator(f'[id="{field["id"]}"]')
        if field.get("name") and field.get("type") not in ("radio", "checkbox"):
            return self.page.locator(f'[name="{field["name"]}"]')
        label = field.get("label") or ""
        if label:
            return self.page.get_by_label(label, exact=False)
        return None

    def _fill_field(self, field, answer):
        if field.get("type") == "file":
            path = self.user_info.get("Resume path") or ""
            if not path or not os.path.isfile(path):
                self.logger.info("  Resume file is not set — leaving the upload empty")
                return False
            target = self._locator_for(field)
            if target is None:
                return False
            target.first.set_input_files(path, timeout=5000)
            return True

        if field.get("type") in ("radio", "checkbox"):
            option = self.page.get_by_text(str(answer), exact=True)
            if option.count():
                option.first.click(timeout=4000)
                return True
            return False

        target = self._locator_for(field)
        if target is None or target.count() == 0:
            return False
        if field.get("tag") == "select":
            try:
                target.first.select_option(label=str(answer), timeout=4000)
                return True
            except Exception:
                target.first.select_option(str(answer), timeout=4000)
                return True
        target.first.fill(str(answer), timeout=4000)
        return True

    def _submit_form(self):
        scope = self.page.locator('[role="dialog"]')
        root = scope.last if scope.count() else self.page.locator("body")
        for pattern in (r"Submit", r"Continue", r"Save", r"Send", r"Apply"):
            button = root.get_by_role("button", name=re.compile(pattern, re.I))
            try:
                if button.count() and button.first.is_visible():
                    button.first.click(timeout=5000)
                    return True
            except Exception:
                continue
        return False

    def _answer_prompts(self, job_url, card, limit=4):
        """Fill an apply form, or a short questionnaire, from the profile.
        Returns False when a required answer is missing and the job is skipped."""
        job_ctx = {
            "title": card.get("title") or "",
            "url": job_url,
            "company": card.get("company") or "",
        }
        for _ in range(limit):
            human_delay(600, 1000)
            if self._saw_success():
                return True
            fields = self._application_fields()
            if not fields:
                return True
            self.logger.info(f"  Application form — {len(fields)} field(s)")
            for field in fields:
                question = field.get("label") or field.get("name") or "Application field"
                if field.get("type") == "file":
                    answer = self.user_info.get("Resume path") or ""
                else:
                    answer = self.agent._resolve_question(
                        question, job_ctx=job_ctx, options=field.get("options") or None,
                    )
                if not answer:
                    self.needs_input_count += 1
                    self.skipped_count += 1
                    self._emit("application_needs_input", naukri_url=job_url, question=question)
                    self.logger.info(f"  Needs input — skipping this job: {question!r}")
                    return False
                try:
                    filled = self._fill_field(field, answer)
                except Exception as e:
                    self.logger.info(f"  Could not fill {question!r}: {e}")
                    filled = False
                if not filled:
                    self.logger.info(f"  Could not fill {question!r}")
                    return False
                self.logger.info(f"  Filled {question}")
            if not self._submit_form():
                self.logger.info("  Form filled, but no submit button was found")
                return False
            human_delay(800, 1400)
        return True

    def _wait_for_listings(self):
        """Portals whose results render after the document loads can wait here."""

    def apply_for_role(self, role, experience=None, location="", job_age="3", reset_seen=True):
        self.search = role
        self.page_no = 1
        self.experience = experience
        self.location = location or ""
        self.jobage = job_age
        if reset_seen:
            self._seen_urls = set()
        human_delay(800, 1500)

        while self.applied_count < self.applno and not self.stop_event.is_set() and not self.quota_exceeded:
            url = self.search_url(self.page_no)
            try:
                self.page.goto(url, timeout=40000, wait_until="domcontentloaded")
                self._wait_for_listings()
                human_delay(600, 1100)
            except Exception as e:
                self.logger.error(f"Could not open the search results: {e}")
                break
            self.logger.info(f"Search: {self.page.url}")

            cards = self.collect_cards()
            fresh = [c for c in cards if c.get("url") and c["url"] not in self._seen_urls]
            if not fresh:
                self.logger.info("No more results")
                break
            self.logger.info(f"Found {len(fresh)} jobs on page {self.page_no}")

            for card in fresh:
                self._seen_urls.add(card["url"])
                if self.stop_event.is_set() or self.quota_exceeded:
                    break
                if self.applied_count >= self.applno:
                    self.logger.info(f"Target reached ({self.applied_count}/{self.applno})")
                    break
                if self.apply_clicks >= self.max_apply_clicks:
                    self.logger.info(
                        f"Apply-click cap reached ({self.apply_clicks}/{self.max_apply_clicks}) — stopping"
                    )
                    self.quota_exceeded = True
                    break

                human_delay(1200, 2200)
                self._emit("job_scanned")
                reason = skip_reason(
                    self.user_info, card.get("url", ""), card.get("title", ""), card.get("company", ""),
                )
                if reason:
                    self.logger.info(f"  Ignored ({reason}): {card.get('title') or card.get('url')}")
                    self.ignored_count += 1
                    continue

                score = score_job(card, self.candidate_skills, self.candidate_years, [self.search])
                self._emit("job_matched", score=score, title=card.get("title"))
                self._emit(
                    "activity_update",
                    text=f"Applying: {card.get('title') or card.get('url')} ({score:.0f}% match)",
                )
                if self.apply_to_job(card["url"], card):
                    self.applied_count += 1
                    self._emit("application_submitted", naukri_url=card["url"])
                    self.logger.info(f"Progress: {self.applied_count}/{self.applno}")

            if self.applied_count >= self.applno or self.stop_event.is_set() or self.quota_exceeded:
                break
            self.page_no += 1
            if self.page_no > 15:
                break

        result = {"response": "done", "applied": self.applied_count, "skipped": self.skipped_count}
        self.logger.info(f"Session complete: {result}")
        return result

    def _finish_apply(self, card, job_url):
        """Shared tail of an apply click: answer a short form, then record."""
        meta = self._meta_from_card(card, job_url)
        if not self._on_site():
            external = self.page.url
            self.logger.info(f"  Company-site apply — opened only, NOT applied: {external}")
            self._record(meta, job_url, "external", "Captured - Not Applied", external)
            return False

        if not self._answer_prompts(job_url, card):
            return False

        human_delay(800, 1400)
        if not self._on_site():
            external = self.page.url
            self._record(meta, job_url, "external", "Captured - Not Applied", external)
            return False
        if self._saw_success() or self._already_applied():
            self._record(meta, job_url, "direct", "Submitted")
            return True
        self.logger.info("  Apply clicked, but no confirmation was visible")
        self.failed_count += 1
        self._record(meta, job_url, "direct", "Unconfirmed")
        return False
