#!/bin/bash
# Steam. Downloads itself the first time (needs internet), then opens.
app=/userdata/system/retrobox/bin/retrobox-app
if ! flatpak info com.valvesoftware.Steam >/dev/null 2>&1; then
    "$app" fetch Steam com.valvesoftware.Steam || exit 0
    # Tell Batocera about it, so Steam and your installed games get their own entries too.
    batocera-flatpak-update >/dev/null 2>&1
    batocera-steam-update >/dev/null 2>&1
fi
# Xbox controllers over Bluetooth: have Steam read them the way the rest of Batocera does.
export SDL_JOYSTICK_HIDAPI_XBOX=0
exec batocera-steam
