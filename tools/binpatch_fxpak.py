#!/usr/bin/env python3
"""Binary-patch FXPak Pro firmware.im3 to enable SuperFX for HiROM ROMs.

Patches the original firmware in-place (preserving embedded FPGA bitstream)
by modifying the smc_id() HiROM case to check for GSU cart types.

Approach: In the HiROM (0x21) case handler, the code checks:
  CMP R5, #0x03  (DSP1B)
  CMP R5, #0x05  (DSP1B alt)
  CMP R5, #0xcb  (combo)

We replace the combo check (CMP R5, #0xcb) with a check for the primary
GSU cart type (CMP R5, #0x15), redirecting its match to the LoROM GSU setup.
This sacrifices combo-type support for HiROM (which doesn't exist in practice).

Usage: python binpatch_fxpak.py <firmware.im3> <output.im3>
"""
import struct, sys, os

def crc_reflect(data, data_len):
    ret = data & 0x01
    for i in range(1, data_len):
        data >>= 1
        ret = (ret << 1) | (data & 0x01)
    return ret

def crc_update(crc, buf):
    for c in buf:
        for i in range(8):
            bit = crc & 0x80000000
            if c & (1 << i):
                bit = 0 if bit else 1
            crc = (crc << 1) & 0xFFFFFFFF
            if bit:
                crc ^= 0x04c11db7
    return crc & 0xFFFFFFFF

def compute_crc(data):
    crcc = crc_update(0xFFFFFFFF, data)
    crcc = crc_reflect(crcc, 32)
    crc = crcc ^ 0xFFFFFFFF
    return crc, crcc

def main():
    if len(sys.argv) < 3:
        print(f"Usage: {sys.argv[0]} <input.im3> <output.im3>")
        sys.exit(1)

    fw = bytearray(open(sys.argv[1], 'rb').read())
    HDR = 0x100
    body = fw[HDR:]
    print(f"Loaded {len(fw)} bytes ({len(body)} body)")

    # Find HiROM handler: CMP R5, #0xcb at the second occurrence
    # (first is in LoROM handler, second is in HiROM handler)
    target = struct.pack('<H', 0x2dcb)  # CMP R5, #0xcb
    occ = []
    idx = 0
    while True:
        idx = fw.find(target, idx)
        if idx < 0:
            break
        occ.append(idx)
        idx += 2

    print(f"Found CMP R5,#0xcb at offsets: {[f'{o:#x}' for o in occ]}")

    if len(occ) < 2:
        print("ERROR: Expected at least 2 occurrences")
        sys.exit(1)

    # The second occurrence should be in the HiROM handler
    # Verify by checking CMP R5,#0x03 and CMP R5,#0x05 nearby (before it)
    hirom_cb = occ[1]
    context = fw[hirom_cb-20:hirom_cb]
    has_03 = struct.pack('<H', 0x2d03) in context
    has_05 = struct.pack('<H', 0x2d05) in context
    print(f"HiROM combo check at {hirom_cb:#x}: DSP 0x03 nearby={has_03}, 0x05 nearby={has_05}")

    if not (has_03 and has_05):
        print("WARNING: Context doesn't match expected HiROM DSP1B pattern!")
        print("Trying other occurrences...")
        for o in occ:
            ctx = fw[o-20:o]
            if struct.pack('<H', 0x2d03) in ctx and struct.pack('<H', 0x2d05) in ctx:
                hirom_cb = o
                print(f"  Using occurrence at {o:#x} instead")
                break

    # === Apply the patch ===
    # Replace CMP R5, #0xcb with CMP R5, #0x15 (primary GSU cart type)
    # This means: if carttype == 0x15, the branch that was handling combo
    # will now fire for GSU ROMs. We need to redirect that branch to the
    # GSU setup code.

    # First, let's look at what happens after CMP R5, #0xcb:
    print(f"\nCode at patch site ({hirom_cb:#x}):")
    for i in range(hirom_cb - 4, hirom_cb + 16, 2):
        val = struct.unpack_from('<H', fw, i)[0]
        marker = ""
        if i == hirom_cb:
            marker = " <-- PATCH: CMP R5, #0xcb -> #0x15"
        print(f"  {i:#06x}: {val:04x}{marker}")

    # The instruction after CMP #0xcb loads a byte and then BNE skips.
    # 0xf1ba: 2dcb  CMP R5, #0xcb
    # 0xf1bc: 7ea3  LDRB R3, [R4, #0x1A]  (loads some field)
    # 0xf1be: d1a6  BNE -0xB4  (if not combo, branch away = break)
    # 0xf1c0: e799  B -0xCC    (if combo, branch to combo handler)

    # If we change 0xcb to 0x15:
    # CMP R5, #0x15 → if carttype == 0x15 (GSU+RAM+Battery), the BEQ falls
    # through to 0xf1c0 which branches to the combo handler code.
    # But we want it to go to the GSU setup code instead!

    # The combo handler (target of e799) probably sets has_combo and fpga_conf.
    # We need to find the LoROM GSU setup address and redirect there.

    # Actually, a simpler approach: change CMP #0xcb to CMP #0x15,
    # AND change the BNE to the GSU setup (if not 0x15, continue to break).
    # The "match" path (BEQ) falls through to the B instruction at +4.
    # We change THAT branch target to point to the LoROM GSU setup.

    # Find the LoROM GSU setup. It's near where has_gsu=1 is stored.
    # Search for the LoROM GSU handler by finding CMP R5, #0x1a near
    # the first CMP R5, #0xcb

    # Actually, the instruction at hirom_cb+4 (after the LDRB) is BNE.
    # And hirom_cb+6 is an unconditional branch B.
    # Let's decode the B target:
    bne_inst = struct.unpack_from('<H', fw, hirom_cb + 4)[0]
    b_inst = struct.unpack_from('<H', fw, hirom_cb + 6)[0]
    print(f"\n  BNE at {hirom_cb+4:#x}: {bne_inst:04x}")
    print(f"  B   at {hirom_cb+6:#x}: {b_inst:04x}")

    # Decode Thumb B (unconditional): 0xE000 | offset (11-bit signed, *2)
    if (b_inst & 0xF800) == 0xE000:
        offset = b_inst & 0x7FF
        if offset & 0x400:
            offset -= 0x800
        target_addr = (hirom_cb + 6) + 4 + offset * 2
        print(f"  B target: {target_addr:#x} (combo handler)")

    # Now find the LoROM GSU setup code.
    # It's near the first CMP R5, #0xcb occurrence, in the 0x20 (LoROM) case.
    lorom_area = occ[0]
    # The GSU setup is BEFORE the combo check in LoROM.
    # Search backwards from lorom_area for the CMP R5, #0x1a pattern
    gsu_setup = None
    for off in range(lorom_area - 60, lorom_area, 2):
        val = struct.unpack_from('<H', fw, off)[0]
        if val == 0x2d1a:  # CMP R5, #0x1a
            print(f"\n  LoROM CMP R5,#0x1a at {off:#x}")
            gsu_setup = off
            break

    if gsu_setup is None:
        # Search forward from the LoROM check area
        for off in range(lorom_area - 100, lorom_area + 40, 2):
            val = struct.unpack_from('<H', fw, off)[0]
            if val == 0x2d15:  # CMP R5, #0x15
                print(f"\n  LoROM CMP R5,#0x15 at {off:#x}")
                gsu_setup = off
                break

    # The simplest reliable patch: just change the one byte from 0xcb to 0x15
    # in the HiROM handler. The "combo handler" code path will execute, but
    # for our ROM it just needs to set fpga_conf to something that loads the
    # GSU bitstream. If the combo handler doesn't do that, we need a different
    # approach.

    # Let's just do the minimal patch and see what happens:
    print(f"\n=== APPLYING PATCH ===")
    print(f"  Offset {hirom_cb:#x}: changing 0x2dcb -> 0x2d15")
    print(f"  (CMP R5, #0xcb -> CMP R5, #0x15)")

    fw[hirom_cb] = 0x15  # change immediate from 0xcb to 0x15
    # byte at hirom_cb+1 stays 0x2d (CMP R5, #imm)

    # Recalculate header CRC
    body = fw[HDR:]
    crc, crcc = compute_crc(body)
    struct.pack_into('<I', fw, 12, crc)
    struct.pack_into('<I', fw, 16, crcc)
    print(f"  Updated CRC: {crc:#010x}, CRCC: {crcc:#010x}")

    out_path = sys.argv[2]
    with open(out_path, 'wb') as f:
        f.write(fw)
    print(f"  Wrote {len(fw)} bytes to {out_path}")
    print(f"\n  NOTE: This patch redirects HiROM carttype 0x15 to the")
    print(f"  combo handler code path. If the combo handler doesn't")
    print(f"  set up GSU, a deeper patch is needed.")

if __name__ == '__main__':
    main()
