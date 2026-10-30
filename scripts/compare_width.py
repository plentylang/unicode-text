#!/usr/bin/env python3
"""Compare unicode_text's display widths with the Rust unicode-width crate.

Checks `scalar_width` for every Unicode scalar and `width` for every sequence
in tests/data/emoji-test.txt plus 300,000 seeded random sequences drawn from
the scalars that take part in width rules. Needs cargo and a `plenty`
compiler on PATH (or PLENTY=/path/to/plenty).

    python3 scripts/compare_width.py
"""

import bisect
import os
import random
import subprocess
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
SCRIPTS = ROOT / "scripts"
# Code points that change the state of the width machine, so random sequences
# exercise selectors, ZWJ sequences, keycaps, tags, flags and line breaks.
STATE_CODES = [0x200D, 0xFE0F, 0xFE0E, 0xFE00, 0xFE01, 0xFE02, 0x0338, 0x20E3,
               0xE007F, 0xE0061, 0xE0030, 0x1F3FB, 0x1F1E6, 0x0A, 0x0D]
EXTRA_CODES = [0x30, 0x39, 0x23, 0x2A, 0x3C, 0x3D, 0x3E, 0x41, 0x61, 0x2018,
               0x201C, 0x17D2, 0x05D0, 0x1A17, 0x1A15, 0x2D7F, 0xA4F8, 0x10C32,
               0x16D63, 0x16D69, 0x1F3F4, 0x0301, 0x4E00, 0x00A1, 0x1F600]


def interesting_codes():
    """Scalars whose width class has a non-default state or flags."""
    data = (ROOT / "src/data/width.bin").read_bytes()
    classes = (ROOT / "src/data/width_classes.bin").read_bytes()
    starts, values = [], []
    for i in range(128, len(data), 4):
        starts.append(int.from_bytes(data[i:i + 3], "big"))
        values.append(data[i + 3])
    codes = set(STATE_CODES) | set(EXTRA_CODES)
    for code in range(0x110000):
        if 0xD800 <= code < 0xE000:
            continue
        value = data[code] if code < 128 else values[bisect.bisect_right(starts, code) - 1]
        record = classes[value * 7:value * 7 + 7]
        if record[1] or record[2] or record[4] or record[5] or record[6]:
            codes.add(code)
    return sorted(codes)


def sequences():
    result = []
    for line in (ROOT / "tests/data/emoji-test.txt").open(encoding="utf-8"):
        fields = line.split("#")[0].split(";")
        if len(fields) == 2 and fields[0].strip():
            result.append([int(code, 16) for code in fields[0].split()])
    pool = interesting_codes()
    rng = random.Random(465)
    for _ in range(300_000):
        size = rng.randint(1, 8)
        result.append([rng.choice(STATE_CODES) if rng.random() < 0.35 else rng.choice(pool)
                       for _ in range(size)])
    return result


def main():
    plenty = os.environ.get("PLENTY", "plenty")
    reference_dir = SCRIPTS / "width-reference"
    subprocess.run(["cargo", "build", "--release", "--quiet"], cwd=reference_dir, check=True)
    reference = reference_dir / "target/release/width-reference"
    dump_dir = SCRIPTS / "width-dump"
    subprocess.run([plenty, "build", "--release"], cwd=dump_dir, check=True)
    dump = dump_dir / "target/release/width_dump"

    cases = sequences()
    corpus = "\n".join(" ".join(f"{code:X}" for code in case) for case in cases) + "\n"
    with tempfile.TemporaryDirectory() as scratch:
        path = Path(scratch) / "corpus.txt"
        path.write_text(corpus)
        ours = subprocess.run([dump, path], capture_output=True, text=True, check=True).stdout.splitlines()
    expected_scalars = {}
    for line in subprocess.run([reference, "scalars"], capture_output=True, text=True,
                               check=True).stdout.splitlines():
        code, narrow, wide = line.split()
        expected_scalars[int(code, 16)] = (narrow, wide)
    expected_sequences = subprocess.run([reference], input=corpus, capture_output=True, text=True,
                                        check=True).stdout.splitlines()

    def shown(option):
        return "-" if option.endswith("Nothing") else option.split("(")[1].rstrip(")")

    failures = 0
    scalar_lines = [line for line in ours if line.startswith("S ")]
    for line in scalar_lines:
        _, code, narrow, wide = line.split()
        if (shown(narrow), shown(wide)) != expected_scalars[int(code)]:
            failures += 1
            if failures <= 10:
                print(f"U+{int(code):04X}: {narrow} {wide}, expected {expected_scalars[int(code)]}")
    sequence_lines = ours[len(scalar_lines):]
    if len(scalar_lines) != len(expected_scalars) or len(sequence_lines) != len(cases):
        sys.exit("output length mismatch")
    for case, got, expected in zip(cases, sequence_lines, expected_sequences):
        if got != expected:
            failures += 1
            if failures <= 10:
                print(" ".join(f"{code:04X}" for code in case), "got", got, "expected", expected)
    print(f"{len(scalar_lines)} scalars and {len(cases)} sequences compared; {failures} mismatches")
    sys.exit(1 if failures else 0)


if __name__ == "__main__":
    main()
