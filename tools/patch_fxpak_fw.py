#!/usr/bin/env python3
"""Patch FXPak Pro firmware.im3 to enable SuperFX for HiROM ROMs.

The stock firmware only enables the GSU FPGA core for LoROM (map==0x20).
This patch adds HiROM (map==0x21) support by finding the smc_id() function's
carttype check for SuperFX and duplicating it for the HiROM code path.

Strategy: Find the LoROM GSU detection sequence in the ARM binary, then find
the HiROM case handler and patch in an equivalent branch to the GSU setup code.

Usage:
    python patch_fxpak_fw.py <input_firmware.im3> <output_firmware.im3>

    Copy output to SD card: /sd2snes/firmware.im3
"""
import sys
import struct

def find_bytes(data, pattern, start=0):
    """Find all occurrences of a byte pattern."""
    results = []
    idx = start
    while True:
        idx = data.find(pattern, idx)
        if idx == -1:
            break
        results.append(idx)
        idx += 1
    return results

def read_im3(path):
    """Read firmware.im3 — skip the 256-byte header."""
    with open(path, 'rb') as f:
        data = f.read()
    # The .im3 format has a header. For patching, work with the raw binary.
    return bytearray(data)

def main():
    if len(sys.argv) < 3:
        print(f"Usage: {sys.argv[0]} <input.im3> <output.im3>")
        sys.exit(1)

    fw = read_im3(sys.argv[1])
    print(f"Loaded {len(fw)} bytes from {sys.argv[1]}")

    # === Strategy ===
    # In smc_id(), the switch(header->map & 0xef) dispatches to case handlers.
    # The LoROM GSU check (case 0x20) compares carttype with 0x13-0x15 and 0x1a.
    # The HiROM handler (case 0x21) only checks for DSP1B (carttype 0x03/0x05).
    #
    # We need to find the HiROM case handler and add a branch to GSU setup
    # when carttype is 0x13-0x15 or 0x1a.
    #
    # ARM Thumb2 comparison patterns we're looking for:
    # - CMP Rn, #0x13  (carttype >= 0x13)
    # - CMP Rn, #0x15  (carttype <= 0x15)
    # - CMP Rn, #0x1a  (carttype == 0x1a)
    # - CMP Rn, #0x03  (DSP1B carttype in HiROM handler)

    # Search for the distinctive sequence: compare with 0x13 near compare with 0x15
    # In Thumb: CMP Rn, #imm8 = 0x2800 | (Rn << 8) | imm8
    # Example: CMP R0, #0x13 = 0x2813, CMP R0, #0x15 = 0x2815

    # Find all CMP Rn, #0x13 instructions (Thumb-16)
    found_gsu_check = False
    gsu_setup_addr = None

    for reg in range(8):  # R0-R7 for Thumb
        cmp_13 = struct.pack('<H', 0x2813 | (reg << 8))
        cmp_15 = struct.pack('<H', 0x2815 | (reg << 8))
        cmp_1a = struct.pack('<H', 0x281a | (reg << 8))

        hits_13 = find_bytes(fw, cmp_13)
        for h in hits_13:
            # Check if CMP #0x15 is nearby (within 20 bytes)
            nearby = fw[h:h+40]
            if cmp_15 in nearby and cmp_1a in nearby:
                print(f"  Found LoROM GSU carttype check at offset ${h:06X} (R{reg})")
                found_gsu_check = True

                # The GSU setup code (has_gsu=1, fpga_conf=FPGA_GSU, etc.)
                # should be right after the comparisons. Look for the
                # "FPGA_GSU" string pointer load or the has_gsu store.
                # We need the address of the GSU setup block.
                gsu_setup_addr = h
                break
        if found_gsu_check:
            break

    if not found_gsu_check:
        print("ERROR: Could not find LoROM GSU detection pattern in firmware.")
        print("This firmware may use a different code structure.")
        sys.exit(1)

    # Now find the HiROM case handler. Look for CMP Rn, #0x03 (DSP1B check)
    # near CMP Rn, #0x05 — this is the HiROM carttype detection.
    found_hirom = False
    hirom_dsp_addr = None

    for reg in range(8):
        cmp_03 = struct.pack('<H', 0x2803 | (reg << 8))
        cmp_05 = struct.pack('<H', 0x2805 | (reg << 8))

        hits_03 = find_bytes(fw, cmp_03)
        for h in hits_03:
            # Must be AFTER the LoROM handler and have CMP #0x05 nearby
            if h > gsu_setup_addr:
                nearby = fw[h:h+20]
                if cmp_05 in nearby:
                    print(f"  Found HiROM DSP1B carttype check at offset ${h:06X} (R{reg})")
                    found_hirom = True
                    hirom_dsp_addr = h
                    break
        if found_hirom:
            break

    if not found_hirom:
        print("ERROR: Could not find HiROM DSP1B detection pattern.")
        sys.exit(1)

    # === Analysis complete. Show what we found. ===
    print(f"\n  LoROM GSU check:  offset ${gsu_setup_addr:06X}")
    print(f"  HiROM DSP1B check: offset ${hirom_dsp_addr:06X}")
    print(f"  Distance: {hirom_dsp_addr - gsu_setup_addr} bytes")

    # Dump context around both locations
    print(f"\n  Context at LoROM GSU ({gsu_setup_addr:06X}):")
    for i in range(0, 48, 2):
        val = struct.unpack_from('<H', fw, gsu_setup_addr + i)[0]
        print(f"    +{i:02X}: {val:04X}", end="")
        if i % 16 == 14:
            print()
    print()

    print(f"\n  Context at HiROM DSP1B ({hirom_dsp_addr:06X}):")
    for i in range(0, 48, 2):
        val = struct.unpack_from('<H', fw, hirom_dsp_addr + i)[0]
        print(f"    +{i:02X}: {val:04X}", end="")
        if i % 16 == 14:
            print()
    print()

    print("\n=== MANUAL PATCH NEEDED ===")
    print("The binary structure varies by compiler version and optimization.")
    print("Use the offsets above to craft a specific patch for this firmware.")
    print("The goal: in the HiROM case (0x21) handler, after the DSP1B check,")
    print("add a branch to the GSU setup code when carttype is 0x13-0x15 or 0x1a.")

    # Write output (unmodified for now — manual analysis needed)
    with open(sys.argv[2], 'wb') as f:
        f.write(fw)
    print(f"\nWrote {len(fw)} bytes to {sys.argv[2]} (analysis only, no patch applied yet)")


if __name__ == '__main__':
    main()
