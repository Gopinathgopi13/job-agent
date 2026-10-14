"""Input widgets shared by the CLI flows.

`choose` is the arrow-key menu everything selectable goes through; it falls
back to a numbered prompt on terminals that can't host a full-screen menu
(some embedded/non-interactive consoles have no real screen buffer, and
prompt_toolkit raises rather than degrading on its own).
"""

import questionary
from questionary import Choice
from rich.prompt import IntPrompt, Prompt

from .theme import ACCENT, MUTED, console

MENU_STYLE = questionary.Style([
    ("qmark", "fg:#d787ff bold"),
    ("question", "bold"),
    ("pointer", "fg:#00d7ff bold"),
    ("highlighted", "fg:#00d7ff bold"),
    ("selected", "fg:#d787ff bold"),
    ("answer", "fg:#00d7ff bold"),
    ("instruction", "fg:#767676"),
])

CANCELLED = object()


def choose(message, choices, default=None):
    """`choices` is a list of (label, value). Ctrl+C / Esc bails out of the
    whole run rather than quietly returning nothing."""
    try:
        menu = questionary.select(
            message,
            choices=[Choice(title=label, value=value) for label, value in choices],
            style=MENU_STYLE,
            default=default,
            instruction="(↑/↓ then Enter)",
        )
        picked = menu.ask()
        if picked is None:
            raise KeyboardInterrupt
        return picked
    except KeyboardInterrupt:
        raise
    except Exception:
        console.print(f"[{ACCENT}]{message}[/{ACCENT}]")
        for i, (label, _value) in enumerate(choices, 1):
            console.print(f"  [bold yellow]{i}[/bold yellow]  {label}")
        # Honour the same default the arrow-key menu would have pre-selected,
        # so both paths behave identically when you just press Enter.
        preselected = next(
            (i for i, (_l, value) in enumerate(choices, 1) if value == default), 1
        )
        index = IntPrompt.ask(f"[{ACCENT}]Choice[/{ACCENT}]", default=preselected)
        index = max(1, min(index, len(choices)))
        return choices[index - 1][1]


def ask_text(label, default="", hint=""):
    # Rich shows `(default)` next to the prompt any time a default is passed
    # at all — even an empty string renders as a bare, ugly "()". Only pass
    # one through when there's an actual value worth offering back.
    suffix = f" [{MUTED}]({hint})[/{MUTED}]" if hint else ""
    kwargs = {"default": default} if default else {}
    return Prompt.ask(f"[{ACCENT}]{label}[/{ACCENT}]{suffix}", **kwargs).strip()


def ask_int(label, default, hint=""):
    suffix = f" [{MUTED}]({hint})[/{MUTED}]" if hint else ""
    return IntPrompt.ask(f"[{ACCENT}]{label}[/{ACCENT}]{suffix}", default=default)


def ask_required_int(label, hint=""):
    """Like ask_int, but with no default to fall back on — Rich itself won't
    accept a blank answer here, so it re-prompts until a number is typed."""
    suffix = f" [{MUTED}]({hint})[/{MUTED}]" if hint else ""
    return IntPrompt.ask(f"[{ACCENT}]{label}[/{ACCENT}]{suffix}")


def ask_required(label):
    value = ask_text(label)
    while not value:
        value = ask_text(f"{label} [red](required)[/red]")
    return value


# ── experience ─────────────────────────────────────────────────────
# Naukri's own search takes one number of years, not a range, so this
# mirrors its dropdown: Fresher (0) through 10, plus a typed escape hatch
# for anything higher.

_CUSTOM = "__custom__"


def ask_experience(default_years=3):
    options = [("Fresher (less than a year)", 0)]
    options += [(f"{y} year{'s' if y > 1 else ''}", y) for y in range(1, 11)]
    options.append(("Something else…", _CUSTOM))

    # questionary matches `default` against choice *values*, not their labels —
    # passing a label raises ValueError, which would quietly drop this prompt
    # into the numbered fallback instead of the arrow-key menu.
    preselect = default_years if any(value == default_years for _, value in options) else None
    picked = choose("Years of experience:", options, default=preselect)

    if picked == _CUSTOM:
        return max(0, min(ask_int("Years of experience", default=default_years or 0), 30))
    return picked
