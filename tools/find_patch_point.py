import struct, sys

data = open('E:/gh/sd2snes/fw_extract/sd2snes/firmware.im3', 'rb').read()

# The .im3 has a 256-byte header (0x100)
# Firmware code starts after that
HDR = 0x100

# Find the /sd2snes/fpga_gsu string
gsu_str = data.find(b'/sd2snes/fpga_gsu')
print(f"GSU path string at: {gsu_str:#06x}")

# Find all references to this string address in the code
# The string's runtime address = flash base + offset
# CONFIG_FW_START = 0xc000, but .im3 starts at 0xc000+0x100 = 0xc100
# So runtime addr of string = 0xc100 + (gsu_str - HDR)
# Actually the header is metadata, code starts at HDR
# Runtime addr = 0xc000 + gsu_str (the header IS part of the flash image)
# Let's just search for the raw offset value as a 32-bit LE word

# Search for Thumb CMP Rn, #imm8 patterns
print("\nSearching for CMP Rn, #0x13 near CMP Rn, #0x15...")
for off in range(HDR, len(data)-2, 2):
    val = struct.unpack_from('<H', data, off)[0]
    # CMP Rn, #0x13: opcode = 0x2N13 where N = 0x8+reg
    if (val & 0xF8FF) == 0x2813:
        reg = (val >> 8) & 0x07
        # Check for CMP same_reg, #0x15 within 40 bytes
        for off2 in range(off+2, min(off+60, len(data)-2), 2):
            val2 = struct.unpack_from('<H', data, off2)[0]
            if val2 == (0x2815 | (reg << 8)):
                print(f"  CMP R{reg},#0x13 at {off:#06x}, CMP R{reg},#0x15 at {off2:#06x}")
                # Dump surrounding code
                start = max(HDR, off - 16)
                for i in range(start, min(off + 64, len(data)-1), 2):
                    v = struct.unpack_from('<H', data, i)[0]
                    marker = " <-- CMP 0x13" if i == off else (" <-- CMP 0x15" if i == off2 else "")
                    print(f"    {i:#06x}: {v:04x}{marker}")
                print()

# Also search for CMP Rn, #0x03 near CMP Rn, #0x05 (HiROM DSP1B check)
print("Searching for CMP Rn, #0x03 near CMP Rn, #0x05...")
for off in range(HDR, len(data)-2, 2):
    val = struct.unpack_from('<H', data, off)[0]
    if (val & 0xF8FF) == 0x2803:
        reg = (val >> 8) & 0x07
        for off2 in range(off+2, min(off+30, len(data)-2), 2):
            val2 = struct.unpack_from('<H', data, off2)[0]
            if val2 == (0x2805 | (reg << 8)):
                print(f"  CMP R{reg},#0x03 at {off:#06x}, CMP R{reg},#0x05 at {off2:#06x}")
                start = max(HDR, off - 16)
                for i in range(start, min(off + 48, len(data)-1), 2):
                    v = struct.unpack_from('<H', data, i)[0]
                    marker = " <-- CMP 0x03" if i == off else (" <-- CMP 0x05" if i == off2 else "")
                    print(f"    {i:#06x}: {v:04x}{marker}")
                print()
