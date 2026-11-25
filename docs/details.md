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
| **Xbox-style look** | Theme for the menus, a start-up film (backing out of the green tunnel as a plasma wakes, a flare, and the orb in its holder coming to rest where the home screen has it, beside the EmuBox name, with its own sound), EmuBox's own loading screens in place of Batocera's (the first picture at start-up, the menus' loading and shutdown screen, and a game-start screen with the game's picture, its name and the holder turning; the boot menu is hidden), a tunnel of green cells behind the menus, a glossy, slightly see-through orb gripped by a see-through ring and four curled arms that turn with the system wheel, each system joined to the holder by a strut (the 3D parts are rendered in Blender: components/look/tools/blender) that goes straight to the menus without Batocera's loading screen, the EmuBox name on the home screen and on an OMEN cooler's screen, matching colours for the in-game menu, fonts, sounds. The systems on a wheel round the orb: the chosen one level to its right, the others turning away above and below and fading out (shaders/wheelfade.glsl); turning slides them round. Top left: the network, the clock, the space used and free, and beneath them a light per controller; EMUBOX V1.1 at the top right of the home screen |
| **Discord**, **Apple Music** | Open from **Apps** on the home screen, or over a running game from the in-game menu's **Apps** tab. The installer puts each one's program on the drive (with `flatpak` on the PC), so there is no waiting in Batocera; without that, or with `--download-later`, it downloads the first time you open it |
| **Terminal**, **Files**, **Browser**, **Claude** | Come with any app, in **Apps**: a command line, Batocera's file manager opened on the drive, and Claude Code in a terminal (it downloads itself the first time and asks you to sign in; a keyboard helps) |
| **ROM-hack patcher** | Drop a `.ips`/`.bps`/`.ups` file in `patches` and it is applied at boot |
| **Play settings** | Auto-save, rewind on 8/16-bit systems, a light CRT shader, a tidier network share |
| **Bluetooth controllers** | Offered when preparing a drive on a PC with paired controllers: copies the pairings so the same controller works in Linux and Batocera without re-pairing. To keep Linux, Windows and Batocera sharing pairings all the time, see bt-share in MacWinBuntu |
| **Xbox button labels in Nintendo games** | Batocera binds the Xbox pad by position, so in Nintendo games the Xbox A button is the console's B. This makes A, B, X and Y do what their labels say in every Nintendo system: RetroArch ones (Game Boy, GBA, NES, SNES, DS...) through batocera.conf, and the standalone 3DS, Switch, Wii U, GameCube and DS emulators through the emubox_buttonlabels service (it changes Batocera's button tables in memory at each start, and leaves one alone if an update changed it). PlayStation, Sega and the rest stay by position |
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
- **APPS**: whether the menu music waits for your own, music dropping during a call and how
  far, and the ad blocker for web apps.
- **RGB HUB** (on a PC with the OMEN lights or the IQUNIX keyboard): following the game (both devices,
  or each on its own), lights on/off and brightness for the PC and the keyboard, a colour per light,
  effects and their speed, the cooler's screen, its picture and fit, and the **Default look** (what
  every device shows once Batocera has shut down: save the look now as the Default, or go back to it).

(Batocera's main menu cannot take a new entry of its own, so they sit inside Game Settings.)

**Batocera's own Sound settings work as they say**, although EmuBox plays the menu music and the
menu sounds itself:

- **FRONTEND MUSIC** turns the menu music on and off, like the Guide's **Menu music** switch:
  changing either one counts (Batocera's own player is kept from finding the songs, so only one
  ever plays). **MUSIC VOLUME** sets how loud it is, **STOP MUSIC ON SCREENSAVER** pauses it while
  the screensaver shows, and **DISPLAY SONG TITLES** puts the song's name in the Guide's music bar.
- **ENABLE NAVIGATION SOUNDS** turns every menu sound off, EmuBox's included.
- Not followed yet: **PLAY SYSTEM-SPECIFIC MUSIC** and **LOWER MUSIC WHEN PLAYING VIDEO**.

Settings the installer chooses for you (the theme, navigation sounds, the play settings, the Store
and Captures folder views) are set the first time only: what you change afterwards in Batocera's
menus stays, also when you run the installer again.

**Guide** opens EmuBox's own quick menu, over the menus or a running game:

- **Settings**: the system volume and mute, the **sound output** (by the names you know them by:
  the TV's own name, your headphones'; kept for the next start; **Automatic** puts sound on headphones
  whenever any are connected (Bluetooth, a USB headset, the headphone socket) and on HDMI otherwise), the **menu music** on or off, the
  menu sound set and its volume, **Bluetooth** (is the adapter working, which controllers are
  connected and their battery, and **Pair a controller**: hold the controller's pair button, B
  stops looking), the lights' basics
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
`menuopen.wav`, `boot.mp4` (a ready-made start-up film, played at start while the set is chosen) and
`boot.wav` for the start-up film's sound (the installer makes that set's film from it with EmuBox's
pictures; it needs GStreamer). A sound a set lacks is taken from EmuBox's. Until you choose a set in the menu, one with "xbox" in its name is used when there is one. Such sets are yours and
stay out of the repository.

### RPG Maker games on Windows (Wine)

Fan games made with RPG Maker XP/VX (Pokémon Essentials ones, for example) read only the keyboard,
and Batocera has no controller mapping for Windows games. The installer gives each such game in
`roms/windows/<Game>.pc/` a `padto.keys`: Xbox A confirms, B goes back, X runs, the d-pad and left
stick move, LB/RB turn pages (Hotkey+Start still quits). A game whose `Game.exe` is mkxp-z also gets an
`mkxp.json` that starts it full screen. A file a game already has is left alone, so your own
mapping wins. (Batocera names buttons by position: its "b" is the bottom button, Xbox A.)

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
- Log on Batocera: `/userdata/system/logs/emubox.log` (`EMUBOX_DEBUG=1` logs every button). About a
  minute after start-up it notes the connected controllers and the Bluetooth adapter's state (is it
  there and powered, what is paired): the place to look when a controller has odd buttons or will
  not connect.
- When Batocera has no layout of a controller's own but borrows one by its name, a note on screen
  says its buttons may be wrong and where to set them up (Start > Controller settings > Controller
  mapping). If a controller's buttons all do the wrong thing, also look in `system/configs/emulationstation/es_input.cfg`
  for an entry with the controller's name but another id: Batocera falls back to an entry with the
  same name when it has no exact one, and uses that entry's button numbers. (The test VM's layout
  for the Xbox pad did that once; it is now only added inside the VM, by `lib/vmpads.py`.)

## Safety

The worst that could happen is a wiped or corrupted drive, a drive or PC that cannot start, or
Batocera touching the PC's other disks. Each guard below exists because something went wrong
once (or nearly did), and each has a test in `tests/` that fails without it (mostly
`tests/test_guards.py`).

| Guard | Where | Protects against |
| --- | --- | --- |
| Batocera's storage helper only sees USB drives that are not Batocera drives | `boot-custom.sh` (drive guard) | Batocera mounting Ubuntu read-write and running ntfsfix on Windows; tested against a pretend `/sys`, `lsblk` and `blkid` |
| Partitions of the PC's own disks mounted while the guard was missing are let go | `emubox_bootguard` | the same, after an update removed `boot-custom.sh` |
| The boot menu is edited as a copy and used only when it still has every entry | `boot-custom.sh` | a drive that cannot start |
| The data partition must be labelled SHARE; the installer and every `batocera-*` tool refuse otherwise, and nothing ever renames or relabels a partition (lint) | `installer/target.py` `label_problem`, `tools/batocera-drive` | Batocera merging `/userdata` and moving every game into `.roms_base` |
| A loud warning at start-up when `/userdata/.roms_base` exists or `batocera-boot.conf` has `mergerfs.roms=` | `emubox_bootguard`, in `logs/emubox.log` | games out of sight going unnoticed |
| Games, saves, BIOS, the drive itself and each system's games folder are never removed whole | `installer/target.py` `Target.remove` | a wiped drive |
| Games, BIOS files and backups are replaced only by a copy checked by size and SHA-256, read back from the drive | `installer/target.py` `verified_copy` (installer, `backup-games`, `batocera-add`) | a game lost to a copy that went wrong |
| `batocera-backup` makes a new folder each time and deletes nothing | `tools/batocera-backup` | an earlier backup written over |
| The installer stops at a drive whose filesystem is larger than its partition, or whose partition is larger than its disk | `installer/target.py` `size_problem` | data written where there is nothing (a fake-capacity stick, a drive copied from a larger one) |
| After every install (and `--remove`) the test VM's pad layout and SSH keys EmuBox did not put there are taken off (keys are set aside in `authorized_keys.emubox-removed`; end a key's line with `emubox-keep` to keep it) | `installer/audit.py` | every face button of the real pad wrong; temporary root keys left on a drive |
| `batocera-vm` writes nothing to the stick unless given `--write`, and never uses a drive that is not removable | `tools/batocera-vm` | the VM changing the stick, or starting the PC's own Batocera |
| The EFI partition is written only with a partition-table backup, on an EFI system partition, in its EFI folder, with twice the loader's size free, and the old loader is replaced whole | `tools/dualboot/build-loader` | a PC that cannot start |
| The Bluetooth archive is never replaced by one without pairings, nor half-written | `components/bluetooth` | every controller having to be paired again |
| The Guide opens on the press and its let-go does not close it; one reading starts at most 12 programs; every label is plain and present; one footer | `lib/guide.py` `GuideButton`, `lib/startmenu.py` `plain_feature` | a Guide that never seems to open, is slow, or is rejected or crashes |
| Every key an app's controller mapper or the typer presses is let go; nothing runs `batocera-mouse`, and `wtype` only types a character the typer's own keyboard has no key for | `lib/pad.py`, `lib/typer.py` | a dead pointer or controller in apps, keys repeating |
| `pkill -f` / `pgrep -f` patterns are bracketed (`[w]sdd`) or anchored (lint) | everywhere | killing the wrong programs |
| The menus start even when EmuBox's music helper is broken | `boot-custom.sh` (`emubox-es`) | a TV with nothing on it |

Licence: GPL-3.0-or-later. Fonts: SIL Open Font Licence (see `components/look/files/fonts`).
EmuBox is not affiliated with Microsoft, Discord or Apple; it ships none of their artwork or software.
A tile's icon is the app's own: taken from the program once it is on the drive, or asked of Flathub or
the app's site when you install. Without a network the tiles keep EmuBox's own drawings.
