# Vault

Your own list of store pages, opened from **Store > Vault** and browsed with the controller.
**Store > itch.io** is the same thing opened straight on itch.io, as a store of its own.
Anything you download in it lands in Vault's downloads folder. The moment a finished file is
noticed there, Vault asks **Install to which system?**, runs the install command for it, and
refreshes the game lists when you leave.

It uses the web engine Batocera already has, so there is nothing to download first.

## Buttons

| Button | In a page | In the lists |
| --- | --- | --- |
| D-pad | Move the highlight between links and buttons; scrolls when there is nothing further | Move |
| A | Press the highlighted thing | Choose |
| B | Leave a text box; back one page; from the first page, back to the list | Leave / "Not now" |
| X (or L3) | On-screen keyboard | |
| Y | Back to the list of pages | |
| Right stick, R3 | Pointer, click (for anything the D-pad cannot reach) | |
| Left stick | Scroll | |
| LB / RB | Back / forward | Jump a screen up / down |
| LT / RT | Zoom out / in | |
| Start | Reload | |
| Select+A | Right click | |
| Select+Start | Leave Vault | Leave Vault |
| Guide | Batocera's in-game menu | |

The page view and its D-pad navigation are not Vault's own: they are the console tools
`lib/webview.py` and `lib/webnav.js`, which any other web app can use (see
[Extending EmuBox](extending.md#add-a-web-app)).

A keyboard and mouse work too.

## Setting it up

On Batocera (over SSH, or from the file manager's terminal):

```sh
vault=/userdata/system/emubox/bin/vault

$vault add "My Shop" https://shop.example      # add a page (same name again: change its address)
$vault rename "My Shop" "Corner Shop"          # the name is whatever you like; it is what the list shows
$vault remove "Corner Shop"                    # take one off
$vault pages                                   # list them

$vault command                                 # show what runs for each download
$vault command 'mv -n -- "$VAULT_FILE" "$VAULT_GAMES/$VAULT_SYSTEM/"'
$vault refresh 'curl -s -m 10 http://127.0.0.1:1234/reloadgames'
$vault downloads /userdata/system/vault/downloads
$vault reset                                   # command, refresh and downloads back to the built-in ones
$vault show                                    # everything that is set
```

The command is one shell line, run once per download after you pick a system. It is given
`$VAULT_FILE` (the download), `$VAULT_SYSTEM` (the folder name of the system you picked, such as
`psx`), `$VAULT_GAMES` (`/userdata/roms`) and `$VAULT_DOWNLOADS`. If it fails, its last line of
output is shown and the file stays in downloads. The refresh line runs once when you leave Vault,
if anything was installed.

With the drive plugged into a PC instead, `batocera-vault` (one of the helpers in `tools/`) takes
the same words and finds the drive itself:

```sh
batocera-vault add "My Shop" https://shop.example
batocera-vault pages
```

To give another site a tile of its own in the Store, like itch.io, add a port to
`components/vault/component.json` whose command is `vault go https://address`.

Settings are one file, `/userdata/system/vault/vault.json`; sign-ins are kept next to it in `web/`.

## When the drive is full

Vault shows the free space at the top right of its lists, and the menus show it under the clock.
A download that would not fit is refused before it starts, with what it needs and what is free.
If the drive fills up while downloading, the half file is removed and Vault says so. If the install
command fails, its last line of output is shown and the file stays in downloads; nothing is lost.

## Good to know

- Pressing B on "Install to which system?" leaves the file in downloads; Vault asks again the
  next time it is opened.
- Files put into the downloads folder some other way (the network share, a USB stick) are
  noticed too, a couple of seconds after they stop growing.
- Systems that play the file's type are listed first. Archives (`.zip`, `.7z`) fit almost
  everything, so for those the list is alphabetical.
- Pages are starting points, not a fence: links can lead anywhere, since stores send you to
  other addresses to sign in and to download.
