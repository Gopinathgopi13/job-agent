"""Command-line entry point: `python -m jobsprint`."""

import argparse
import sys

# NB: cli.theme forces UTF-8 on stdout/stderr at import time — see the comment
# there. It has to happen before anything renders, which importing it does.
from .cli import flows
from .cli.theme import WARN, banner, console

EPILOG = """
examples:
  python -m jobsprint --apply
  python -m jobsprint --apply --jobs 25
  python -m jobsprint --apply --email you@example.com
  python -m jobsprint --train
  python -m jobsprint --edit-answers
"""


def build_parser():
    parser = argparse.ArgumentParser(
        prog="jobsprint",
        description="JobSprint — apply to Naukri jobs automatically.",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog=EPILOG,
    )
    parser.add_argument("--apply", action="store_true",
                        help="Run an auto-apply session")
    parser.add_argument("--train", action="store_true",
                        help="Rebuild the question-answer store from config.json and exit")
    parser.add_argument("--edit-answers", action="store_true",
                        help="Review, fix, or delete answers the bot has learned")
    parser.add_argument("--email", default=None,
                        help="Naukri email (otherwise you're asked, and it's remembered)")
    parser.add_argument("--jobs", type=int, default=0,
                        help="How many jobs to apply to (skips the prompt)")
    parser.add_argument("--resume", default="",
                        help="Path to your resume PDF (defaults to the one in your profile)")
    return parser


def main():
    banner()
    args = build_parser().parse_args()

    if args.train:
        flows.run_train()
    elif args.edit_answers:
        flows.run_edit_answers()
    elif args.apply:
        flows.run_apply(args)
    else:
        flows.show_usage()


if __name__ == "__main__":
    try:
        main()
    except KeyboardInterrupt:
        console.print(f"\n[bold {WARN}]Stopped.[/bold {WARN}]\n")
        sys.exit(130)
