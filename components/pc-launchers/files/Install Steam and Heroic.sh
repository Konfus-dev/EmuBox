#!/bin/bash
# Installs the Steam and Heroic (Epic/GOG) launchers. Needs internet and ~6 GB free.
LOG=/userdata/system/logs/install-launchers.log
install() {
    free_gb=$(df -BG --output=avail /userdata | tail -1 | tr -dc 0-9)
    if [ "${free_gb:-0}" -lt 6 ]; then echo "Not enough free space (${free_gb} GB free, 6 GB needed)."; return 1; fi
    flatpak remote-add --if-not-exists flathub https://dl.flathub.org/repo/flathub.flatpakrepo || return 1
    flatpak install -y --noninteractive flathub com.valvesoftware.Steam com.heroicgameslauncher.hgl || return 1
    batocera-flatpak-update
    batocera-steam-update
    echo "Done. Steam and Heroic are now in the menu (restart the menu if they don't appear)."
}
export -f install
if command -v xterm >/dev/null && [ -n "$DISPLAY" ]; then
    xterm -fullscreen -fa Monospace -fs 14 -e bash -c "install 2>&1 | tee $LOG; sleep 8"
else
    install > "$LOG" 2>&1
fi
