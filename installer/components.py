"""Components: the things the installer can put on a Batocera drive.

A component is a folder under components/ with a component.json that says
what it is and what to copy where. An app is a folder under apps/ with an
app.json; it becomes a component automatically. A component that needs more
than copying (a hardware check, an outside installer) adds a component.py
with `available(env)` and/or `install(env)`.

component.json:
    title          short name, shown in summaries
    question       the yes/no question the installer asks
    default        the answer when Enter is pressed (true/false)
    order          position in the list of questions
    hidden         true: never asked about; installed when another component requires it
    comes_with     (apps) the id of a component this app is installed along with, unasked
    requires       ids of components this one needs
    ask            things to type in when the component is chosen:
                   [{"id": "user", "question": "Username", "secret": false, "optional": false,
                     "reject": ["\\"], "reject_message": "..."}]
                   Use an answer as {user} in batocera_conf and es_settings values.
                   Answers are used once and never stored by the installer.
    files          [{"from": path here, "to": path on the drive, "mode": "755"}]
    flatpaks       Flathub programs to put on the drive now, so Batocera need not download them
                   (an app's own program is added by itself); skipped with --download-later
    folders        {"Games": {"system": "store", "image": "files/games.png", "icon": "gamepad",
                   "description": "..."}}: the picture and words of a sub-section tiles sit in
    ports          menu entries: name, description, image, and either "script" (a file here)
                   or "command" (one line to run). They go in Ports unless "system" names
                   another system folder (for example "store"); "folder" puts one in a
                   sub-section of that system (for example "Games"). "icon" names the
                   drawing on its picture (tools/dev/tile.py --icons); "icon_flatpak" or "icon_web"
                   say where the tile's own icon is to be found when the installer has a network.
    services       Batocera services to switch on
    batocera_conf  {"key": "value"} settings for batocera.conf
    es_settings    {"name": "value"} settings of the menu program
    renamed_from   ids this component had in older versions
    generated      files the component creates on Batocera while running, to remove with it:
                   [{"path": "...", "contains": "text that proves the file is ours"}]
    replaces       paths from older versions to delete
    retired_services  services from older versions to switch off
    after          a note printed when the installation is done
"""
from __future__ import annotations

import importlib.util
import json
import os
import sys
from datetime import date
from dataclasses import dataclass, field
from pathlib import Path
from types import ModuleType
from typing import Callable

from . import flatpak, gamelist
from .host import Host
from .target import OLD_MANIFESTS, Target

PORTS = "roms/ports"
APPS_ON_DRIVE = "system/emubox/apps"
OPEN_APP = "exec /userdata/system/emubox/bin/emubox-app open {id} --wait"


@dataclass
class Component:
    id: str
    folder: Path
    spec: dict
    hooks: ModuleType | None = None

    @property
    def title(self) -> str:
        return self.spec.get("title", self.id)

    @property
    def question(self) -> str:
        return self.spec.get("question", f"Install {self.title}?")

    @property
    def default(self) -> bool:
        return self.spec.get("default", True)

    @property
    def hidden(self) -> bool:
        return self.spec.get("hidden", False)

    @property
    def requires(self) -> list[str]:
        return self.spec.get("requires", [])


@dataclass
class Env:
    """What a component gets to work with while it is checked or installed."""
    target: Target
    repo: Path
    host: Host
    fetch: Callable[[str, str], Path]          # (address, name) -> folder with the downloaded repository
    component: Component | None = None
    say: Callable[[str], None] = print
    answers: dict[str, dict[str, str]] = field(default_factory=dict)   # component id -> what was typed for "ask"
    downloads: bool = True                     # fetch apps' programs onto the drive now


@dataclass
class Record:
    """What installing a component put on the drive, so it can be taken off again."""
    files: list[str] = field(default_factory=list)
    services: list[str] = field(default_factory=list)
    ports: list[str] = field(default_factory=list)


def _app_spec(app_id: str, app: dict) -> dict:
    """An app.json, seen as a component: its folder, plus an entry in the Ports menu."""
    return {
        "title": app["name"],
        "question": app.get("question", f"Install {app['name']}?"),
        "default": app.get("default", True),
        "order": app.get("order", 20),
        "requires": ["console"],
        "hidden": bool(app.get("comes_with")),
        "comes_with": app.get("comes_with"),
        "files": [{"from": ".", "to": f"{APPS_ON_DRIVE}/{app_id}"}],
        "flatpaks": [app["flatpak"]] if app.get("flatpak") else [],
        "replaces": [f"{PORTS}/{app['name']}.sh"],   # apps used to sit among the ports
        "ports": [{
            "system": "apps",
            "name": app["name"],
            "command": OPEN_APP.format(id=app_id),
            "image": "tile.png",
            "genre": "Apps",
            "description": app.get("description", ""),
            "app": app, "app_id": app_id,          # where the tile's own icon is looked for
        }],
    }


def _hooks(folder: Path, component_id: str) -> ModuleType | None:
    path = folder / "component.py"
    if not path.is_file():
        return None
    spec = importlib.util.spec_from_file_location(f"emubox_component_{component_id.replace('-', '_')}", path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def discover(repo: Path) -> dict[str, Component]:
    """Every component and app in the repository, in the order they are asked about."""
    found = []
    for path in sorted((repo / "components").glob("*/component.json")):
        found.append(Component(path.parent.name, path.parent, json.loads(path.read_text()), _hooks(path.parent, path.parent.name)))
    for path in sorted((repo / "apps").glob("*/app.json")):
        app_id = path.parent.name
        found.append(Component(app_id, path.parent, _app_spec(app_id, json.loads(path.read_text())), _hooks(path.parent, app_id)))
    found.sort(key=lambda c: (c.spec.get("order", 100), c.id))
    return {c.id: c for c in found}


def available(component: Component, env: Env) -> bool:
    """False when this component makes no sense here (hardware that is not present, say)."""
    check = getattr(component.hooks, "available", None)
    env.component = component
    return check(env) if check else True


def with_requirements(chosen: list[str], everything: dict[str, Component]) -> list[str]:
    """The chosen ids with what they need added in front, each once, and after them
    whatever "comes_with" one of them (Terminal and Files come with the console tools)."""
    ordered: list[str] = []

    def add(component_id: str) -> None:
        if component_id in ordered:
            return
        for needed in everything[component_id].requires:
            add(needed)
        ordered.append(component_id)

    for component_id in chosen:
        add(component_id)
    for component in everything.values():   # the small things that come along unasked
        if component.spec.get("comes_with") in ordered:
            add(component.id)
    return ordered


def _tile(recorded: str) -> tuple[str, str]:
    """A recorded tile as (its system's folder, its path inside that without ".sh"):
    "Discord" is in Ports; "roms/store/Games/Steam" is Games/Steam in roms/store."""
    parts = recorded.split("/")
    if parts[0] != "roms" or len(parts) < 3:
        return PORTS, recorded
    return "/".join(parts[:2]), "/".join(parts[2:])


def _remove_port(target: Target, name: str, folder: str = PORTS) -> None:
    """Take a tile off: its script, its picture and its line in the system's list.
    `name` may sit in a sub-section: "Games/Steam"."""
    target.remove(f"{folder}/{name}.sh")
    target.remove(f"{folder}/images/{Path(name).name}.png")
    gamelist.remove_entry(target.path(f"{folder}/gamelist.xml"), f"{name}.sh")
    sub = target.path(folder) / Path(name).parent
    if sub != target.path(folder) and sub.is_dir() and not any(sub.iterdir()):
        sub.rmdir()


def _add_port(component: Component, port: dict, target: Target, record: Record) -> None:
    name, folder = port["name"], f"roms/{port.get('system', 'ports')}"
    inside = f"{port['folder']}/{name}" if port.get("folder") else name   # a sub-section of the system
    if "script" in port:
        record.files.append(target.copy_file(component.folder / port["script"], f"{folder}/{inside}.sh", 0o755))
    else:
        text = f"#!/bin/bash\n# {name}, installed by EmuBox.\n{port['command']}\n"
        record.files.append(target.write_text(f"{folder}/{inside}.sh", text, 0o755))
    fields = {"name": name, "desc": port.get("description", ""), "genre": port.get("genre", ""),
              "developer": "EmuBox", "players": "1", "releasedate": f"{date.today().year}0101T000000"}
    if port.get("image"):
        record.files.append(target.copy_file(component.folder / port["image"], f"{folder}/images/{name}.png"))
        fields["image"] = f"./images/{name}.png"
    target.make_dir(target.path(folder))
    gamelist.set_entry(target.path(f"{folder}/gamelist.xml"), f"{inside}.sh", {k: v for k, v in fields.items() if v})
    record.ports.append(name if folder == PORTS else f"{folder}/{inside}")


def _fill(value, typed: dict[str, str]):
    """Put typed answers into a setting: "{user}" becomes what was typed for "user"."""
    if isinstance(value, str):
        for field_id, answer in typed.items():
            value = value.replace(f"{{{field_id}}}", answer)
    return value


def install(component: Component, env: Env) -> Record:
    target, spec, record = env.target, component.spec, Record()
    env.component = component

    for old in spec.get("replaces", []):
        if old.startswith("roms/") and old.endswith(".sh"):   # a tile from an older version
            folder, inside = _tile(old[:-3])
            _remove_port(target, inside, folder)
        else:
            target.remove(old)
    for service in spec.get("retired_services", []):
        target.disable_service(service)

    for item in spec.get("files", []):
        mode = int(item["mode"], 8) if "mode" in item else None
        record.files += target.copy(component.folder / item["from"], item["to"], mode)
    for port in spec.get("ports", []):
        _add_port(component, port, target, record)
    for name, folder in spec.get("folders", {}).items():   # a sub-section of a system: its picture and words
        system = f"roms/{folder.get('system', 'ports')}"
        record.files.append(target.copy_file(component.folder / folder["image"], f"{system}/images/{name}.png"))
        gamelist.set_entry(target.path(f"{system}/gamelist.xml"), name,
                           {"name": name, "desc": folder.get("description", ""), "image": f"./images/{name}.png"}, tag="folder")
    typed = env.answers.get(component.id, {})
    for key, value in spec.get("batocera_conf", {}).items():
        target.conf_set(key, _fill(value, typed))
    for name, value in spec.get("es_settings", {}).items():
        target.es_setting(name, _fill(value, typed))

    run = getattr(component.hooks, "install", None)
    if run:
        run(env)
    if spec.get("flatpaks") and env.downloads:
        flatpak.preinstall(target, spec["flatpaks"], env.say)
    if env.downloads and not os.environ.get("EMUBOX_OFFLINE"):
        _own_icons(component, target, record)

    for service in spec.get("services", []):
        target.enable_service(service)
        record.services.append(service)
    return record


def _own_icons(component: Component, target: Target, record: Record) -> None:
    """Each tile's picture redrawn around the app's own icon, where one is to be had: from the
    program on the drive, or asked of Flathub or the app's site (see tileicon.py). Nothing is
    kept in this repository; without a network the tiles keep their drawings."""
    lib = str(component.folder.parents[1] / "components" / "console" / "files" / "lib")
    if lib not in sys.path:
        sys.path.insert(0, lib)
    try:
        import tileicon
    except ImportError:
        return
    font = component.folder.parents[1] / "components" / "look" / "files" / "fonts" / "Michroma-Regular.ttf"
    roots = [target.path("saves/flatpak/binaries")]
    for port in component.spec.get("ports", []):
        entry = port.get("app") or port
        if not port.get("image") or not any(tileicon.sources(entry)):
            continue
        picture = target.path(f"roms/{port.get('system', 'ports')}/images/{port['name']}.png")
        try:
            done = tileicon.upgrade({**entry, "name": port["name"]}, picture, font, roots)
        except Exception:   # noqa: BLE001  a tile keeps its drawing
            done = False
        if done and port.get("app_id"):   # so Batocera does not ask again
            record.files.append(target.write_text(f"{APPS_ON_DRIVE}/{port['app_id']}/.icon", "the tile shows the app's own icon\n"))


def remember(target: Target, component: Component, record: Record) -> None:
    manifest = target.manifest()
    generated = component.spec.get("generated", [])
    for old_id in component.spec.get("renamed_from", []):
        manifest["components"].pop(old_id, None)
    manifest["components"][component.id] = {
        "title": component.title, "files": sorted(set(record.files)),
        "services": record.services, "ports": record.ports, "generated": generated,
    }
    target.save_manifest(manifest)


def uninstall(component_id: str, target: Target) -> bool:
    """Take a component off again, using the record made when it was installed."""
    manifest = target.manifest()
    entry = manifest["components"].pop(component_id, None)
    if entry is None:
        return False
    _take_off(entry, target)
    target.save_manifest(manifest)
    return True


def retire_old_names(target: Target) -> list[str]:
    """Take off an installation made when the project had another name (RetroBox), so the
    drive does not end up with both. Gives the titles of what was installed; where the
    BIOS and games libraries are is carried over. Batocera's own files and yours stay."""
    titles = []
    for old in OLD_MANIFESTS:
        path = target.path(old)
        if not path.is_file():
            continue
        try:
            before = json.loads(path.read_text())
        except ValueError:
            before = {}
        for component_id, entry in before.get("components", {}).items():
            _take_off(entry, target)
            titles.append(entry.get("title", component_id))
        target.remove(str(Path(old).parent))   # the old folder, with its record
        if before.get("sources"):
            manifest = target.manifest()
            manifest["sources"] = {**before["sources"], **manifest.get("sources", {})}
            target.save_manifest(manifest)
    return titles


def _take_off(entry: dict, target: Target) -> None:
    """Remove what one component's record says it put on the drive."""
    for service in entry.get("services", []):
        target.disable_service(service)
    for name in entry.get("ports", []):
        folder, inside = _tile(name)
        _remove_port(target, inside, folder)
    for made in entry.get("generated", []):
        path = target.path(made["path"])
        if path.is_file() and made["contains"] in path.read_text(errors="replace"):
            path.unlink()   # only when it is recognisably ours
    for relative in entry.get("files", []):
        target.remove(relative)
        folder = target.path(relative).parent   # tidy folders we emptied, but never a top-level one
        while len(folder.relative_to(target.root).parts) >= 2 and folder.is_dir() and not any(folder.iterdir()):
            folder.rmdir()
            folder = folder.parent
