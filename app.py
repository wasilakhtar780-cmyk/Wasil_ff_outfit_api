import io
import os
from concurrent.futures import ThreadPoolExecutor
from functools import lru_cache
from threading import Lock
from typing import Any

import requests
from flask import Flask, Response, jsonify, request
from PIL import Image, ImageChops, ImageDraw, ImageFilter, ImageFont

app = Flask(__name__)

INFO_API = "https://out-bar-info.vercel.app/info?uid={uid}"
ICON_API = "https://iconapi.wasmer.app/{}"

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
TEMPLATE_PATH = os.path.join(BASE_DIR, "banner_template.jpg")
FONT_BOLD = os.path.join(BASE_DIR, "fonts", "Poppins-Bold.ttf")
FONT_MEDIUM = os.path.join(BASE_DIR, "fonts", "Poppins-Medium.ttf")

fallback_ids = [
    "907192607",
    "212000000",
    "211000000",
    "214000000",
    "208000000",
    "203000000",
    "204000000",
    "205000000",
]

# ---------------------------------------------------------------------------
# Layout (সব মান এখন সরাসরি banner pixel-এ — আগের মতো আর দ্বিতীয়বার scale হয় না)
# ---------------------------------------------------------------------------
BANNER_W, BANNER_H = 1536, 1430
HEX_SCALE = 1.30          # সোনালি বক্স আগের চেয়ে ~30% বড়
ICON_FILL = 0.66          # বক্সের ভেতরে আইকন কতটা জায়গা নেবে

# প্রতিটি বক্সের center (x, y)
SLOT_CENTERS = [
    (400, 215),    # 1. Pet
    (1136, 215),   # 2. Weapon
    (240, 550),    # 3. Item
    (1296, 550),   # 4. Item
    (240, 885),    # 5. Item
    (1296, 885),   # 6. Item
    (400, 1220),   # 7. Item
    (1136, 1220),  # 8. Item
]
# বাম পাশের বক্সগুলো original orientation-এ, ডান পাশেরগুলো mirror করা (symmetry)
SLOT_MIRROR = [False, True, False, True, False, True, False, True]

GOLD = (255, 205, 80)
GOLD_SOFT = (255, 226, 150)
WHITE = (255, 255, 255)

# ---------------------------------------------------------------------------
# Branding
# ---------------------------------------------------------------------------
BRAND_NAME = "WASIL"
BRAND_CHANNEL = "t.me/jihad_x_leaker"

_LOCK = Lock()
_STATIC = {}


# 5x7 bitmap font: no system font or FreeType required.
FONT = {
    "A": ("01110", "10001", "10001", "11111", "10001", "10001", "10001"),
    "B": ("11110", "10001", "10001", "11110", "10001", "10001", "11110"),
    "C": ("01111", "10000", "10000", "10000", "10000", "10000", "01111"),
    "D": ("11110", "10001", "10001", "10001", "10001", "10001", "11110"),
    "E": ("11111", "10000", "10000", "11110", "10000", "10000", "11111"),
    "F": ("11111", "10000", "10000", "11110", "10000", "10000", "10000"),
    "G": ("01111", "10000", "10000", "10111", "10001", "10001", "01111"),
    "H": ("10001", "10001", "10001", "11111", "10001", "10001", "10001"),
    "I": ("11111", "00100", "00100", "00100", "00100", "00100", "11111"),
    "J": ("00111", "00010", "00010", "00010", "10010", "10010", "01100"),
    "K": ("10001", "10010", "10100", "11000", "10100", "10010", "10001"),
    "L": ("10000", "10000", "10000", "10000", "10000", "10000", "11111"),
    "M": ("10001", "11011", "10101", "10101", "10001", "10001", "10001"),
    "N": ("10001", "11001", "10101", "10011", "10001", "10001", "10001"),
    "O": ("01110", "10001", "10001", "10001", "10001", "10001", "01110"),
    "P": ("11110", "10001", "10001", "11110", "10000", "10000", "10000"),
    "Q": ("01110", "10001", "10001", "10001", "10101", "10010", "01101"),
    "R": ("11110", "10001", "10001", "11110", "10100", "10010", "10001"),
    "S": ("01111", "10000", "10000", "01110", "00001", "00001", "11110"),
    "T": ("11111", "00100", "00100", "00100", "00100", "00100", "00100"),
    "U": ("10001", "10001", "10001", "10001", "10001", "10001", "01110"),
    "V": ("10001", "10001", "10001", "10001", "10001", "01010", "00100"),
    "W": ("10001", "10001", "10001", "10101", "10101", "10101", "01010"),
    "X": ("10001", "10001", "01010", "00100", "01010", "10001", "10001"),
    "Y": ("10001", "10001", "01010", "00100", "00100", "00100", "00100"),
    "Z": ("11111", "00001", "00010", "00100", "01000", "10000", "11111"),
    "0": ("01110", "10001", "10011", "10101", "11001", "10001", "01110"),
    "1": ("00100", "01100", "00100", "00100", "00100", "00100", "01110"),
    "2": ("01110", "10001", "00001", "00010", "00100", "01000", "11111"),
    "3": ("11110", "00001", "00001", "01110", "00001", "00001", "11110"),
    "4": ("00010", "00110", "01010", "10010", "11111", "00010", "00010"),
    "5": ("11111", "10000", "10000", "11110", "00001", "00001", "11110"),
    "6": ("01110", "10000", "10000", "11110", "10001", "10001", "01110"),
    "7": ("11111", "00001", "00010", "00100", "01000", "01000", "01000"),
    "8": ("01110", "10001", "10001", "01110", "10001", "10001", "01110"),
    "9": ("01110", "10001", "10001", "01111", "00001", "00001", "01110"),
    "-": ("00000", "00000", "00000", "11111", "00000", "00000", "00000"),
    " ": ("00000", "00000", "00000", "00000", "00000", "00000", "00000"),
}


def draw_bitmap_text(draw, text, center, max_width, max_height, fill):
    """Fallback: draw centered text without any font/FreeType."""
    text = str(text).upper()
    patterns = [FONT.get(char, FONT["-"]) for char in text]

    if not patterns:
        return

    units_wide = len(patterns) * 6 - 1
    scale = max(1, min(max_width // max(1, units_wide), max_height // 7))

    text_width = units_wide * scale
    text_height = 7 * scale
    start_x = int(center[0] - text_width / 2)
    start_y = int(center[1] - text_height / 2)

    for char_index, pattern in enumerate(patterns):
        for row, line in enumerate(pattern):
            for col, pixel in enumerate(line):
                if pixel != "1":
                    continue
                x = start_x + (char_index * 6 + col) * scale
                y = start_y + row * scale
                draw.rectangle((x, y, x + scale - 1, y + scale - 1), fill=fill)



# ---------------------------------------------------------------------------
# Text helpers (TTF থাকলে সুন্দর font, না থাকলে bitmap font fallback)
# ---------------------------------------------------------------------------
@lru_cache(maxsize=64)
def load_font(path: str, size: int):
    try:
        return ImageFont.truetype(path, size)
    except Exception:  # OSError, ValueError, ImportError (FreeType নেই, যেমন Termux)
        return None


def draw_text(draw, text, center, size, fill, bold=True, max_width=None,
              shadow=True):
    """Centered text. Auto-shrinks to max_width."""
    text = str(text)
    path = FONT_BOLD if bold else FONT_MEDIUM

    if load_font(path, size) is None:
        # bitmap fallback
        draw_bitmap_text(
            draw, text, center,
            max_width=max_width or size * 12,
            max_height=max(7, int(size * 0.8)),
            fill=fill + (255,) if len(fill) == 3 else fill,
        )
        return

    while True:
        font = load_font(path, size)
        left, top, right, bottom = draw.textbbox((0, 0), text, font=font)
        w, h = right - left, bottom - top
        if max_width is None or w <= max_width or size <= 10:
            break
        size -= 2

    x = center[0] - w / 2 - left
    y = center[1] - h / 2 - top

    if shadow:
        draw.text((x + 2, y + 3), text, font=font, fill=(0, 0, 0, 200))
    draw.text((x, y), text, font=font, fill=fill)


def short_name(name: str, limit: int = 16) -> str:
    name = " ".join(str(name or "").replace("_", " ").split())
    if len(name) > limit:
        name = name[: limit - 1].rstrip() + "…"
    return name


# ---------------------------------------------------------------------------
# Static artwork (একবারই তৈরি হয়, তারপর cache)
# ---------------------------------------------------------------------------
def build_hex_sprite() -> Image.Image:
    """Template থেকে একটি সোনালি hexagon frame কেটে নিয়ে বড় করে (RGB, কালো = স্বচ্ছ)."""
    if not os.path.isfile(TEMPLATE_PATH):
        raise RuntimeError(f"Banner template missing: {TEMPLATE_PATH}")

    with Image.open(TEMPLATE_PATH) as src:
        src = src.convert("RGB")
        # top-left hexagon এর আশেপাশের অংশ
        region = src.crop((285, 50, 515, 300))

    bbox = region.convert("L").point(lambda v: 255 if v > 40 else 0).getbbox()
    sprite = region.crop(bbox)
    new_size = (
        int(sprite.width * HEX_SCALE),
        int(sprite.height * HEX_SCALE),
    )
    return sprite.resize(new_size, Image.Resampling.LANCZOS)


def hex_polygon(cx, cy, w, h, inset=0):
    """Pointy-top hexagon polygon."""
    hw, hh = w / 2 - inset, h / 2 - inset
    return [
        (cx, cy - hh),
        (cx + hw, cy - hh / 2),
        (cx + hw, cy + hh / 2),
        (cx, cy + hh),
        (cx - hw, cy + hh / 2),
        (cx - hw, cy - hh / 2),
    ]


def soft_ellipse_mask(size, strength=1.0, inset=0.0, blur=0.25):
    """নরম কিনারার ellipse mask (L) — blocky gradient এড়াতে blur দিয়ে তৈরি।"""
    w, h = size
    mask = Image.new("L", size, 0)
    ImageDraw.Draw(mask).ellipse(
        (w * inset, h * inset, w * (1 - inset), h * (1 - inset)),
        fill=int(255 * strength),
    )
    return mask.filter(ImageFilter.GaussianBlur(min(w, h) * blur))


def glow_blob(size, color, strength):
    layer = Image.new("RGBA", size, color + (0,))
    layer.putalpha(soft_ellipse_mask(size, strength, inset=0.18, blur=0.16))
    return layer


def get_static():
    """returns dict(base=RGBA background+hex fill, frames=RGB hex frames)"""
    if _STATIC:
        return _STATIC

    with _LOCK:
        if _STATIC:
            return _STATIC

        sprite = build_hex_sprite()
        sw, sh = sprite.size

        # ---- background -------------------------------------------------
        bg = Image.new("RGBA", (BANNER_W, BANNER_H), (8, 7, 6, 255))

        # মাঝখানে সোনালি আভা
        center_glow = glow_blob((1200, 1100), (150, 100, 20), 0.55)
        bg.alpha_composite(
            center_glow,
            ((BANNER_W - 1200) // 2, (BANNER_H - 1100) // 2),
        )

        # কোণায় গাঢ় vignette
        vig_mask = soft_ellipse_mask(
            (BANNER_W, BANNER_H), 1.0, inset=-0.05, blur=0.12
        ).point(lambda v: 255 - v)
        dark = Image.new("RGBA", bg.size, (0, 0, 0, 0))
        dark.putalpha(vig_mask.point(lambda v: int(v * 0.85)))
        bg.alpha_composite(dark)

        # হালকা hex-জাল প্যাটার্ন
        pattern = Image.new("RGBA", bg.size, (0, 0, 0, 0))
        pd = ImageDraw.Draw(pattern)
        step_x, step_y, r = 96, 83, 48
        for row in range(-1, BANNER_H // step_y + 2):
            for col in range(-1, BANNER_W // step_x + 2):
                cx = col * step_x + (step_x // 2 if row % 2 else 0)
                cy = row * step_y
                pd.polygon(
                    hex_polygon(cx, cy, r * 1.73, r * 2),
                    outline=(255, 190, 70, 14),
                )
        bg.alpha_composite(pattern)

        draw = ImageDraw.Draw(bg)

        # বাইরের border
        draw.rounded_rectangle(
            (14, 14, BANNER_W - 15, BANNER_H - 15),
            radius=26, outline=(255, 190, 70, 150), width=3,
        )
        draw.rounded_rectangle(
            (26, 26, BANNER_W - 27, BANNER_H - 27),
            radius=20, outline=(255, 190, 70, 55), width=1,
        )

        # ---- hex fill + glow + frames -----------------------------------
        frames = Image.new("RGB", bg.size, (0, 0, 0))
        mirrored = sprite.transpose(Image.Transpose.FLIP_LEFT_RIGHT)

        for (cx, cy), mirror in zip(SLOT_CENTERS, SLOT_MIRROR):
            # বক্সের পেছনের নরম glow
            gw = int(sw * 1.7)
            gh = int(sh * 1.7)
            bg.alpha_composite(
                glow_blob((gw, gh), (255, 170, 40), 0.22),
                (cx - gw // 2, cy - gh // 2),
            )

            # ভেতরের গাঢ় fill + হালকা সোনালি gradient
            inner = Image.new("RGBA", (sw, sh), (0, 0, 0, 0))
            idraw = ImageDraw.Draw(inner)
            idraw.polygon(
                hex_polygon(sw / 2, sh / 2, sw, sh, inset=sw * 0.05),
                fill=(14, 11, 8, 245),
            )
            inner_glow = glow_blob((sw, sh), (255, 180, 60), 0.3)
            hex_mask = Image.new("L", (sw, sh), 0)
            ImageDraw.Draw(hex_mask).polygon(
                hex_polygon(sw / 2, sh / 2, sw, sh, inset=sw * 0.05),
                fill=255,
            )
            inner_glow.putalpha(
                ImageChops.multiply(inner_glow.getchannel("A"), hex_mask)
            )
            inner.alpha_composite(inner_glow)
            bg.alpha_composite(inner, (cx - sw // 2, cy - sh // 2))

            sp = mirrored if mirror else sprite
            frames.paste(
                ImageChops.add(
                    frames.crop((cx - sw // 2, cy - sh // 2,
                                 cx - sw // 2 + sw, cy - sh // 2 + sh)),
                    sp,
                ),
                (cx - sw // 2, cy - sh // 2),
            )

        # frame এর হালকা glow
        frame_glow = frames.filter(ImageFilter.GaussianBlur(14))
        frames = ImageChops.add(frames, frame_glow.point(lambda v: v // 5))

        _STATIC["base"] = bg
        _STATIC["frames"] = frames
        _STATIC["hex_size"] = (sw, sh)

    return _STATIC



def find_named_id(data: Any, names: set[str]) -> str | None:
    if isinstance(data, dict):
        for key, value in data.items():
            normalized = (
                str(key).lower().replace("_", "").replace("-", "")
            )

            if normalized in names and value is not None:
                if isinstance(value, (str, int)):
                    result = str(value).strip()
                    if result and result != "0":
                        return result

                if isinstance(value, dict):
                    found = find_named_id(
                        value, {"id", "petid", "weaponid"}
                    )
                    if found:
                        return found

        for value in data.values():
            found = find_named_id(value, names)
            if found:
                return found

    elif isinstance(data, list):
        for value in data:
            found = find_named_id(value, names)
            if found:
                return found

    return None


def get_pet_id(data: Any) -> str:
    return (
        find_named_id(
            data,
            {"petid", "currentpetid", "equippedpetid"},
        )
        or "404"
    )


def find_equipped_items(data: Any) -> list[dict]:
    if isinstance(data, dict):
        outfit = data.get("Outfit")

        if isinstance(outfit, dict):
            equipped = outfit.get("Equipped")

            if isinstance(equipped, list):
                return [
                    item for item in equipped
                    if isinstance(item, dict)
                    and item.get("id") is not None
                ]

        for value in data.values():
            found = find_equipped_items(value)
            if found:
                return found

    elif isinstance(data, list):
        for value in data:
            found = find_equipped_items(value)
            if found:
                return found

    return []


def get_weapon_id(data: Any, items: list[dict]) -> str:
    weapon_id = find_named_id(
        data,
        {"weaponid", "equippedweaponid", "currentweaponid"},
    )

    if weapon_id:
        return weapon_id

    for item in items:
        name = str(item.get("name") or "").lower()
        item_id = str(item.get("id") or "")

        if (
            "weapon" in name
            or "gun" in name
            or item_id.startswith("907")
        ):
            if item_id:
                return item_id

    return "404"



@lru_cache(maxsize=512)
def get_item_image_bytes(item_id: str) -> bytes | None:
    try:
        response = requests.get(
            ICON_API.format(item_id),
            timeout=(10, 25),
            headers={"User-Agent": "PlayerOutfitBannerAPI/1.2"},
        )
        response.raise_for_status()

        image_bytes = response.content

        with Image.open(io.BytesIO(image_bytes)) as check:
            check.verify()

        return image_bytes

    except (requests.RequestException, OSError, ValueError):
        return None


def get_item_image(item_id: str):
    raw = get_item_image_bytes(item_id)

    if raw is None:
        return None

    try:
        with Image.open(io.BytesIO(raw)) as image:
            return image.convert("RGBA")

    except (OSError, ValueError):
        return None


def fit_icon(image: Image.Image, size: tuple[int, int]):
    image = image.copy()
    image.thumbnail(size, Image.Resampling.LANCZOS)

    canvas = Image.new("RGBA", size, (0, 0, 0, 0))
    canvas.alpha_composite(
        image,
        ((size[0] - image.width) // 2, (size[1] - image.height) // 2),
    )
    return canvas


def with_shadow(icon: Image.Image) -> Image.Image:
    """আইকনের নিচে নরম ছায়া, যাতে বক্সে 'ভাসছে' মনে হয়।"""
    pad = 24
    out = Image.new("RGBA", (icon.width + pad * 2, icon.height + pad * 2),
                    (0, 0, 0, 0))
    shadow = Image.new("RGBA", out.size, (0, 0, 0, 0))
    shadow.paste((0, 0, 0, 190), (pad, pad + 8), icon.getchannel("A"))
    shadow = shadow.filter(ImageFilter.GaussianBlur(9))
    out.alpha_composite(shadow)
    out.alpha_composite(icon, (pad, pad))
    return out


def prepare_icon(item: dict):
    item_id = str(item.get("id", ""))

    if not item_id or item_id == "404":
        return item_id, None

    icon = get_item_image(item_id)

    if icon is None:
        return item_id, None

    sw, sh = get_static()["hex_size"]
    side = int(min(sw, sh) * ICON_FILL)
    return item_id, with_shadow(fit_icon(icon, (side, side)))


def paste_center(banner, icon, cx, cy):
    banner.alpha_composite(
        icon, (cx - icon.width // 2, cy - icon.height // 2)
    )


def draw_caption(draw, cx, cy_bottom, text, sub=None):
    """বক্সের নিচে ছোট নাম-ট্যাগ (FreeType না থাকলেও কাজ করে)।"""
    text = short_name(text).upper().replace("\u2026", "")
    font = load_font(FONT_BOLD, 22)
    pill_h = 38
    y0 = cy_bottom + 2

    if font is None:
        # bitmap fallback: প্রতি অক্ষর 6 unit চওড়া, scale 3
        scale = 3
        w = min((len(text) * 6 - 1) * scale, 230)
    else:
        left, _, right, _ = draw.textbbox((0, 0), text, font=font)
        w = min(right - left, 230)

    pill_w = w + 40
    draw.rounded_rectangle(
        (cx - pill_w // 2, y0, cx + pill_w // 2, y0 + pill_h),
        radius=pill_h // 2,
        fill=(20, 14, 6, 235),
        outline=(255, 190, 70, 200),
        width=2,
    )

    if font is None:
        draw_bitmap_text(draw, text, (cx, y0 + pill_h // 2), 230, 21,
                         GOLD_SOFT + (255,))
    else:
        draw_text(draw, text, (cx, y0 + pill_h // 2 + 1), 22, GOLD_SOFT,
                  max_width=230, shadow=False)


def make_banner(
    items: list[dict],
    pet_id: str,
    weapon_id: str,
    uid: str = "",
) -> tuple[bytes, bool]:
    static = get_static()
    banner = static["base"].copy()
    sw, sh = static["hex_size"]

    # slot 1 = Pet, slot 2 = Weapon, slot 3..8 = equipped items
    selected = items[:6]
    using_fallback = not bool(selected)

    if not selected:
        selected = [
            {"id": item_id, "name": "Item"} for item_id in fallback_ids[:6]
        ]

    jobs = (
        [{"id": pet_id, "name": "Pet"}, {"id": weapon_id, "name": "Weapon"}]
        + selected
    )

    with ThreadPoolExecutor(max_workers=8) as pool:
        prepared = list(pool.map(prepare_icon, jobs))

    # সব item icon fail করলে fallback ID দিয়ে আবার চেষ্টা
    if not any(icon is not None for _, icon in prepared[2:]):
        using_fallback = True
        selected = [
            {"id": item_id, "name": "Item"} for item_id in fallback_ids[:6]
        ]
        jobs = jobs[:2] + selected
        with ThreadPoolExecutor(max_workers=6) as pool:
            prepared = prepared[:2] + list(pool.map(prepare_icon, selected))

    # আইকন বসাও
    for (cx, cy), (_, icon) in zip(SLOT_CENTERS, prepared):
        if icon is not None:
            paste_center(banner, icon, cx, cy)

    # সোনালি frame আইকনের উপরে (কালো অংশ স্বচ্ছ ধরে add)
    rgb = ImageChops.add(banner.convert("RGB"), static["frames"])
    banner = rgb.convert("RGBA")
    draw = ImageDraw.Draw(banner)

    # ---- ক্যাপশন + আইকন না থাকলে ID লেখা ----------------------------------
    for index, ((cx, cy), (item_id, icon), job) in enumerate(
        zip(SLOT_CENTERS, prepared, jobs)
    ):
        if icon is None:
            draw_text(draw, item_id or "404", (cx, cy), 34, WHITE,
                      max_width=int(sw * 0.62))

        if index == 0:
            caption = f"PET  {item_id or '404'}"
        elif index == 1:
            caption = f"WEAPON  {item_id or '404'}"
        else:
            caption = job.get("name") or "Item"
            # name শুধু সংখ্যা/ID হলে (fallback) "Item" দেখাও
            if str(caption).strip().isdigit():
                caption = "Item"

        draw_caption(draw, cx, cy + sh // 2 - 8, caption)

    # ---- মাঝখানের টাইটেল ------------------------------------------------
    mid = BANNER_W // 2
    draw_text(draw, "PLAYER", (mid, 580), 92, WHITE, max_width=560)
    draw_text(draw, "OUTFIT", (mid, 690), 92, GOLD, max_width=560)
    draw.line((mid - 170, 770, mid + 170, 770), fill=(255, 190, 70, 200),
              width=3)
    if uid:
        draw_text(draw, f"UID  {uid}", (mid, 830), 40, GOLD_SOFT,
                  bold=False, max_width=560)

    # ---- branding footer -------------------------------------------------
    draw_text(draw, f"POWERED BY {BRAND_NAME}", (mid, BANNER_H - 56), 30,
              GOLD, bold=True, max_width=700)
    draw_text(draw, BRAND_CHANNEL, (mid, BANNER_H - 24), 22, GOLD_SOFT,
              bold=False, max_width=700, shadow=False)

    output = io.BytesIO()
    banner.convert("RGB").save(output, format="PNG", optimize=False)

    return output.getvalue(), using_fallback


@app.get("/")
def home():
    return jsonify({
        "status": "online",
        "powered_by": BRAND_NAME,
        "official_channel": BRAND_CHANNEL,
        "endpoint": "/player-outfit?uid=PLAYER_UID",
        "template": os.path.basename(TEMPLATE_PATH),
        "id_boxes": {
            "first": "Pet ID",
            "second": "Weapon ID",
            "missing_id": "404",
        },
        "icon_slots": 8,
        "font_mode": "Poppins TTF (bitmap fallback)",
    })


@app.get("/player-outfit")
def player_outfit():
    uid = (request.args.get("uid") or "").strip()

    if not uid:
        return jsonify({
            "error": "Missing required query parameter: uid"
        }), 400

    if not uid.isdigit() or len(uid) > 24:
        return jsonify({
            "error": "UID must contain 1-24 digits"
        }), 400

    try:
        response = requests.get(
            INFO_API.format(uid=uid),
            timeout=(10, 30),
            headers={"User-Agent": "PlayerOutfitBannerAPI/1.2"},
        )
        response.raise_for_status()
        player_data = response.json()

    except requests.RequestException:
        app.logger.exception("Player info request failed")
        return jsonify({
            "error": "Player info API request failed"
        }), 502

    except ValueError:
        return jsonify({
            "error": "Player info API returned invalid JSON"
        }), 502

    items = find_equipped_items(player_data)
    pet_id = get_pet_id(player_data)
    weapon_id = get_weapon_id(player_data, items)

    try:
        image_bytes, using_fallback = make_banner(
            items,
            pet_id,
            weapon_id,
            uid,
        )

    except (OSError, RuntimeError, ValueError):
        app.logger.exception(
            "Could not create banner for UID %s", uid
        )
        return jsonify({
            "error": "Could not create outfit banner"
        }), 500

    return Response(
        image_bytes,
        mimetype="image/png",
        headers={
            "Cache-Control": "public, max-age=60",
            "Content-Disposition": (
                f'inline; filename="player-outfit-{uid}.png"'
            ),
            "X-Equipped-Items": str(min(len(items), 6)),
            "X-Pet-ID": pet_id,
            "X-Weapon-ID": weapon_id,
            "X-Fallback-Used": (
                "true" if using_fallback else "false"
            ),
            "X-Powered-By": f"{BRAND_NAME} ({BRAND_CHANNEL})",
        },
    )


if __name__ == "__main__":
    app.run(
        host="0.0.0.0",
        port=int(os.environ.get("PORT", "8000")),
        debug=False,
        threaded=True,
    )
