"""
PDF Comparison GUI
------------------
Drag-and-drop or browse to select two PDFs, choose a comparison mode,
and see colourised results — all in a single window.

Run:
    python pdf_compare_gui.py
"""

import threading
import tkinter as tk
from tkinter import filedialog, font, scrolledtext, ttk

from tkinterdnd2 import DND_FILES, TkinterDnD

import pdf_compare as core          # reuse all comparison logic
import pdf_export_report as exporter  # highlighted PDF exporter
import pdf_annotator as annotator     # highlights on original PDFs


# ── Colour palette ────────────────────────────────────────────────────────────
BG          = "#1a1a2e"
PANEL       = "#16213e"
ACCENT      = "#0f3460"
HIGHLIGHT   = "#e94560"
TEXT        = "#eaeaea"
MUTED       = "#8892a4"
DROP_IDLE   = "#0f3460"
DROP_HOVER  = "#1a4a8a"
GREEN       = "#4caf50"
YELLOW      = "#ffc107"
RED         = "#ef5350"
MONO_FONT   = ("Consolas", 10)


# ── Helper: strip surrounding braces that Windows DnD sometimes adds ──────────
def _clean_path(raw: str) -> str:
    raw = raw.strip()
    if raw.startswith("{") and raw.endswith("}"):
        raw = raw[1:-1]
    return raw


# ─────────────────────────────────────────────────────────────────────────────
class DropZone(tk.Frame):
    """A labelled drop-target that also has a Browse button."""

    def __init__(self, parent, label: str, on_file, **kw):
        super().__init__(parent, bg=PANEL, **kw)
        self._on_file = on_file
        self._path: str = ""

        # ── outer border frame ────────────────────────────────────────────────
        self._border = tk.Frame(self, bg=DROP_IDLE, padx=2, pady=2)
        self._border.pack(fill="both", expand=True, padx=10, pady=6)

        inner = tk.Frame(self._border, bg=DROP_IDLE, padx=16, pady=14)
        inner.pack(fill="both", expand=True)

        # icon
        tk.Label(inner, text="📄", font=("Segoe UI Emoji", 28),
                 bg=DROP_IDLE, fg=TEXT).pack()

        self._title = tk.Label(inner, text=label,
                               font=("Segoe UI", 11, "bold"),
                               bg=DROP_IDLE, fg=TEXT)
        self._title.pack(pady=(4, 2))

        self._hint = tk.Label(inner,
                              text="Drag & drop a PDF here\nor click Browse",
                              font=("Segoe UI", 9), bg=DROP_IDLE, fg=MUTED,
                              justify="center")
        self._hint.pack()

        self._name_lbl = tk.Label(inner, text="", font=("Segoe UI", 9, "italic"),
                                  bg=DROP_IDLE, fg=GREEN, wraplength=230,
                                  justify="center")
        self._name_lbl.pack(pady=(6, 0))

        btn = tk.Button(inner, text="  Browse…  ",
                        font=("Segoe UI", 9, "bold"),
                        bg=HIGHLIGHT, fg=TEXT, activebackground="#c73652",
                        activeforeground=TEXT, relief="flat", cursor="hand2",
                        command=self._browse, padx=10, pady=4)
        btn.pack(pady=(10, 0))

        # ── DnD registration ──────────────────────────────────────────────────
        for widget in (self._border, inner, self._title, self._hint,
                       self._name_lbl, btn):
            widget.drop_target_register(DND_FILES)
            widget.dnd_bind("<<DropEnter>>", self._on_enter)
            widget.dnd_bind("<<DropLeave>>", self._on_leave)
            widget.dnd_bind("<<Drop>>",      self._on_drop)

    # ── visual feedback ───────────────────────────────────────────────────────
    def _set_bg(self, color):
        for widget in self._border.winfo_children():
            try:
                widget.configure(bg=color)
            except Exception:
                pass
        self._border.configure(bg=color)

    def _on_enter(self, event):
        self._set_bg(DROP_HOVER)

    def _on_leave(self, event):
        self._set_bg(DROP_IDLE)

    def _on_drop(self, event):
        self._set_bg(DROP_IDLE)
        path = _clean_path(event.data)
        if path.lower().endswith(".pdf"):
            self._set_path(path)
        else:
            self._name_lbl.configure(text="⚠ Not a PDF file", fg=RED)

    def _browse(self):
        path = filedialog.askopenfilename(
            title="Select PDF",
            filetypes=[("PDF files", "*.pdf"), ("All files", "*.*")]
        )
        if path:
            self._set_path(path)

    def _set_path(self, path: str):
        import os
        self._path = path
        short = os.path.basename(path)
        self._name_lbl.configure(text=f"✔ {short}", fg=GREEN)
        self._on_file(path)

    @property
    def path(self) -> str:
        return self._path


# ─────────────────────────────────────────────────────────────────────────────
class App(TkinterDnD.Tk):

    def __init__(self):
        super().__init__()
        self.title("PDF Comparison Tool")
        self.geometry("900x700")
        self.minsize(820, 620)
        self.configure(bg=BG)

        # Set the window icon
        import sys
        import os
        if hasattr(sys, '_MEIPASS'):
            # PyInstaller extracting to temporary location
            icon_path = os.path.join(sys._MEIPASS, 'app_icon.ico')
        else:
            icon_path = os.path.abspath('app_icon.ico')
            
        if os.path.exists(icon_path):
            self.iconbitmap(icon_path)

        self._path_a = ""
        self._path_b = ""

        # last run — needed for PDF export
        self._last_diffs: list  = []
        self._last_pdf_a: str   = ""
        self._last_pdf_b: str   = ""
        self._last_mode:  str   = "data"

        self._build_ui()

    # ── UI construction ───────────────────────────────────────────────────────
    def _build_ui(self):
        # ── header ────────────────────────────────────────────────────────────
        hdr = tk.Frame(self, bg=ACCENT, pady=14)
        hdr.pack(fill="x")

        tk.Label(hdr, text="PDF  COMPARISON  TOOL",
                 font=("Segoe UI", 16, "bold"),
                 bg=ACCENT, fg=TEXT).pack()
        tk.Label(hdr, text="Drag & drop or browse to compare two PDFs",
                 font=("Segoe UI", 9), bg=ACCENT, fg=MUTED).pack()

        # ── drop zones ────────────────────────────────────────────────────────
        zones_frame = tk.Frame(self, bg=BG)
        zones_frame.pack(fill="x", padx=16, pady=(12, 4))
        zones_frame.columnconfigure(0, weight=1)
        zones_frame.columnconfigure(1, weight=1)

        self.zone_a = DropZone(zones_frame, "PDF  A  (Reference)",
                               lambda p: setattr(self, "_path_a", p))
        self.zone_a.grid(row=0, column=0, sticky="nsew", padx=(0, 6))

        self.zone_b = DropZone(zones_frame, "PDF  B  (Comparison)",
                               lambda p: setattr(self, "_path_b", p))
        self.zone_b.grid(row=0, column=1, sticky="nsew", padx=(6, 0))

        # ── options bar ───────────────────────────────────────────────────────
        opts = tk.Frame(self, bg=PANEL, pady=10, padx=16)
        opts.pack(fill="x", padx=16, pady=(4, 4))

        tk.Label(opts, text="Mode:", font=("Segoe UI", 10, "bold"),
                 bg=PANEL, fg=TEXT).pack(side="left", padx=(0, 8))

        self._mode = tk.StringVar(value="data")
        for val, lbl in [("data", "Data only"), ("full", "Full (incl. formatting)")]:
            tk.Radiobutton(opts, text=lbl, variable=self._mode, value=val,
                           font=("Segoe UI", 9), bg=PANEL, fg=TEXT,
                           selectcolor=ACCENT, activebackground=PANEL,
                           activeforeground=TEXT).pack(side="left", padx=6)

        tk.Label(opts, text="Export:", font=("Segoe UI", 10, "bold"),
                 bg=PANEL, fg=TEXT).pack(side="left", padx=(24, 8))

        self._export = tk.StringVar(value="none")
        for val, lbl in [("none", "None"), ("txt", "TXT"), ("json", "JSON"), ("both", "Both")]:
            tk.Radiobutton(opts, text=lbl, variable=self._export, value=val,
                           font=("Segoe UI", 9), bg=PANEL, fg=TEXT,
                           selectcolor=ACCENT, activebackground=PANEL,
                           activeforeground=TEXT).pack(side="left", padx=4)

        # ── compare button ────────────────────────────────────────────────────
        btn_frame = tk.Frame(self, bg=BG)
        btn_frame.pack(pady=6)

        self._compare_btn = tk.Button(
            btn_frame, text="  ▶   COMPARE  PDFs  ",
            font=("Segoe UI", 11, "bold"),
            bg=HIGHLIGHT, fg=TEXT,
            activebackground="#c73652", activeforeground=TEXT,
            relief="flat", cursor="hand2", padx=20, pady=8,
            command=self._run_comparison
        )
        self._compare_btn.pack()

        self._status_lbl = tk.Label(btn_frame, text="",
                                    font=("Segoe UI", 9),
                                    bg=BG, fg=MUTED)
        self._status_lbl.pack(pady=(4, 0))

        # ── results pane ──────────────────────────────────────────────────────
        res_frame = tk.Frame(self, bg=BG)
        res_frame.pack(fill="both", expand=True, padx=16, pady=(0, 12))

        header_row = tk.Frame(res_frame, bg=BG)
        header_row.pack(fill="x")
        tk.Label(header_row, text="RESULTS", font=("Segoe UI", 9, "bold"),
                 bg=BG, fg=MUTED).pack(side="left")

        clear_btn = tk.Button(header_row, text="Clear",
                              font=("Segoe UI", 8), bg=ACCENT, fg=MUTED,
                              activebackground=DROP_HOVER, relief="flat",
                              cursor="hand2", padx=6, pady=2,
                              command=self._clear_output)
        clear_btn.pack(side="right")

        self._pdf_export_btn = tk.Button(
            header_row,
            text="  📄  Export as PDF Report  ",
            font=("Segoe UI", 8, "bold"),
            bg="#2e7d32", fg=TEXT,
            activebackground="#1b5e20", activeforeground=TEXT,
            relief="flat", cursor="hand2", padx=8, pady=2,
            state="disabled",
            command=self._export_pdf
        )
        self._pdf_export_btn.pack(side="right", padx=(0, 6))

        self._annotate_export_btn = tk.Button(
            header_row,
            text="  🖍  Export Annotated PDFs  ",
            font=("Segoe UI", 8, "bold"),
            bg="#b71c1c", fg=TEXT,
            activebackground="#7f0000", activeforeground=TEXT,
            relief="flat", cursor="hand2", padx=8, pady=2,
            state="disabled",
            command=self._export_annotated_pdfs
        )
        self._annotate_export_btn.pack(side="right", padx=(0, 6))

        self._output = scrolledtext.ScrolledText(
            res_frame,
            font=MONO_FONT,
            bg="#0d0d1a", fg=TEXT,
            insertbackground=TEXT,
            relief="flat", bd=0,
            wrap="word",
            state="disabled"
        )
        self._output.pack(fill="both", expand=True, pady=(4, 0))

        # colour tags
        self._output.tag_configure("red",    foreground=RED)
        self._output.tag_configure("yellow", foreground=YELLOW)
        self._output.tag_configure("green",  foreground=GREEN)
        self._output.tag_configure("cyan",   foreground="#4fc3f7")
        self._output.tag_configure("bold",   font=("Consolas", 10, "bold"))
        self._output.tag_configure("muted",  foreground=MUTED)

    # ── helpers ───────────────────────────────────────────────────────────────
    def _clear_output(self):
        self._output.configure(state="normal")
        self._output.delete("1.0", "end")
        self._output.configure(state="disabled")

    def _append(self, text: str, *tags):
        self._output.configure(state="normal")
        self._output.insert("end", text, tags)
        self._output.see("end")
        self._output.configure(state="disabled")

    def _set_status(self, msg: str, color: str = MUTED):
        self._status_lbl.configure(text=msg, fg=color)

    # ── comparison runner ─────────────────────────────────────────────────────
    def _run_comparison(self):
        pdf_a = self._path_a or self.zone_a.path
        pdf_b = self._path_b or self.zone_b.path

        if not pdf_a:
            self._set_status("⚠  Please select PDF A first.", RED)
            return
        if not pdf_b:
            self._set_status("⚠  Please select PDF B first.", RED)
            return

        self._compare_btn.configure(state="disabled", text="  ⏳  Running…  ")
        self._set_status("Comparing…", YELLOW)
        self._clear_output()

        mode   = self._mode.get()
        export = self._export.get()
        if export == "none":
            export = None

        # run in background thread so UI stays responsive
        threading.Thread(
            target=self._do_compare,
            args=(pdf_a, pdf_b, mode, export),
            daemon=True
        ).start()

    def _do_compare(self, pdf_a, pdf_b, mode, export):
        try:
            self.after(0, self._append, "Extracting text from PDF A …\n", "cyan")
            lines_a = core.extract_text(pdf_a)

            self.after(0, self._append, "Extracting text from PDF B …\n", "cyan")
            lines_b = core.extract_text(pdf_b)

            self.after(0, self._append,
                       f"Aligning {len(lines_a)} / {len(lines_b)} lines …\n", "cyan")
            pairs = core.align_lines(lines_a, lines_b)

            self.after(0, self._append,
                       f"Running [{mode.upper()}] comparison …\n\n", "cyan")
            if mode == "data":
                diffs = core.compare_data(pairs)
            else:
                diffs = core.compare_full(pairs)

            # build and display report
            self.after(0, self._render_report, diffs, pdf_a, pdf_b, mode, export)

        except Exception as exc:
            self.after(0, self._append, f"\nERROR: {exc}\n", "red")
            self.after(0, self._set_status, "Error during comparison.", RED)
            self.after(0, self._reset_btn)

    def _export_pdf(self):
        """Export the last comparison result as a highlighted PDF."""
        import os
        from tkinter import filedialog, messagebox

        if not self._last_diffs and self._last_pdf_a:
            # no diffs but comparison was run — still export (shows clean result)
            pass
        elif not self._last_pdf_a:
            return

        include_annot = messagebox.askyesno(
            "Include Original PDFs?",
            "Do you want to append the highlighted original PDFs to the end of this report?"
        )

        save_path = filedialog.asksaveasfilename(
            title="Save Highlighted PDF Report",
            defaultextension=".pdf",
            filetypes=[("PDF files", "*.pdf")],
            initialfile=f"pdf_compare_highlighted_{self._last_mode}.pdf",
        )
        if not save_path:
            return

        self._pdf_export_btn.configure(state="disabled", text="  ⏳  Exporting…  ")
        self._set_status("Exporting highlighted PDF…", YELLOW)

        def _do_export():
            try:
                # 1. Generate ReportLab report
                out = exporter.export_pdf_report(
                    self._last_diffs,
                    self._last_pdf_a,
                    self._last_pdf_b,
                    self._last_mode,
                    output_path=save_path,
                )
                
                # 2. Append Annotations if requested
                if include_annot:
                    import fitz
                    temp_annot = "temp_annotated.pdf"
                    annotator.create_combined_annotated_pdf(
                        self._last_pdf_a, self._last_pdf_b, self._last_diffs, temp_annot
                    )
                    if os.path.exists(temp_annot):
                        doc_report = fitz.open(out)
                        doc_annot = fitz.open(temp_annot)
                        doc_report.insert_pdf(doc_annot)
                        # save to temporary memory then overwrite
                        combined_bytes = doc_report.write()
                        doc_report.close()
                        doc_annot.close()
                        
                        with open(out, "wb") as f:
                            f.write(combined_bytes)
                            
                        os.remove(temp_annot)

                self.after(0, self._append,
                           f"\n  ✔ Highlighted PDF saved → {out}\n", "green")
                self.after(0, self._set_status,
                           f"PDF exported: {os.path.basename(out)}", GREEN)
            except Exception as exc:
                self.after(0, self._append,
                           f"\n  ✘ PDF export failed: {exc}\n", "red")
                self.after(0, self._set_status, "PDF export failed.", RED)
            finally:
                self.after(0, self._pdf_export_btn.configure,
                           {"state": "normal", "text": "  📄  Export as PDF Report  "})

        threading.Thread(target=_do_export, daemon=True).start()

    def _export_annotated_pdfs(self):
        """Export a single combined PDF with both original PDFs boxed in rectangles."""
        from tkinter import filedialog
        import os

        if not self._last_diffs:
            return

        save_path = filedialog.asksaveasfilename(
            title="Save Combined Annotated PDF",
            defaultextension=".pdf",
            filetypes=[("PDF files", "*.pdf")],
            initialfile="Combined_Annotated_Differences.pdf",
        )
        if not save_path:
            return

        self._annotate_export_btn.configure(state="disabled", text="  ⏳  Annotating…  ")
        self._set_status("Creating combined annotated PDF…", YELLOW)

        def _do_annotate():
            try:
                # Combine both PDFs with rectangle box highlights
                out = annotator.create_combined_annotated_pdf(
                    self._last_pdf_a,
                    self._last_pdf_b,
                    self._last_diffs,
                    save_path
                )
                
                self.after(0, self._append,
                           f"\n  ✔ Combined Annotated PDF saved → {out}\n", "green")
                self.after(0, self._set_status,
                           "Combined annotated PDF saved successfully.", GREEN)
            except Exception as exc:
                self.after(0, self._append,
                           f"\n  ✘ Annotation export failed: {exc}\n", "red")
                self.after(0, self._set_status, "Annotation export failed.", RED)
            finally:
                self.after(0, self._annotate_export_btn.configure,
                           {"state": "normal", "text": "  🖍  Export Annotated PDFs  "})

        threading.Thread(target=_do_annotate, daemon=True).start()

    def _render_report(self, diffs, pdf_a, pdf_b, mode, export):
        import os
        from datetime import datetime

        hr = "─" * 60
        now = datetime.now().strftime("%Y-%m-%d %H:%M:%S")

        data_diffs   = [d for d in diffs if d["category"] == "DATA"]
        format_diffs = [d for d in diffs if d["category"] == "FORMAT"]

        self._append(hr + "\n",            "muted")
        self._append("  PDF COMPARISON REPORT\n", "bold")
        self._append(hr + "\n",            "muted")
        self._append(f"  Generated : {now}\n")
        self._append(f"  Mode      : {mode.upper()}\n")
        self._append(f"  PDF A     : {os.path.basename(pdf_a)}\n")
        self._append(f"  PDF B     : {os.path.basename(pdf_b)}\n")
        self._append(hr + "\n\n",          "muted")

        self._append("[SUMMARY]\n",        "bold")
        self._append(f"  Total Differences  : {len(diffs)}\n")
        self._append(f"  Data Differences   : {len(data_diffs)}\n",   "red")
        if mode == "full":
            self._append(f"  Format Differences : {len(format_diffs)}\n", "yellow")

        self._append("\n[DETAILS]\n", "bold")

        if not diffs:
            self._append("  ✔ No differences found.\n", "green")
        else:
            _TYPE_LABEL = {
                "DATA_MISMATCH": "DATA MISMATCH",
                "MISSING_IN_B":  "MISSING IN PDF-B",
                "EXTRA_IN_B":    "EXTRA IN PDF-B",
                "FORMAT_DIFF":   "FORMAT DIFFERENCE",
                "LABEL_DIFF":    "LABEL DIFFERENCE",
            }
            for i, d in enumerate(diffs, start=1):
                tag   = "red" if d["category"] == "DATA" else "yellow"
                label = _TYPE_LABEL.get(d["type"], d["type"])
                self._append(f"\n  [{i}] {label}\n",       (tag, "bold"))
                if d.get("line_a") is not None:
                    self._append(f"      PDF-A : {d['line_a']}\n", tag)
                if d.get("line_b") is not None:
                    self._append(f"      PDF-B : {d['line_b']}\n", tag)
                if "similarity" in d:
                    self._append(f"      Similarity : {d['similarity']}%\n", tag)

        self._append("\n" + hr + "\n", "muted")

        # store for PDF export button
        self._last_diffs = diffs
        self._last_pdf_a = pdf_a
        self._last_pdf_b = pdf_b
        self._last_mode  = mode
        self._pdf_export_btn.configure(state="normal")
        self._annotate_export_btn.configure(state="normal")

        # export
        if export:
            plain = core.generate_report.__doc__ and ""   # dummy
            # rebuild plain text via core helper (no ANSI)
            import io, contextlib
            buf = io.StringIO()
            with contextlib.redirect_stdout(buf):
                plain = "\n".join([
                    hr, "  PDF COMPARISON REPORT", hr,
                    f"  Generated : {now}", f"  Mode      : {mode.upper()}",
                    f"  PDF A     : {os.path.basename(pdf_a)}",
                    f"  PDF B     : {os.path.basename(pdf_b)}", hr, "",
                    f"  Total Differences  : {len(diffs)}",
                    f"  Data Differences   : {len(data_diffs)}",
                ])
            core.export_results(plain, diffs, pdf_a, pdf_b, mode, export)
            self._append(f"\n  Report exported ({export}).\n", "green")

        total = len(diffs)
        if total == 0:
            self._set_status("✔ No differences found.", GREEN)
        else:
            self._set_status(
                f"Done — {total} difference(s) found "
                f"({len(data_diffs)} data, {len(format_diffs)} format).",
                YELLOW if format_diffs else RED
            )

        self._reset_btn()

    def _reset_btn(self):
        self._compare_btn.configure(state="normal", text="  ▶   COMPARE  PDFs  ")


# ─────────────────────────────────────────────────────────────────────────────
if __name__ == "__main__":
    app = App()
    app.mainloop()
