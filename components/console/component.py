"""Console tools: one extra step while installing.

The Xbox Wireless Controller over Bluetooth is known to Batocera the way its own driver presents
it. Handed to a virtual machine (tools/batocera-vm), or on a system without that driver, the same
controller shows up in its plain form, which Batocera's list does not have: the menus then ignore
every button. This adds that form to the drive's own list of controllers, leaving anything
already there alone.
"""
import re

FILE = "system/configs/emulationstation/es_input.cfg"
GUID = "050000005e040000220b000023050000"
# Batocera names buttons by position, Nintendo-style: "b" is the bottom one (A on this pad).
# The button numbers start at 107: in this form the pad also reports 107 keyboard-style keys,
# and Batocera's input library counts those first (checked on Batocera 43 with a stand-in pad).
LAYOUT = f"""	<inputConfig type="joystick" deviceName="Xbox Wireless Controller" deviceGUID="{GUID}">
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


def with_layout(text: str) -> str:
    """The controllers file with our layout in it, replacing an earlier version of ours."""
    old = re.search(rf'[ \t]*<inputConfig [^>]*deviceGUID="{GUID}">.*?</inputConfig>\n?', text, re.S)
    if old:
        return text[:old.start()] + LAYOUT + text[old.end():]
    if "</inputList>" in text:
        return text.replace("</inputList>", LAYOUT + "</inputList>", 1)
    return '<?xml version="1.0"?>\n<inputList>\n' + LAYOUT + "</inputList>\n"


def install(env) -> None:
    path = env.target.path(FILE)
    before = path.read_text() if path.is_file() else ""
    after = with_layout(before)
    if after != before:
        env.target.write_text(FILE, after)
