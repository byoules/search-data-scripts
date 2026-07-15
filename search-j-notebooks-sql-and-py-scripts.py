#!/usr/bin/env python3

import os
import json
import csv
from pathlib import Path
import tkinter as tk
from tkinter import filedialog, messagebox


IGNORE_DIRS = {
    ".git",
    ".venv",
    "venv",
    "__pycache__",
    ".ipynb_checkpoints",
}

SEARCHABLE_SUFFIXES = {".sql", ".py", ".ipynb"}


def choose_folder():
    folder = filedialog.askdirectory(title="Select folder to search")
    if folder:
        folder_var.set(folder)


def iter_files(root: Path):
    for dirpath, dirnames, filenames in os.walk(root):
        dirnames[:] = [
            directory
            for directory in dirnames
            if directory not in IGNORE_DIRS
        ]

        for filename in filenames:
            path = Path(dirpath) / filename

            if path.suffix.lower() in SEARCHABLE_SUFFIXES:
                yield path


def parse_needles(raw: str):
    needles = [term.strip() for term in raw.split(",") if term.strip()]

    # De-duplicate terms case-insensitively.
    seen = set()
    output = []

    for needle in needles:
        key = needle.lower()

        if key not in seen:
            seen.add(key)
            output.append(needle)

    return output


def trim(text_value: str, length: int = 250):
    text_value = text_value.rstrip("\n")

    if len(text_value) > length:
        return text_value[:length] + "…"

    return text_value


def search_text_file(path: Path, needles, file_kind: str):
    """
    Search a normal line-based text file, such as .sql or .py.
    """
    results = []

    try:
        with path.open(
            "r",
            encoding="utf-8-sig",
            errors="replace",
        ) as file:
            for line_no, line in enumerate(file, start=1):
                haystack = line.lower()

                for needle in needles:
                    normalized_needle = needle.lower()
                    start = 0

                    while True:
                        index = haystack.find(normalized_needle, start)

                        if index == -1:
                            break

                        results.append(
                            (
                                str(path),
                                file_kind,
                                needle,
                                f"line {line_no}",
                                index,
                                trim(line),
                            )
                        )

                        start = index + max(1, len(normalized_needle))

    except Exception as error:
        results.append(
            (
                str(path),
                file_kind,
                "(n/a)",
                "(read error)",
                -1,
                f"ERROR: {error}",
            )
        )

    return results


def cell_lines(cell):
    source = cell.get("source", [])

    if isinstance(source, list):
        return "".join(source).splitlines()

    if isinstance(source, str):
        return source.splitlines()

    return []


def search_ipynb(path: Path, needles):
    results = []

    try:
        notebook = json.loads(
            path.read_text(
                encoding="utf-8",
                errors="replace",
            )
        )

        for cell_index, cell in enumerate(notebook.get("cells", [])):
            cell_type = cell.get("cell_type", "unknown")

            for line_index, line in enumerate(cell_lines(cell), start=1):
                haystack = line.lower()

                for needle in needles:
                    normalized_needle = needle.lower()
                    start = 0

                    while True:
                        index = haystack.find(normalized_needle, start)

                        if index == -1:
                            break

                        location = (
                            f"cell {cell_index} "
                            f"({cell_type}), line {line_index}"
                        )

                        results.append(
                            (
                                str(path),
                                "ipynb",
                                needle,
                                location,
                                index,
                                trim(line),
                            )
                        )

                        start = index + max(1, len(normalized_needle))

    except Exception as error:
        results.append(
            (
                str(path),
                "ipynb",
                "(n/a)",
                "(read/parse error)",
                -1,
                f"ERROR: {error}",
            )
        )

    return results


def run_search():
    folder = folder_var.get().strip()
    raw_terms = terms_var.get().strip()

    if not folder:
        messagebox.showerror(
            "Missing folder",
            "Select a folder first.",
        )
        return

    needles = parse_needles(raw_terms)

    if not needles:
        messagebox.showerror(
            "Missing search terms",
            "Enter at least one search term (comma-separated).",
        )
        return

    root = Path(folder)

    if not root.exists() or not root.is_dir():
        messagebox.showerror(
            "Invalid folder",
            "The selected folder does not exist or is not a directory.",
        )
        return

    text.delete("1.0", tk.END)
    text.insert(tk.END, f"Folder: {root}\n")
    text.insert(
        tk.END,
        "File types: .sql, .py, .ipynb\n",
    )
    text.insert(
        tk.END,
        f"Search terms (case-insensitive): {', '.join(needles)}\n\n",
    )

    scanned = 0
    matches = []

    for path in iter_files(root):
        scanned += 1
        suffix = path.suffix.lower()

        if suffix == ".ipynb":
            matches.extend(search_ipynb(path, needles))

        elif suffix == ".sql":
            matches.extend(
                search_text_file(
                    path,
                    needles,
                    file_kind="sql",
                )
            )

        elif suffix == ".py":
            matches.extend(
                search_text_file(
                    path,
                    needles,
                    file_kind="python",
                )
            )

    # Write CSV.
    output_csv = root / "search_results.csv"

    try:
        with output_csv.open(
            "w",
            newline="",
            encoding="utf-8-sig",
        ) as file:
            writer = csv.writer(file)

            writer.writerow(
                [
                    "file_path",
                    "file_kind",
                    "needle",
                    "location",
                    "start_index",
                    "line_preview",
                ]
            )

            writer.writerows(matches)

    except Exception as error:
        messagebox.showerror(
            "CSV write error",
            f"Could not write the results CSV:\n\n{error}",
        )
        return

    # Display results.
    text.insert(tk.END, f"Scanned files: {scanned}\n")
    text.insert(tk.END, f"Matches found: {len(matches)}\n")
    text.insert(tk.END, f"CSV written: {output_csv}\n\n")

    if not matches:
        text.insert(tk.END, "No matches were found.\n")
    else:
        for file_path, kind, needle, location, index, preview in matches:
            text.insert(tk.END, f"{file_path}\n")
            text.insert(
                tk.END,
                (
                    f"  [{kind}] {needle!r} @ {location} "
                    f"(idx {index}): {preview}\n\n"
                ),
            )

    messagebox.showinfo(
        "Search complete",
        (
            f"Scanned {scanned} files.\n"
            f"Found {len(matches)} matches.\n\n"
            f"Results saved to:\n{output_csv}"
        ),
    )


def make_gui():
    global folder_var, terms_var, text

    window = tk.Tk()
    window.title(
        "Search .sql, .py, and .ipynb files "
        "(case-insensitive)"
    )
    window.geometry("900x550")

    folder_var = tk.StringVar()
    terms_var = tk.StringVar()

    top_frame = tk.Frame(window)
    top_frame.pack(
        fill="x",
        padx=10,
        pady=10,
    )

    tk.Button(
        top_frame,
        text="Choose Folder…",
        command=choose_folder,
    ).pack(side="left")

    tk.Entry(
        top_frame,
        textvariable=folder_var,
    ).pack(
        side="left",
        fill="x",
        expand=True,
        padx=8,
    )

    middle_frame = tk.Frame(window)
    middle_frame.pack(
        fill="x",
        padx=10,
        pady=(0, 10),
    )

    tk.Label(
        middle_frame,
        text="Search terms (comma-separated):",
    ).pack(side="left")

    terms_entry = tk.Entry(
        middle_frame,
        textvariable=terms_var,
    )
    terms_entry.pack(
        side="left",
        fill="x",
        expand=True,
        padx=8,
    )

    tk.Button(
        middle_frame,
        text="Search",
        command=run_search,
        height=1,
    ).pack(side="left")

    text = tk.Text(
        window,
        wrap="none",
    )
    text.pack(
        fill="both",
        expand=True,
        padx=10,
        pady=(0, 10),
    )

    # Pressing Enter while in the search-term field runs the search.
    terms_entry.bind(
        "<Return>",
        lambda event: run_search(),
    )

    return window


if __name__ == "__main__":
    app = make_gui()
    app.mainloop()