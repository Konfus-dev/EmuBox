#!/usr/bin/env python3
"""Add an "Apps" tab to Batocera's Control Center (the in-game menu).

Batocera reads /userdata/system/configs/controlcenter/controlcenter.xml in
place of its own file when that exists. We write that file as Batocera's
current menu plus our tab, and do so at every boot, so the rest of the menu
keeps following Batocera's updates. The tab lists every app in apps/*/app.json
(except those with "menu": false), with a few quick controls under them, and
a strip along the bottom says what is playing and whether you are in a call.
Plain ASCII only in every label: the menu program crashes on anything else
when it is started without a language set, as it is from a boot service.
"""
from __future__ import annotations

import glob
import importlib.util
import json
import os
import re
import sys
from xml.sax.saxutils import quoteattr


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


def app_rows(app_id: str, app: dict) -> list[str]:
    """One row per app, named after it: Open and Close, and Play for a music player (it carries
    on with the paused song, or opens the app when there is none).

    Open and Play go through "detach": the menu stops whatever a button started after three
    seconds, which would cut short an app's first download or a slow start."""
    c = EMUBOX_APP
    row = [f'\t\t<feature display={quoteattr(app["name"])}>',
           button("Open", f"{c} detach open {app_id}", close=True)]
    if app.get("player"):
        row.append(button("Play", f"{c} detach play {app_id}", close=True))
    return row + [button("Close", f"{c} close {app_id}"), '\t\t</feature>']


def apps_tab(listed: list[tuple[str, dict]], extras: bool = True) -> str:
    """The Apps tab: your apps, then the quick controls that are worth having one press away."""
    c = EMUBOX_APP
    rows = [f'\t{MARK}', '\t<hgroup name="Apps" display="Apps">']
    for app_id, app in listed:
        rows += app_rows(app_id, app)
    if any(app.get("player") for _, app in listed):
        rows += ['\t\t<feature display="Music">',
                 button("<", f"{c} media Previous"), button("||", f"{c} media PlayPause"), button(">", f"{c} media Next"),
                 '\t\t</feature>']
    if any(app.get("voice") for _, app in listed):
        rows += ['\t\t<feature display="Mute my microphone">',
                 f'\t\t\t<switch value="${{{c} mic muted}}" refresh="2" action_on="{c} mic mute" action_off="{c} mic unmute" />',
                 '\t\t</feature>']
    rows += [
        '\t\t<feature display="Volume">',
        button("-", "batocera-audio setSystemVolume -5"),
        '\t\t\t<progressbar display="${batocera-audio getSystemVolume}" min="0" max="100" refresh="1" />',
        button("+", "batocera-audio setSystemVolume +5"),
        '\t\t</feature>',
        # In a game this is the emulator's own menu; from the menus it is Batocera's main menu,
        # where all the settings are (EmuBox's under Game Settings).
        '\t\t<feature display="Options and settings">',
        button("Open the menu", "hotkeygen --send menu", close=True),
        button("Back to game", f"{c} back", close=True),
        '\t\t</feature>',
    ]
    if extras:
        rows += extra_rows()
    rows.append('\t</hgroup>')
    return "\n".join(rows) + "\n"


def with_status(menu: str) -> str:
    """What is going on right now (the song, a call) in the strip along the bottom of the menu.

    Batocera's own bottom bar is the place: a second bar, or more than three things in the one,
    makes the whole menu wider than the screen. So the song and the call take the places of the
    temperature and the resolution; the processor load stays. A menu without that bar is left as it is."""
    c = EMUBOX_APP
    start = menu.find('role="footer"')
    end = menu.find("</vgroup>", start)
    if start < 0 or end < 0:
        return menu
    bar = menu[start:end]
    kept = re.sub(r'[ \t]*<feature display="(?:Temp:|Resolution:)">.*?</feature>\n', "", bar, flags=re.S)
    if kept == bar:
        return menu   # not the bar we know: do not crowd it
    ours = (f'\t\t<feature>\n\t\t\t<text display="${{{c} status music}}" refresh="2" align="left" />\n\t\t</feature>\n'
            f'\t\t<feature>\n\t\t\t<text display="${{{c} status call}}" refresh="2" align="left" />\n\t\t</feature>\n\t')
    return menu[:start] + kept + ours + menu[end:]


def build(menu: str, found: list[tuple[str, dict]] | None = None, extras: bool = True) -> str:
    found = apps() if found is None else found
    listed = [(app_id, app) for app_id, app in found if app.get("menu", True)]
    menu = with_status(menu)
    at = menu.index('name="shortcuts_tabs"')
    end = menu.index(TABS_END, at)
    menu = menu[:end] + '\t<tab display="Apps" target="Apps" />\n\t' + menu[end:]
    close = menu.rindex("</features>")
    return menu[:close] + apps_tab(listed, extras) + menu[close:]


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
