# PDF Comparison CLI Tool Implementation Plan

This plan outlines the design and architecture for a Python terminal-based tool to compare two PDFs, identifying data mismatches, formatting differences, and structural changes per the updated requirements.

## Proposed Changes

### 1. Project Structure

The application will be built as a modular Python script, utilizing standard libraries alongside robust text extraction and fuzzy matching libraries.

- `pdf_compare.py` - The main CLI entry point using `argparse`.
- `requirements.txt` - Will list `pymupdf` (or `pdfplumber`), `colorama`, and `rapidfuzz`.

### 2. Core Functions

The comparison logic will be cleanly separated into distinct functions:

- `extract_text(pdf_path)`: Uses `pdfplumber` or `PyMuPDF` to read tables and lines structure efficiently.
- `normalize_data(text)`: Scrubs formatting differences for `--mode=data` (removes `%`, spaces, normalizes number formats like `290,000` -> `290000`).
- `align_lines(lines_a, lines_b)`: Uses `rapidfuzz` or `difflib` to pair up similar lines from both PDFs, handling reordered sections and additions/deletions.
- `compare_data(aligned_pairs)`: Performs structural comparison on normalized values to find pure numeric or factual differences.
- `compare_full(aligned_pairs)`: Performs strict comparison without normalization to catch labeling discrepancies ("No of Month" vs "No. of Months"), formatting (whitespace, %), and extra content.
- `generate_report(differences, summary)`: Formats the terminal output using `colorama` for red/yellow indicators, and handles exporting to `.txt` or `.json`.

### 3. Comparison Mode Details

#### Data Mode (`--mode=data`)

- Normalizes all text and numeric values prior to comparison.
- Skips over lines that were only re-formatted (i.e., `10` matches `10%`).
- Highlights only when core facts mismatch (e.g., `Tax: 10` vs `Tax: 15`).

#### Full Mode (`--mode=full`)

- Executes data mode comparison, but adds supplementary checks.
- Highlights formatting discrepancies (`10` vs `10%`).
- Detects label variance utilizing fuzzy ratios (`rapidfuzz.fuzz.ratio`).
- Identifies entirely new lines or missing content via line alignment.

### 4. Output Formatting

The terminal will use `colorama` to print a highly readable report block:

```text
----------------------------------
PDF COMPARISON REPORT
----------------------------------
[SUMMARY]
Total Differences: X
Data Differences: X
Format Differences: X

[DETAILS]
...
(Red for DATA MISMATCH or MISSING/EXTRA lines)
(Yellow for FORMAT or LABEL DIfferences)
```

## User Review Required

> [!IMPORTANT]
>
> - **Dependency Selection:** I recommend using `PyMuPDF` (`fitz`) for speed, but `pdfplumber` is inherently better at preserving complex table structures and reading them logically. I plan to use `pdfplumber` as it perfectly fits your text/table parsing needs. Is `pdfplumber` perfectly okay with you?
> - **Export format arguments:** Should I introduce `--export json` or `--export txt`, or just export both formats automatically to a folder on every run?

## Verification Plan

### Automated Tests

* None initially required.

### Manual Verification

1. Run `python pdf_compare.py path/to/A.pdf path/to/B.pdf --mode=data`
2. Verify output color coding and that format-level differences (e.g., `10` vs `10%`) are successfully ignored.
3. Run `python pdf_compare.py path/to/A.pdf path/to/B.pdf --mode=full`
4. Confirm additional output highlighting label variations and added timestamps.
