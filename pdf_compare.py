"""
PDF Comparison CLI Tool
-----------------------
Compares two PDFs for data mismatches, formatting differences,
and structural changes.

Usage:
    python pdf_compare.py A.pdf B.pdf --mode=data
    python pdf_compare.py A.pdf B.pdf --mode=full
    python pdf_compare.py A.pdf B.pdf --mode=full --export txt
    python pdf_compare.py A.pdf B.pdf --mode=full --export json
    python pdf_compare.py A.pdf B.pdf --mode=full --export both
"""

import argparse
import json
import os
import re
import sys
from datetime import datetime
from typing import Optional

import colorama
import pdfplumber
from colorama import Fore, Style
from rapidfuzz import fuzz
from rapidfuzz.distance import Levenshtein

# ── Initialise colorama for cross-platform ANSI colours ──────────────────────
colorama.init(autoreset=True)

# ── Thresholds ───────────────────────────────────────────────────────────────
FUZZY_MATCH_THRESHOLD = 60   # minimum score to consider two lines "related"
LABEL_DIFF_THRESHOLD  = 85   # below this → label mismatch (full mode)


# ─────────────────────────────────────────────────────────────────────────────
# 1. EXTRACTION
# ─────────────────────────────────────────────────────────────────────────────

def extract_text(pdf_path: str) -> list[str]:
    """
    Opens *pdf_path* with pdfplumber and returns a flat list of non-blank
    text lines, preserving page order.
    Tables are extracted row-by-row so their cells appear as tab-separated
    lines which later stages can process uniformly.
    """
    if not os.path.isfile(pdf_path):
        print(f"{Fore.RED}ERROR: File not found → {pdf_path}{Style.RESET_ALL}")
        sys.exit(1)

    lines: list[str] = []

    with pdfplumber.open(pdf_path) as pdf:
        for page_num, page in enumerate(pdf.pages, start=1):
            # --- extract tables first ---
            tables = page.extract_tables()
            table_bboxes = []
            for table in tables:
                # collect raw table text
                for row in table:
                    cell_values = [str(c).strip() if c is not None else "" for c in row]
                    row_text = "\t".join(cell_values)
                    if row_text.strip():
                        lines.append(row_text)
                # remember the bbox so we can skip the same region in text
                table_bboxes.append(page.find_tables())

            # --- extract remaining text (non-table regions) ---
            # Use crop + extract_text per word-block to avoid duplication
            page_text = page.extract_text(x_tolerance=3, y_tolerance=3)
            if page_text:
                for line in page_text.splitlines():
                    stripped = line.strip()
                    if stripped:
                        lines.append(stripped)

    # De-duplicate consecutive identical lines that pdfplumber sometimes emits
    deduped: list[str] = []
    for line in lines:
        if not deduped or line != deduped[-1]:
            deduped.append(line)

    return deduped


# ─────────────────────────────────────────────────────────────────────────────
# 2. NORMALISATION
# ─────────────────────────────────────────────────────────────────────────────

_NUM_RE     = re.compile(r"[\s,_]")          # spaces, commas, underscores
_PERCENT_RE = re.compile(r"%")
_MULTI_SP   = re.compile(r"\s+")


def normalize_data(text: str) -> str:
    """
    Strips formatting so that pure data mismatches stand out:
    - Removes % signs
    - Removes thousands separators (commas) and spaces inside numbers
    - Collapses multiple whitespace
    - Lowercases
    """
    t = _PERCENT_RE.sub("", text)
    # remove commas/spaces between digits  e.g. 290,000 → 290000
    t = re.sub(r"(\d)[,\s](\d)", r"\1\2", t)
    t = _MULTI_SP.sub(" ", t).strip().lower()
    return t


def normalize_label(text: str) -> str:
    """Light normalisation for label comparison: lowercase + collapse spaces."""
    return _MULTI_SP.sub(" ", text).strip().lower()


# ─────────────────────────────────────────────────────────────────────────────
# 3. LINE ALIGNMENT
# ─────────────────────────────────────────────────────────────────────────────

def align_lines(
    lines_a: list[str],
    lines_b: list[str],
) -> list[tuple[Optional[str], Optional[str]]]:
    """
    Aligns two lists of lines using a greedy best-match algorithm backed by
    rapidfuzz token_set_ratio so that reordered or slightly reworded sections
    are paired correctly.

    Returns a list of (line_a | None, line_b | None) pairs.
    """
    used_b = [False] * len(lines_b)
    pairs: list[tuple[Optional[str], Optional[str]]] = []
    unmatched_a: list[str] = []

    for la in lines_a:
        best_score = -1
        best_idx   = -1
        for ib, lb in enumerate(lines_b):
            if used_b[ib]:
                continue
            score = fuzz.token_set_ratio(normalize_data(la), normalize_data(lb))
            if score > best_score:
                best_score = score
                best_idx   = ib

        if best_score >= FUZZY_MATCH_THRESHOLD and best_idx >= 0:
            used_b[best_idx] = True
            pairs.append((la, lines_b[best_idx]))
        else:
            unmatched_a.append(la)

    # Lines only in A (deleted)
    for la in unmatched_a:
        pairs.append((la, None))

    # Lines only in B (added)
    for ib, lb in enumerate(lines_b):
        if not used_b[ib]:
            pairs.append((None, lb))

    return pairs


# ─────────────────────────────────────────────────────────────────────────────
# 4. COMPARISON ENGINES
# ─────────────────────────────────────────────────────────────────────────────

def compare_data(
    aligned_pairs: list[tuple[Optional[str], Optional[str]]],
) -> list[dict]:
    """
    Data mode: compare normalised values only.
    Returns a list of difference dicts.
    """
    diffs: list[dict] = []

    for la, lb in aligned_pairs:
        if la is None:
            diffs.append({"type": "EXTRA_IN_B", "category": "DATA",
                          "line_a": None, "line_b": lb})
        elif lb is None:
            diffs.append({"type": "MISSING_IN_B", "category": "DATA",
                          "line_a": la, "line_b": None})
        else:
            na, nb = normalize_data(la), normalize_data(lb)
            if na != nb:
                diffs.append({"type": "DATA_MISMATCH", "category": "DATA",
                              "line_a": la, "line_b": lb,
                              "norm_a": na, "norm_b": nb})

    return diffs


def compare_full(
    aligned_pairs: list[tuple[Optional[str], Optional[str]]],
) -> list[dict]:
    """
    Full mode: data mode diffs + formatting + label checks.
    """
    diffs = compare_data(aligned_pairs)
    already_flagged = {(d["line_a"], d["line_b"]) for d in diffs}

    for la, lb in aligned_pairs:
        if la is None or lb is None:
            continue  # already caught by compare_data
        if (la, lb) in already_flagged:
            continue

        na, nb = normalize_data(la), normalize_data(lb)

        # ── Format difference: raw differs but normalised equals ─────────────
        if na == nb and la.strip() != lb.strip():
            diffs.append({"type": "FORMAT_DIFF", "category": "FORMAT",
                          "line_a": la, "line_b": lb})
            continue

        # ── Label / wording difference ────────────────────────────────────────
        label_score = fuzz.ratio(normalize_label(la), normalize_label(lb))
        if label_score < LABEL_DIFF_THRESHOLD:
            diffs.append({"type": "LABEL_DIFF", "category": "FORMAT",
                          "line_a": la, "line_b": lb,
                          "similarity": round(label_score, 1)})

    return diffs


# ─────────────────────────────────────────────────────────────────────────────
# 5. REPORT GENERATION
# ─────────────────────────────────────────────────────────────────────────────

_CATEGORY_COLOR = {
    "DATA":   Fore.RED,
    "FORMAT": Fore.YELLOW,
}

_TYPE_LABEL = {
    "DATA_MISMATCH": "DATA MISMATCH",
    "MISSING_IN_B":  "MISSING IN PDF-B",
    "EXTRA_IN_B":    "EXTRA IN PDF-B",
    "FORMAT_DIFF":   "FORMAT DIFFERENCE",
    "LABEL_DIFF":    "LABEL DIFFERENCE",
}


def _hr(char: str = "─", width: int = 60) -> str:
    return char * width


def generate_report(
    diffs: list[dict],
    pdf_a: str,
    pdf_b: str,
    mode: str,
) -> str:
    """
    Builds and prints the colourised terminal report.
    Returns the plain-text version (no ANSI codes) for file export.
    """
    data_diffs   = [d for d in diffs if d["category"] == "DATA"]
    format_diffs = [d for d in diffs if d["category"] == "FORMAT"]
    total        = len(diffs)

    now = datetime.now().strftime("%Y-%m-%d %H:%M:%S")

    # ── Terminal output ───────────────────────────────────────────────────────
    print()
    print(Fore.CYAN + Style.BRIGHT + _hr("─"))
    print(Fore.CYAN + Style.BRIGHT + "  PDF COMPARISON REPORT")
    print(Fore.CYAN + Style.BRIGHT + _hr("─"))
    print(f"  Generated : {now}")
    print(f"  Mode      : {mode.upper()}")
    print(f"  PDF A     : {os.path.basename(pdf_a)}")
    print(f"  PDF B     : {os.path.basename(pdf_b)}")
    print(Fore.CYAN + _hr("─"))

    print(Style.BRIGHT + "\n[SUMMARY]")
    print(f"  Total Differences  : {total}")
    print(f"  {Fore.RED}Data Differences   : {len(data_diffs)}{Style.RESET_ALL}")
    if mode == "full":
        print(f"  {Fore.YELLOW}Format Differences : {len(format_diffs)}{Style.RESET_ALL}")

    print(Style.BRIGHT + "\n[DETAILS]")

    if not diffs:
        print(f"  {Fore.GREEN}✔ No differences found.{Style.RESET_ALL}")
    else:
        for i, d in enumerate(diffs, start=1):
            color   = _CATEGORY_COLOR.get(d["category"], Fore.WHITE)
            label   = _TYPE_LABEL.get(d["type"], d["type"])
            print()
            print(color + Style.BRIGHT + f"  [{i}] {label}")
            if d["line_a"] is not None:
                print(color + f"      PDF-A : {d['line_a']}")
            if d["line_b"] is not None:
                print(color + f"      PDF-B : {d['line_b']}")
            if "similarity" in d:
                print(color + f"      Similarity : {d['similarity']}%")

    print()
    print(Fore.CYAN + _hr("─"))

    # ── Build plain-text version for export ───────────────────────────────────
    lines = [
        _hr("─"),
        "  PDF COMPARISON REPORT",
        _hr("─"),
        f"  Generated : {now}",
        f"  Mode      : {mode.upper()}",
        f"  PDF A     : {os.path.basename(pdf_a)}",
        f"  PDF B     : {os.path.basename(pdf_b)}",
        _hr("─"),
        "",
        "[SUMMARY]",
        f"  Total Differences  : {total}",
        f"  Data Differences   : {len(data_diffs)}",
    ]
    if mode == "full":
        lines.append(f"  Format Differences : {len(format_diffs)}")

    lines += ["", "[DETAILS]"]
    if not diffs:
        lines.append("  No differences found.")
    else:
        for i, d in enumerate(diffs, start=1):
            label = _TYPE_LABEL.get(d["type"], d["type"])
            lines.append(f"\n  [{i}] {label}")
            if d["line_a"] is not None:
                lines.append(f"      PDF-A : {d['line_a']}")
            if d["line_b"] is not None:
                lines.append(f"      PDF-B : {d['line_b']}")
            if "similarity" in d:
                lines.append(f"      Similarity : {d['similarity']}%")

    lines.append(_hr("─"))
    return "\n".join(lines)


# ─────────────────────────────────────────────────────────────────────────────
# 6. EXPORT
# ─────────────────────────────────────────────────────────────────────────────

def export_results(
    plain_text: str,
    diffs: list[dict],
    pdf_a: str,
    pdf_b: str,
    mode: str,
    export_fmt: Optional[str],
) -> None:
    """Saves the report to .txt and/or .json based on *export_fmt*."""
    if export_fmt is None:
        return

    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    stem = f"pdf_compare_{timestamp}"

    do_txt  = export_fmt in ("txt",  "both")
    do_json = export_fmt in ("json", "both")

    if do_txt:
        path = f"{stem}.txt"
        with open(path, "w", encoding="utf-8") as fh:
            fh.write(plain_text)
        print(f"{Fore.GREEN}✔ Report saved → {path}{Style.RESET_ALL}")

    if do_json:
        path = f"{stem}.json"
        payload = {
            "generated": datetime.now().isoformat(),
            "mode": mode,
            "pdf_a": pdf_a,
            "pdf_b": pdf_b,
            "summary": {
                "total": len(diffs),
                "data":  sum(1 for d in diffs if d["category"] == "DATA"),
                "format": sum(1 for d in diffs if d["category"] == "FORMAT"),
            },
            "differences": diffs,
        }
        with open(path, "w", encoding="utf-8") as fh:
            json.dump(payload, fh, indent=2, ensure_ascii=False)
        print(f"{Fore.GREEN}✔ JSON saved    → {path}{Style.RESET_ALL}")


# ─────────────────────────────────────────────────────────────────────────────
# 7. CLI ENTRY POINT
# ─────────────────────────────────────────────────────────────────────────────

def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="pdf_compare",
        description=(
            "Compare two PDF files for data mismatches, formatting "
            "differences, and structural changes."
        ),
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  python pdf_compare.py report_a.pdf report_b.pdf --mode=data
  python pdf_compare.py report_a.pdf report_b.pdf --mode=full
  python pdf_compare.py report_a.pdf report_b.pdf --mode=full --export json
  python pdf_compare.py report_a.pdf report_b.pdf --mode=full --export both
        """,
    )
    parser.add_argument("pdf_a", help="Path to the first (reference) PDF")
    parser.add_argument("pdf_b", help="Path to the second (comparison) PDF")
    parser.add_argument(
        "--mode",
        choices=["data", "full"],
        default="data",
        help=(
            "data – compare normalised values only (ignores formatting). "
            "full – data mode + formatting and label checks. "
            "(default: data)"
        ),
    )
    parser.add_argument(
        "--export",
        choices=["txt", "json", "both"],
        default=None,
        help="Export the report to a file. Choices: txt | json | both.",
    )
    return parser


def main() -> None:
    parser = build_parser()
    args   = parser.parse_args()

    print(f"{Fore.CYAN}Extracting text from PDF A …{Style.RESET_ALL}")
    lines_a = extract_text(args.pdf_a)

    print(f"{Fore.CYAN}Extracting text from PDF B …{Style.RESET_ALL}")
    lines_b = extract_text(args.pdf_b)

    print(f"{Fore.CYAN}Aligning {len(lines_a)} / {len(lines_b)} lines …{Style.RESET_ALL}")
    pairs = align_lines(lines_a, lines_b)

    print(f"{Fore.CYAN}Running comparison in [{args.mode.upper()}] mode …{Style.RESET_ALL}")
    if args.mode == "data":
        diffs = compare_data(pairs)
    else:
        diffs = compare_full(pairs)

    plain = generate_report(diffs, args.pdf_a, args.pdf_b, args.mode)

    export_results(plain, diffs, args.pdf_a, args.pdf_b, args.mode, args.export)


if __name__ == "__main__":
    main()
