"""Console tools: one extra step while installing.

Earlier versions added the test VM's form of the Xbox Wireless Controller to the drive's list of
controllers. On real hardware Batocera matched the real pad to it by name, and every face button
was wrong. That layout now lives in lib/vmpads.py and is added at start-up inside a VM only; this
takes it off a drive that still has it, leaving everything else in the list alone.
"""
import importlib.util
from pathlib import Path

FILE = "system/configs/emulationstation/es_input.cfg"

_spec = importlib.util.spec_from_file_location("vmpads", Path(__file__).parent / "files/lib/vmpads.py")
vmpads = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(vmpads)


def install(env) -> None:
    path = env.target.path(FILE)
    if not path.is_file():
        return
    before = path.read_text()
    after = vmpads.without_layout(before)
    if after != before:
        env.target.write_text(FILE, after)
