"""The EmuBox wordmark, drawn the same way wherever it appears (start-up film, cooler screen)."""
from pathlib import Path

from PIL import Image, ImageDraw, ImageFilter, ImageFont

FONT = Path(__file__).resolve().parent.parent / "files" / "theme" / "art" / "fonts" / "Michroma-Regular.ttf"
NAME = "EMUBOX"


def wordmark(width: int, height: int, letters: int, gap: int = 0, name: str = NAME) -> tuple[Image.Image, Image.Image]:
    """The name centred on a clear canvas of this size (letters = font size in pixels), and what
    sits behind it: a dark shadow so it reads on a bright background, with a green glow."""
    font = ImageFont.truetype(str(FONT), letters)
    gap = gap or max(2, letters // 7)
    text = Image.new("RGBA", (width, height), (0, 0, 0, 0))
    draw = ImageDraw.Draw(text)
    widths = [draw.textlength(letter, font=font) for letter in name]
    x = (width - sum(widths) - gap * (len(name) - 1)) / 2
    for letter, letter_width in zip(name, widths):
        draw.text((x, height / 2 - letters * 0.65), letter, font=font, fill=(240, 255, 215, 255))
        x += letter_width + gap
    glow = Image.new("RGBA", (width, height), (150, 255, 60, 0))
    glow.putalpha(text.getchannel("A").filter(ImageFilter.GaussianBlur(letters / 6)).point(lambda v: min(255, int(v * 1.6))))
    dark = Image.new("RGBA", (width, height), (0, 12, 0, 0))
    dark.putalpha(text.getchannel("A").filter(ImageFilter.GaussianBlur(letters / 2.8)).point(lambda v: min(255, int(v * 2.2))))
    return text, Image.alpha_composite(dark, glow)
