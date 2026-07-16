from __future__ import annotations

import hashlib
import textwrap
from io import BytesIO

from PIL import Image, ImageDraw, ImageFont

from src.fridgechef.models import RecipeItem
from src.fridgechef.recipe_planner import clean_user_text, sentence_case


_CANVAS_SIZE = (1200, 900)


def _font(size: int, *, bold: bool = False) -> ImageFont.ImageFont:
    """Load a common container font and keep a Pillow fallback for portability."""
    candidates = (
        "/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf"
        if bold
        else "/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf",
        "DejaVuSans-Bold.ttf" if bold else "DejaVuSans.ttf",
    )
    for candidate in candidates:
        try:
            return ImageFont.truetype(candidate, size=size)
        except OSError:
            continue
    return ImageFont.load_default()


def _palette(seed_text: str) -> tuple[tuple[int, int, int], ...]:
    """Build a stable warm palette from the recipe content."""
    digest = hashlib.sha256(seed_text.encode("utf-8")).digest()
    accent = (150 + digest[0] % 70, 75 + digest[1] % 90, 55 + digest[2] % 80)
    secondary = (75 + digest[3] % 90, 125 + digest[4] % 90, 85 + digest[5] % 80)
    return (
        (250, 245, 235),
        (236, 224, 203),
        accent,
        secondary,
        (52, 48, 55),
    )


def generate_local_recipe_image(recipe: RecipeItem) -> tuple[bytes, str]:
    """Create a deterministic recipe card when cloud image generation is unavailable.

    The fallback is generated entirely on the application host. It guarantees that
    every requested recipe still has a useful visual without pretending that a
    cloud-generated food photograph succeeded.
    """
    title = sentence_case(recipe.title) or "Receta FridgeChef"
    ingredients = [sentence_case(item) for item in recipe.ingredients_used if clean_user_text(item)]
    seed_text = "|".join([title, *ingredients])
    background, surface, accent, secondary, ink = _palette(seed_text)

    image = Image.new("RGB", _CANVAS_SIZE, background)
    draw = ImageDraw.Draw(image)

    # Layered rounded surfaces provide a polished result without external assets.
    draw.rounded_rectangle((65, 55, 1135, 845), radius=58, fill=surface)
    draw.rounded_rectangle((105, 95, 1095, 805), radius=48, fill=(255, 253, 248))

    # Draw a simple top-down plated dish motif that changes with each recipe hash.
    plate_box = (150, 150, 690, 690)
    draw.ellipse(plate_box, fill=(240, 237, 229), outline=(210, 202, 189), width=10)
    draw.ellipse((205, 205, 635, 635), fill=(250, 248, 242))
    draw.ellipse((270, 270, 570, 570), fill=accent)
    draw.arc((245, 245, 595, 595), 205, 350, fill=secondary, width=42)
    draw.arc((275, 280, 560, 575), 20, 165, fill=(245, 190, 95), width=36)

    digest = hashlib.sha256(seed_text.encode("utf-8")).digest()
    for index in range(14):
        x = 300 + digest[index] % 225
        y = 305 + digest[-index - 1] % 215
        radius = 8 + digest[(index + 7) % len(digest)] % 13
        colour = secondary if index % 2 == 0 else (247, 211, 120)
        draw.ellipse((x - radius, y - radius, x + radius, y + radius), fill=colour)

    title_font = _font(54, bold=True)
    subtitle_font = _font(30, bold=True)
    body_font = _font(27)
    small_font = _font(22)

    wrapped_title = textwrap.wrap(title, width=22)[:4]
    y = 150
    for line in wrapped_title:
        draw.text((745, y), line, font=title_font, fill=ink)
        y += 68

    y += 18
    draw.rounded_rectangle((745, y, 1045, y + 7), radius=4, fill=accent)
    y += 45
    draw.text((745, y), "Ingredientes principales", font=subtitle_font, fill=secondary)
    y += 54

    visible_ingredients = ingredients[:6] or ["Alimentos disponibles"]
    for ingredient in visible_ingredients:
        wrapped = textwrap.wrap(ingredient, width=28) or [ingredient]
        draw.ellipse((746, y + 10, 758, y + 22), fill=accent)
        draw.text((775, y), wrapped[0], font=body_font, fill=ink)
        y += 42

    draw.text(
        (745, 745),
        "Imagen local de respaldo · FridgeChef AI",
        font=small_font,
        fill=(105, 100, 108),
    )

    output = BytesIO()
    image.save(output, format="JPEG", quality=90, optimize=True)
    return output.getvalue(), "image/jpeg"
