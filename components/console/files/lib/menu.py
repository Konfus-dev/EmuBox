#!/usr/bin/env python3
"""Add an "Apps" tab to Batocera's Control Center (the in-game menu).

Batocera reads /userdata/system/configs/controlcenter/controlcenter.xml in
place of its own file when that exists. We write that file as Batocera's
current menu plus our tab, and do so at every boot, so the rest of the menu
keeps following Batocera's updates. The tab lists every app in apps/*/app.json
(except those with "menu": false); a music player gets a "Now Playing" row
under it while something is playing. A Call tab shows by itself while an app
is using the microphone.
"""
from __future__ import annotations

import glob
import importlib.util
import json
import os
import sys
from xml.sax.saxutils import quoteattr

import settings

ROOT = os.path.dirname(os.path.dirname(os.path.realpath(__file__)))
EMUBOX_APP = os.path.join(ROOT, "bin", "emubox-app")
SYSTEM_MENU = "/usr/share/batocera/controlcenter/controlcenter.xml"
OUR_MENU = "/userdata/system/configs/controlcenter/controlcenter.xml"
TABS_END = "</feature>"   # the first one after the tab list closes it
MARK = "<!-- emubox apps -->"
CHANGED = 10   # exit status when the menu file was (re)written: a running menu must be restarted to show it


def apps() -> list[tuple[str, dict]]:
    found = []
    for path in sorted(glob.glob(os.path.join(ROOT, "apps", "*", "app.json"))):
        with open(path) as f:
            found.append((os.path.basename(os.path.dirname(path)), json.load(f)))
    return found


def button(label: str, action: str, close: bool = False) -> str:
    after = ' afterclick="bcc_close"' if close else ""
    return f'\t\t\t<button display={quoteattr(label)} action={quoteattr(action)}{after} />'


def heading(text: str) -> str:
    """A row that only names the rows under it (the menu has no section titles of its own).
    Plain ASCII only, here and in every label: the menu program crashes on anything else when
    it is started without a language set, as it is from a boot service."""
    return f'\t\t<feature display={quoteattr("--  " + text.upper() + "  --")}>\n\t\t\t<text display="-" />\n\t\t</feature>'


def app_rows(app_id: str, app: dict) -> list[str]:
    """One row per app, named after it: Open and Close, and for a music player a quick
    Play while nothing is playing. Under a player, while it has a song:
    "Now Playing: Song by Artist  <  ||  >".

    Open goes through "detach": the menu stops whatever a button started after
    three seconds, which would cut short an app's first download or a slow start.

    The menu decides which rows exist once, when it starts, so emubox-app starts
    it afresh (hidden) when music begins or ends; see watch_player there."""
    c = EMUBOX_APP
    opens = button("Open", f"{c} detach open {app_id}", close=True)
    closes = button("Close", f"{c} close {app_id}")
    name = quoteattr(app["name"])
    if not app.get("player"):
        return [f'\t\t<feature display={name}>', opens, closes, '\t\t</feature>']
    # A player's row comes in two forms, of which the menu builds one: with a quick Play
    # while nothing is coming out (it carries on with the paused song, or opens the app
    # when there is none), and without it while music is playing.
    rows = [
        f'\t\t<feature display={name} if="${{{c} media silent}}">',
        opens, button("Play", f"{c} detach play {app_id}", close=True), closes,
        '\t\t</feature>',
        f'\t\t<feature display={name} if="${{{c} media sounding}}">',
        opens, closes,
        '\t\t</feature>',
        f'\t\t<feature display="Now Playing:" if="${{{c} media title}}">',
        f'\t\t\t<text display="${{{c} media playing}}" refresh="2" align="left" />',
        button("<", f"{c} media Previous"),
        button("||", f"{c} media PlayPause"),
        button(">", f"{c} media Next"),
        '\t\t</feature>',
    ]
    return rows


def apps_tab(listed: list[tuple[str, dict]], extras: bool = True) -> str:
    rows = [f'\t{MARK}', '\t<hgroup name="Apps" display="Apps">']
    for app_id, app in listed:
        rows += app_rows(app_id, app)
    rows += [
        '\t\t<feature display="Game">',
        button("Back to game", f"{EMUBOX_APP} back", close=True),
        '\t\t</feature>',
    ]
    rows.append(heading("Settings"))
    for name, (_, text) in settings.KNOWN.items():   # the apps' settings, as switches
        if text:
            c = EMUBOX_APP
            rows += [
                f'\t\t<feature display={quoteattr(text)} group="Settings">',
                f'\t\t\t<switch value="${{{c} setting is {name}}}" '
                f'action_on="{c} setting set {name} on" action_off="{c} setting set {name} off" />',
                '\t\t</feature>',
            ]
    rows += sound_rows()
    if extras:
        rows += extra_rows()
    rows.append('\t</hgroup>')
    return "\n".join(rows) + "\n"


def sound_rows() -> list[str]:
    """Menu sounds: which set, each sound's own switch, and how loud."""
    import menusounds
    c = EMUBOX_APP
    me = f"python3 {os.path.join(os.path.dirname(os.path.realpath(__file__)), 'menusounds.py')}"
    names = list(menusounds.sets(menusounds.es_text())) or [menusounds.BUILT_IN]
    rows = [heading("Menu sounds"),
            '\t\t<feature display="Sound set">',
            f'\t\t\t<text display="${{{me} set-now}}" refresh="2" />']
    rows += [f'\t\t\t<choice display={quoteattr(name)} action={quoteattr(f"{me} set {chr(39)}{name}{chr(39)}")} '
             f'afterclick="bcc_refresh" />' for name in names]
    rows += ['\t\t</feature>',
             '\t\t<feature display="Volume">',
             f'\t\t\t<button display="-" action="{me} volume -10" />',
             f'\t\t\t<progressbar display="${{{c} setting get ui.sound_volume}}" min="0" max="100" refresh="1" />',
             f'\t\t\t<button display="+" action="{me} volume +10" />',
             '\t\t</feature>']
    for kind, label in (("scroll", "Moving through a list"), ("select", "Choosing"), ("back", "Going back"),
                        ("menuopen", "Opening the menu")):
        rows += [f'\t\t<feature display={quoteattr(label)}>',
                 f'\t\t\t<switch value="${{{c} setting is ui.sound.{kind}}}" action_on="{me} on {kind}" action_off="{me} off {kind}" />',
                 '\t\t</feature>']
    return rows


def extra_rows(folder: str | None = None) -> list[str]:
    """Rows other components add to the Apps tab: each lib/menu_<name>.py gives them from rows()."""
    rows: list[str] = []
    for path in sorted(glob.glob(os.path.join(folder or os.path.dirname(os.path.realpath(__file__)), "menu_*.py"))):
        try:
            spec = importlib.util.spec_from_file_location(os.path.basename(path)[:-3], path)
            module = importlib.util.module_from_spec(spec)
            spec.loader.exec_module(module)
            rows += module.rows()
        except Exception as error:   # noqa: BLE001  one broken add-on must not cost the whole menu
            print(f"menu: {path} was left out: {error}", file=sys.stderr)
    return rows


def call_tab() -> str:
    """Shown only while an app is using the microphone, which is what being in a call looks like."""
    c = EMUBOX_APP
    return "\n".join([
        '\t<hgroup name="Call" display="Call">',
        '\t\t<feature display="Mute my microphone">',
        f'\t\t\t<switch value="${{{c} mic muted}}" refresh="2" action_on="{c} mic mute" action_off="{c} mic unmute" />',
        '\t\t</feature>',
        '\t</hgroup>',
    ]) + "\n"


def faults(menu: str) -> list[str]:
    """What Batocera's own checker says is wrong with a menu (it refuses to start on any error)."""
    folder = os.path.dirname(SYSTEM_MENU)
    try:
        if folder not in sys.path:
            sys.path.append(folder)
        import xml_utils   # Batocera's
        import tempfile
        with tempfile.NamedTemporaryFile("w", suffix=".xml") as file:
            file.write(menu)
            file.flush()
            return xml_utils.validate_xml(xml_utils.parse_xml(file.name))[0]
    except Exception as error:   # noqa: BLE001  no checker here (not on Batocera): nothing to say
        return [] if isinstance(error, ImportError) else [f"could not be checked: {error}"]


def build(menu: str, found: list[tuple[str, dict]] | None = None, extras: bool = True) -> str:
    found = apps() if found is None else found
    listed = [(app_id, app) for app_id, app in found if app.get("menu", True)]
    c = EMUBOX_APP
    tabs, pages = ['<tab display="Apps" target="Apps" />'], apps_tab(listed, extras)
    if any(app.get("voice") for _, app in listed):
        tabs.append(f'<tab display="Call" target="Call" if="${{{c} mic in-use}}" />')
        pages += call_tab()
    at = menu.index('name="shortcuts_tabs"')
    end = menu.index(TABS_END, at)
    menu = menu[:end] + "".join(f"\t{tab}\n\t" for tab in tabs) + menu[end:]
    close = menu.rindex("</features>")
    return menu[:close] + pages + menu[close:]


def main() -> int:
    if "--remove" in sys.argv:
        # Only ever delete a file we wrote.
        if os.path.exists(OUR_MENU) and MARK in open(OUR_MENU).read():
            os.unlink(OUR_MENU)
        return 0
    if os.path.exists(OUR_MENU) and MARK not in open(OUR_MENU).read():
        print(f"{OUR_MENU} is someone else's custom menu; leaving it alone.", file=sys.stderr)
        return 1
    with open(SYSTEM_MENU) as f:
        stock = f.read()
    menu = build(stock)
    problems = faults(menu)
    if problems:   # a menu Batocera refuses is no menu at all: the Guide button would do nothing
        print("menu: Batocera would refuse this menu:", *problems, sep="\n  ", file=sys.stderr)
        menu = build(stock, extras=False)
        problems = faults(menu)
    if problems:   # still refused: step aside, so Batocera's own menu opens
        print("menu: leaving Batocera's own menu in place:", *problems, sep="\n  ", file=sys.stderr)
        if os.path.exists(OUR_MENU):
            os.unlink(OUR_MENU)
            return CHANGED
        return 1
    if os.path.exists(OUR_MENU) and open(OUR_MENU).read() == menu:
        return 0
    os.makedirs(os.path.dirname(OUR_MENU), exist_ok=True)
    with open(OUR_MENU + ".new", "w") as f:
        f.write(menu)
    os.replace(OUR_MENU + ".new", OUR_MENU)
    return CHANGED


if __name__ == "__main__":
    sys.exit(main())
