"""Hirist (hirist.tech) search and one-job-at-a-time apply.

Login uses the "Use Password to Login" form. Search opens the public keyword
URL with an experience band, then each /j/ listing is opened and Apply is
clicked. Jobs that only offer a company-site button are recorded and skipped.
"""

import re
from urllib.parse import urlencode

from .listing import ListingBot, _slug, human_delay


def _cities(location):
    """'Bangalore, Chennai, Coimbatore' -> three cities. Hirist has one
    listings page per city; a combined slug matches nothing."""
    text = (location or "").strip()
    if not text or text.lower() == "any":
        return [""]
    parts = re.split(r"\s*(?:,|/|;|\||\band\b)\s*", text, flags=re.I)
    cities = [part.strip() for part in parts if part.strip()]
    return cities or [""]


class HiristBot(ListingBot):
    site_name = "Hirist"
    home_url = "https://www.hirist.tech/"

    def login(self, retries=3):
        for attempt in range(1, retries + 1):
            try:
                self.logger.info(f"Login attempt {attempt}/{retries}")
                self.page.goto(self.home_url, timeout=40000, wait_until="domcontentloaded")
                human_delay(800, 1400)
                if self._signed_in():
                    self.logger.info("Logged in successfully")
                    return True

                self.page.evaluate(
                    """() => {
                        const button = [...document.querySelectorAll('button')]
                            .find(el => (el.innerText || '').trim() === 'Login');
                        if (button) button.click();
                    }"""
                )
                human_delay(400, 800)
                self.page.get_by_text("Use Password to Login", exact=True).click(timeout=8000)
                human_delay(300, 600)
                self.page.locator('input[name="email"]').fill(self.usr[0])
                human_delay(200, 400)
                self.page.locator('input[name="password"]').fill(self.usr[1])
                human_delay(200, 400)
                self.page.locator('button[type="submit"]').filter(has_text="Login").click(timeout=8000)
                self.page.wait_for_timeout(2500)
                if self._signed_in():
                    self.logger.info("Logged in successfully")
                    return True
                self.logger.warning("Hirist did not confirm the sign-in")
            except Exception as e:
                self.logger.warning(f"Login attempt {attempt} failed: {e}")
        return False

    def _signed_in(self):
        try:
            text = self.page.locator("body").inner_text(timeout=3000)
        except Exception:
            return False
        return "My Jobfeed" in text or "Logout" in text

    def _wait_for_listings(self):
        try:
            self.page.wait_for_selector('a[href*="/j/"]', timeout=8000)
        except Exception:
            pass

    def apply_for_role(self, role, experience=None, location="", job_age="3", reset_seen=True):
        cities = _cities(location)
        self._seen_urls = set()
        result = {"response": "done", "applied": self.applied_count, "skipped": self.skipped_count}
        for city in cities:
            if self.applied_count >= self.applno or self.stop_event.is_set() or self.quota_exceeded:
                break
            if city and len(cities) > 1:
                self.logger.info(f"Location: {city}")
            result = super().apply_for_role(
                role, experience, city, job_age, reset_seen=False,
            )
        return result

    def search_url(self, page_no=1):
        # Hirist's own search box lands on /search/<slug>. A location uses the
        # "{role}-jobs-in-{city}" page, which is what the site links itself.
        role = _slug(self.search) or "jobs"
        location = _slug(self.location)
        if location:
            path = f"https://www.hirist.tech/{role}-jobs-in-{location}"
        else:
            path = f"https://www.hirist.tech/search/{role}"
        params = {}
        years = self.experience
        if years is not None and str(years) != "":
            params["minexp"] = int(years)
            params["maxexp"] = int(years)
        # `posting` is not a day count. 7 and 30 return listings; other values
        # (including 1) can wipe the page, so only those two are forwarded.
        if str(self.jobage) in ("7", "30"):
            params["posting"] = self.jobage
        if page_no > 1:
            params["page"] = page_no
        if not params:
            return path
        return f"{path}?{urlencode(params)}"

    def collect_cards(self):
        try:
            return self.page.evaluate(
                """() => {
                    const seen = new Set();
                    const cards = [];
                    for (const a of document.querySelectorAll('a[href*="/j/"]')) {
                        const url = a.href.split('?')[0];
                        if (!url || seen.has(url)) continue;
                        seen.add(url);
                        let node = a;
                        let text = '';
                        for (let i = 0; i < 6 && node; i++) {
                            node = node.parentElement;
                            const next = node ? (node.innerText || '') : '';
                            if (next.split('\\n').length > text.split('\\n').length) text = next;
                            if (/\\d+\\s*-\\s*\\d+\\s*yrs/i.test(next)) break;
                        }
                        const title = (a.innerText || '').trim();
                        const company = title.includes(' - ') ? title.split(' - ')[0].trim() : '';
                        const exp = (text.match(/\\d+\\s*-\\s*\\d+\\s*yrs/i) || [''])[0];
                        const posted = (text.match(/Posted[^\\n]*/i) || [''])[0];
                        cards.push({url, title, company, experience: exp, posted_date: posted, salary: ''});
                    }
                    return cards;
                }"""
            )
        except Exception as e:
            self.logger.error(f"collect_cards: {e}")
            return []

    def apply_to_job(self, job_url, card):
        try:
            self.page.goto(job_url, timeout=40000, wait_until="domcontentloaded")
            human_delay(800, 1400)
        except Exception as e:
            self.logger.warning(f"  Could not open {job_url}: {e}")
            self.failed_count += 1
            return False

        if self._already_applied() or self._saw_success():
            self.logger.info(f"  Already applied: {card.get('title') or job_url}")
            self.skipped_count += 1
            return False

        action = self._click_apply()
        if action == "external":
            self.logger.info(f"  Company-site apply — not clicked: {card.get('title') or job_url}")
            self._record(self._meta_from_card(card, job_url), job_url, "external", "Captured - Not Applied")
            return False
        if action != "clicked":
            self.logger.info(f"  No Apply button: {card.get('title') or job_url}")
            self.failed_count += 1
            return False

        self.apply_clicks += 1
        human_delay(900, 1600)
        return self._finish_apply(card, job_url)
