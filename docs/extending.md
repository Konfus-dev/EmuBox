# Extending EmuBox

## Add an app

Make a folder `apps/<id>/` with two files.

**`app.json`**

```json
{
  "name": "My App",
  "question": "Install My App?",
  "description": "Shown in the Ports menu.",
  "flatpak": "org.example.MyApp",
  "args": ["--no-sandbox"],
  "window": "myapp",
  "pad": {
    "up": ["KEY_UP"], "down": ["KEY_DOWN"], "left": ["KEY_LEFT"], "right": ["KEY_RIGHT"],
    "a": ["KEY_ENTER"],
    "b": ["KEY_ESC"],
    "x": ["KEY_LEFTCTRL", "KEY_F"],
    "rb": {"media": "Next"},
    "rt": {"run": "batocera-audio setSystemVolume +5"},
    "select+b": "back",
    "select+start": "close",
    "guide": "menu",
    "l3": "osk",
    "r3": "click",
    "left_stick": "scroll",
    "right_stick": "pointer"
  }
}
```

- `flatpak`: the app's id on [Flathub](https://flathub.org). It is downloaded the first time the app is opened.
- `args`: extra arguments. Browser-based apps need `--no-sandbox` on Batocera.
- `player`: `true` for a music or video player. Its row in the Guide menu's Apps tab gets a Play
  button, the tab gets music controls, and the strip along the bottom says what is playing.
- `voice`: `true` for a chat app. The Apps tab gets a microphone mute, and the strip along the
  bottom says when you are in a call.
- `menu`: `false` keeps the app out of the Apps tab (for something opened rarely, from its own tile).
- The program is fetched onto the drive when the installer runs (needs `flatpak` on the PC), so it
  is ready in Batocera. A component can ask the same for other Flathub programs with
  `"flatpaks": ["org.example.Thing"]`.
- `window`: how the app's window id starts. Find it on Batocera with `wlrctl toplevel list` while the app is open.
- `pad`: what each button does. Leave `pad` out for a program that understands controllers
  itself (a game launcher); it then receives the controller untouched.
  Buttons: `a b x y lb rb lt rt start select guide l3 r3 up down left right`,
  and `select+<button>` for a second layer. Actions:

  | Action | Meaning |
  | --- | --- |
  | `["KEY_LEFTCTRL", "KEY_K"]` | keys pressed together, held while the button is held ([key names](https://github.com/torvalds/linux/blob/master/include/uapi/linux/input-event-codes.h)) |
  | `"click"`, `"rightclick"` | mouse buttons |
  | `"osk"` | on-screen keyboard |
  | `"menu"` | Batocera's in-game menu |
  | `"back"` | hide the app, return to the game |
  | `"close"` | quit the app |
  | `{"media": "PlayPause"}` | also `Next`, `Previous`: controls whatever is playing |
  | `{"run": "command"}` | any shell command |

  Sticks (`left_stick`, `right_stick`) can be `"pointer"`, `"scroll"` or `"dpad"`.

**`tile.png`**: the picture in the Ports menu. `python3 tools/dev/tile.py "MY APP" apps/my-app/tile.png` draws one.

That is all: `./install` now asks about it, adds it to Ports and to the Apps tab of the in-game menu.

## Add a web app

A site that works in an ordinary browser needs no download at all: show it with the console's own
web view. Add a component whose port runs it:

```json
{
  "title": "My Site",
  "question": "Add My Site?",
  "requires": ["console"],
  "ports": [{
    "name": "My Site", "image": "files/tile.png", "description": "...",
    "command": "exec python3 /userdata/system/emubox/lib/webview.py https://example.org --id my-site"
  }]
}
```

The d-pad moves between links and buttons, A presses, B goes back, X opens the keyboard, the right
stick is a pointer for anything the d-pad cannot reach; `lib/web-pad.json` holds the full list.
Sign-ins are remembered per `--id`. Two limits: it cannot play copy-protected music or video
(Apple Music, Netflix: those need Chrome, as an app above, which has its own d-pad navigation
switched on with `--enable-spatial-navigation`), and it shows one page at a time, no tabs.

Adverts and trackers are kept out by `lib/adblock.txt` (a switch in the Apps tab turns that off).

Before anything large is downloaded, ask whether it fits: `python3 lib/space.py --need <bytes>`
prints why not and exits 1, and `space.py --theme` redraws the indicator in the menus afterwards.

## Add a component (settings, scripts, files)

Make a folder `components/<id>/` with a `component.json`:

```json
{
  "title": "Short name",
  "question": "The yes/no question the installer asks?",
  "default": true,
  "order": 50,
  "files": [{"from": "files/my_script", "to": "system/services/my_service", "mode": "755"}],
  "services": ["my_service"],
  "batocera_conf": {"global.shaderset": "zfast"},
  "es_settings": {"ThemeSet": "emubox"},
  "ports": [{"name": "My Port", "script": "files/My Port.sh", "image": "files/tile.png", "description": "...",
             "system": "store"}],
  "after": "A note printed when the installation is done."
}
```

To ask for something to type in (a network name, an account), add `ask` and use the answers in
settings as `{id}`:

```json
"ask": [
  {"id": "user", "question": "Username"},
  {"id": "password", "question": "Password", "secret": true}
],
"batocera_conf": {"some.username": "{user}", "some.password": "{password}"}
```

Answers are used once and never recorded by the installer. For scripts they can be given ahead:
`--set <component>.user=me`, or the environment variable `EMUBOX_<COMPONENT>_PASSWORD`.

A menu entry goes in Ports unless `"system"` names another system folder; `"store"` puts it in the
Store on the home screen (`components/store` is the example).

Every key but `title` is optional. Paths under `to` are relative to Batocera's data folder
(`/userdata`). The full list of keys is at the top of `installer/components.py`.

When copying is not enough, add a `component.py` next to it with either or both of:

```python
def available(env) -> bool:   # False: the installer never mentions this component
    return "03f0:7397" in env.host.usb_devices()

def install(env) -> None:     # runs after the files are copied
    repo = env.fetch("https://github.com/someone/something", "something")
```

`env` gives you `target` (the drive: `copy`, `conf_set`, `enable_service`...), `repo`, `host`, `fetch`
and `component`. `components/omen-lights` is a complete example.

## Test

```sh
python3 -m unittest discover tests
```

The tests install into a pretend drive in a temporary folder. To try the real thing without a
drive, make a folder with `system/batocera.conf` and `roms/` in it and pass it as `--target`.
