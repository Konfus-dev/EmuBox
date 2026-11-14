"""The command line: asks what you want, then installs it.

    ./install                 ask about everything
    ./install --yes           take every default, ask nothing
    ./install --list          show what can be installed
    ./install --remove ID...  take components off again
    ./backup-games FOLDER     copy the games on a Batocera drive into a library folder
"""
from __future__ import annotations

import argparse
import os
import shutil
import subprocess
import sys
import tempfile
from contextlib import contextmanager
from pathlib import Path

from . import components, library
from .components import Component, Env
from .fetch import FetchError, fetch, is_url, without_secrets
from .host import Host, expand
from .library import Library, Selection
from .prompts import NoAnswer, Prompts
from .target import Target

REPO = Path(__file__).resolve().parent.parent
MENU_SERVICE = "/etc/init.d/S31emulationstation"


class Stop(Exception):
    """Something the person has to sort out; shown as a plain message."""


# --- small helpers ----------------------------------------------------------------------

def parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(prog="install", description="RetroBox: a look, apps, settings, BIOS files and games for Batocera.")
    p.add_argument("--target", metavar="FOLDER", help="the Batocera data folder (default: found automatically)")
    p.add_argument("--yes", action="store_true", help="take the default answer to every question")
    p.add_argument("--with", dest="include", metavar="IDS", help="with --yes: install exactly these, comma-separated (see --list)")
    p.add_argument("--set", dest="values", action="append", default=[], metavar="ID.FIELD=VALUE",
                   help="answer a component's question in advance, e.g. --set wifi.ssid=Home "
                        "(for passwords prefer the environment: RETROBOX_WIFI_KEY=...)")
    p.add_argument("--bios", metavar="WHERE", help="BIOS library: a folder or a repository address")
    p.add_argument("--games", metavar="WHERE", help="games library: a folder or a repository address")
    p.add_argument("--bios-systems", metavar="IDS", help="only these systems' BIOS files, comma-separated")
    p.add_argument("--game-systems", dest="games_systems", metavar="IDS", help="only these systems' games, comma-separated")
    p.add_argument("--list", action="store_true", help="show what can be installed and what is installed")
    p.add_argument("--remove", nargs="+", metavar="ID", help="take these components off the drive")
    p.add_argument("--backup-games", metavar="FOLDER", help="copy the drive's games into this library folder")
    return p


def find_target(args, ask: Prompts) -> Target:
    if args.target:
        root = expand(args.target)
        if not Target.looks_right(root):
            raise Stop(f"{root} is not a Batocera data folder (it should contain 'system' and 'roms').")
        return Target(root)
    found = Target.find()
    if len(found) == 1:
        ask.say(f"Batocera found at {found[0]}")
        return Target(found[0])
    if found:
        picked = ask.choose("More than one Batocera drive is connected:", [str(p) for p in found])
        if len(picked) != 1:
            raise Stop("Pick one drive, or name it with --target.")
        return Target(found[picked[0]])
    ask.say("No Batocera drive found. Plug it in and open it in the file manager, or type where it is.")
    root = expand(ask.text("Batocera data folder (the one containing 'system' and 'roms')"))
    if not Target.looks_right(root):
        raise Stop(f"{root} is not a Batocera data folder.")
    return Target(root)


def become_root_if_needed(target: Target, argv: list[str], ask: Prompts) -> None:
    """Batocera's system folder belongs to root; restart through sudo when we cannot write it."""
    if target.writable():
        return
    if os.geteuid() == 0:
        raise Stop(f"{target.root} cannot be written, even as administrator. Is the drive read-only?")
    if not sys.stdin.isatty() or not shutil.which("sudo"):
        raise Stop(f"{target.root} belongs to the administrator. Run this again with sudo.")
    ask.say("Batocera's system folder belongs to the administrator; asking for your password to continue.")
    if "--target" not in argv:
        argv = ["--target", str(target.root), *argv]
    os.chdir(REPO)
    os.execvp("sudo", ["sudo", sys.executable, "-m", "installer", *argv])


@contextmanager
def menu_paused(target: Target, needed: bool, say):
    """On Batocera itself the menu rewrites its settings when it quits, so stop it while we change them."""
    pause = needed and target.live and os.path.exists(MENU_SERVICE)
    if pause:
        say("Stopping Batocera's menu while its settings are changed...")
        subprocess.run([MENU_SERVICE, "stop"], check=False)
    try:
        yield
    finally:
        if pause:
            subprocess.run([MENU_SERVICE, "start"], check=False, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)


class Downloads:
    """Repositories fetched during this run, cleaned up at the end."""

    def __init__(self, target: Target):
        # Batocera keeps /tmp in memory, so on Batocera itself we use the drive.
        self.base = Path(tempfile.mkdtemp(prefix="retrobox-", dir=target.path("system") if target.live else None))

    def get(self, url: str, name: str) -> Path:
        return fetch(url, self.base / name)

    def clean(self) -> None:
        shutil.rmtree(self.base, ignore_errors=True)


# --- the questions ----------------------------------------------------------------------

def typed_answers(component: Component, args, ask: Prompts) -> dict[str, str]:
    """What a component needs typed in (a network name, an account). Given ahead with --set or
    RETROBOX_<ID>_<FIELD>, asked for otherwise."""
    given = dict(item.split("=", 1) for item in args.values if "=" in item)
    answers = {}
    for wanted in component.spec.get("ask", []):
        name = f"{component.id}.{wanted['id']}"
        variable = "RETROBOX_" + name.upper().replace(".", "_").replace("-", "_")
        while True:
            if name in given:
                answer = given[name]
            elif variable in os.environ:
                answer = os.environ[variable]
            elif wanted.get("secret"):
                answer = ask.secret(f"  {wanted['question']}")
            else:
                answer = ask.text(f"  {wanted['question']}") if not wanted.get("optional") else ask.text_or_empty(f"  {wanted['question']}")
            problem = None
            if not answer and not wanted.get("optional"):
                problem = "This cannot be empty."
            elif any(bad in answer for bad in [*wanted.get("reject", []), "\n"]):
                problem = wanted.get("reject_message", "That contains a character that cannot be stored.")
            if problem is None:
                break
            if name in given or variable in os.environ or ask.assume_defaults:
                raise Stop(f"{name}: {problem}")
            ask.say(f"  {problem}")
        answers[wanted["id"]] = answer
    return answers


def choose_components(everything: dict[str, Component], env: Env, args, ask: Prompts) -> list[str]:
    offered = [c for c in everything.values() if not c.hidden and components.available(c, env)]
    if args.include is not None:
        wanted = [i for i in args.include.split(",") if i]
        unknown = [i for i in wanted if i not in {c.id for c in offered}]
        if unknown:
            raise Stop(f"Not available here: {', '.join(unknown)}. See --list.")
        chosen = [everything[i] for i in wanted]
    else:
        chosen = []
        for component in offered:
            if ask.yes_no(component.question, component.default):
                env.answers[component.id] = typed_answers(component, args, ask)
                chosen.append(component)
        return [c.id for c in chosen]
    for component in chosen:
        env.answers[component.id] = typed_answers(component, args, ask)
    return [c.id for c in chosen]


def open_library(kind: str, where: str, downloads: Downloads) -> Library:
    if is_url(where):
        return Library(downloads.get(where, kind), kind)
    folder = expand(where)
    if not folder.is_dir():
        raise Stop(f"{folder} is not a folder.")
    return Library(folder, kind)


def choose_from_library(library_: Library, only: str | None, ask: Prompts) -> Selection:
    found = library_.systems()
    if not found:
        raise Stop(f"No {library_.noun}s found in {library_.root}. It should hold one folder per system (psx, snes...).")
    if only:
        wanted = only.split(",")
        missing = set(wanted) - {s.id for s in found}
        if missing:
            raise Stop(f"Not in the library: {', '.join(sorted(missing))}.")
        return [(s, s.items) for s in found if s.id in wanted]
    picked = [found[i] for i in ask.choose("Systems in this library:", [s.label(library_.noun) for s in found])]
    if library_.kind == "bios" or ask.yes_no("All games on these systems?", True):
        return [(s, s.items) for s in picked]
    selection = []
    for system in picked:
        heading = f"{system.label('game')}:"
        items = [system.items[i] for i in ask.choose(heading, [f"{g.name} ({library.human(g.size)})" for g in system.items])]
        selection.append((system, items))
    return selection


def ask_library(kind: str, title: str, args, target: Target, downloads: Downloads, ask: Prompts) -> tuple[Library, Selection] | None:
    where = getattr(args, kind)
    if not where:
        if args.yes or not ask.yes_no(f"Install {title}?", False):
            return None
        remembered = target.manifest().get("sources", {}).get(kind, "")
        if remembered and not is_url(remembered) and not expand(remembered).is_dir():
            remembered = ""   # a folder that has moved since
        where = ask.text("  Where are they? A repository address or a folder", remembered)
    library_ = open_library(kind, where, downloads)
    selection = choose_from_library(library_, getattr(args, f"{kind}_systems"), ask)
    manifest = target.manifest()
    manifest.setdefault("sources", {})[kind] = without_secrets(where)
    target.save_manifest(manifest)
    return library_, selection


def summary(chosen: list[Component], libraries: list[tuple[str, Library, Selection]], target: Target, ask: Prompts) -> None:
    ask.say()
    ask.say(f"About to install onto {target.root}:")
    for component in chosen:
        ask.say(f"  - {component.title}")
    for title, library_, selection in libraries:
        count = sum(len(items) for _system, items in selection)
        size = library.human(library.needed_bytes(selection, target, library_.kind))
        ask.say(f"  - {title}: {count} {library_.noun}{'' if count == 1 else 's'} on {len(selection)} system(s), {size} to copy")
    if not chosen and not libraries:
        raise Stop("Nothing chosen, so nothing to do.")


# --- the commands -------------------------------------------------------------------------

def run_install(args, target: Target, ask: Prompts) -> None:
    downloads = Downloads(target)
    try:
        everything = components.discover(REPO)
        env = Env(target=target, repo=REPO, host=Host(), fetch=downloads.get, say=ask.say)
        ask.say()
        ids = components.with_requirements(choose_components(everything, env, args, ask), everything)
        chosen = [everything[i] for i in ids]
        libraries = []
        for kind, title in (("bios", "BIOS files"), ("games", "games")):
            picked = ask_library(kind, title, args, target, downloads, ask)
            if picked:
                libraries.append((title, *picked))
        summary(chosen, libraries, target, ask)
        if not ask.yes_no("Go ahead?", True):
            raise Stop("Nothing was changed.")

        ask.say()
        with menu_paused(target, any(c.spec.get("es_settings") for c in chosen), ask.say):
            for component in chosen:
                ask.say(f"Installing {component.title}...")
                components.remember(target, component, components.install(component, env))
        for title, library_, selection in libraries:
            ask.say(f"Copying {title}...")
            library.install(library_, selection, target, ask.say)
        os.sync()
    finally:
        downloads.clean()

    ask.say()
    ask.say("Done.")
    for component in chosen:
        if component.spec.get("after"):
            ask.say(f"  {component.title}: {component.spec['after']}")
    if not target.live:
        ask.say("  Eject the drive, then boot Batocera from it.")
    elif libraries:
        ask.say("  To see new games: Main menu > Game settings > Update gamelists.")


def run_list(target: Target | None, ask: Prompts) -> None:
    everything = components.discover(REPO)
    installed = target.manifest()["components"] if target else {}
    env = Env(target=target, repo=REPO, host=Host(), fetch=lambda *_: REPO)
    for component in everything.values():
        if component.hidden:
            continue
        notes = [n for n, yes in (("installed", component.id in installed),
                                  ("not available on this PC", not components.available(component, env))) if yes]
        ask.say(f"  {component.id:<14} {component.title}{'  (' + ', '.join(notes) + ')' if notes else ''}")


def run_remove(ids: list[str], target: Target, ask: Prompts) -> None:
    for component_id in ids:
        done = components.uninstall(component_id, target)
        ask.say(f"Removed {component_id}." if done else f"{component_id} is not installed.")
    remaining = target.manifest()["components"]
    if "runtime" in remaining and not any(f"system/retrobox/apps/" in f for e in remaining.values() for f in e["files"]):
        components.uninstall("runtime", target)   # no apps left that need it
        ask.say("Removed RetroBox app support (no apps left).")


def run_backup(folder: str, args, target: Target, ask: Prompts) -> None:
    destination = expand(folder)
    selection = choose_from_library(Library(target.root, "games"), args.games_systems, ask)
    ask.say(f"Backing up to {destination}...")
    library.backup(selection, destination, ask.say)
    ask.say("Done. Small games can be committed to git from there; MANIFEST.tsv lists everything.")


def main(argv: list[str] | None = None) -> int:
    argv = sys.argv[1:] if argv is None else argv
    args = parser().parse_args(argv)
    ask = Prompts(assume_defaults=args.yes)
    try:
        ask.say("RetroBox")
        if args.list:
            found = Target.find()
            run_list(Target(expand(args.target)) if args.target else Target(found[0]) if len(found) == 1 else None, ask)
            return 0
        target = find_target(args, ask)
        if args.backup_games:
            run_backup(args.backup_games, args, target, ask)
            return 0
        become_root_if_needed(target, argv, ask)
        if args.remove:
            run_remove(args.remove, target, ask)
        else:
            run_install(args, target, ask)
        return 0
    except (Stop, FetchError, library.NotEnoughSpace) as problem:
        ask.say(f"\n{problem}")
        return 1
    except NoAnswer as question:
        ask.say(f"\nThis needs an answer, and none can be asked for here: {question}")
        return 1
    except KeyboardInterrupt:
        ask.say("\nStopped.")
        return 130
