#!/usr/bin/env python3
"""Add an "Apps" tab to Batocera's Control Center (the in-game menu).

Batocera reads /userdata/system/configs/controlcenter/controlcenter.xml in
place of its own file when that exists. We write that file as Batocera's
current menu plus our tab, and do so at every boot, so the rest of the menu
keeps following Batocera's updates. The tab lists every app in apps/*/app.json.
"""
from __future__ import annotations

import glob
import json
import os
import sys
from xml.sax.saxutils import quoteattr

ROOT = os.path.dirname(os.path.dirname(os.path.realpath(__file__)))
RETROBOX_APP = os.path.join(ROOT, "bin", "retrobox-app")
SYSTEM_MENU = "/usr/share/batocera/controlcenter/controlcenter.xml"
OUR_MENU = "/userdata/system/configs/controlcenter/controlcenter.xml"
TABS_END = "</feature>"   # the first one after the tab list closes it
MARK = "<!-- retrobox apps -->"
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
    """One row per app, named after it. A music player gets its buttons on that
    row and, under it, what is playing."""
    c = RETROBOX_APP
    rows = [f'\t\t<feature display={quoteattr(app["name"])}>']
    if app.get("player"):
        rows += [
            button("Previous", f"{c} media Previous"),
            button("Play / Pause", f"{c} play {app_id}"),
            button("Next", f"{c} media Next"),
        ]
    rows += [
        button("Open", f"{c} open {app_id}", close=True),
        button("Quit", f"{c} close {app_id}"),
        '\t\t</feature>',
    ]
    if app.get("player"):
        playing = quoteattr(f"${{{c} media playing}}")
        rows += [
            '\t\t<feature display="Now playing">',
            f'\t\t\t<text display={playing} refresh="2" align="left" />',
            '\t\t</feature>',
        ]
    return rows


def apps_tab() -> str:
    rows = [f'\t{MARK}', '\t<hgroup name="Apps" display="Apps">']
    for app_id, app in apps():
        rows += app_rows(app_id, app)
    rows += [
        '\t\t<feature display="Game">',
        button("Back to game", f"{RETROBOX_APP} back", close=True),
        '\t\t</feature>',
        '\t</hgroup>',
    ]
    return "\n".join(rows) + "\n"


def build(menu: str) -> str:
    tabs = menu.index('name="shortcuts_tabs"')
    end = menu.index(TABS_END, tabs)
    menu = menu[:end] + '\t<tab display="Apps" target="Apps" />\n\t' + menu[end:]
    close = menu.rindex("</features>")
    return menu[:close] + apps_tab() + menu[close:]


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
        menu = build(f.read())
    if os.path.exists(OUR_MENU) and open(OUR_MENU).read() == menu:
        return 0
    os.makedirs(os.path.dirname(OUR_MENU), exist_ok=True)
    with open(OUR_MENU + ".new", "w") as f:
        f.write(menu)
    os.replace(OUR_MENU + ".new", OUR_MENU)
    return CHANGED


if __name__ == "__main__":
    sys.exit(main())
