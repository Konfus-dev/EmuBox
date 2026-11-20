# EmuBox in detail

Everything the short [README](../README.md) leaves out.

## Install

**From a Linux PC**, with the Batocera drive plugged in and opened in the file manager:

```sh
git clone https://github.com/Konfus-dev/EmuBox
cd EmuBox
./install
```

**On Batocera itself** (over SSH, or from a terminal):

```sh
cd /userdata/system
curl -L https://github.com/Konfus-dev/EmuBox/archive/HEAD.tar.gz | tar xz
EmuBox-*/install
```

The installer finds the drive and asks what you want:

```
Install the Xbox-style look (green theme, menu colours, fonts and sounds)? [Y/n]
Install Apple Music (the web player, set up for the controller)? [Y/n]
Install Discord (voice and text chat, set up for the controller)? [Y/n]
...
Install BIOS files? [y/N] y
  Where are they? A repository address or a folder: https://github.com/you/your-bios
Systems in this library:
   1) PlayStation (7 files, 4 MB)
   2) PlayStation 2 (18 files, 36 MB)
Which ones? Numbers like 1,3-5, or Enter for all:
```

It shows a summary and asks once more before changing anything. Run it again any time to add
things or update; it only copies what is missing.

| Command | Does |
| --- | --- |
| `./install` | ask about everything |
| `./install --list` | show what can be installed, and what is |
| `./install --remove discord` | take something off again |
| `./install --yes --with look,discord --games /mnt/games` | no questions (for scripts) |
| `./install --setup setups/example.json` | your own answers kept in a file: what to install, where your sounds, BIOS files and games are (folders relative to the file), the graphics driver to fetch for the apps, pages for Vault. One command then rebuilds a drive the same way. If the file has no `bios` or `games` line you are asked for each folder ([laid out like this](#your-bios-files-and-games)) and the answer is written into the file; `""` means none |
| `./backup-games ~/my-games` | copy the games on a drive into a library folder |

## What you can install

| | |
| --- | --- |
| **Xbox-style look** | Theme for the menus, a start-up film (a plasma waking in a dark chamber and flaring into the EmuBox name, with its own sound), a tunnel of green cells behind the menus, a glossy, slightly see-through orb gripped by a see-through ring and four curled arms that turn with the system wheel, each system joined to the holder by a strut (the 3D parts are rendered in Blender: components/look/tools/blender) that goes straight to the menus without Batocera's loading screen, the EmuBox name on the home screen and on an OMEN cooler's screen, matching colours for the in-game menu, fonts, sounds. The systems on a wheel round the orb: the chosen one level to its right, the others turning away above and below and fading out (shaders/wheelfade.glsl); turning slides them round. Top left: the network, the clock, the space used and free, and beneath them a light per controller; EMUBOX V1 at the top right of the home screen |
| **Discord**, **Apple Music** | Open from **Apps** on the home screen, or over a running game from the in-game menu's **Apps** tab. The installer puts each one's program on the drive (with `flatpak` on the PC), so there is no waiting in Batocera; without that, or with `--download-later`, it downloads the first time you open it |
| **Terminal**, **Files**, **Browser**, **Claude** | Come with any app, in **Apps**: a command line, Batocera's file manager opened on the drive, and Claude Code in a terminal (it downloads itself the first time and asks you to sign in; a keyboard helps) |
| **ROM-hack patcher** | Drop a `.ips`/`.bps`/`.ups` file in `patches` and it is applied at boot |
| **Play settings** | Auto-save, rewind on 8/16-bit systems, a light CRT shader, a tidier network share |
| **Bluetooth controllers** | Offered when preparing a drive on a PC with paired controllers: copies the pairings so the same controller works in Linux and Batocera without re-pairing |
| **Wi-Fi** | Asks for the network name and password, so Batocera connects by itself |
| **ScreenScraper account** | For box art, videos and descriptions; with the picture style and extras already chosen |
| **RetroAchievements account** | Trophies for older games |
| **Store** | A Store on the home screen: Batocera's catalogue of free games (browse and install with the controller), Steam, and Heroic for Epic and GOG. Each downloads itself the first time you open it |
| **Vault** | In the Store: your own list of store pages, browsed with the controller. Downloads are noticed straight away, Vault asks which system to install them to, then moves them into your games. See [Vault](vault.md) |
| **RGB Hub** | The lights program (once OMEN lights): the HP OMEN PC's cooler screen, case and memory lights, and the IQUNIX keyboard's lights follow the game. Only offered on a PC with one of them; fetched from [its own repository](https://github.com/Konfus-dev/RGB-Hub) |

### Controller buttons in the apps

| Button | Does |
| --- | --- |
| D-pad | Move |
| A / B | Select / back |
| Right stick, R3 | Pointer, click |
| Left stick | Scroll |
| L3 | On-screen keyboard |
| Guide, or Select+A | In-game menu |
| Select+B | Hide the app and go back to the game (it keeps running) |
| Select+Start | Quit the app |

Each app adds its own on top (see its `app.json`): in Discord, X mutes, Y searches, LB/RB step
through items, LT/RT switch servers; in Apple Music, X or Start plays and pauses, LB/RB change
song, LT/RT change the volume, Y opens the keyboard.

**Signing in without a keyboard.** In the on-screen keyboard, click the left stick again (or choose
the **PHONE** key): it shows a QR code,
and scanning it opens a small page on your phone; what you type there and send is typed into the
app on the TV. It works on your own network, only while the code is on screen, at an address made
for that one time; what you send is not encrypted on its way across your network, so use it at
home, not on a network you do not trust. (Discord's own sign-in page also has a QR code for its
phone app.)

### Two menus, two jobs

**Start** opens Batocera's main menu, where every setting lives. EmuBox's own are under
**Game Settings**, in an EMUBOX block:

- **MENU SOUNDS**: which sound set, the volume, and a switch each for moving (through lists and
  pop-up menus alike), choosing, going back and opening the menu.
- **APPS**: the menu music and whether it waits for your own, music dropping during a call and how
  far, and the ad blocker for web apps.
- **RGB HUB** (on a PC with the OMEN lights or the IQUNIX keyboard): following the game (both devices,
  or each on its own), lights on/off and brightness for the PC and the keyboard, a colour per light,
  effects and their speed, the cooler's screen, its picture and fit, and the **Default look** (what
  every device shows once Batocera has shut down: save the look now as the Default, or go back to it).

(Batocera's main menu cannot take a new entry of its own, so they sit inside Game Settings.)

**Guide** opens EmuBox's own quick menu, over the menus or a running game:

- **Settings**: the system volume and mute, the menu sound set and its volume, the lights' basics
  (following the game, on/off and brightness for the PC and the keyboard, saving the look as the Default),
  power mode, plane mode, stopping a stuck emulator, and **Open full settings** (Batocera's main menu).
- **Apps**: open an app or a tool, or hide the apps and go back. **Capture**: take a screenshot (the menu
  closes first, so it is not in the picture) and start or stop a recording. Both are kept under
  **Captures** on the home screen (Screenshots and Recordings; on the drive they stay in Batocera's own
  `screenshots` and `recordings` folders).
- **Running**, while anything is: the emulator Batocera started (resume, its own settings menu,
  quit, force close) and each app that is open (resume, hide, force close).
- Each tab's rows sit under headings (Sound, RGB Hub, System; Apps, Tools).
- Along the bottom, a bar for each thing that is live, with its controls: a call (microphone
  switch), your music app (previous, pause, next), or the menus' own music (the same three).
  Under them, the processor load and how full the drive is; along the top, the time and the
  network address.

D-pad or stick moves, A presses, left/right changes a value, LB/RB change tab, B or Guide closes.
The menu opens as the Guide button goes down; its values are read a few seconds after start-up and
again each time it opens. The tab you are on is the bright one.

Every app shows what the buttons do in a row along the bottom, and its window sits above that
row. In any app Select+B hides it and Select+Start quits it; holding B hides it too (not in the
terminal, where B is Backspace). In a browser-based app B goes back, and on the page the app
opened on it leaves. Opening an app shows "Opening ..." until its window is there (from the Guide menu, the menu itself
says so the instant Open is pressed).

The menus' background music is played by EmuBox (Batocera's own is switched off) so that it can
be shown, skipped and paused. It plays in the menus only, and waits while a music app of yours
is playing.

### Menu sounds

The sounds are kept loaded in the sound server, so one plays within a few milliseconds of the
press instead of being read from the drive each time.

EmuBox's own set is synthesised and is what you get unless you bring your own: the installer asks
for a folder of sound sets (or take `--sounds FOLDER`), one sub-folder per set, named as it should
be listed. What a file does is told by its name: `scroll.wav`, `select.wav`, `back.wav`,
`menuopen.wav`, and `boot.wav` for the start-up film's sound (the installer makes that set's film
from it; it needs GStreamer). A sound a set lacks is taken from EmuBox's. Until you choose a set in the menu, one with "xbox" in its name is used when there is one. Such sets are yours and
stay out of the repository.

## Your BIOS files and games

These are yours, so they are not in this repository. Keep each in a **library**: a folder with one
sub-folder per system, named as Batocera names them.

```
my-games/                      my-bios/
  psx/Some Game (USA).chd        psx/scph5501.bin
  psx/images/...                 ps2/ps2/SCPH-70012.bin     (as it sits in Batocera's bios folder)
  snes/Another Game.sfc          segacd/bios_CD_U.bin
```

Inside a system's folder the files sit exactly as they go into Batocera: a game straight in the
folder (with `images/` and a `gamelist.xml` beside it if you have them), a BIOS file at the path
Batocera's "Missing BIOS" screen names, minus the leading `bios/` (so `bios/dc/dc_boot.bin` is
`dreamcast/dc/dc_boot.bin` in the library, and `bios/GC/USA/IPL.bin` is `gamecube/GC/USA/IPL.bin`).

A library can be a folder on a drive or NAS, or a private git repository; the installer takes
either. Multi-disc games count as one game. For games, another Batocera drive works as a library
too. `./backup-games` makes a games library from a drive, with a `MANIFEST.tsv` of checksums and a
`.gitignore` for the files too large for GitHub (those stay in the folder only).

On Batocera itself there is no `git`: public GitHub repositories download directly, private ones
need an access token (`https://TOKEN@github.com/you/repo`) or use a folder on a USB drive.

## How it is put together

```
install, backup-games    what you run
installer/               the installer (plain Python, nothing to install)
apps/<name>/             one app: app.json (what to start, controller buttons) and tile.png
components/<name>/       everything else: component.json says what to copy and switch on
components/console/      the console tools every app shares: launcher, controller mapper, keyboard, menu tab
tools/                   commands for looking after a drive from a Linux PC (see its README); dev/ for development
tests/                   python3 -m unittest discover tests
```

Adding an app or a tweak means adding a folder; the installer picks it up and asks about it.
See [docs/extending.md](extending.md).

## Good to know

- Batocera runs everything as the administrator, and the apps run without the browser sandbox, as
  Chromium-based programs must there. Treat the drive as a games machine, not a place for
  sensitive browsing.
- Controller buttons are read by their Xbox-pad labels.
- Log on Batocera: `/userdata/system/logs/emubox.log` (`EMUBOX_DEBUG=1` logs every button).

Licence: GPL-3.0-or-later. Fonts: SIL Open Font Licence (see `components/look/files/fonts`).
EmuBox is not affiliated with Microsoft, Discord or Apple; it ships none of their artwork or software.
A tile's icon is the app's own: taken from the program once it is on the drive, or asked of Flathub or
the app's site when you install. Without a network the tiles keep EmuBox's own drawings.
