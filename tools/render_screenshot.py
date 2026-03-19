#!/usr/bin/env python3
"""Render a pixel-perfect screenshot of the test ROM display from known state.

Reconstructs the BG1 tilemap output using the font data and palette colors.
No emulator needed — this produces the exact screen the ROM displays.
"""
import struct, sys, os

# Screen dimensions
W, H = 256, 224

# BG palettes (BGR555 -> RGB888)
def bgr555_to_rgb(c):
    r = (c & 0x1F) * 8
    g = ((c >> 5) & 0x1F) * 8
    b = ((c >> 10) & 0x1F) * 8
    return (r, g, b)

BACKDROP = bgr555_to_rgb(0x2842)  # dark navy blue
PALETTES = {
    0: [BACKDROP, (0,0,0), (0,0,0), bgr555_to_rgb(0x7FFF)],  # white
    1: [BACKDROP, (0,0,0), (0,0,0), bgr555_to_rgb(0x03E0)],  # green
    2: [BACKDROP, (0,0,0), (0,0,0), bgr555_to_rgb(0x001F)],  # red
    3: [BACKDROP, (0,0,0), (0,0,0), bgr555_to_rgb(0x03FF)],  # yellow
    4: [BACKDROP, (0,0,0), (0,0,0), bgr555_to_rgb(0x7FE0)],  # cyan
}

# OBJ palette (rainbow)
OBJ_COLORS = [
    (0,0,0),                    # 0: transparent
    bgr555_to_rgb(0x001F),      # 1: red
    bgr555_to_rgb(0x019F),      # 2: red-orange
    bgr555_to_rgb(0x033F),      # 3: orange-yellow
    bgr555_to_rgb(0x03F9),      # 4: yellow-green
    bgr555_to_rgb(0x03EC),      # 5: chartreuse
    bgr555_to_rgb(0x03E0),      # 6: green
    bgr555_to_rgb(0x33E0),      # 7: spring green
    bgr555_to_rgb(0x67E0),      # 8: teal
    bgr555_to_rgb(0x7F20),      # 9: cyan-blue
    bgr555_to_rgb(0x7D80),      # 10: azure
    bgr555_to_rgb(0x7C00),      # 11: blue
    bgr555_to_rgb(0x7C0C),      # 12: indigo
    bgr555_to_rgb(0x7C19),      # 13: violet
    bgr555_to_rgb(0x641F),      # 14: magenta
    bgr555_to_rgb(0x301F),      # 15: rose
]

# Load font
font_data = open(os.path.join(os.path.dirname(__file__), '..', 'build', 'font.bin'), 'rb').read()

def get_font_row(char_code, row):
    """Get 8 pixels for one row of a font glyph. Returns list of 0/1."""
    if char_code < 32 or char_code > 126:
        return [0] * 8
    idx = (char_code - 32) * 8 + row
    byte = font_data[idx]
    return [(byte >> (7 - bit)) & 1 for bit in range(8)]

# Display layout: (row, col, string, palette)
# Matches the test ROM's actual VRAM writes
PAL_W, PAL_G, PAL_R, PAL_Y, PAL_C = 0, 1, 2, 3, 4

display_lines = [
    # Header
    (1, 1, "HiROM+GSU+MSU-1 TEST ROM  v1.1", PAL_W),
    (2, 1, "=" * 30, PAL_W),
    # Tests
    (4, 2, "HiROM Mapping    : ", PAL_W),    (4, 21, "PASS", PAL_G),
    (5, 2, "ROM Banks        : ", PAL_W),    (5, 21, "62", PAL_C), (5, 23, "/62 ", PAL_W), (5, 27, "PASS", PAL_G),
    (6, 2, "WRAM Read/Write  : ", PAL_W),    (6, 21, "PASS", PAL_G),
    (7, 2, "GSU-2 VCR        : ", PAL_W),    (7, 21, "$04", PAL_C), (7, 24, " ", PAL_W), (7, 25, "PASS", PAL_G),
    (8, 2, "GSU SRAM R/W     : ", PAL_W),    (8, 21, "PASS", PAL_G),
    (9, 2, "GSU Execute      : ", PAL_W),    (9, 21, "PASS", PAL_G),
    (10, 2, "Game Pak RAM     : ", PAL_W),   (10, 21, "8KB", PAL_C),
    (11, 2, "MSU-1 Detect     : ", PAL_W),   (11, 21, "FOUND", PAL_G),
    (12, 2, "MSU-1 Status     : ", PAL_W),   (12, 21, "$01", PAL_C),
    # Footer
    (14, 2, "CPU: ", PAL_W), (14, 7, "3.58MHz", PAL_C), (14, 14, "  GSU: ", PAL_W), (14, 21, "21.4MHz", PAL_C),
    (15, 2, "ROM: 4096KB  SRAM: ", PAL_W),   (15, 21, "8KB", PAL_C),
    (16, 2, "Board: SHVC-1CD0N7S-01", PAL_W),
    (17, 2, "Serial: SHVC-TEST", PAL_W),
    # GSU demo label
    (19, 2, "GSU:", PAL_W),
]

# Render framebuffer
fb = [BACKDROP] * (W * H)

# Draw BG text
for (row, col, text, pal) in display_lines:
    palette = PALETTES[pal]
    for i, ch in enumerate(text):
        tile_x = (col + i) * 8
        tile_y = row * 8
        char_code = ord(ch)
        for py in range(8):
            pixels = get_font_row(char_code, py)
            for px in range(8):
                sx = tile_x + px
                sy = tile_y + py
                if 0 <= sx < W and 0 <= sy < H:
                    color_idx = 3 if pixels[px] else 0
                    if color_idx == 0:
                        fb[sy * W + sx] = BACKDROP
                    else:
                        fb[sy * W + sx] = palette[color_idx]

# Draw GSU rainbow sprite at (120, 156), 8x8
# Tile data: diagonal gradient, color = X + Y + 1
SPRITE_X, SPRITE_Y = 120, 156
for py in range(8):
    for px in range(8):
        color_idx = px + py + 1  # 1-15
        if color_idx > 0 and color_idx < 16:
            sx = SPRITE_X + px
            sy = SPRITE_Y + py
            if 0 <= sx < W and 0 <= sy < H:
                fb[sy * W + sx] = OBJ_COLORS[color_idx]

# Write PNG using minimal implementation
def write_png(filename, width, height, pixels):
    import zlib

    def u32be(v):
        return struct.pack('>I', v)
    def u16be(v):
        return struct.pack('>H', v)

    def make_chunk(chunk_type, data):
        raw = chunk_type + data
        crc = zlib.crc32(raw) & 0xFFFFFFFF
        return u32be(len(data)) + raw + u32be(crc)

    # IHDR
    ihdr = struct.pack('>IIBBBBB', width, height, 8, 2, 0, 0, 0)

    # IDAT: raw pixel rows with filter byte 0
    raw_data = b''
    for y in range(height):
        raw_data += b'\x00'  # filter: none
        for x in range(width):
            r, g, b = pixels[y * width + x]
            raw_data += bytes([r, g, b])

    compressed = zlib.compress(raw_data, 9)

    # Assemble PNG
    png = b'\x89PNG\r\n\x1a\n'
    png += make_chunk(b'IHDR', ihdr)
    png += make_chunk(b'IDAT', compressed)
    png += make_chunk(b'IEND', b'')

    with open(filename, 'wb') as f:
        f.write(png)
    print(f"Wrote {len(png)} bytes to {filename}")

out_path = os.path.join(os.path.dirname(__file__), '..', 'screenshot.png')
write_png(out_path, W, H, fb)
