"""The look of the terminal UI — one place for the palette, the wordmark,
step headers, and result cards, so every screen is styled the same way
instead of each flow inventing its own formatting.
"""

import logging
import sys

# Must happen before the Console below is built, and before anything renders.
# Some Windows consoles report an ANSI-incapable terminal, which drops Rich
# onto a legacy renderer that writes through the OS codepage (usually cp1252).
# That codepage can't encode the box-drawing wordmark or the step icons, and
# the very first print raises UnicodeEncodeError. This lives here rather than
# in __main__ so it also covers anything importing the CLI directly.
for _stream in (sys.stdout, sys.stderr):
    if hasattr(_stream, "reconfigure"):
        try:
            _stream.reconfigure(encoding="utf-8", errors="replace")
        except Exception:
            pass

from rich.align import Align
from rich.box import DOUBLE, ROUNDED, SIMPLE_HEAD
from rich.console import Console, Group
from rich.logging import RichHandler
from rich.padding import Padding
from rich.panel import Panel
from rich.table import Table
from rich.text import Text

console = Console()

# ── palette ────────────────────────────────────────────────────────
BRAND = "#d787ff"      # violet — headings, borders, the SPRINT half
ACCENT = "#00d7ff"     # cyan — prompts, labels, the JOB half
MUTED = "grey54"
OK = "#5fd75f"
WARN = "#ffaf5f"
BAD = "#ff5f5f"
AUTHOR = "Rahul Swargam"

# ── wordmark ───────────────────────────────────────────────────────
# Box-drawing capitals. Every letter cell in "JOB" is exactly 4 columns
# wide, so slicing each line at column 12 splits JOB from SPRINT cleanly
# and lets the two halves take different colours.
_WORDMARK = (
    "  ╦ ╔═╗ ╔╗  ╔═╗ ╔═╗ ╦═╗ ╦ ╔╗╔ ╔╦╗",
    "  ║ ║ ║ ╠╩╗ ╚═╗ ╠═╝ ╠╦╝ ║ ║║║  ║ ",
    "╚═╝ ╚═╝ ╚═╝ ╚═╝ ╩   ╩╚═ ╩ ╝╚╝  ╩ ",
)
_SPLIT = 12
_RULE = "─" * 33


def banner(tagline="Naukri job applications, on autopilot"):
    art = Text(justify="center")
    for i, line in enumerate(_WORDMARK):
        if i:
            art.append("\n")
        art.append(line[:_SPLIT], style=f"bold {ACCENT}")
        art.append(line[_SPLIT:], style=f"bold {BRAND}")

    art.append(f"\n{_RULE}\n", style=MUTED)
    art.append(tagline, style="italic grey70")
    art.append("\n\nCreated by ", style=MUTED)
    art.append(AUTHOR, style=f"bold {BRAND}")

    console.print()
    console.print(
        Panel(art, border_style=BRAND, box=DOUBLE, padding=(1, 6)),
        justify="center",
    )


def step(number, total, title, icon=""):
    """A numbered stage header, so a run reads as a sequence rather than an
    undifferentiated wall of prompts."""
    heading = Text()
    heading.append(f" {icon} " if icon else " ")
    heading.append(title.upper(), style=f"bold {ACCENT}")
    heading.append(f"   step {number} of {total} ", style=MUTED)

    console.print()
    console.print(Panel(heading, border_style=MUTED, box=ROUNDED, padding=(0, 1), expand=True))
    console.print()


def field_table(rows):
    grid = Table.grid(padding=(0, 3))
    grid.add_column(style=MUTED, justify="right")
    grid.add_column(style="bold white")
    for label, value in rows:
        grid.add_row(label, str(value))
    return grid


def card(rows, title, border=BRAND, footer=None):
    body = field_table(rows)
    if footer:
        body = Group(body, Text(""), Text(footer, style=f"italic {MUTED}"))
    console.print(
        Panel(Padding(body, (1, 2)), title=f"[bold {border}]{title}[/bold {border}]",
              border_style=border, box=ROUNDED, title_align="left")
    )


def note(message, style=MUTED, bullet="·"):
    console.print(f"  [{style}]{bullet} {message}[/{style}]")


def result(headline, title, border=OK, detail=None):
    body = Text(headline, style=f"bold {border}", justify="center")
    if detail:
        body = Group(body, Text(""), Text(detail, style=MUTED, justify="center"))
    console.print()
    console.print(
        Panel(Align.center(body), title=f"[bold {border}]{title}[/bold {border}]",
              border_style=border, box=ROUNDED, padding=(1, 4))
    )


def alert(message, title="Something went wrong", border=BAD):
    console.print()
    console.print(
        Panel(Text(message), title=f"[bold {border}]{title}[/bold {border}]",
              border_style=border, box=ROUNDED, title_align="left")
    )


def listing(headers, rows, title=None):
    table = Table(
        box=SIMPLE_HEAD, header_style=f"bold {ACCENT}", show_edge=False,
        title=title, title_style=f"bold {BRAND}", title_justify="left",
        pad_edge=False, padding=(0, 2),
    )
    for header, justify in headers:
        table.add_column(header, justify=justify)
    for row in rows:
        table.add_row(*[str(cell) for cell in row])
    console.print(table)


def attach_rich_logging(logger):
    """Route the bot's own log records through Rich so a live run reads as
    colour-coded, aligned output instead of raw `[timestamp] LEVEL - text`.

    Only the console handler is swapped — the session log file keeps its
    plain, greppable format. `markup=False` matters: log lines carry job
    titles and Playwright selectors full of square brackets, which Rich
    would otherwise try (and fail) to parse as style tags.
    """
    for handler in list(logger.handlers):
        if isinstance(handler, logging.StreamHandler) and not isinstance(handler, logging.FileHandler):
            logger.removeHandler(handler)

    rich_handler = RichHandler(
        console=console, markup=False, rich_tracebacks=False,
        show_path=False, omit_repeated_times=False, log_time_format="[%H:%M:%S]",
    )
    rich_handler.setFormatter(logging.Formatter("%(message)s"))
    logger.addHandler(rich_handler)
    return logger
