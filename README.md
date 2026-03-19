# SNES HiROM+GSU+MSU-1 Test ROM

A standalone **4 MB** test ROM for validating **HiROM + SuperFX (GSU-2) + MSU-1** coprocessor configurations in SNES emulators. Built as a reference implementation for emulator developers working on combined HiROM+GSU support — a mapping mode that no commercial cartridge ever used, but is now needed for homebrew projects.

## Screenshot

```
  HiROM+GSU+MSU-1 TEST ROM  v1.1
  ==============================

  HiROM Mapping    : PASS
  ROM Banks        : 62/62 PASS
  WRAM Read/Write  : PASS
  GSU-2 VCR        : $04 PASS
  GSU SRAM R/W     : PASS
  GSU Execute      : PASS
  Game Pak RAM     : 8KB
  MSU-1 Detect     : FOUND
  MSU-1 Status     : $01

  CPU: 3.58MHz  GSU: 21.4MHz
  ROM: 4096KB  SRAM: 8KB
  Board: SHVC-1CD0N7S-01
  Serial: SHVC-TEST
```

Dark navy blue background. Test results are color-coded: green = PASS/FOUND, red = FAIL, yellow = SKIPPED/NOT FOUND, cyan = hex values and hardware info.

## Background

Commercial SNES cartridges with the SuperFX (GSU) coprocessor always used **LoROM** mapping (boards like SHVC-1C0N, SHVC-1CB5B). No retail game combined HiROM with GSU. However, homebrew projects targeting modern flash cartridges (SD2SNES/FXPak Pro) can benefit from HiROM's larger contiguous bank layout (64 KB per bank vs LoROM's 32 KB) alongside GSU-2 sprite scaling.

This combination requires emulator-side changes because the memory maps don't overlap cleanly with existing board definitions:

- **Mesen2**: [PR #89](https://github.com/SourMesen/Mesen2/pull/89) — HiROM+GSU support
- **bsnes**: [PR #380](https://github.com/bsnes-emu/bsnes/pull/380) — HiROM+GSU board recognition

This test ROM gives emulator developers a zero-dependency way to validate their implementations without needing commercial game assets. At 4 MB (64 banks), it stress-tests the full HiROM address space, verifying every bank maps correctly.

## What It Tests

The ROM runs 9 hardware tests sequentially and displays color-coded results on a Mode 0 BG1 text screen:

| Test | What It Verifies | Pass Condition |
|------|-----------------|----------------|
| **HiROM Mapping** | Reads the RESET vector from both `$C0:FFFC` (HiROM direct) and `$00:FFFC` (mirror). Both addresses must resolve to the same ROM byte. | Values match |
| **ROM Banks** | Reads a unique signature byte from offset `$FFA0` in each of the 62 ROM-mapped banks (`$C0`-`$EF`, `$F2`-`$FF`), injected at build time by `inject_signatures.py`. Banks `$F0`-`$F1` are skipped (SRAM mirrors). | All 62 match |
| **WRAM Read/Write** | Writes `$A55A` to `$7E:2000` and reads it back. | Read == Write |
| **GSU-2 VCR** | Reads the GSU Version Code Register at `$303B`. GSU-2 reports `$04`. | VCR == `$04` |
| **GSU SRAM R/W** | Writes and reads test patterns to Game Pak RAM at `$70:0000`-`$70:0003`. Skipped if VCR failed. | Read == Write |
| **GSU Execute** | Copies a 26-byte GSU pixel-plot program to `$70:0100`, configures the coprocessor, triggers execution via R15, and polls SFR.GO until the GSU halts. Skipped if VCR failed. | GSU executes STOP |
| **Game Pak RAM** | Detects available SRAM by writing sentinel values at power-of-2 boundaries (`$70:0800` through `$70:8000`) and checking for address wraparound. Skipped if VCR failed. | Reports detected size |
| **MSU-1 Detect** | Reads 6 bytes from `$002002`-`$002007` and compares against the magic string `S-MSU1`. A companion `.msu` data file is included to enable MSU-1 in emulators. | ID matches |
| **MSU-1 Status** | If MSU-1 was detected, reads and displays `MSU_STATUS` (`$2000`). Otherwise displays `--`. | Informational |

### Hardware Info (Footer)

| Field | Source | Example |
|-------|--------|---------|
| **CPU clock** | Derived from MEMSEL register (FastROM = 3.58 MHz, SlowROM = 2.68 MHz) | `3.58MHz` |
| **GSU clock** | Read from CLSR register after GSU execution (`$3039` bit 0: 0=10.7 MHz, 1=21.4 MHz) | `21.4MHz` |
| **ROM size** | From header declaration | `4096KB` |
| **SRAM size** | Detected via wraparound probe | `8KB` |

### Why 62/62 (Not 64)?

In HiROM+GSU, banks `$F0`-`$F1` are mapped to Game Pak RAM (SRAM) mirrors, not ROM. This is standard GSU behavior — the SRAM at `$70`-`$71` mirrors to `$F0`-`$F1`. The bank test skips these 2 banks, leaving 62 verifiable ROM banks. If an emulator reports fewer than 62, it isn't mapping the full 4 MB address range.

### GSU Program Detail

The embedded GSU test program (`pixel_test.gsu`) plots an 8x8 solid square using the GSU's hardware pixel cache. It exercises the full GSU pipeline: instruction fetch from Game Pak RAM, CACHE/COLOR/PLOT/LOOP/STOP opcodes, and pixel cache flush to the screen buffer. If SFR.GO clears after launch, the GSU successfully decoded instructions, plotted pixels, and executed STOP — proving the coprocessor is fully functional.

## ROM Configuration

| Field | Value |
|-------|-------|
| Size | **4 MB** (64 banks × 64 KB) |
| Mapping | HiROM + FastROM (`$31`) |
| Cartridge Type | ROM + GSU + RAM + Battery (`$15`) |
| SRAM | 8 KB at `$70`-`$71` (mirrors at `$F0`-`$F1`) |
| Title | `HIROM GSU MSU1 TEST` |
| Serial | SHVC-TEST |
| Board | SHVC-1CD0N7S-01 |

### Memory Map

```
$C0:0000-$EF:FFFF  ROM banks 0-47 (3 MB)
$F0:0000-$F1:FFFF  Game Pak RAM mirrors (SRAM, NOT ROM)
$F2:0000-$FF:FFFF  ROM banks 50-63 (896 KB)
$00:8000-$3F:FFFF  ROM LoROM mirrors
$70:0000-$71:1FFF  Game Pak RAM (GSU SRAM, 8KB)
$00:3000-$00:34FF  GSU I/O registers
$00:2000-$00:2007  MSU-1 registers
```

### VRAM Layout

```
$0000-$03FF  BG1 tilemap (32x32, Mode 0)
$1000-$17FF  BG1 CHR tiles (2bpp, ASCII font at tiles 32-126)
```

## Building

### Prerequisites

- **WSL** (Windows Subsystem for Linux) or a native Linux environment
- **Python 3** (any version, no external packages needed)
- Assembler toolchain is included in `tools/`:
  - [WLA-DX](https://github.com/vhelin/wla-dx) v9.3 (`wla-65816` + `wlalink`)
  - [Bass](https://github.com/ARM9/bass) v18 (`bass.exe` for GSU assembly)

### Build

```bash
# From WSL or Linux shell:
cd /path/to/SNES-HiRomGsuTest
make

# Output:
#   build/HiRomGsuTest.sfc  (4 MB ROM)
#   build/HiRomGsuTest.msu  (4 KB MSU-1 data file)
```

```bash
# From Windows (PowerShell):
wsl -e bash -lc "cd /mnt/e/gh/SNES-HiRomGsuTest && make"
```

### Build Pipeline

```
gen_font.py ──────────────────► build/font.bin (760B, 1bpp 8x8 font)
pixel_test.gsu ─────[bass]───► build/pixel_test.bin (26B, GSU binary)
test_rom.65816 ─────[wla]────► build/test_rom.o
build/test_rom.o ───[wlalink]─► build/HiRomGsuTest.sfc (4 MB)
                 ───[python]──► inject bank signatures into ROM
                 ───[python]──► build/HiRomGsuTest.msu (4 KB)
```

## Running

### Mesen 2 (with HiROM+GSU patch)

Place both files in the same directory and load the `.sfc`:
```
HiRomGsuTest.sfc
HiRomGsuTest.msu
```
Mesen auto-detects the mapping from the ROM header. The `.msu` file enables MSU-1 detection.

### bsnes / bsnes-plus

Place the manifest alongside the ROM:
```
HiRomGsuTest.sfc
HiRomGsuTest.msu
hirom_gsu_test.bml
```
bsnes reads the `.bml` manifest to configure the HiROM+GSU memory map.

### Hardware (FXPak Pro / SD2SNES)

Copy `.sfc` and `.msu` to the SD card. The FXPak Pro firmware recognizes the GSU cart type from the header and configures the FPGA accordingly. GSU-2 tests should pass on real hardware.

### Expected Results

| Emulator / Hardware | HiROM | Banks | WRAM | GSU VCR | GSU SRAM | GSU Exec | Pak RAM | MSU-1 |
|---------------------|-------|-------|------|---------|----------|----------|---------|-------|
| Mesen 2 (patched) | PASS | 62/62 | PASS | $04 PASS | PASS | PASS | 64KB+ | FOUND |
| bsnes (with .bml) | PASS | 62/62 | PASS | $04 PASS | PASS | PASS | 8KB | FOUND |
| FXPak Pro (stock fw) | PASS | 62/62 | PASS | $00 FAIL | SKIP | SKIP | SKIP | FOUND |
| FXPak Pro (patched fw) | PASS | 62/62 | PASS | $04 PASS | PASS | PASS | 8KB | FOUND |
| Unpatched emulator | PASS | ??/62 | PASS | FAIL | SKIP | SKIP | SKIP | varies |

### FXPak Pro: SuperFX Not Enabled for HiROM

Stock FXPak Pro firmware (v1.11.0 and earlier) does **not** enable the SuperFX FPGA core for HiROM ROMs. The detection logic in [`src/smc.c`](https://github.com/mrehkopf/sd2snes/blob/master/src/smc.c) hardcodes LoROM:

```c
// Only triggers for map == 0x20 (LoROM), rejects 0x21 (HiROM)
if (header->map == 0x20 && ((header->carttype >= 0x13
     && header->carttype <= 0x15) || header->carttype == 0x1a)) {
    props->has_gsu = 1;
    props->fpga_conf = FPGA_GSU;
```

No commercial SNES cartridge ever combined HiROM with SuperFX, so the firmware never needed this path. The fix is a one-line change:

```c
if ((header->map == 0x20 || header->map == 0x21) && ((header->carttype >= 0x13
     && header->carttype <= 0x15) || header->carttype == 0x1a)) {
```

The GSU FPGA core itself should work with HiROM — the GSU accesses ROM via its own ROMBR register and RAM via `$70`-`$71`, independent of the SNES mapping mode. Confirmed via FXPak USB diagnostic: HiROM bank mapping (62/62), MSU-1, and SRAM all function correctly; only the GSU core loading is gated on the LoROM check.

## Technical Details

### Design Philosophy

Single flat 65816 assembly file, no OOP framework, no engine dependencies, no external game assets. Bare-metal: hardware init, run tests, write results to BG1 tilemap, enable screen, halt. Total code + data is under 4 KB within a 4 MB ROM image.

### Bank Verification

At build time, `inject_signatures.py` writes each bank's index number (0-63) at ROM offset `$FFA0` within that bank. At runtime, the test loops through all 64 banks using indirect long addressing (`lda [$10]` with a 24-bit pointer at `$C0+N:$FFA0`), comparing each byte against the expected bank number. Banks `$F0`-`$F1` are skipped because they overlap with Game Pak RAM mirrors.

### SRAM Size Detection

The Game Pak RAM probe writes a sentinel byte (`$55`) to `$70:0000`, then writes a different value (`$AA`) at each power-of-2 boundary: `$70:0800` (2 KB), `$70:1000` (4 KB), `$70:2000` (8 KB), `$70:4000` (16 KB), `$70:8000` (32 KB). After each probe write, it reads `$70:0000` — if the sentinel changed, the address wrapped, revealing the RAM size. If no wrap is detected at 32 KB, it reports `64KB+`.

### Font

A 1bpp 8x8 bitmap font covering ASCII 32-126 (95 glyphs, 760 bytes) is generated by `gen_font.py` and uploaded to VRAM with 1bpp-to-2bpp doubling. Each source byte is written to both bitplane 0 and bitplane 1, producing color index 3 (text color) for set pixels and color index 0 (transparent/backdrop) for clear pixels.

### GSU Init Sequence

1. Zero screen buffer at `$70:0C00`
2. Copy `pixel_test.bin` to `$70:0100`
3. `CFGR` = `$80` (mask GSU IRQ)
4. `CLSR` = `$01` (21.4 MHz clock)
5. `PBR` = `$70` (execute from Game Pak RAM)
6. `SCBR` = `$03` (screen base at `$70:0C00`)
7. `SCMR` = `$2D` (16-color OBJ mode, GSU owns RAM bus)
8. Write `R15` = `$0100` (writing high byte triggers GO)
9. Poll `SFR` bit 5 until clear, or timeout
10. Read `CLSR` for clock speed display
11. Clear RAN/RON in `SCMR` to return buses to CPU

### Color Palette

| Palette | CGRAM Color 3 | Usage |
|---------|--------------|-------|
| 0 | `$7FFF` white | Default text, labels, footer |
| 1 | `$03E0` green | PASS, FOUND |
| 2 | `$001F` red | FAIL |
| 3 | `$03FF` yellow | SKIPPED, NOT FOUND |
| 4 | `$7FE0` cyan | Hex values, clock speeds, RAM sizes |

Backdrop (CGRAM[0]): `$2842` — dark navy blue (R=2, G=2, B=10).

## File Structure

```
SNES-HiRomGsuTest/
├── test_rom.65816       # Main 65816 assembly (code, strings, palettes)
├── test_rom.h           # WLA-DX memory map (4MB HiROM, 64 banks)
├── pixel_test.gsu       # GSU-2 pixel plot test (Bass v18 syntax)
├── gen_font.py          # 8x8 1bpp font generator (Python 3, no deps)
├── inject_signatures.py # Post-link: write bank ID at $FFA0 per bank
├── makefile             # Build orchestration (WSL/Linux)
├── linkfile.lnk         # WLA-DX linker configuration
├── hirom_gsu_test.bml   # bsnes board manifest
└── tools/
    ├── bass/            # Bass v18 assembler + architecture definitions
    └── wla-dx/          # WLA-DX v9.3 (wla-65816 + wlalink)
```

## License

Public domain. Use this ROM freely for emulator testing, development, and validation.
