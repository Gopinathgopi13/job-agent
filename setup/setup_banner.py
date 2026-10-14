"""Shows the JOBSPRINT wordmark during first-time setup — before the venv
exists, so this has to run with the bare system Python and can't import
anything third-party (no rich, no colorama). It writes raw ANSI escapes
directly, same colours as jobsprint/cli/theme.py's real banner, so the setup
screen and the app itself look like one thing rather than two.

Cosmetic only: setup/install.bat and setup/install.sh call this and ignore
whatever it does, so a terminal that chokes on UTF-8 or ANSI never blocks
the actual install.
"""

import sys

for _stream in (sys.stdout, sys.stderr):
    if hasattr(_stream, "reconfigure"):
        try:
            _stream.reconfigure(encoding="utf-8", errors="replace")
        except Exception:
            pass

BRAND = "\x1b[1m\x1b[38;2;215;135;255m"   # bold violet — matches theme.py's BRAND
ACCENT = "\x1b[1m\x1b[38;2;0;215;255m"    # bold cyan — matches theme.py's ACCENT
MUTED = "\x1b[38;5;246m"
RESET = "\x1b[0m"

WORDMARK = (
    "  ╦ ╔═╗ ╔╗  ╔═╗ ╔═╗ ╦═╗ ╦ ╔╗╔ ╔╦╗",
    "  ║ ║ ║ ╠╩╗ ╚═╗ ╠═╝ ╠╦╝ ║ ║║║  ║ ",
    "╚═╝ ╚═╝ ╚═╝ ╚═╝ ╩   ╩╚═ ╩ ╝╚╝  ╩ ",
)
SPLIT = 12
RULE = "─" * 33


def main():
    print()
    for line in WORDMARK:
        print(f"{ACCENT}{line[:SPLIT]}{RESET}{BRAND}{line[SPLIT:]}{RESET}")
    print(f"{MUTED}{RULE}{RESET}")
    print("Naukri job applications, on autopilot")
    print(f"{MUTED}Created by {RESET}{BRAND}Rahul Swargam{RESET}")
    print()
    print(f"{MUTED}First-time setup — installing dependencies once.{RESET}")
    print()


if __name__ == "__main__":
    main()
