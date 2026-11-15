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
    exit 0
fi

# --- stop: keep this file through Batocera updates ---------------------------------------------
# Batocera's updater lists the files on /boot that it did not ship in /boot/boot.stale and deletes
# them at the next start, which would remove this file. Shutdown (the reboot after an update
# included) takes it off that list. EmuBox's emubox_bootguard service and the EmuBox boot loader
# also put it back when it is missing.
if [ "$1" = "stop" ] && [ -f /boot/boot.stale ] && grep -q '^boot-custom' /boot/boot.stale; then
    if mount -o remount,rw /boot; then
        grep -v '^boot-custom' /boot/boot.stale > /tmp/boot.stale.kept
        cat /tmp/boot.stale.kept > /boot/boot.stale
        sync
        mount -o remount,ro /boot
    fi
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
if pgrep -f /usr/bin/wsdd >/dev/null 2>&1; then
    pkill -f /usr/bin/wsdd
    for i in 1 2 3 4 5 6; do pgrep -f /usr/bin/wsdd >/dev/null 2>&1 || break; sleep 0.5; done
    pgrep -f /usr/bin/wsdd >/dev/null 2>&1 && pkill -9 -f /usr/bin/wsdd
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

# Show kernel messages on screen from here on, so a hang leaves its last lines visible.
dmesg -n 7 2>/dev/null
chvt 3 2>/dev/null
say "handing over to unmount and power-off"
exit 0
