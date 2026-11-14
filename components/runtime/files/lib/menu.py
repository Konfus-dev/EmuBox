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


def apps() -> list[tuple[str, str]]:
    found = []
    for path in sorted(glob.glob(os.path.join(ROOT, "apps", "*", "app.json"))):
        with open(path) as f:
            found.append((os.path.basename(os.path.dirname(path)), json.load(f)["name"]))
    return found


def apps_tab() -> str:
    c = RETROBOX_APP
    rows = [
        f'\t{MARK}',
        '\t<hgroup name="Apps" display="Apps">',
        '\t\t<feature>',
        f'\t\t\t<button display="Back to game" action="{c} back" afterclick="bcc_close" />',
        '\t\t</feature>',
    ]
    for app, name in apps():
        rows += [
            f'\t\t<feature display={quoteattr(name)}>',
            f'\t\t\t<button display="Open" action="{c} open {app}" afterclick="bcc_close" />',
            f'\t\t\t<button display="Quit" action="{c} close {app}" />',
            '\t\t</feature>',
        ]
    title = quoteattr(f"${{{c} media title}}")
    rows += [
        '\t\t<feature display="Music">',
        f'\t\t\t<button display="Previous" action="{c} media Previous" />',
        f'\t\t\t<button display="Play / Pause" action="{c} media PlayPause" />',
        f'\t\t\t<button display="Next" action="{c} media Next" />',
        '\t\t</feature>',
        '\t\t<feature>',
        f'\t\t\t<text display={title} refresh="3" align="left" />',
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
    os.makedirs(os.path.dirname(OUR_MENU), exist_ok=True)
    with open(OUR_MENU + ".new", "w") as f:
        f.write(menu)
    os.replace(OUR_MENU + ".new", OUR_MENU)
    return 0


if __name__ == "__main__":
    sys.exit(main())
