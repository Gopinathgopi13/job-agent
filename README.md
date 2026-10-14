# JobSprint

**Applies to Naukri.com jobs for you, automatically.**

Tell it a role and how many years you have. It opens a browser, signs into your Naukri account, runs the search, opens each result, clicks Apply, fills the form, answers the chatbot's questions from your config, and moves on to the next one.

Runs on **Windows** and **macOS** (and Linux). Created by **Gopinath**.

---

## Contents

- [What you run](#what-you-run)
- [Install](#install)
- [Set up your answers](#set-up-your-answers)
- [How it works](#how-it-works)
- [Dependencies](#dependencies)
- [Commands](#commands)
- [Where your data lives](#where-your-data-lives)
- [Project layout](#project-layout)
- [Desktop dashboard](#desktop-dashboard-optional)
- [Troubleshooting](#troubleshooting)

---

## What you run

There is **one file to start the bot**:

| Your machine | Run this |
|---|---|
| **Windows** | **`jobsprint.bat`** — double-click it in Explorer, or `.\jobsprint.bat` in a terminal |
| **macOS / Linux** | **`./jobsprint.sh`** in a terminal |

Both live in the project root. They set everything up on first launch, then go straight to applying on every launch after.

---

## Install

You need **Python 3.9 or newer** first. Check with `python --version` (Windows) or `python3 --version` (macOS).
If it's missing, get it from [python.org/downloads](https://www.python.org/downloads/) — on Windows, tick **"Add python.exe to PATH"** during setup. On macOS you can also use `brew install python`.

### Windows

```bat
git clone <this-repo-url>
cd jobautobot
setup\install.bat
```

### macOS / Linux

```bash
git clone <this-repo-url>
cd jobautobot
chmod +x setup/install.sh jobsprint.sh
./setup/install.sh
```

Either way the installer does three things, once:

```
[1/3] Creating the virtual environment          ->  venv/
[2/3] Installing Python dependencies            ->  pip install -r requirements.txt
[3/3] Installing the Chromium browser           ->  python -m playwright install chromium
```

The Chromium download is about 150MB and only happens the first time.

> You can skip `install` entirely and just run `jobsprint.bat` / `./jobsprint.sh` — it runs the installer itself if it sees no `venv`. Running it separately just makes the first launch quicker to follow.

### Doing it by hand

If you'd rather not use the scripts:

<table>
<tr><th>Windows</th><th>macOS / Linux</th></tr>
<tr><td>

```bat
python -m venv venv
venv\Scripts\activate
pip install -r requirements.txt
python -m playwright install chromium
```

</td><td>

```bash
python3 -m venv venv
source venv/bin/activate
pip install -r requirements.txt
python -m playwright install chromium
```

</td></tr>
</table>

On a minimal or server Linux install, Chromium also needs system libraries:

```bash
python -m playwright install-deps chromium   # needs sudo
```

Then start it with `python -m jobsprint --apply`.

---

## Set up your answers

Copy **`config.example.json`** to **`config.json`** in the project root and fill it in. This one file holds everything the bot types into an application form. `config.json` is gitignored, so your personal answers are never committed.

```bash
cp config.example.json config.json      # Windows: copy config.example.json config.json
```

### Config keys

| Key | Type | What it answers |
|---|---|---|
| `Salutation`, `Full name`, `First name`, `Last name` | text | Name fields on forms |
| `Email`, `Mobile` | text | Contact details |
| `Date of birth`, `Gender`, `Father's name`, `Mother's name`, `Marital status` | text | Personal details some forms ask |
| `Location`, `Current location` | text | Where you live now |
| `Preferred work location` | text | Comma-separated cities you'd work in |
| `Relocate`, `Open to relocate` | Yes/No | Willingness to relocate |
| `Total experience` | years | Overall experience; also the fallback for unlisted skills |
| `Current CTC`, `Salary`, `Expected salary` | text | e.g. `9 LPA`, `15 LPA` |
| `Notice period` | days | Also drives the "last working day" answer |
| `Notice period negotiable`, `Immediately available` | Yes/No | Availability questions |
| `Highest qualification` | text | e.g. `B.Tech` |
| `Passport`, `Shift willingness`, `Vehicle`, `Work authorization`, `Visa sponsorship required` | Yes/No | Screening questions |
| `Resume path` | path | Full path to your resume PDF |
| `Cover letter` | text | Cover letter text, if a form asks |
| `Job roles` | list | Roles to search one after another until the target is reached; when set, the role isn't asked |
| `Skip companies` | list | Never apply to these companies |
| `Skip title keywords` | list | Never apply when the job title contains these |
| `Skip job links` | list | Never apply to links containing these (e.g. a job ID) |
| `Skills` | object | Tool → your years with it |

Skip lists match case-insensitively and ignore spacing and punctuation, so `Infosys` also catches `Infosys BPM` and `Java Full Stack` catches `Java Fullstack`. Keys starting with `__` are treated as comments.

Values set in the dashboard's Profile tab are stored per-machine and override `config.json`. Any blank or missing key falls back to a built-in default.

A few things worth knowing:

- **`Skills`** maps a tool to your years with it. That's what answers *"How many years of experience do you have in Docker?"*. A tool you haven't listed falls back to `Total experience`, so an unfamiliar technology is never answered "No experience".
- **`Notice period`** also drives the *"what's your last working day?"* answer — set `15` and it replies with today + 15 days.
- **`Resume path`** must be a full path to a PDF. On Windows use forward slashes (`C:/Users/...`) or doubled backslashes.
- Fields you leave blank are **asked** during a run rather than submitted empty.

Your Naukri **password is never stored** — anywhere. It's typed fresh each run. Your email is remembered in `.env` so you don't retype it.

---

## How it works

```
   your config.json                    Naukri.com
         │                                  │
         ▼                                  ▼
   ┌───────────┐   role + experience   ┌──────────┐
   │ JobSprint │ ────────────────────► │  search  │
   └───────────┘                       └────┬─────┘
         ▲                                  │ each result
         │  answers                         ▼
   ┌─────┴───────────────┐            ┌──────────┐
   │ 1. config.json      │◄───────────│  apply   │
   │ 2. pattern reader   │  questions │   form   │
   │ 3. question store   │            └──────────┘
   └─────────────────────┘
         │ doesn't know it?
         ▼
     asks you once, remembers forever
```

**A run has three steps.** It asks for your account, then role/experience/location/how-many, then starts applying. Each answer becomes next run's default, so repeat runs are just Enter, Enter, Enter.

**Answering the forms.** There's **no machine-learning model here and nothing is "trained"**, despite the `--train` flag's name. Three deterministic layers, in order:

1. **Your config** — name, CTC, notice period, skills.
2. **A pattern reader** — anything shaped like *"years of experience in X"* has `X` pulled out of the question and looked up in your `Skills` map, fuzzily, so "Dockers" finds Docker and "Teraform" finds Terraform.
3. **A question store** — ~60 known intents, each with several phrasings, matched by fuzzy string similarity. Above 90% confidence it answers; below, it asks you.

**It never guesses.** Anything the three layers don't cover stops and asks you in the terminal:

```
❓ New question
  Are you okay with a 3-year bond?

  Your answer (Enter alone skips this job):
```

Whatever you type is saved, so it's answered automatically from then on. Judgement calls — salary cuts, bonds, visas — deliberately stay with you. Fix a wrong answer any time with `--edit-answers`.

---

## Dependencies

Everything below is installed for you by the install step — this is just what's in the box and why.

| Package | Why it's needed |
|---|---|
| **playwright** | drives the Chromium browser that does the applying |
| **rich** | the terminal interface — panels, colour, the wordmark |
| **questionary** | arrow-key menus |
| **colorama** | ANSI colour on older Windows consoles |
| **rapidfuzz** | fuzzy matching of application questions |
| **python-dotenv** | reads `.env` |
| **pdfplumber** | pulls skills out of your resume PDF |
| **fastapi**, **uvicorn**, **websockets**, **python-multipart**, **pydantic** | the optional desktop dashboard's server |
| **openpyxl** | Excel tracker of what was applied to |
| **pywebview** (+ **pythonnet**, **clr_loader** on Windows) | native window around the dashboard |

Plus **Chromium**, fetched by `python -m playwright install chromium`.

Exact pins are in [`requirements.txt`](requirements.txt); pip resolves everything transitive.

---

## Commands

Run these from an activated virtual environment (`venv\Scripts\activate` on Windows, `source venv/bin/activate` on macOS).

| Command | What it does |
|---|---|
| `jobsprint.bat` / `./jobsprint.sh` | **Start the bot.** One click: set up, sign in, apply |
| `python -m jobsprint --apply` | The same thing, from an activated venv |
| `python -m jobsprint --apply --jobs 25` | Skip the "how many jobs" question |
| `python -m jobsprint --apply --email you@example.com` | Skip the account picker |
| `python -m jobsprint --train` | Rebuild the question store from `config.json` |
| `python -m jobsprint --edit-answers` | Review, fix or delete answers it has learned |
| `python -m jobsprint.desktop` | Open the desktop dashboard |
| `python -m jobsprint -h` | Full option list |

---

## Where your data lives

Nothing personal is kept inside the repo. Your profile, learned answers, session logs and the Excel tracker live outside it:

| | |
|---|---|
| **Windows** | `%LOCALAPPDATA%\JobSprint\` |
| **macOS / Linux** | `~/.jobsprint/` |

So pulling updates, or deleting the checkout entirely, never touches your data. The only local files the repo holds are `config.json` (your answers, copied from `config.example.json` and gitignored) and `.env` (your saved email — gitignored, never published).

---

## Project layout

```
jobsprint.bat  jobsprint.sh   ← start here
config.example.json           ← template; copy to config.json and edit
config.json                   ← your answers (gitignored)
requirements.txt
setup/                        ← one-time environment setup
packaging/                    ← builds the Windows .exe installer
jobsprint/
├── __main__.py               ← argument parsing
├── desktop.py                ← dashboard entry point
├── paths.py                  ← where app data lives
├── cli/                      ← the terminal interface
│   ├── theme.py                  palette, wordmark, cards
│   ├── prompts.py                arrow-key menus, typed input
│   ├── credentials.py            email (saved) + password (never saved)
│   ├── questions.py              asking about an unknown question
│   └── flows.py                  train / apply / edit-answers
├── automation/               ← the browser work
│   ├── naukri.py                 search, apply, chatbot handling
│   └── browser.py                first-run Chromium setup
├── knowledge/                ← how questions get answered
│   ├── skills.py                 the pattern reader
│   ├── seed_intents.py           the built-in question corpus
│   ├── matcher.py                fuzzy matching + the "don't guess" rule
│   ├── resolver.py               intent → live value from your config
│   └── store.py                  SQLite
├── preferences/              ← config.json + search settings
├── resume/                   ← resume parsing, job match scoring
├── tracker/                  ← Excel export
├── dashboard/                ← the optional web UI
└── workers/                  ← session orchestration
```

---

## Desktop dashboard (optional)

A GUI over the same engine — live progress, a Profile editor, and the Excel tracker:

```bash
python -m jobsprint.desktop
```

Works as-is on **Windows** and **macOS**. On **Linux** it needs a system webview backend that pip can't install:

```bash
sudo apt install python3-gi gir1.2-webkit2-4.0     # or: pip install pywebview[qt]
```

The CLI needs none of that.

### Building the Windows installer

```bat
pip install -r packaging\requirements-build.txt
venv\Scripts\pyinstaller.exe packaging\jobsprint.spec --noconfirm
"C:\Program Files (x86)\Inno Setup 6\ISCC.exe" packaging\installer.iss
```

Produces `dist\JobSprint\JobSprint.exe`, then `dist_installer\JobSprint-Setup.exe`. Per-user, no admin rights needed.

---

## Troubleshooting

| Problem | Fix |
|---|---|
| `python` not recognised (Windows) | Reinstall Python with **"Add python.exe to PATH"** ticked |
| `python: command not found` (macOS) | Use `python3`, or `brew install python` |
| `No module named 'playwright'` (or rich, questionary…) | Re-run `setup\install.bat` / `./setup/install.sh` |
| `Executable doesn't exist` | `python -m playwright install chromium` |
| Chromium won't launch (Linux) | `python -m playwright install-deps chromium` |
| `./jobsprint.sh: Permission denied` | `chmod +x jobsprint.sh setup/install.sh` |
| Login failed | Re-check the password — it's asked fresh each run and never stored |
| Wrong account picked | `python -m jobsprint --apply --email you@example.com` |
| It asked something it should know | Answer once; it's remembered. Or add the field to `config.json` |
| It answered something wrong | `python -m jobsprint --edit-answers` |
| Menus show numbers instead of arrow keys | That terminal has no full-screen buffer; the numbered fallback works the same |
| "Chromium's sandbox is unavailable" warning (Ubuntu 23.10+) | Ubuntu's AppArmor blocks the sandbox. Allow it for Playwright's Chromium — see below |

**Enabling Chromium's sandbox on Ubuntu 23.10+** (one-time, needs sudo):

```bash
sudo tee /etc/apparmor.d/playwright-chromium >/dev/null <<EOF
abi <abi/4.0>,
include <tunables/global>
profile playwright-chromium $HOME/.cache/ms-playwright/chromium-*/chrome-linux/chrome flags=(unconfined) {
  userns,
}
EOF
sudo apparmor_parser -r /etc/apparmor.d/playwright-chromium
```

---

## Licence

[GNU GPL v3](LICENSE).

> Use this on your own Naukri account, at a sensible pace. You're responsible for what gets submitted under your name — keep `config.json` accurate.
