//! Reads lines of space-separated hexadecimal code points from standard input
//! and prints `width width_cjk` for each, using unicode-width's string width.
//! With the argument `scalars`, instead prints `code width width_cjk` for every
//! Unicode scalar value, using its character width (`-` for no width).
use std::io::{self, BufRead, Write};
use unicode_width::{UnicodeWidthChar, UnicodeWidthStr};

fn main() {
    let stdout = io::stdout();
    let mut out = io::BufWriter::new(stdout.lock());
    if std::env::args().nth(1).as_deref() == Some("scalars") {
        for c in (0..=0x10FFFFu32).filter_map(char::from_u32) {
            let show = |w: Option<usize>| w.map_or("-".to_string(), |w| w.to_string());
            writeln!(out, "{:X} {} {}", c as u32, show(c.width()), show(c.width_cjk())).unwrap();
        }
        return;
    }
    for line in io::stdin().lock().lines() {
        let line = line.unwrap();
        let text: String = line
            .split_whitespace()
            .map(|cp| char::from_u32(u32::from_str_radix(cp, 16).unwrap()).unwrap())
            .collect();
        writeln!(out, "{} {}", text.width(), text.width_cjk()).unwrap();
    }
}
