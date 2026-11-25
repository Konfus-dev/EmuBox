#!/bin/sh
# EmuBox: keeps each game's launch log. Batocera keeps only the last launch's
# (es_launch_stdout.log / es_launch_stderr.log), so when a game fails and another
# is started, the error is gone. At each game's end the two are saved as
# /userdata/system/logs/launches/<date> <system> <game>.log; the last 10 are kept.
# Batocera calls this with: gameStart|gameStop <system> <emulator> <core> <rom>
[ "$1" = gameStop ] || exit 0
sleep 1   # the launcher's last lines
dir=/userdata/system/logs/launches
mkdir -p "$dir"
name=$(basename "$5" | tr -c 'A-Za-z0-9._ -\n' '_' | cut -c1-60)
out="$dir/$(date '+%F %H%M%S') $2 $name.log"
{
    echo "== $2 / $3 / $4: $5"
    echo "== stdout"; cat /userdata/system/logs/es_launch_stdout.log 2>/dev/null
    echo "== stderr"; cat /userdata/system/logs/es_launch_stderr.log 2>/dev/null
} > "$out"
ls -1t "$dir"/*.log 2>/dev/null | tail -n +11 | while IFS= read -r old; do rm -f "$old"; done
exit 0
