#!/usr/bin/env python3

import csv
import json
import os
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

SEARCHABLE_SUFFIXES = {
    ".sql",
    ".py",
    ".ipynb",
}

RESULTS_FILENAME = "search_results.csv"
ERRORS_FILENAME = "search_errors.csv"


def choose_folder():
    """Open a folder-selection dialog."""
    folder = filedialog.askdirectory(title="Select folder to search")

    if folder:
        folder_var.set(folder)


def windows_long_path(path: Path) -> str:
    """
    Convert a path to Windows extended-length format.

    Examples:
        N:\\folder\\file.py
            becomes
        \\\\?\\N:\\folder\\file.py

        \\\\server\\share\\folder
            becomes
        \\\\?\\UNC\\server\\share\\folder
    """
    path_string = os.path.abspath(os.fspath(path))

    if os.name != "nt":
        return path_string

    if path_string.startswith("\\\\?\\"):
        return path_string

    if path_string.startswith("\\\\"):
        return "\\\\?\\UNC\\" + path_string[2:]

    return "\\\\?\\" + path_string


def is_linked_directory(entry: os.DirEntry) -> bool:
    """
    Determine whether a directory entry is a symbolic link, junction,
    or another Windows reparse-point directory.

    Such directories are skipped because they can redirect back to an
    ancestor and create infinitely repeated paths.
    """
    try:
        if entry.is_symlink():
            return True

        # Python versions that expose DirEntry.is_junction().
        junction_check = getattr(entry, "is_junction", None)

        if callable(junction_check) and junction_check():
            return True

        # Fallback for Windows versions of Python without is_junction().
        if os.name == "nt":
            stat_result = entry.stat(follow_symlinks=False)
            file_attributes = getattr(stat_result, "st_file_attributes", 0)

            # Windows FILE_ATTRIBUTE_REPARSE_POINT.
            if file_attributes & 0x400:
                return True

    except OSError:
        # If the entry cannot be inspected reliably, do not recurse into it.
        return True

    return False


def iter_files(root: Path, scan_errors: list):
    """
    Recursively yield supported files from all normal subfolders.

    Directory links and junctions are not followed. This prevents recursive
    paths such as:

        folder\\backup\\folder\\backup\\folder\\backup
    """
    folders_to_scan = [root]

    while folders_to_scan:
        current_folder = folders_to_scan.pop()

        try:
            current_folder_for_open = windows_long_path(current_folder)

            with os.scandir(current_folder_for_open) as entries:
                child_folders = []

                for entry in entries:
                    display_path = current_folder / entry.name

                    try:
                        if entry.is_dir(follow_symlinks=False):
                            if entry.name in IGNORE_DIRS:
                                continue

                            if is_linked_directory(entry):
                                scan_errors.append(
                                    (
                                        str(display_path),
                                        "linked directory skipped",
                                        (
                                            "Directory is a symbolic link, "
                                            "junction, or reparse point."
                                        ),
                                    )
                                )
                                continue

                            child_folders.append(display_path)

                        elif entry.is_file(follow_symlinks=False):
                            if display_path.suffix.lower() in SEARCHABLE_SUFFIXES:
                                yield display_path

                    except OSError as error:
                        scan_errors.append(
                            (
                                str(display_path),
                                "entry inspection error",
                                str(error),
                            )
                        )

                # Reverse to preserve a folder order similar to os.walk().
                folders_to_scan.extend(reversed(child_folders))

        except OSError as error:
            scan_errors.append(
                (
                    str(current_folder),
                    "folder scan error",
                    str(error),
                )
            )


def parse_needles(raw: str):
    """
    Convert comma-separated text into a de-duplicated list of search terms.
    """
    entered_terms = [
        term.strip()
        for term in raw.split(",")
        if term.strip()
    ]

    seen = set()
    needles = []

    for term in entered_terms:
        normalized = term.casefold()

        if normalized not in seen:
            seen.add(normalized)
            needles.append(term)

    return needles


def trim(value: str, maximum_length: int = 250):
    """Limit a displayed line preview to a manageable length."""
    value = value.rstrip("\r\n")

    if len(value) > maximum_length:
        return value[:maximum_length] + "…"

    return value


def find_matches_in_line(
    path: Path,
    file_kind: str,
    location: str,
    line: str,
    needles: list,
):
    """Find all occurrences of every search term within one line."""
    results = []
    haystack = line.casefold()

    for needle in needles:
        normalized_needle = needle.casefold()
        start_position = 0

        while True:
            match_index = haystack.find(
                normalized_needle,
                start_position,
            )

            if match_index == -1:
                break

            results.append(
                (
                    str(path),
                    file_kind,
                    needle,
                    location,
                    match_index,
                    trim(line),
                )
            )

            start_position = match_index + max(
                1,
                len(normalized_needle),
            )

    return results


def search_text_file(
    path: Path,
    needles: list,
    file_kind: str,
    scan_errors: list,
):
    """
    Search a normal line-based text file.

    This function is used for SQL and Python files.
    """
    results = []

    try:
        with open(
            windows_long_path(path),
            "r",
            encoding="utf-8-sig",
            errors="replace",
        ) as file:
            for line_number, line in enumerate(file, start=1):
                results.extend(
                    find_matches_in_line(
                        path=path,
                        file_kind=file_kind,
                        location=f"line {line_number}",
                        line=line,
                        needles=needles,
                    )
                )

    except OSError as error:
        scan_errors.append(
            (
                str(path),
                "file read error",
                str(error),
            )
        )

    except Exception as error:
        scan_errors.append(
            (
                str(path),
                "unexpected file error",
                repr(error),
            )
        )

    return results


def cell_lines(cell: dict):
    """Return the source of a notebook cell as individual lines."""
    source = cell.get("source", [])

    if isinstance(source, list):
        return "".join(source).splitlines()

    if isinstance(source, str):
        return source.splitlines()

    return []


def search_ipynb(
    path: Path,
    needles: list,
    scan_errors: list,
):
    """Search code and Markdown cells in a Jupyter notebook."""
    results = []

    try:
        with open(
            windows_long_path(path),
            "r",
            encoding="utf-8",
            errors="replace",
        ) as file:
            notebook = json.load(file)

        for cell_index, cell in enumerate(
            notebook.get("cells", [])
        ):
            cell_type = cell.get("cell_type", "unknown")

            for line_number, line in enumerate(
                cell_lines(cell),
                start=1,
            ):
                location = (
                    f"cell {cell_index} "
                    f"({cell_type}), line {line_number}"
                )

                results.extend(
                    find_matches_in_line(
                        path=path,
                        file_kind="ipynb",
                        location=location,
                        line=line,
                        needles=needles,
                    )
                )

    except json.JSONDecodeError as error:
        scan_errors.append(
            (
                str(path),
                "notebook parse error",
                str(error),
            )
        )

    except OSError as error:
        scan_errors.append(
            (
                str(path),
                "notebook read error",
                str(error),
            )
        )

    except Exception as error:
        scan_errors.append(
            (
                str(path),
                "unexpected notebook error",
                repr(error),
            )
        )

    return results


def write_results_csv(output_path: Path, matches: list):
    """Write successful search matches to CSV."""
    with open(
        windows_long_path(output_path),
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


def write_errors_csv(output_path: Path, scan_errors: list):
    """Write skipped paths and read problems to a separate CSV."""
    with open(
        windows_long_path(output_path),
        "w",
        newline="",
        encoding="utf-8-sig",
    ) as file:
        writer = csv.writer(file)

        writer.writerow(
            [
                "path",
                "error_type",
                "error_message",
            ]
        )

        writer.writerows(scan_errors)


def run_search():
    """Validate the form, search files, and write the output files."""
    folder = folder_var.get().strip()
    raw_terms = terms_var.get().strip()

    if not folder:
        messagebox.showerror(
            "Missing folder",
            "Select a folder first.",
        )
        return

    root = Path(folder)

    if not root.exists():
        messagebox.showerror(
            "Folder not found",
            f"The selected folder does not exist:\n\n{root}",
        )
        return

    if not root.is_dir():
        messagebox.showerror(
            "Invalid folder",
            f"The selected path is not a folder:\n\n{root}",
        )
        return

    needles = parse_needles(raw_terms)

    if not needles:
        messagebox.showerror(
            "Missing search terms",
            (
                "Enter at least one search term.\n\n"
                "Separate multiple terms with commas."
            ),
        )
        return

    search_button.config(state="disabled")
    choose_button.config(state="disabled")
    window.config(cursor="wait")
    window.update_idletasks()

    text.delete("1.0", tk.END)

    text.insert(tk.END, f"Folder: {root}\n")
    text.insert(
        tk.END,
        "File types: .sql, .py, .ipynb\n",
    )
    text.insert(
        tk.END,
        (
            "Search terms (case-insensitive): "
            f"{', '.join(needles)}\n\n"
        ),
    )
    text.insert(tk.END, "Searching...\n")
    text.see(tk.END)
    window.update_idletasks()

    scanned = 0
    matches = []
    scan_errors = []

    try:
        for path in iter_files(root, scan_errors):
            scanned += 1
            suffix = path.suffix.lower()

            if suffix == ".ipynb":
                matches.extend(
                    search_ipynb(
                        path=path,
                        needles=needles,
                        scan_errors=scan_errors,
                    )
                )

            elif suffix == ".sql":
                matches.extend(
                    search_text_file(
                        path=path,
                        needles=needles,
                        file_kind="sql",
                        scan_errors=scan_errors,
                    )
                )

            elif suffix == ".py":
                matches.extend(
                    search_text_file(
                        path=path,
                        needles=needles,
                        file_kind="python",
                        scan_errors=scan_errors,
                    )
                )

            if scanned % 100 == 0:
                text.delete("end-2l", "end-1l")
                text.insert(
                    tk.END,
                    (
                        f"Searching... {scanned:,} files scanned, "
                        f"{len(matches):,} matches found.\n"
                    ),
                )
                text.see(tk.END)
                window.update_idletasks()

        results_csv = root / RESULTS_FILENAME
        errors_csv = root / ERRORS_FILENAME

        write_results_csv(results_csv, matches)
        write_errors_csv(errors_csv, scan_errors)

        text.delete("1.0", tk.END)

        text.insert(tk.END, f"Folder: {root}\n")
        text.insert(
            tk.END,
            "File types: .sql, .py, .ipynb\n",
        )
        text.insert(
            tk.END,
            (
                "Search terms (case-insensitive): "
                f"{', '.join(needles)}\n\n"
            ),
        )

        text.insert(
            tk.END,
            f"Scanned files: {scanned:,}\n",
        )
        text.insert(
            tk.END,
            f"Matches found: {len(matches):,}\n",
        )
        text.insert(
            tk.END,
            f"Skipped paths or errors: {len(scan_errors):,}\n",
        )
        text.insert(
            tk.END,
            f"Results CSV: {results_csv}\n",
        )
        text.insert(
            tk.END,
            f"Errors CSV: {errors_csv}\n\n",
        )

        if matches:
            for (
                file_path,
                file_kind,
                needle,
                location,
                index,
                preview,
            ) in matches:
                text.insert(
                    tk.END,
                    f"{file_path}\n",
                )
                text.insert(
                    tk.END,
                    (
                        f"  [{file_kind}] {needle!r} "
                        f"@ {location} "
                        f"(index {index}): {preview}\n\n"
                    ),
                )

        else:
            text.insert(
                tk.END,
                "No matching text was found.\n",
            )

        text.see("1.0")

        completion_message = (
            f"Scanned {scanned:,} files.\n"
            f"Found {len(matches):,} matches.\n"
            f"Recorded {len(scan_errors):,} skipped paths "
            f"or errors.\n\n"
            f"Results:\n{results_csv}\n\n"
            f"Errors:\n{errors_csv}"
        )

        messagebox.showinfo(
            "Search complete",
            completion_message,
        )

    except Exception as error:
        messagebox.showerror(
            "Search failed",
            (
                "The search stopped because of an unexpected error:\n\n"
                f"{error}"
            ),
        )

    finally:
        search_button.config(state="normal")
        choose_button.config(state="normal")
        window.config(cursor="")


def make_gui():
    """Create and return the Tkinter application window."""
    global window
    global folder_var
    global terms_var
    global text
    global search_button
    global choose_button

    window = tk.Tk()
    window.title(
        "Search SQL, Python, and Jupyter Notebook Files"
    )
    window.geometry("1050x650")
    window.minsize(750, 450)

    folder_var = tk.StringVar()
    terms_var = tk.StringVar()

    folder_frame = tk.Frame(window)
    folder_frame.pack(
        fill="x",
        padx=10,
        pady=(10, 5),
    )

    choose_button = tk.Button(
        folder_frame,
        text="Choose Folder…",
        command=choose_folder,
    )
    choose_button.pack(side="left")

    folder_entry = tk.Entry(
        folder_frame,
        textvariable=folder_var,
    )
    folder_entry.pack(
        side="left",
        fill="x",
        expand=True,
        padx=(8, 0),
    )

    terms_frame = tk.Frame(window)
    terms_frame.pack(
        fill="x",
        padx=10,
        pady=(5, 10),
    )

    terms_label = tk.Label(
        terms_frame,
        text="Search terms (comma-separated):",
    )
    terms_label.pack(side="left")

    terms_entry = tk.Entry(
        terms_frame,
        textvariable=terms_var,
    )
    terms_entry.pack(
        side="left",
        fill="x",
        expand=True,
        padx=8,
    )

    search_button = tk.Button(
        terms_frame,
        text="Search",
        command=run_search,
    )
    search_button.pack(side="left")

    results_frame = tk.Frame(window)
    results_frame.pack(
        fill="both",
        expand=True,
        padx=10,
        pady=(0, 10),
    )

    vertical_scrollbar = tk.Scrollbar(
        results_frame,
        orient="vertical",
    )
    vertical_scrollbar.pack(
        side="right",
        fill="y",
    )

    horizontal_scrollbar = tk.Scrollbar(
        results_frame,
        orient="horizontal",
    )
    horizontal_scrollbar.pack(
        side="bottom",
        fill="x",
    )

    text = tk.Text(
        results_frame,
        wrap="none",
        yscrollcommand=vertical_scrollbar.set,
        xscrollcommand=horizontal_scrollbar.set,
    )
    text.pack(
        side="left",
        fill="both",
        expand=True,
    )

    vertical_scrollbar.config(command=text.yview)
    horizontal_scrollbar.config(command=text.xview)

    terms_entry.bind(
        "<Return>",
        lambda event: run_search(),
    )

    folder_entry.bind(
        "<Return>",
        lambda event: terms_entry.focus_set(),
    )

    terms_entry.focus_set()

    return window


if __name__ == "__main__":
    app = make_gui()
    app.mainloop()
