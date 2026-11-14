"""Friendly names for Batocera's system folders. Unknown folders are shown as they are."""

NAMES = {
    "3ds": "Nintendo 3DS", "atari2600": "Atari 2600", "c64": "Commodore 64", "dreamcast": "Dreamcast",
    "fds": "Famicom Disk System", "gamecube": "GameCube", "gamegear": "Game Gear", "gb": "Game Boy",
    "gba": "Game Boy Advance", "gbc": "Game Boy Color", "mame": "Arcade (MAME)", "mastersystem": "Master System",
    "megadrive": "Mega Drive / Genesis", "n64": "Nintendo 64", "nds": "Nintendo DS", "nes": "NES",
    "pcengine": "PC Engine", "pcenginecd": "PC Engine CD", "ports": "Ports", "ps2": "PlayStation 2",
    "ps3": "PlayStation 3", "psp": "PSP", "psx": "PlayStation", "satellaview": "Satellaview",
    "saturn": "Saturn", "segacd": "Sega CD", "sgb": "Super Game Boy", "snes": "Super Nintendo",
    "sufami": "Sufami Turbo", "switch": "Switch", "wii": "Wii", "wiiu": "Wii U", "xbox": "Xbox",
    "xbox360": "Xbox 360",
}


def name(system_id: str) -> str:
    return NAMES.get(system_id, system_id)
