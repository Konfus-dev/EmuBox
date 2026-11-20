#!/bin/sh
# EmuBox: Batocera's menu program runs this when its screensaver starts and stops (installed as
# scripts/screensaver-start/ and scripts/screensaver-stop/). While the screensaver shows, EmuBox's
# menu music pauses when Sound settings > STOP MUSIC ON SCREENSAVER is on (lib/audio.py).
mkdir -p /var/run/emubox
case "$(basename "$(dirname "$0")")" in
    screensaver-start) : > /var/run/emubox/screensaver ;;
    *)                 rm -f /var/run/emubox/screensaver ;;
esac
exit 0
