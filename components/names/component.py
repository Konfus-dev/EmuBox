"""Tidy the names on the drive right away, not only at Batocera's next start."""
import importlib.util
from pathlib import Path


def install(env) -> None:
    spec = importlib.util.spec_from_file_location("nicenames", Path(__file__).parent / "files" / "nicenames.py")
    nicenames = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(nicenames)
    changed = nicenames.run(env.target.root, say=lambda line: None)
    env.say(f"  Tidied {changed} game name{'s' if changed != 1 else ''}.")
