# PDF Comparison Tool

A full-featured Python desktop application that automatically compares two PDF files, detecting differences in data, formatting, and structures. It provides both a colourised terminal report and detailed highlighted visual exports.

## Features

- **Data Mode & Full Mode**: Ignore simple formatting changes (like added commas or `%` signs) when you only care about actual numbers, or use full mode to catch every discrepancy!
- **Drag & Drop GUI**: Simply drop your PDFs onto the app window.
- **Combined Annotated Export**: Generates a single boxed-highlight PDF containing both original files so you can visibly trace differences.
- **Side-by-Side Comparison Reports**: Exports detailed red/yellow comparison tables.
- **Background Multi-threading**: The app stays responsive during massive file comparisons. 

## Run From Source

To run the application from source:
```bash
pip install -r requirements.txt
python pdf_compare_gui.py
```

## Download the Executable

You can download a standalone Windows executable (`.exe`) from the [Releases page](../../releases) — no Python installation required!
