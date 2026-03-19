#!/usr/bin/env python3
"""FXPak Pro diagnostic — reads key memory regions to diagnose GSU detection failure.

Usage: python tools/fxpak_diag.py
Requires: QUsb2Snes running and FXPak connected via USB.
"""
import asyncio
import struct
import sys

try:
    import websockets
except ImportError:
    print("ERROR: pip install websockets")
    sys.exit(1)

WS_URL = "ws://localhost:23074"


async def read_mem(ws, addr, size):
    """Read bytes from USB2SNES address space."""
    cmd = {
        "Opcode": "GetAddress",
        "Space": "SNES",
        "Operands": [format(addr, 'X'), format(size, 'X')]
    }
    await ws.send(str(cmd).replace("'", '"'))
    data = b""
    while len(data) < size:
        chunk = await ws.recv()
        if isinstance(chunk, str):
            print(f"  Unexpected text: {chunk}")
            break
        data += chunk
    return data[:size]


def hexdump(data, addr=0, width=16):
    for i in range(0, len(data), width):
        row = data[i:i+width]
        hexstr = " ".join(f"{b:02X}" for b in row)
        ascstr = "".join(chr(b) if 32 <= b < 127 else "." for b in row)
        print(f"  ${addr+i:06X}: {hexstr:<{width*3}} {ascstr}")


async def main():
    print("Connecting to QUsb2Snes...")
    async with websockets.connect(WS_URL) as ws:
        # Attach
        await ws.send('{"Opcode":"DeviceList","Space":"SNES","Operands":[]}')
        resp = await ws.recv()
        print(f"  Devices: {resp}")

        # Parse first device from list
        import json
        devices = json.loads(resp).get("Results", [])
        dev = devices[0] if devices else "SD2SNES COM3"
        print(f"  Attaching to: {dev}")
        await ws.send(json.dumps({"Opcode":"Attach","Space":"SNES","Operands":[dev]}))
        await asyncio.sleep(0.5)  # Attach has no response

        await ws.send('{"Opcode":"Info","Space":"SNES","Operands":[]}')
        resp = await ws.recv()
        print(f"  Info: {resp}")
        print()

        # 1. ROM Header at ROM offset $FFC0 (USB2SNES: direct ROM offset)
        print("\n=== ROM HEADER (offset $FFC0) ===")
        hdr = await read_mem(ws, 0x00FFC0, 32)
        hexdump(hdr, 0xFFC0)
        if len(hdr) >= 32:
            title = hdr[0:21].decode('ascii', errors='replace').rstrip()
            mapping = hdr[21]
            carttype = hdr[22]
            romsize = hdr[23]
            sramsize = hdr[24]
            country = hdr[25]
            licensee = hdr[26]
            print(f"  Title:    '{title}'")
            print(f"  Mapping:  ${mapping:02X} ({'HiROM' if mapping & 1 else 'LoROM'}{'+FastROM' if mapping & 0x10 else ''})")
            print(f"  CartType: ${carttype:02X} ({'GSU' if carttype in (0x13,0x14,0x15) else 'no GSU'})")
            print(f"  ROM Size: {1 << romsize} KB")
            print(f"  SRAM:     {1 << sramsize} KB")

        # 2. Extended header at ROM offset $FFB0
        print("\n=== EXTENDED HEADER (offset $FFB0) ===")
        ext = await read_mem(ws, 0x00FFB0, 16)
        hexdump(ext, 0xFFB0)

        # 3. WRAM direct page (CPU test state) — USB2SNES $F50000
        print("\n=== WRAM DIRECT PAGE ($7E:0000) ===")
        dp = await read_mem(ws, 0xF50000, 32)
        hexdump(dp, 0x0000)
        if len(dp) >= 16:
            palByte = dp[2]
            gsuDet = dp[3]
            msuDet = dp[4]
            gsuVcr = dp[5]
            msuStat = dp[6]
            bankPassed = dp[7]
            gsuClsr = dp[10]
            print(f"  gsuDetected: {gsuDet}")
            print(f"  msuDetected: {msuDet}")
            print(f"  gsuVcrVal:   ${gsuVcr:02X}")
            print(f"  msuStatVal:  ${msuStat:02X}")
            print(f"  bankPassed:  {bankPassed}")
            print(f"  gsuClsrVal:  ${gsuClsr:02X}")

        # 4. SRAM at $70:0000 — USB2SNES $E00000
        print("\n=== SRAM ($70:0000) via USB2SNES $E00000 ===")
        sram = await read_mem(ws, 0xE00000, 16)
        hexdump(sram, 0x700000)

        # 5. Try reading GSU register area via SNES bus
        # $00:3000-$303F — may return open bus if GSU not enabled
        print("\n=== GSU REGISTERS ($00:3030-$303F) ===")
        print("  (May return open bus $00/FF if GSU FPGA not enabled)")
        try:
            # SNES address $003030 — USB2SNES mapping unclear for I/O
            # Try direct SNES space read
            gsu = await read_mem(ws, 0x003030, 16)
            hexdump(gsu, 0x3030)
            if len(gsu) >= 12:
                sfr = gsu[0]
                vcr = gsu[11]  # $303B - $3030 = 11
                print(f"  SFR ($3030): ${sfr:02X}")
                print(f"  VCR ($303B): ${vcr:02X} ({'GSU-2' if vcr == 4 else 'NOT DETECTED'})")
        except Exception as e:
            print(f"  Read failed: {e}")

        # 6. ROM bank signatures — check a few banks
        print("\n=== ROM BANK SIGNATURES (offset $FFA0 per bank) ===")
        for bank in [0, 1, 31, 62, 63]:
            offset = bank * 0x10000 + 0xFFA0
            sig = await read_mem(ws, offset, 1)
            expected = bank
            actual = sig[0] if sig else -1
            status = "OK" if actual == expected else f"MISMATCH (expected {expected})"
            print(f"  Bank {bank:2d} (ROM ${offset:06X}): ${actual:02X} {status}")


asyncio.run(main())
