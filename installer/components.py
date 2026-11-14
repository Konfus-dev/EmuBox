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
    requires       ids of components this one needs
    files          [{"from": path here, "to": path on the drive, "mode": "755"}]
    ports          entries for the Ports menu: name, description, image,
                   and either "script" (a file here) or "command" (one line to run)
    services       Batocera services to switch on
    batocera_conf  {"key": "value"} settings for batocera.conf
    es_settings    {"name": "value"} settings of the menu program
    replaces       paths from older versions to delete
    retired_services  services from older versions to switch off
    after          a note printed when the installation is done
"""
from __future__ import annotations

import importlib.util
import json
from dataclasses import dataclass, field
from pathlib import Path
from types import ModuleType
from typing import Callable

from . import gamelist
from .host import Host
from .target import Target

PORTS = "roms/ports"
APPS_ON_DRIVE = "system/retrobox/apps"
OPEN_APP = "exec /userdata/system/retrobox/bin/retrobox-app open {id} --wait"


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
        "requires": ["runtime"],
        "files": [{"from": ".", "to": f"{APPS_ON_DRIVE}/{app_id}"}],
        "ports": [{
            "name": app["name"],
            "command": OPEN_APP.format(id=app_id),
            "image": "tile.png",
            "genre": "Apps",
            "description": app.get("description", ""),
        }],
    }


def _hooks(folder: Path, component_id: str) -> ModuleType | None:
    path = folder / "component.py"
    if not path.is_file():
        return None
    spec = importlib.util.spec_from_file_location(f"retrobox_component_{component_id.replace('-', '_')}", path)
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
    """The chosen ids with what they need added in front, each once."""
    ordered: list[str] = []

    def add(component_id: str) -> None:
        if component_id in ordered:
            return
        for needed in everything[component_id].requires:
            add(needed)
        ordered.append(component_id)

    for component_id in chosen:
        add(component_id)
    return ordered


def _remove_port(target: Target, name: str) -> None:
    target.remove(f"{PORTS}/{name}.sh")
    target.remove(f"{PORTS}/images/{name}.png")
    gamelist.remove_entry(target.path(f"{PORTS}/gamelist.xml"), f"{name}.sh")


def _add_port(component: Component, port: dict, target: Target, record: Record) -> None:
    name = port["name"]
    if "script" in port:
        record.files.append(target.copy_file(component.folder / port["script"], f"{PORTS}/{name}.sh", 0o755))
    else:
        text = f"#!/bin/bash\n# {name}, installed by RetroBox.\n{port['command']}\n"
        record.files.append(target.write_text(f"{PORTS}/{name}.sh", text, 0o755))
    fields = {"name": name, "desc": port.get("description", ""), "genre": port.get("genre", "")}
    if port.get("image"):
        record.files.append(target.copy_file(component.folder / port["image"], f"{PORTS}/images/{name}.png"))
        fields["image"] = f"./images/{name}.png"
    target.make_dir(target.path(PORTS))
    gamelist.set_entry(target.path(f"{PORTS}/gamelist.xml"), f"{name}.sh", {k: v for k, v in fields.items() if v})
    record.ports.append(name)


def install(component: Component, env: Env) -> Record:
    target, spec, record = env.target, component.spec, Record()
    env.component = component

    for old in spec.get("replaces", []):
        if old.startswith(f"{PORTS}/") and old.endswith(".sh"):
            _remove_port(target, Path(old).stem)
        else:
            target.remove(old)
    for service in spec.get("retired_services", []):
        target.disable_service(service)

    for item in spec.get("files", []):
        mode = int(item["mode"], 8) if "mode" in item else None
        record.files += target.copy(component.folder / item["from"], item["to"], mode)
    for port in spec.get("ports", []):
        _add_port(component, port, target, record)
    for key, value in spec.get("batocera_conf", {}).items():
        target.conf_set(key, value)
    for name, value in spec.get("es_settings", {}).items():
        target.es_setting(name, value)

    run = getattr(component.hooks, "install", None)
    if run:
        run(env)

    for service in spec.get("services", []):
        target.enable_service(service)
        record.services.append(service)
    return record


def remember(target: Target, component: Component, record: Record) -> None:
    manifest = target.manifest()
    manifest["components"][component.id] = {
        "title": component.title, "files": sorted(set(record.files)),
        "services": record.services, "ports": record.ports,
    }
    target.save_manifest(manifest)


def uninstall(component_id: str, target: Target) -> bool:
    """Take a component off again, using the record made when it was installed."""
    manifest = target.manifest()
    entry = manifest["components"].pop(component_id, None)
    if entry is None:
        return False
    for service in entry.get("services", []):
        target.disable_service(service)
    for name in entry.get("ports", []):
        _remove_port(target, name)
    for relative in entry.get("files", []):
        target.remove(relative)
        folder = target.path(relative).parent   # tidy folders we emptied, but never a top-level one
        while len(folder.relative_to(target.root).parts) >= 2 and folder.is_dir() and not any(folder.iterdir()):
            folder.rmdir()
            folder = folder.parent
    target.save_manifest(manifest)
    return True
