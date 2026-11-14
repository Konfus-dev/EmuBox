# Console tools

The pieces that make a desktop program behave like a console app on Batocera. Every app in
`apps/` uses them, and they work on their own too. On the drive they live in
`/userdata/system/retrobox/`.

| Tool | What it does | Use it by itself |
| --- | --- | --- |
| `bin/retrobox-app` | Opens, hides and quits apps; downloads them on first use; sends play/pause/next to whatever is playing | `retrobox-app open discord`, `retrobox-app back`, `retrobox-app media Next` |
| `lib/pad.py` | Turns the controller into keys and a mouse pointer while one app has the focus, and lets go for the keyboard, the in-game menu and your game | `python3 pad.py apps/<id>/app.json` |
| `lib/osk.py` | On-screen keyboard driven by the controller, with button prompts; types into whatever is in front | `python3 osk.py` (again with `--toggle` to close) |
| `lib/menu.py` | Adds the **Apps** tab to Batocera's in-game menu, rebuilt at each boot from Batocera's own menu | `python3 menu.py` / `--remove` |
| `services/retrobox` | Batocera service that runs the menu builder at boot | System Settings > Services |

Set `RETROBOX_DEBUG=1` to log every button press to `/userdata/system/logs/retrobox.log`.

To test without a real controller, `tools/fakepad.py` (in the repository's top-level `tools`)
creates a pretend Xbox pad that plays commands written to a pipe.
