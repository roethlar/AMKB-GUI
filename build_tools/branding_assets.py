"""Generate OpenKeeb identity assets from one deterministic geometry source."""

from __future__ import annotations

from pathlib import Path

from PIL import Image, ImageDraw, ImageFilter


ROOT = Path(__file__).resolve().parents[1]
ASSETS = ROOT / "assets"
WEB_ICON = ROOT / "am_configurator" / "web" / "icon.png"
MASTER_SIZE = 1024

INK = "#0B0E14"
SURFACE = "#151A24"
SURFACE_HIGH = "#242B39"
VIOLET = "#9B7BFF"
VIOLET_DARK = "#6946DF"
CYAN = "#52D6E8"
WHITE = "#F5F7FB"


def _scaled(value: int, size: int = MASTER_SIZE) -> int:
    return round(value * size / 256)


def _rounded(
    draw: ImageDraw.ImageDraw,
    box: tuple[int, int, int, int],
    radius: int,
    *,
    fill: str | None = None,
    outline: str | None = None,
    width: int = 1,
) -> None:
    draw.rounded_rectangle(
        tuple(_scaled(value) for value in box),
        radius=_scaled(radius),
        fill=fill,
        outline=outline,
        width=_scaled(width),
    )


def master_icon() -> Image.Image:
    image = Image.new("RGBA", (MASTER_SIZE, MASTER_SIZE), (0, 0, 0, 0))

    shadow = Image.new("RGBA", image.size, (0, 0, 0, 0))
    shadow_draw = ImageDraw.Draw(shadow)
    _rounded(shadow_draw, (20, 24, 236, 240), 50, fill="#000000C8")
    shadow = shadow.filter(ImageFilter.GaussianBlur(_scaled(10)))
    image.alpha_composite(shadow)

    glow = Image.new("RGBA", image.size, (0, 0, 0, 0))
    glow_draw = ImageDraw.Draw(glow)
    _rounded(glow_draw, (24, 20, 232, 228), 46, outline="#8B6BFFB8", width=7)
    glow = glow.filter(ImageFilter.GaussianBlur(_scaled(9)))
    image.alpha_composite(glow)

    draw = ImageDraw.Draw(image)
    _rounded(draw, (20, 18, 236, 234), 48, fill=INK, outline=VIOLET, width=4)
    _rounded(draw, (31, 29, 225, 223), 39, fill=SURFACE, outline="#343C4D", width=2)

    # Three keys orbit an intentionally open lower-right station: a small hub
    # rather than a monogram or a vendor keyboard silhouette.
    _rounded(draw, (54, 54, 122, 122), 15, fill=VIOLET_DARK, outline=VIOLET, width=3)
    _rounded(draw, (134, 54, 202, 122), 15, fill=SURFACE_HIGH, outline=CYAN, width=3)
    _rounded(draw, (54, 134, 122, 202), 15, fill=SURFACE_HIGH, outline=CYAN, width=3)
    _rounded(draw, (134, 134, 202, 202), 15, fill="#0F131B", outline="#566071", width=3)

    # Connection seams converge on one portable configuration hub.
    seam_width = _scaled(5)
    draw.line(
        [(_scaled(122), _scaled(88)), (_scaled(134), _scaled(88))],
        fill=VIOLET,
        width=seam_width,
    )
    draw.line(
        [(_scaled(88), _scaled(122)), (_scaled(88), _scaled(134))],
        fill=CYAN,
        width=seam_width,
    )
    draw.line(
        [(_scaled(122), _scaled(122)), (_scaled(145), _scaled(145))],
        fill=WHITE,
        width=_scaled(4),
    )
    draw.ellipse(
        (_scaled(109), _scaled(109), _scaled(147), _scaled(147)),
        fill=INK,
        outline=WHITE,
        width=_scaled(3),
    )
    draw.ellipse(
        (_scaled(119), _scaled(119), _scaled(137), _scaled(137)),
        fill=CYAN,
    )

    # The open corner is the distinguishing silhouette at small sizes.
    draw.line(
        [(_scaled(176), _scaled(202)), (_scaled(202), _scaled(202)), (_scaled(202), _scaled(176))],
        fill=CYAN,
        width=_scaled(6),
        joint="curve",
    )
    return image


def svg_mark() -> str:
    return """<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 256 256" role="img" aria-labelledby="title">
  <title id="title">OpenKeeb</title>
  <rect x="20" y="18" width="216" height="216" rx="48" fill="#0B0E14" stroke="#9B7BFF" stroke-width="4"/>
  <rect x="31" y="29" width="194" height="194" rx="39" fill="#151A24" stroke="#343C4D" stroke-width="2"/>
  <rect x="54" y="54" width="68" height="68" rx="15" fill="#6946DF" stroke="#9B7BFF" stroke-width="3"/>
  <rect x="134" y="54" width="68" height="68" rx="15" fill="#242B39" stroke="#52D6E8" stroke-width="3"/>
  <rect x="54" y="134" width="68" height="68" rx="15" fill="#242B39" stroke="#52D6E8" stroke-width="3"/>
  <rect x="134" y="134" width="68" height="68" rx="15" fill="#0F131B" stroke="#566071" stroke-width="3"/>
  <path d="M122 88h12M88 122v12" fill="none" stroke-linecap="round" stroke-width="5" stroke="#52D6E8"/>
  <path d="M122 122l23 23" fill="none" stroke-linecap="round" stroke-width="4" stroke="#F5F7FB"/>
  <circle cx="128" cy="128" r="19" fill="#0B0E14" stroke="#F5F7FB" stroke-width="3"/>
  <circle cx="128" cy="128" r="9" fill="#52D6E8"/>
  <path d="M176 202h26v-26" fill="none" stroke-linecap="round" stroke-linejoin="round" stroke-width="6" stroke="#52D6E8"/>
</svg>
"""


def generate() -> None:
    ASSETS.mkdir(parents=True, exist_ok=True)
    master = master_icon()
    (ASSETS / "openkeeb-mark.svg").write_text(svg_mark(), encoding="utf-8")
    master.save(ASSETS / "openkeeb.png", format="PNG", optimize=True)
    master.resize((512, 512), Image.Resampling.LANCZOS).save(
        ASSETS / "openkeeb-512.png", format="PNG", optimize=True
    )
    master.save(
        ASSETS / "openkeeb.ico",
        format="ICO",
        sizes=((16, 16), (24, 24), (32, 32), (48, 48), (64, 64), (128, 128), (256, 256)),
    )
    master.save(ASSETS / "openkeeb.icns", format="ICNS")
    master.resize((128, 128), Image.Resampling.LANCZOS).save(
        WEB_ICON, format="PNG", optimize=True
    )


if __name__ == "__main__":
    generate()
