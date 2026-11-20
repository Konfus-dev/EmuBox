#!/bin/bash
# Batocera runs this file at the very start of boot ("start") and as the last step of shutdown ("stop").
# Installed by EmuBox's drive-guard component; the master copy is /userdata/system/emubox/boot/boot-custom.sh.
#
# --- start: keep Batocera away from this PC's own disks (added 2026-11-15) ---------------------
# Why: Batocera's storage manager mounts every partition it finds as a games drive. Booted from the
# PC's own disk it mounted Ubuntu read-write and ran ntfsfix on Windows, and it tried to merge the
# USB stick into the games library. The owner's rule: Batocera must never touch other partitions.
# How: every drive Batocera notices goes through /usr/bin/batocera-storage-udev (its udev rule). Before
# udev starts, that helper is replaced (in memory only) by a guard that lets through only USB drives
# that are not Batocera drives themselves. Batocera's own partitions are mounted at boot by other
# code and are not affected. Decisions are logged to /var/log/emubox-drive-guard.log.
if [ "$1" = "start" ]; then
    H=/usr/bin/batocera-storage-udev
    [ -e "$H.real" ] || cp -p "$H" "$H.real"
    cat > "$H" <<'GUARD'
#!/bin/bash
# EmuBox drive guard (written by /boot/boot-custom.sh at every boot): only USB drives that are not
# Batocera drives reach Batocera's storage manager. This PC's own disks are never mounted or changed.
ACTION=$1; DEV=$2
[ "$ACTION" = add ] || exec /usr/bin/batocera-storage-udev.real "$@"
if [ -e "/sys/class/block/$DEV/partition" ]; then
    disk=$(basename "$(dirname "$(readlink -f "/sys/class/block/$DEV")")")
else
    disk=$DEV
fi
why=""
case "$(readlink -f "/sys/block/$disk")" in
    */usb*) ;;
    *) why="not a USB drive (this PC's own disk)" ;;
esac
if [ -z "$why" ]; then
    # Labels of this partition, or of every partition when it is the whole disk.
    labels="${ID_FS_LABEL:-} $(lsblk -nro LABEL "/dev/$DEV" 2>/dev/null | tr '\n' ' ') $(blkid -s LABEL -o value "/dev/$DEV" 2>/dev/null)"
    case " $labels " in
        *" SHARE "*|*" BATOCERA "*) why="another Batocera drive" ;;
    esac
fi
if [ -n "$why" ]; then
    echo "$(date '+%F %T') left alone: $DEV ($why)" >> /var/log/emubox-drive-guard.log
    exit 0
fi
echo "$(date '+%F %T') passed on: $DEV" >> /var/log/emubox-drive-guard.log
exec /usr/bin/batocera-storage-udev.real "$@"
GUARD
    chmod 755 "$H"

    # --- the start-up film keeps its sound (added 2026-11-15) ---
    # Batocera sets up the sound output (S27audioconfig) just before the film starts (S28splash).
    # When the TV's sound is not ready yet it keeps retrying in the background, and the retry that
    # finally works switches the output while the film plays, cutting its sound off. So the film
    # waits for that (10 seconds at most); when the first try works there is no wait at all.
    S=/etc/init.d/S28splash
    if [ -f "$S" ] && ! grep -q EMUBOX "$S"; then
        cp -p "$S" /etc/init.d/.S28splash.batocera
        cat > "$S" <<'SPLASH'
#!/bin/sh
# EMUBOX: wait for Batocera's sound set-up to finish, then start the film (see /boot/boot-custom.sh).
if [ "$1" = "start" ]; then
    n=0
    while [ $n -lt 20 ] && pgrep -f '/etc/init.d/[S]27audioconfig' >/dev/null 2>&1; do
        sleep 0.5; n=$((n + 1))
    done
    [ $n -gt 0 ] && echo "$(date '+%F %T') film waited $((n / 2)) s for the sound set-up" >> /var/log/emubox-boot.log
fi
exec /etc/init.d/.S28splash.batocera "$@"
SPLASH
        chmod 755 "$S"
    fi

    # --- the test VM's controller layout, in the VM only (added 2026-11-19) ---
    # Batocera's menus read the controller list once, when they start (S31emulationstation), and
    # /userdata is not there yet while this file runs. So a step that runs in between is added (in
    # memory): lib/vmpads.py puts the VM's layout in the list inside a VM and takes it out on real
    # hardware, where it made every face button of the real Xbox pad wrong.
    cat > /etc/init.d/S30emuboxpads <<'PADS'
#!/bin/sh
# EMUBOX (written by /boot/boot-custom.sh): the test VM's controller layout, in a VM only.
[ "$1" = start ] || exit 0
f=/userdata/system/emubox/lib/vmpads.py
[ -f "$f" ] && python3 "$f" >> /var/log/emubox-boot.log 2>&1
exit 0
PADS
    chmod 755 /etc/init.d/S30emuboxpads

    # --- FRONTEND MUSIC switches EmuBox's music (added 2026-11-19) ---
    # EmuBox plays the menus' music itself. Batocera's menu program is started through emubox-es,
    # which hides the music folders from it (lib/esquiet.py), so its own player stays silent and
    # its FRONTEND MUSIC switch only turns EmuBox's music on and off (lib/audio.py).
    cat > /usr/bin/emubox-es <<'ES'
#!/bin/sh
# EMUBOX (written by /boot/boot-custom.sh): start the menu program without its own music.
# Only when the helper is there and sound: a missing Python or a damaged file must never keep the
# menus from starting (it would leave the TV with nothing to use), so then they start as usual.
f=/userdata/system/emubox/lib/esquiet.py
if [ -f "$f" ] && command -v python3 >/dev/null 2>&1 && python3 -m py_compile "$f" 2>/dev/null; then
    exec python3 "$f" "$@"
fi
exec "$@"
ES
    chmod 755 /usr/bin/emubox-es
    E=/usr/bin/emulationstation-standalone
    if [ -f "$E" ] && ! grep -q "emubox-es emulationstation" "$E"; then
        sed -i 's/dbus-run-session -- emulationstation /dbus-run-session -- emubox-es emulationstation /' "$E"
    fi

    # --- EmuBox's look from the first moment (added 2026-11-19) ---
    # Batocera's logo is the first thing on screen (S03system-splash, just after this file runs).
    # EmuBox's own loading picture takes its place, in memory only: the boot guard keeps a copy on
    # this partition as /boot/emubox-boot-logo.png.
    if [ -f /boot/emubox-boot-logo.png ]; then
        for f in /usr/share/batocera/splash/boot-logo.png /usr/share/batocera/splash/boot-logo-4x3.png; do
            [ -e "$f" ] && cp /boot/emubox-boot-logo.png "$f"
        done
    fi
    # The boot menu on this drive stays hidden (Esc still shows it) and does not print
    # "Booting Batocera.linux...". Only this drive's own grub.cfg is changed, and again after an
    # update puts Batocera's back.
    for g in /boot/EFI/BOOT/grub.cfg /boot/EFI/batocera/grub.cfg; do
        [ -f "$g" ] || continue
        if grep -q '^[[:space:]]*echo Booting Batocera' "$g" || ! grep -q '^set timeout_style=hidden' "$g"; then
            if mount -o remount,rw /boot; then
                # Edited as a copy, which replaces the boot menu only when it still has every entry
                # and its start command: a damaged grub.cfg would leave this drive unable to start.
                sed -e '/^[[:space:]]*echo Booting Batocera/d' -e '/^set timeout=/{n;/^set timeout_style=hidden/!i set timeout_style=hidden
}' "$g" > "$g.emubox-new"
                # The new file must be exactly the old one without the message lines and with the
                # one hiding line: anything else (a lost brace, a lost entry) and it is not used.
                grep -v -e '^[[:space:]]*echo Booting Batocera' -e '^set timeout_style=hidden' "$g" > "$g.emubox-want"
                grep -v -e '^set timeout_style=hidden' "$g.emubox-new" > "$g.emubox-got"
                if [ -s "$g.emubox-new" ] && cmp -s "$g.emubox-want" "$g.emubox-got" \
                   && grep -q '^set timeout_style=hidden' "$g.emubox-new"; then
                    cp -p "$g" "$g.emubox-before" 2>/dev/null
                    mv "$g.emubox-new" "$g"
                    echo "$(date '+%F %T') boot menu: hid it and its message in $g" >> /var/log/emubox-boot.log
                else
                    rm -f "$g.emubox-new"
                    echo "$(date '+%F %T') boot menu: edit did not check out, left as it was: $g" >> /var/log/emubox-boot.log
                fi
                rm -f "$g.emubox-want" "$g.emubox-got"
                sync
                mount -o remount,ro /boot
            fi
        fi
    done
    exit 0
fi

# --- stop: keep this file through Batocera updates ---------------------------------------------
# Batocera's updater lists the files on /boot that it did not ship in /boot/boot.stale and deletes
# them at the next start, which would remove this file. Shutdown (the reboot after an update
# included) takes it off that list. EmuBox's emubox_bootguard service and the EmuBox boot loader
# also put it back when it is missing.
if [ "$1" = "stop" ] && [ -f /boot/boot.stale ] && grep -q -e '^boot-custom' -e '^emubox-boot-logo' /boot/boot.stale; then
    if mount -o remount,rw /boot; then
        grep -v -e '^boot-custom' -e '^emubox-boot-logo' /boot/boot.stale > /tmp/boot.stale.kept
        cat /tmp/boot.stale.kept > /boot/boot.stale
        sync
        mount -o remount,ro /boot
    fi
fi

# --- stop: keep this start's timings, for finding what is slow (Batocera keeps them in memory) ---
if [ "$1" = "stop" ] && [ -d /userdata/system/logs ]; then
    cat /var/run/boot.log /var/log/emubox-boot.log /var/log/emubox-drive-guard.log \
        > /userdata/system/logs/last-boot.log 2>/dev/null
fi

# --- stop: shutdown tracer and Wi-Fi power-down (added 2026-11-13) ------------------------------
# Shutdown tracer and Wi-Fi power-down test (added 2026-11-13).
# Why: on the OMEN desktop, "Shutdown" left the PC hung with its lights on. Batocera runs this
# file with "stop" as the last step before it unmounts the drives and powers off.
# It writes /userdata/system/logs/shutdown-trace.log, then unloads the Wi-Fi driver, which is the
# suspected cause of the hang. Delete this file to undo.
[ "$1" = "stop" ] || exit 0
L=/userdata/system/logs/shutdown-trace.log
say() { echo "$(date '+%F %T') $*" >> "$L"; sync; }

say "=== shutdown reached the last step (runlevel: $(runlevel 2>/dev/null | cut -d' ' -f2))"
# Batocera's network-discovery helper (wsdd) is told to stop but is still running when the drives
# are unmounted, so the games partition is never cleanly unmounted. Stop it properly and wait.
# ([w]sdd: the brackets keep the pattern from matching its own command line.)
if pgrep -f '/usr/bin/[w]sdd' >/dev/null 2>&1; then
    pkill -f '/usr/bin/[w]sdd'
    for i in 1 2 3 4 5 6; do pgrep -f '/usr/bin/[w]sdd' >/dev/null 2>&1 || break; sleep 0.5; done
    pgrep -f '/usr/bin/[w]sdd' >/dev/null 2>&1 && pkill -9 -f '/usr/bin/[w]sdd'
    say "stopped leftover wsdd"
fi
for p in $(fuser -m /userdata 2>/dev/null); do
    [ "$p" = "$$" ] && continue
    c=$(tr '\0' ' ' < /proc/$p/cmdline 2>/dev/null) || continue
    [ -n "$c" ] && say "still using /userdata: pid $p: $c"
done

for n in /sys/class/net/wl*; do
    [ -e "$n" ] || continue
    ifc=$(basename "$n")
    mod=$(basename "$(readlink -f "$n/device/driver/module" 2>/dev/null)" 2>/dev/null)
    say "wifi: $ifc uses driver '$mod'; taking it down"
    ip link set dev "$ifc" down 2>>"$L"
    if [ -n "$mod" ]; then
        say "wifi: unloading $mod"
        timeout 10 modprobe -r "$mod" >>"$L" 2>&1
        say "wifi: unload finished (exit code $?)"
    fi
done
[ -e /sys/class/net/wlan0 ] || say "wifi: no Wi-Fi interface is present now"

say "handing over to unmount and power-off"
exit 0
