# Tools

Commands for looking after a Batocera drive from a Linux PC. `./install` links them into
`~/.local/bin`. Each explains itself with `--help` or in the comment at its top.

| Tool | Does |
| --- | --- |
| `batocera-add` | copy games and ROM-hack patches onto the drive, into the right folders |
| `batocera-backup` | back up saves, screenshots and settings |
| `batocera-wifi` | set the drive's Wi-Fi network |
| `batocera-scraper`, `batocera-achievements` | set the ScreenScraper / RetroAchievements account |
| `batocera-vm` | boot the drive in a window (QEMU), without restarting the PC |
| `batocera-preview` | preview a theme in a window (needs a `~/batocera-preview` folder with Batocera's files) |

`dev/` holds two helpers for working on RetroBox itself: `fakepad.py` (a pretend controller for
testing in a virtual machine) and `tile.py` (draws an app's menu picture).
