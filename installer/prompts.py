"""Questions asked in the terminal. Nothing here knows about Batocera."""
from __future__ import annotations

import re
import sys


class NoAnswer(Exception):
    """A question needed an answer but we were told not to ask (--yes) or have no terminal."""


class Prompts:
    def __init__(self, assume_defaults: bool = False):
        self.assume_defaults = assume_defaults

    def say(self, text: str = "") -> None:
        print(text, file=sys.stdout, flush=True)

    def _read(self, prompt: str) -> str:
        try:
            return input(prompt).strip()
        except EOFError:
            raise NoAnswer(prompt) from None

    def yes_no(self, question: str, default: bool = True) -> bool:
        if self.assume_defaults:
            return default
        hint = "Y/n" if default else "y/N"
        while True:
            answer = self._read(f"{question} [{hint}] ").lower()
            if not answer:
                return default
            if answer in ("y", "yes"):
                return True
            if answer in ("n", "no"):
                return False
            self.say("  Please answer y or n.")

    def text(self, question: str, default: str = "") -> str:
        if self.assume_defaults:
            if default:
                return default
            raise NoAnswer(question)
        hint = f" [{default}]" if default else ""
        while True:
            answer = self._read(f"{question}{hint}: ") or default
            if answer:
                return answer

    def choose(self, heading: str, options: list[str]) -> list[int]:
        """Pick any number of options. Returns their positions; everything by default."""
        everything = list(range(len(options)))
        if self.assume_defaults or not options:
            return everything
        self.say(heading)
        for number, option in enumerate(options, 1):
            self.say(f"  {number:>2}) {option}")
        while True:
            answer = self._read("Which ones? Numbers like 1,3-5, or Enter for all: ").lower()
            if answer in ("", "a", "all"):
                return everything
            try:
                return parse_numbers(answer, len(options))
            except ValueError as problem:
                self.say(f"  {problem}")


def parse_numbers(text: str, count: int) -> list[int]:
    """'1,3-5' -> [0, 2, 3, 4]. Raises ValueError with a message for the person typing."""
    picked: set[int] = set()
    for part in re.split(r"[,\s]+", text.strip()):
        if not part:
            continue
        match = re.fullmatch(r"(\d+)(?:-(\d+))?", part)
        if not match:
            raise ValueError(f"'{part}' is not a number or a range like 2-4.")
        first, last = int(match[1]), int(match[2] or match[1])
        if not 1 <= first <= last <= count:
            raise ValueError(f"'{part}' is outside 1-{count}.")
        picked.update(range(first - 1, last))
    if not picked:
        raise ValueError("Nothing chosen.")
    return sorted(picked)
