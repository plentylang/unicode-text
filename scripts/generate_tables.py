#!/usr/bin/env python3
"""Generate the unicode_text lookup tables from the Unicode Character Database.

Usage: python3 -B scripts/generate_tables.py

Downloads the pinned Unicode version's data files into `data/UNICODE_VERSION/`
(a cache, ignored by Git), writes compact range tables to `src/data/*.bin`,
writes `src/tables.plenty`, and copies the UAX #29 conformance tests and
`emoji-test.txt` into `tests/data/`. Python 3.10+, standard library only.

Each `.bin` table starts with 128 direct entries for ASCII, followed by
4-byte records `(start: 3 bytes big-endian, value: 1 byte)` sorted by start.
Records partition U+0080..U+10FFFF: a code point's value is that of the last
record whose start is not greater than it.

The display-width derivation follows `scripts/unicode.py` of the Rust
`unicode-width` crate 0.2.2 (MIT OR Apache-2.0), which defines the reference
semantics this package implements.
"""

import os
import re
import shutil
import sys
import urllib.request

UNICODE_VERSION = "17.0.0"
NUM_CODEPOINTS = 0x110000

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
CACHE = os.path.join(ROOT, "data", UNICODE_VERSION)
TABLES = os.path.join(ROOT, "src", "data")
TEST_DATA = os.path.join(ROOT, "tests", "data")

BASE = f"https://www.unicode.org/Public/{UNICODE_VERSION}"
FILES = {
    "GraphemeBreakProperty.txt": "ucd/auxiliary/GraphemeBreakProperty.txt",
    "WordBreakProperty.txt": "ucd/auxiliary/WordBreakProperty.txt",
    "SentenceBreakProperty.txt": "ucd/auxiliary/SentenceBreakProperty.txt",
    "GraphemeBreakTest.txt": "ucd/auxiliary/GraphemeBreakTest.txt",
    "WordBreakTest.txt": "ucd/auxiliary/WordBreakTest.txt",
    "SentenceBreakTest.txt": "ucd/auxiliary/SentenceBreakTest.txt",
    "DerivedCoreProperties.txt": "ucd/DerivedCoreProperties.txt",
    "PropList.txt": "ucd/PropList.txt",
    "EastAsianWidth.txt": "ucd/EastAsianWidth.txt",
    "LineBreak.txt": "ucd/LineBreak.txt",
    "HangulSyllableType.txt": "ucd/HangulSyllableType.txt",
    "UnicodeData.txt": "ucd/UnicodeData.txt",
    "DerivedGeneralCategory.txt": "ucd/extracted/DerivedGeneralCategory.txt",
    "DerivedJoiningGroup.txt": "ucd/extracted/DerivedJoiningGroup.txt",
    "DerivedJoiningType.txt": "ucd/extracted/DerivedJoiningType.txt",
    "DerivedCombiningClass.txt": "ucd/extracted/DerivedCombiningClass.txt",
    "emoji-data.txt": "ucd/emoji/emoji-data.txt",
    "emoji-variation-sequences.txt": "ucd/emoji/emoji-variation-sequences.txt",
    "emoji-test.txt": "emoji/emoji-test.txt",
}
COPIED_TESTS = [
    "GraphemeBreakTest.txt",
    "WordBreakTest.txt",
    "SentenceBreakTest.txt",
    "emoji-test.txt",
]


def fetch(name: str) -> str:
    path = os.path.join(CACHE, name)
    if not os.path.exists(path):
        os.makedirs(CACHE, exist_ok=True)
        url = f"{BASE}/{FILES[name]}"
        print(f"downloading {url}", file=sys.stderr)
        partial = path + ".part"
        urllib.request.urlretrieve(url, partial)
        os.replace(partial, path)
    return path


def read_lines(name: str):
    with open(fetch(name), encoding="utf-8") as handle:
        for line in handle:
            data = line.split("#", 1)[0].strip()
            if data:
                yield [field.strip() for field in data.split(";")]


def code_range(field: str) -> range:
    if ".." in field:
        low, high = field.split("..")
        return range(int(low, 16), int(high, 16) + 1)
    return range(int(field, 16), int(field, 16) + 1)


def property_values(name: str, index: int = 1) -> dict[str, set[int]]:
    """Map each value of a `code ; value` property file to its code points."""
    values: dict[str, set[int]] = {}
    for fields in read_lines(name):
        values.setdefault(fields[index], set()).update(code_range(fields[0]))
    return values


def check_version() -> None:
    with open(fetch("DerivedCoreProperties.txt"), encoding="utf-8") as handle:
        header = handle.readline()
    if UNICODE_VERSION not in header:
        sys.exit(f"DerivedCoreProperties.txt is not version {UNICODE_VERSION}: {header}")


# Segmentation property numbering; src/tables.plenty exports the same names.
GCB = ["Other", "CR", "LF", "Control", "Extend", "ZWJ", "Regional_Indicator",
       "Prepend", "SpacingMark", "L", "V", "T", "LV", "LVT"]
INCB = ["None", "Consonant", "Extend", "Linker"]
WB = ["Other", "CR", "LF", "Newline", "Extend", "ZWJ", "Regional_Indicator",
      "Format", "Katakana", "Hebrew_Letter", "ALetter", "Single_Quote",
      "Double_Quote", "MidNumLet", "MidLetter", "MidNum", "Numeric",
      "ExtendNumLet", "WSegSpace"]
SB = ["Other", "CR", "LF", "Extend", "Sep", "Format", "Sp", "Lower", "Upper",
      "OLetter", "Numeric", "ATerm", "STerm", "Close", "SContinue"]


def assign(table: list[int], values: dict[str, set[int]], names: list[str]) -> None:
    for name, cps in values.items():
        number = names.index(name)
        for cp in cps:
            table[cp] = number


def segmentation_tables() -> tuple[list[int], list[int], list[int]]:
    ext_pict = property_values("emoji-data.txt")["Extended_Pictographic"]
    core: dict[str, set[int]] = {}
    incb: dict[str, set[int]] = {}
    for fields in read_lines("DerivedCoreProperties.txt"):
        if fields[1] == "InCB":
            incb.setdefault(fields[2], set()).update(code_range(fields[0]))
        else:
            core.setdefault(fields[1], set()).update(code_range(fields[0]))
    categories = property_values("DerivedGeneralCategory.txt")
    alnum = set(core["Alphabetic"])
    for category in ("Nd", "Nl", "No"):
        alnum |= categories[category]

    gcb = [0] * NUM_CODEPOINTS
    assign(gcb, property_values("GraphemeBreakProperty.txt"), GCB)
    incb_values = [0] * NUM_CODEPOINTS
    assign(incb_values, incb, INCB)
    grapheme = [gcb[cp] | (incb_values[cp] << 4) | ((cp in ext_pict) << 6)
                for cp in range(NUM_CODEPOINTS)]

    wb = [0] * NUM_CODEPOINTS
    assign(wb, property_values("WordBreakProperty.txt"), WB)
    word = [wb[cp] | ((cp in ext_pict) << 5) | ((cp in alnum) << 6)
            for cp in range(NUM_CODEPOINTS)]

    sentence = [0] * NUM_CODEPOINTS
    assign(sentence, property_values("SentenceBreakProperty.txt"), SB)
    return grapheme, word, sentence


# Width states, numbered as `WidthState` in unicode-width's unicode.py. Values
# above 0xFFFF carry no state through the string; the low 16 bits of the rest
# are the `WidthInfo` bit patterns the width state machine in lib.plenty uses.
ZERO, NARROW, WIDE, THREE = 0x1_0000, 0x1_0001, 0x1_0002, 0x1_0003
LINE_FEED = 0b0000_0000_0000_0001
EMOJI_MODIFIER = 0b0000_0000_0000_0010
REGIONAL_INDICATOR = 0b0000_0000_0000_0011
EMOJI_PRESENTATION = 0b0000_0000_0000_0101
KIRAT_RAI_VOWEL_SIGN_E = 0b0000_0000_0010_0000
KIRAT_RAI_VOWEL_SIGN_AI = 0b0000_0000_0010_0001
VARIATION_SELECTOR_1_2_OR_3 = 0b0000_0010_0000_0000
VARIATION_SELECTOR_15 = 0b0100_0000_0000_0000
VARIATION_SELECTOR_16 = 0b1000_0000_0000_0000
JOINING_GROUP_ALEF = 0b0011_0000_1111_1111
COMBINING_LONG_SOLIDUS_OVERLAY = 0b0011_1100_1111_1111
HEBREW_LETTER_LAMED = 0b0011_1000_0000_0000
BUGINESE_LETTER_YA = 0b0011_1000_0000_0001
TIFINAGH_CONSONANT = 0b0011_1000_0000_0011
LISU_TONE_LETTER_MYA_NA_JEU = 0b0011_1100_0000_0101
OLD_TURKIC_LETTER_ORKHON_I = 0b0011_1000_0000_0110
KHMER_COENG_ELIGIBLE_LETTER = 0b0011_1100_0000_0111


def width_alone(state: int) -> int:
    if state in (ZERO, COMBINING_LONG_SOLIDUS_OVERLAY, VARIATION_SELECTOR_15,
                 VARIATION_SELECTOR_16, VARIATION_SELECTOR_1_2_OR_3):
        return 0
    if state in (WIDE, EMOJI_MODIFIER, EMOJI_PRESENTATION):
        return 2
    if state == THREE:
        return 3
    return 1


def east_asian_widths() -> list[str]:
    """`N` (narrow), `W` (wide), or `A` (ambiguous) for each code point."""
    codes = {"N": "N", "Na": "N", "H": "N", "W": "W", "F": "W", "A": "A"}
    widths = ["N"] * NUM_CODEPOINTS
    for fields in read_lines("EastAsianWidth.txt"):
        for cp in code_range(fields[0]):
            widths[cp] = codes[fields[1]]
    for cp in property_values("LineBreak.txt")["AI"]:
        widths[cp] = "A"
    categories = property_values("DerivedGeneralCategory.txt")
    for category in ("Lu", "Ll", "Lt", "Lm", "Lo", "Sk"):
        for cp in categories[category]:
            if widths[cp] == "A":
                widths[cp] = "N"
    widths[0x0387] = "A"
    for fields in read_lines("UnicodeData.txt"):
        decomposition = fields[5].split()
        if len(decomposition) == 2 and decomposition[1] == "0338" \
                and not decomposition[0].startswith("<"):
            if widths[int(decomposition[0], 16)] == "A":
                widths[int(fields[0], 16)] = "A"
    return widths


def zero_widths() -> list[bool]:
    zero = [False] * NUM_CODEPOINTS
    core = property_values("DerivedCoreProperties.txt")
    for name in ("Default_Ignorable_Code_Point", "Grapheme_Extend"):
        for cp in core[name]:
            zero[cp] = True
    hangul = property_values("HangulSyllableType.txt")
    for name in ("V", "T"):
        for cp in hangul[name]:
            zero[cp] = True
    for cp in (0x070F, 0x0605, 0x0890, 0x0891, 0x08E2, 0xA8FA):
        zero[cp] = True
    prepend = property_values("GraphemeBreakProperty.txt")["Prepend"]
    prepend -= property_values("PropList.txt")["Prepended_Concatenation_Mark"]
    for cp in prepend:
        zero[cp] = True
    zero[0x115F] = False
    zero[0x2D7F] = False
    return zero


def width_states() -> tuple[list[int], list[int]]:
    eaws = east_asian_widths()
    zws = zero_widths()
    not_ea: list[int] = []
    ea: list[int] = []
    for eaw, zw in zip(eaws, zws):
        if zw:
            not_ea.append(ZERO)
            ea.append(ZERO)
        else:
            not_ea.append(WIDE if eaw == "W" else NARROW)
            ea.append(NARROW if eaw == "N" else WIDE)

    emoji = property_values("emoji-data.txt")
    khmer = (list(range(0x1780, 0x1783)) + list(range(0x1784, 0x1788))
             + list(range(0x1789, 0x178D)) + list(range(0x178E, 0x1794))
             + list(range(0x1795, 0x1799)) + list(range(0x179B, 0x179E))
             + [0x17A0, 0x17A2, 0x17A7, 0x17AB, 0x17AC, 0x17AF])
    for cps, state in [
        ([0x0A], LINE_FEED),
        ([0x05DC], HEBREW_LETTER_LAMED),
        (sorted(property_values("DerivedJoiningGroup.txt")["Alef"]), JOINING_GROUP_ALEF),
        (khmer, KHMER_COENG_ELIGIBLE_LETTER),
        ([0x17A4], WIDE),
        ([0x17D8], THREE),
        ([0x1A10], BUGINESE_LETTER_YA),
        (list(range(0x2D31, 0x2D66)) + [0x2D6F], TIFINAGH_CONSONANT),
        ([0xA4FC, 0xA4FD], LISU_TONE_LETTER_MYA_NA_JEU),
        ([0xFE0F], VARIATION_SELECTOR_16),
        ([0x10C03], OLD_TURKIC_LETTER_ORKHON_I),
        ([0x16D67], KIRAT_RAI_VOWEL_SIGN_E),
        ([0x16D68], KIRAT_RAI_VOWEL_SIGN_AI),
        (sorted(emoji["Emoji_Presentation"]), EMOJI_PRESENTATION),
        (sorted(emoji["Emoji_Modifier"]), EMOJI_MODIFIER),
        (sorted(property_values("PropList.txt")["Regional_Indicator"]), REGIONAL_INDICATOR),
    ]:
        for cp in cps:
            not_ea[cp] = state
            ea[cp] = state
    ea[0x0338] = COMBINING_LONG_SOLIDUS_OVERLAY
    ea[0xFE00] = VARIATION_SELECTOR_1_2_OR_3
    ea[0xFE02] = VARIATION_SELECTOR_1_2_OR_3
    not_ea[0xFE01] = VARIATION_SELECTOR_1_2_OR_3
    not_ea[0xFE0E] = VARIATION_SELECTOR_15
    return not_ea, ea


# Width flag bits stored with each width class.
EMOJI_PRESENTATION_SEQ = 1
TEXT_PRESENTATION_SEQ = 2
EMOJI_MODIFIER_BASE = 4
TRANSPARENT_ZERO_WIDTH = 8
LIGATURE_TRANSPARENT = 16
SOLIDUS_TRANSPARENT = 32
JOINING_GROUP_LAM = 64


def width_flags(not_ea: list[int]) -> list[int]:
    flags = [0] * NUM_CODEPOINTS
    emoji = property_values("emoji-data.txt")
    emoji_style: set[int] = set()
    text_style: set[int] = set()
    for fields in read_lines("emoji-variation-sequences.txt"):
        base, selector = fields[0].split()
        if selector == "FE0F" and fields[1] == "emoji style":
            emoji_style.add(int(base, 16))
        if selector == "FE0E" and fields[1] == "text style":
            text_style.add(int(base, 16))
    text_style &= emoji["Emoji_Presentation"]
    text_style -= set(range(0x1F200, 0x1F300))

    transparent = property_values("DerivedJoiningType.txt")["T"]
    default_ignorable = property_values("DerivedCoreProperties.txt")["Default_Ignorable_Code_Point"]
    categories = property_values("DerivedGeneralCategory.txt")
    marks = categories["Mn"] | categories["Mc"] | categories["Me"]
    ligature = (default_ignorable & marks) | {0x200D}

    solidus = set()
    for value, cps in property_values("DerivedCombiningClass.txt").items():
        if int(value) > 1:
            solidus |= cps
    solidus |= ligature
    decompositions = []
    for fields in read_lines("UnicodeData.txt"):
        if fields[5]:
            decompositions.append((int(fields[0], 16), fields[5].split()))
    count = len(solidus)
    while True:
        for composed, parts in decompositions:
            if all(not part.startswith("<") and int(part, 16) in solidus for part in parts):
                solidus.add(composed)
        if len(solidus) == count:
            break
        count = len(solidus)

    lam = property_values("DerivedJoiningGroup.txt")["Lam"]
    for cp in range(NUM_CODEPOINTS):
        value = 0
        if cp in emoji_style:
            value |= EMOJI_PRESENTATION_SEQ
        if cp in text_style:
            value |= TEXT_PRESENTATION_SEQ
        if cp in emoji["Emoji_Modifier_Base"]:
            value |= EMOJI_MODIFIER_BASE
        if width_alone(not_ea[cp]) == 0 and cp in transparent:
            value |= TRANSPARENT_ZERO_WIDTH
        if cp in ligature:
            value |= LIGATURE_TRANSPARENT
        if cp in solidus:
            value |= SOLIDUS_TRANSPARENT
        if cp in lam:
            value |= JOINING_GROUP_LAM
        flags[cp] = value
    return flags


def width_tables() -> tuple[list[int], bytes]:
    """Per-code-point class numbers and the class table.

    Each class is 7 bytes: narrow width, narrow info (u16 big-endian), wide
    (East Asian) width, wide info, and the flag bits above.
    """
    not_ea, ea = width_states()
    flags = width_flags(not_ea)
    classes: dict[tuple[int, int, int], int] = {}
    numbers = [0] * NUM_CODEPOINTS
    for cp in range(NUM_CODEPOINTS):
        key = (not_ea[cp], ea[cp], flags[cp])
        if key not in classes:
            classes[key] = len(classes)
        numbers[cp] = classes[key]
    if len(classes) > 256:
        sys.exit(f"{len(classes)} width classes do not fit in a byte")
    table = bytearray()
    for (narrow, wide, flag), _ in sorted(classes.items(), key=lambda item: item[1]):
        for state in (narrow, wide):
            info = state if state <= 0xFFFF else 0
            table += bytes([width_alone(state), info >> 8, info & 0xFF])
        table.append(flag)
    return numbers, bytes(table)


def range_table(values: list[int]) -> bytes:
    if max(values) > 255:
        sys.exit("table value does not fit in a byte")
    out = bytearray(values[:128])
    previous = None
    for cp in range(128, NUM_CODEPOINTS):
        if values[cp] != previous:
            out += bytes([cp >> 16, (cp >> 8) & 0xFF, cp & 0xFF, values[cp]])
            previous = values[cp]
    return bytes(out)


def names_block(prefix: str, names: list[str]) -> str:
    return "\n".join(f"pub const {prefix}_{name.upper()}: i64 = {number}"
                     for number, name in enumerate(names))


PLENTY_MODULE = '''# Generated by scripts/generate_tables.py from Unicode {version}; do not edit.
# Internal to unicode_text: these names are not part of its public API.
# Table layout is described in the generator.

pub const UNICODE_VERSION: str = "{version}"

const GRAPHEME: bytes = include_bytes("data/grapheme.bin")
const WORD: bytes = include_bytes("data/word.bin")
const SENTENCE: bytes = include_bytes("data/sentence.bin")
const WIDTH: bytes = include_bytes("data/width.bin")
const WIDTH_CLASSES: bytes = include_bytes("data/width_classes.bin")

# Grapheme table value: Grapheme_Cluster_Break | Indic_Conjunct_Break << 4 |
# Extended_Pictographic << 6.
{gcb}
{incb}
pub const GRAPHEME_EXT_PICT: i64 = 64

# Word table value: Word_Break | Extended_Pictographic << 5 | alphanumeric << 6.
{wb}
pub const WORD_EXT_PICT: i64 = 32
pub const WORD_ALNUM: i64 = 64

{sb}

# Width class flags.
pub const EMOJI_PRESENTATION_SEQ: i64 = {eps}
pub const TEXT_PRESENTATION_SEQ: i64 = {tps}
pub const EMOJI_MODIFIER_BASE: i64 = {emb}
pub const TRANSPARENT_ZERO_WIDTH: i64 = {tzw}
pub const LIGATURE_TRANSPARENT: i64 = {lt}
pub const SOLIDUS_TRANSPARENT: i64 = {st}
pub const JOINING_GROUP_LAM: i64 = {lam}


def lookup(table: bytes, code: i64) -> i64:
    if code < 128:
        return i64(table[code])
    # Find the last record whose start is not greater than code.
    mut low = 0
    mut high = (len(table) - 128) // 4
    while high - low > 1:
        middle = (low + high) // 2
        at = 128 + middle * 4
        start = (i64(table[at]) << 16) | (i64(table[at + 1]) << 8) | i64(table[at + 2])
        if start <= code:
            low = middle
        else:
            high = middle
    i64(table[128 + low * 4 + 3])


pub def grapheme(code: i64) -> i64:
    lookup(GRAPHEME, code)


pub def word(code: i64) -> i64:
    lookup(WORD, code)


pub def sentence(code: i64) -> i64:
    lookup(SENTENCE, code)


# A width class is an offset into WIDTH_CLASSES: narrow width, narrow state
# (2 bytes), wide width, wide state (2 bytes), flags.
pub def width_class(code: i64) -> i64:
    lookup(WIDTH, code) * 7


pub def class_width(offset: i64, wide: bool) -> i64:
    classes = WIDTH_CLASSES
    i64(classes[offset + 3]) if wide else i64(classes[offset])


pub def class_state(offset: i64, wide: bool) -> i64:
    classes = WIDTH_CLASSES
    at = offset + 4 if wide else offset + 1
    (i64(classes[at]) << 8) | i64(classes[at + 1])


pub def class_flags(offset: i64) -> i64:
    classes = WIDTH_CLASSES
    i64(classes[offset + 6])
'''


def main() -> None:
    check_version()
    os.makedirs(TABLES, exist_ok=True)
    os.makedirs(TEST_DATA, exist_ok=True)
    grapheme, word, sentence = segmentation_tables()
    width_numbers, width_classes = width_tables()
    outputs = {
        "grapheme.bin": range_table(grapheme),
        "word.bin": range_table(word),
        "sentence.bin": range_table(sentence),
        "width.bin": range_table(width_numbers),
        "width_classes.bin": width_classes,
    }
    for name, data in outputs.items():
        with open(os.path.join(TABLES, name), "wb") as handle:
            handle.write(data)
        records = (len(data) - 128) // 4 if name != "width_classes.bin" else len(data) // 7
        print(f"src/data/{name}: {len(data)} bytes, {records} entries")
    module = PLENTY_MODULE.format(
        version=UNICODE_VERSION,
        gcb=names_block("GCB", GCB),
        incb=names_block("INCB", INCB),
        wb=names_block("WB", WB),
        sb=names_block("SB", SB),
        eps=EMOJI_PRESENTATION_SEQ, tps=TEXT_PRESENTATION_SEQ,
        emb=EMOJI_MODIFIER_BASE, tzw=TRANSPARENT_ZERO_WIDTH,
        lt=LIGATURE_TRANSPARENT, st=SOLIDUS_TRANSPARENT, lam=JOINING_GROUP_LAM,
    )
    with open(os.path.join(ROOT, "src", "tables.plenty"), "w", encoding="utf-8") as handle:
        handle.write(module)
    for name in COPIED_TESTS:
        shutil.copyfile(fetch(name), os.path.join(TEST_DATA, name))
    print(f"Unicode {UNICODE_VERSION} tables written")


if __name__ == "__main__":
    main()
