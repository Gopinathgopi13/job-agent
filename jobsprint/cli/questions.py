"""Answering an application question the knowledge base doesn't already cover.

A drop-in, synchronous stand-in for workers/pending_question.py's
PendingQuestionRegistry. The desktop app answers these from its browser UI on
another thread; the CLI has no second thread to answer from, so this just asks
in the terminal and returns immediately — same `.submit()` contract, none of
the threading/event-bus machinery.

Whatever gets typed here is written into the same knowledge base `--train`
builds (via knowledge/matcher.py's teach()), so each question is only ever
asked once — every later application answers it automatically.
"""

from .prompts import ask_text, choose
from .theme import ACCENT, MUTED, WARN, console

_TYPE_INSTEAD = "__type_instead__"


class TerminalQuestionPrompt:
    def submit(self, question, candidates=None, suggested_answer=None, job_ctx=None,
               timeout=None, options=None):
        console.print()
        console.rule(
            f"[bold {WARN}]❓ {'Confirm this answer' if suggested_answer else 'New question'}[/bold {WARN}]",
            style=WARN,
        )
        console.print(f"\n  [bold]{question}[/bold]\n")

        if job_ctx and job_ctx.get("title"):
            console.print(f"  [{MUTED}]for: {job_ctx['title']}[/{MUTED}]\n")

        if options:
            # The page already offers a fixed set of choices (a radio/checkbox
            # group or a dropdown) — pick from those instead of typing free
            # text that then has to be fuzzy-matched back onto them.
            menu = [(opt, opt) for opt in options]
            menu.append(("Type something else…", _TYPE_INSTEAD))
            default = suggested_answer if suggested_answer in options else None
            picked = choose("Pick an answer", menu, default=default)
            answer = (
                ask_text("Your answer", default=suggested_answer or "", hint="Enter alone skips this job")
                if picked == _TYPE_INSTEAD else picked
            )
        else:
            answer = ask_text(
                "Your answer", default=suggested_answer or "", hint="Enter alone skips this job"
            )

        if answer:
            console.print(f"  [{ACCENT}]Saved — it won't ask again.[/{ACCENT}]\n")
        return answer or None
