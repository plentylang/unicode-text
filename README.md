# unicode_text

Unicode text segmentation and terminal display width for the
Plenty programming language:

- [UAX #29](https://www.unicode.org/reports/tr29/) extended grapheme
  clusters, word boundaries and sentence boundaries;
- display width in terminal columns, following the Rust
  [`unicode-width`](https://github.com/unicode-rs/unicode-width) crate and
  [UAX #11](https://www.unicode.org/reports/tr11/) East Asian Width.

The package is plain Plenty with no native code. Iteration allocates nothing;
the `*_list` conveniences allocate and return `AllocError` on failure.

Data version: **Unicode 17.0.0**, the version of Plenty's `std.unicode`.

## Install

```toml
[dependencies]
unicode_text = { git = "https://github.com/plentylang/unicode-text.git", tag = "v0.1.0" }
```

Then run `plenty fetch` (or any build command).

## Example

```plenty
import unicode_text
from unicode_text import Ambiguous

def main() -> Result[(), AllocError | IoError]:
    text = "Hi 👩‍🔬! 日本語のテキスト。"
    print(unicode_text.grapheme_list(&text)?)?
    print(unicode_text.word_list(&text)?)?
    for span in unicode_text.sentences(text):
        print(span.start, span.stop)?
    print(unicode_text.width(&text, Ambiguous.Narrow))?
    print(unicode_text.width("±1", Ambiguous.Wide))?
    Ok(())
```

Output (sentence spans are scalar positions; the ZWJ emoji is three scalars):

```text
["H", "i", " ", "👩‍🔬", "!", " ", "日", "本", "語", "の", "テ", "キ", "ス", "ト", "。"]
["Hi", "日", "本", "語", "の", "テキスト"]
0 8
8 17
25
3
```

## API

| Item | Meaning |
|---|---|
| `unicode_version() -> str` | `"17.0.0"`, the Unicode version of every table |
| `Span(start, stop, byte_start, byte_stop)` | One segment: scalar positions `start..stop` (as used by `str.slice` and `str.find`) and UTF-8 byte offsets `byte_start..byte_stop`, both half-open |
| `graphemes(text) -> Generator[Span]` | Extended grapheme clusters |
| `word_bounds(text) -> Generator[Span]` | Every segment between word boundaries, including spaces and punctuation |
| `words(text) -> Generator[Span]` | Word-boundary segments containing an alphanumeric scalar (Alphabetic, or general category Nd, Nl or No), like Rust's `unicode_words` |
| `sentences(text) -> Generator[Span]` | Sentences, including trailing spaces and line breaks |
| `grapheme_list`, `word_bound_list`, `word_list`, `sentence_list` | `(text: &str) -> Result[list[str], AllocError]`: the same segments as strings |
| `enum Ambiguous: Narrow \| Wide` | How to count East Asian Ambiguous characters |
| `width(text: &str, ambiguous) -> i64` | Columns used to display `text` |
| `scalar_width(scalar: &str, ambiguous) -> Option[i64]` | Columns of one scalar on its own; `Nothing` for a control or for text that is not exactly one scalar |

The generators take `str` (pass `*text` for a `&str`), keep a few integers of
state, and allocate nothing. Segments always cover the whole text in order,
and empty text has none. UAX #29 sentence boundaries have no abbreviation
list, so `"Mr. Smith"` is two sentences.

### Display width

`width` and `scalar_width` match `unicode-width` 0.2.2's `width`/`width_cjk`
and `UnicodeWidthChar::width`/`width_cjk` for every scalar and every tested
sequence:

- East Asian Wide and Fullwidth characters, and emoji presentation, are 2.
- Combining marks, format characters, default-ignorable scalars and Hangul
  medial vowels and final consonants are 0.
- Emoji ZWJ sequences, flags, keycaps, modifier sequences and tag sequences
  that form one emoji are 2; `U+FE0F` selects emoji presentation and
  `U+FE0E` text presentation.
- A few contextual ligatures (Arabic lam-alef, some Buginese, Tifinagh, Lisu,
  Old Turkic, Khmer and Kirat Rai sequences) follow `unicode-width`'s rules.

**Ambiguous width.** There is no default. Use `Ambiguous.Narrow` for most
terminals and `Ambiguous.Wide` for CJK legacy contexts (terminals or fonts
that draw characters such as `±`, `§` and box drawing two columns wide).

**Controls.** As in `unicode-width`, `width` counts each control scalar
(U+0000..U+001F, U+007F..U+009F) as one column, except that `"\r\n"` counts
one in total; `scalar_width` returns `Nothing` for them. A terminal does not
draw a tab, newline or escape sequence as one column, so strip, expand or
escape controls before measuring text that contains them.

Width is a property of a terminal and font, not of Unicode alone. These rules
match common modern terminals, which may still differ for new emoji or
unusual sequences.

## Development

```sh
plenty test                        # conformance and unit tests
python3 -B scripts/generate_tables.py
python3 -B scripts/compare_width.py  # needs cargo; PLENTY=/path/to/plenty
```

`tests/test_conformance.plenty` runs the unmodified Unicode
`GraphemeBreakTest.txt` (766 cases), `WordBreakTest.txt` (1,944) and
`SentenceBreakTest.txt` (512). `tests/test_width.plenty` checks width cases
and every fully-qualified emoji in `emoji-test.txt` (3,953).
`scripts/compare_width.py` compares `width` and `scalar_width` with
`unicode-width` 0.2.2 for all 1,112,064 scalars and 305,225 sequences
(emoji-test plus seeded random sequences); its Rust program in
`scripts/width-reference/` is a development tool, not part of the package.

### Data and updates

`scripts/generate_tables.py` (Python 3.10+, standard library only) downloads
the pinned Unicode Character Database files into `data/VERSION/` (ignored by
Git), and writes the committed tables `src/data/*.bin`, `src/tables.plenty`,
and the conformance files in `tests/data/`. To move to a new Unicode version:

1. Check that Plenty's `std.unicode.version()` has moved to the new version,
   so both report the same data.
2. Set `UNICODE_VERSION` in `scripts/generate_tables.py` and run it.
3. Compare the width derivation with the `scripts/unicode.py` of the
   `unicode-width` release for that Unicode version, and port any new rules
   to the generator and `src/width.plenty`; bump the crate pin in
   `scripts/width-reference/Cargo.toml`.
4. Update UAX #29 rule changes in `src/lib.plenty` if the new test files fail.
5. Run `plenty test` and `scripts/compare_width.py`, update the counts in
   the tests and this file, and tag a new version.

## Licence

Licensed under either of [Apache License, Version 2.0](LICENSE-APACHE) or
[MIT license](LICENSE-MIT), at your option.

The tables in `src/data/` and the test files in `tests/data/` are derived from
or copied from the Unicode Character Database, © Unicode, Inc., under the
[Unicode License v3](LICENSE-UNICODE).

The display-width rules in `src/width.plenty` and `scripts/generate_tables.py`
are ported from the Rust `unicode-width` crate, Copyright (c) 2015 The Rust
Project Developers, under MIT OR Apache-2.0.
