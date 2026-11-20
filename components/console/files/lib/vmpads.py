"""The test VM's controller layout: in Batocera's controller list inside the VM only.

The Xbox Wireless Controller handed to the test VM (tools/batocera-vm) shows up in its plain
form, which Batocera's list does not have, so its menus would ignore every button. That form has
the same name as the real controller, "Xbox Wireless Controller", and Batocera's menus fall back
to a name match for a controller they have no exact entry for: on real hardware, a layout for the
VM's form makes every face button of the real pad wrong (that happened, 2026-11-19).

So the layout is added only when Batocera runs in a VM, and taken out on real hardware. Run at
every start before the menus start (S30emuboxpads, written by /boot/boot-custom.sh):

    python3 vmpads.py            add in a VM, remove otherwise
    python3 vmpads.py --remove   remove
"""
import re
import sys
from pathlib import Path

FILE = Path("/userdata/system/configs/emulationstation/es_input.cfg")
GUID = "050000005e040000220b000023050000"
# Batocera names buttons by position, Nintendo-style: "b" is the bottom one (A on this pad).
# The button numbers start at 107: in this form the pad also reports 107 keyboard-style keys,
# and Batocera's input library counts those first (checked on Batocera 43 with a stand-in pad).
LAYOUT = f"""\
	<inputConfig type="joystick" deviceName="Xbox Wireless Controller" deviceGUID="{GUID}">
		<input name="a" type="button" id="108" value="1" code="305" />
		<input name="b" type="button" id="107" value="1" code="304" />
		<input name="x" type="button" id="111" value="1" code="308" />
		<input name="y" type="button" id="110" value="1" code="307" />
		<input name="pageup" type="button" id="113" value="1" code="310" />
		<input name="pagedown" type="button" id="114" value="1" code="311" />
		<input name="select" type="button" id="117" value="1" code="314" />
		<input name="start" type="button" id="118" value="1" code="315" />
		<input name="hotkey" type="button" id="119" value="1" code="316" />
		<input name="l3" type="button" id="120" value="1" code="317" />
		<input name="r3" type="button" id="121" value="1" code="318" />
		<input name="l2" type="axis" id="5" value="1" code="10" />
		<input name="r2" type="axis" id="4" value="1" code="9" />
		<input name="up" type="hat" id="0" value="1" code="16" />
		<input name="right" type="hat" id="0" value="2" code="16" />
		<input name="down" type="hat" id="0" value="4" code="16" />
		<input name="left" type="hat" id="0" value="8" code="16" />
		<input name="joystick1left" type="axis" id="0" value="-1" code="0" />
		<input name="joystick1up" type="axis" id="1" value="-1" code="1" />
		<input name="joystick2left" type="axis" id="2" value="-1" code="2" />
		<input name="joystick2up" type="axis" id="3" value="-1" code="5" />
	</inputConfig>
"""
OURS = re.compile(rf'[ \t]*<inputConfig [^>]*deviceGUID="{GUID}">.*?</inputConfig>\n?', re.S)


def in_vm() -> bool:
    try:
        vendor = Path("/sys/class/dmi/id/sys_vendor").read_text()
    except OSError:
        vendor = ""
    return "QEMU" in vendor or "emubox.vm" in Path("/proc/cmdline").read_text()


def without_layout(text: str) -> str:
    return OURS.sub("", text)


def with_layout(text: str) -> str:
    """The controllers file with our layout in it, replacing an earlier version of ours."""
    text = without_layout(text)
    if "</inputList>" in text:
        return text.replace("</inputList>", LAYOUT + "</inputList>", 1)
    return '<?xml version="1.0"?>\n<inputList>\n' + LAYOUT + "</inputList>\n"


def main(argv: list[str]) -> int:
    before = FILE.read_text() if FILE.is_file() else ""
    after = with_layout(before) if in_vm() and "--remove" not in argv else without_layout(before)
    if after != before:
        FILE.parent.mkdir(parents=True, exist_ok=True)
        FILE.write_text(after)
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
