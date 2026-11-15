# Tools

Commands for looking after a Batocera drive from a Linux PC. `./install` links them into
`~/.local/bin`. Each explains itself with `--help` or in the comment at its top.

| Tool | Does |
| --- | --- |
| `batocera-drive` | prints where Batocera's data is (a USB stick, an internal disk, or the folder you name with `--drive` or `BATOCERA_DRIVE`); the others find the drive with it. `--list` shows every Batocera drive, `--main N` sets the one used when there are several |
| `batocera-add` | copy games and ROM-hack patches onto the drive, into the right folders |
| `batocera-backup` | back up saves, screenshots and settings |
| `batocera-wifi` | set the drive's Wi-Fi network |
| `batocera-vault` | set Vault's pages and install command on the drive |
| `batocera-scraper`, `batocera-achievements` | set the ScreenScraper / RetroAchievements account |
| `batocera-vm` | boot the drive in a window (QEMU), without restarting the PC |
| `batocera-preview` | preview a theme in a window (needs a `~/batocera-preview` folder with Batocera's files) |

`dev/` holds helpers for working on EmuBox itself:

| | |
| --- | --- |
| `fakepad.py` | a pretend controller that plays commands written to a pipe |
| `tile.py` | draws a tile's picture for the menus: an icon over the name (`--all` redraws every one) |
| `headless` | runs a command on a display nobody sees, so trying a screen does not pop a window up: `tools/dev/headless batocera-preview` |
| `webcheck.py` | drives Vault and the web view from start to finish against a pretend shop: `tools/dev/headless python3 tools/dev/webcheck.py` |