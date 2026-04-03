"""
pdf_annotator.py
----------------
Uses PyMuPDF (fitz) to highlight the differences in the original PDFs.
Now exports a single combined PDF containing both PDF A and PDF B.
Instead of marker highlights, it draws colored border boxes (rectangles)
around the differences.
"""

import fitz  # PyMuPDF
import os
from typing import List, Dict

# Colours for boxes: (R, G, B) mapping (0-1 range)
COLOR_DATA = (0.9, 0.1, 0.1)    # Red for Data mismatch
COLOR_FORMAT = (1.0, 0.7, 0.0)  # Orange/Yellow for Format mismatch


def create_combined_annotated_pdf(pdf_a: str, pdf_b: str, diffs: List[Dict], output_path: str) -> str:
    """
    Opens both PDFs, searches for the lines that have differences,
    and adds rectangular box annotations.
    Combines both into a single PDF, inserting a title page before each.
    Saves the result to output_path.
    """
    if not os.path.exists(pdf_a) or not os.path.exists(pdf_b):
        return ""

    doc_a = fitz.open(pdf_a)
    doc_b = fitz.open(pdf_b)

    def process_doc(doc, is_pdf_a: bool, filename: str):
        # 1. Add annotations
        for d in diffs:
            text = d.get("line_a") if is_pdf_a else d.get("line_b")
            if not text:
                continue

            color = COLOR_DATA if d["category"] == "DATA" else COLOR_FORMAT

            # Split into chunks based on tabs
            chunks = [chunk.strip() for chunk in text.split("\t") if chunk.strip()]
            
            for page in doc:
                for chunk in chunks:
                    rects = page.search_for(chunk)
                    for rect in rects:
                        # Slightly expand the rectangle for a better looking box
                        rect.x0 -= 2
                        rect.y0 -= 2
                        rect.x1 += 2
                        rect.y1 += 2
                        
                        # Add rectangle annotation (border box)
                        annot = page.add_rect_annot(rect)
                        annot.set_colors(stroke=color)
                        annot.set_border(width=1.5)
                        annot.update()

        # 2. Add a clear label to the top-left of every page
        label_text = f"PDF A (Reference): {filename}" if is_pdf_a else f"PDF B (Comparison): {filename}"
        for page in doc:
            # We insert text with a small red font at the top left corner.
            # coordinates: (x, y)
            page.insert_text(
                (10, 15), 
                label_text, 
                fontsize=10, 
                color=(0.8, 0.1, 0.1)
            )

        # 3. Insert a title page at the beginning of this document to cleanly separate
        title_page = doc.new_page(pno=0, width=595, height=842) # A4 size
        title = "PDF A (Reference)" if is_pdf_a else "PDF B (Comparison)"
        
        # Add basic text to the title page
        title_page.insert_text((50, 100), title, fontsize=24, color=(0.1, 0.2, 0.4))
        title_page.insert_text((50, 140), f"File: {filename}", fontsize=14, color=(0, 0, 0))

    # Process both documents
    process_doc(doc_a, True, os.path.basename(pdf_a))
    process_doc(doc_b, False, os.path.basename(pdf_b))
    
    # Append PDF B into PDF A
    doc_a.insert_pdf(doc_b)

    # Save as one single file
    doc_a.save(output_path)
    doc_a.close()
    doc_b.close()

    return output_path
