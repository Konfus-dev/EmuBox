# Console tools

The pieces that make a desktop program behave like a console app on Batocera. Every app in
`apps/` uses them, and they work on their own too. On the drive they live in
`/userdata/system/emubox/`.

| Tool | What it does | Use it by itself |
| --- | --- | --- |
| `bin/emubox-app` | Opens, hides and quits apps; downloads them on first use; sends play/pause/next to whatever is playing | `emubox-app open discord`, `emubox-app back`, `emubox-app media Next`, `emubox-app fetch Steam com.valvesoftware.Steam` |
| `lib/pad.py` | Turns the controller into keys and a mouse pointer while one app has the focus, and lets go for the keyboard, the in-game menu and your game | `python3 pad.py apps/<id>/app.json` |
| `lib/osk.py` | On-screen keyboard driven by the controller, with button prompts; types into whatever is in front | `python3 osk.py` (again with `--toggle` to close) |
| `lib/notice.py` | Full-screen "please wait" around a slow command, with its latest output and B to cancel; used for an app's first download | `python3 notice.py "Downloading X" -- command` |
| `lib/store.py` | Batocera's free-games catalogue as a console screen: browse by system, A installs or removes | `python3 store.py` |
| `lib/padinput.py` | Controller input for these screens: takes over the pads while a screen is up and reports presses by their Xbox-pad names | `from padinput import Pads` |
| `lib/guide.py` | EmuBox's Guide menu (the Guide button opens it; `bin/emubox-guide` toggles it): Settings, Apps, Record and Game tabs, bars along the bottom for a call, your music and the menu music, each with its controls. What is in it is the `layout()` at the top of the file | started hidden by the service |
| `lib/music.py` | The menus' background music, played with mpv so it can be shown, skipped and paused | `python3 music.py line`, `toggle`, `next`, `previous` |
| `lib/startmenu.py` | Puts EmuBox's settings in Batocera's own menu (Start > Game Settings) and passes your choices on. Other components add a sub-menu with a `lib/startmenu_<name>.py` (see RGB Hub's, the lights') | `python3 startmenu.py` |
| `lib/webview.py` | Any web page as a full-screen app, on the web engine Batocera already has (nothing to download). Brings the controller navigation and the button strip; remembers sign-ins | `python3 webview.py https://example.org --id example` |
| `lib/webnav.js` | The controller navigation itself, put into every page `webview.py` shows: the d-pad moves a highlight between links and buttons, A presses, B leaves a text box | loaded by `webview.py`; `web-pad.json` beside it says what each button sends |
| `lib/space.py` | How full the drive is: draws the indicator at the top right of the menus, and tells a download whether it will fit | `python3 space.py`, `space.py --theme`, `space.py --need 2000000000` |
| `lib/audio.py` | Decides when the menu music plays (in the menus, not over your own music) and turns music down during a call. Undoes only what it changed | started by the service |
| `lib/menusounds.py` | Menu sounds: plays select, back and menu-open sounds (Batocera's menus only play a scroll sound), and keeps the sound set, the volume and each sound's switch. Your own sets go in `/userdata/system/configs/emubox/sounds/<Name>/`. Silent in games, apps and while your music plays | started by the service; `python3 menusounds.py sets`, `set <name>`, `volume +10`, `off scroll` |
| `lib/settings.py` | The list of EmuBox's settings and their values: what you chose in Batocera's menu (kept in `batocera.conf` as `global.emubox_*`), else the defaults | `python3 settings.py`, `settings.py get ui.sound_set` |
| `lib/adblock.txt` | What the web view keeps out of pages: one advertising service or `##selector` per line. Yours go in `/userdata/system/emubox-web/adblock.txt` | edit and reopen the web app |
| `services/emubox` | Batocera service that runs the menu builder at boot | System Settings > Services |

Set `EMUBOX_DEBUG=1` to log every button press to `/userdata/system/logs/emubox.log`.

To test without a real controller, `tools/dev/fakepad.py` (at the top of the repository)
creates a pretend Xbox pad that plays commands written to a pipe.
