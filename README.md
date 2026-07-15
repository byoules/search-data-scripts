# SQL, Python, and Jupyter Notebook Search Tool

**Owner:** Brad Youles
**Status:** Active  
**Last reviewed:** 2026-07-15  

## Purpose

This desktop application searches SQL files, Python files, and Jupyter notebooks for one or more case-insensitive terms. It recursively scans a selected folder, displays matching lines in the application, and exports all results to a CSV file.

## Supported File Types

The application searches:

- SQL files (`.sql`)
- Python files (`.py`)
- Jupyter notebooks (`.ipynb`)

For Jupyter notebooks, the application searches both code cells and Markdown cells.

## Requirements

- Python 3.8 or newer
- Tkinter

Tkinter is included with most standard Windows Python installations. No third-party Python packages are required.

## Run The Application

Open PowerShell or Command Prompt in the folder containing the script.

Run:

```powershell
python search-app.py
```

If the `python` command is not available, run:

```powershell
py search-app.py
```

Replace `search-app.py` with the actual script name if it differs.

## Use The Application

1. Select **Choose Folder**.
2. Select the top-level folder to search.
3. Enter one or more comma-separated search terms.
4. Select **Search** or press Enter while the search-term field is active.
5. Review the matches displayed in the application.
6. Open `search_results.csv` in the selected folder for the complete exported results.

Example search terms:

```text
employee_id, release_version, lab_id
```

Searches are case-insensitive. For example, searching for `employee_id` also finds `EMPLOYEE_ID`, `Employee_ID`, and `employee_id`.

## Search Behavior

The application recursively scans all supported files under the selected folder.

Each search term is evaluated separately. If the same term occurs more than once on a line, each occurrence is recorded as a separate match.

For SQL and Python files, the location is reported as a source-file line number:

```text
line 42
```

For Jupyter notebooks, the location includes the cell number, cell type, and line within the cell:

```text
cell 7 (code), line 4
```

The search includes matches in:

- Source code
- Comments
- String values
- SQL statements
- Jupyter code cells
- Jupyter Markdown cells

The application performs literal text matching. It does not currently support regular expressions or syntax-aware searching.

## Output

The application writes the results to:

```text
search_results.csv
```

The file is saved in the top-level folder selected for the search. A new search overwrites the existing file.

The output includes:

| Column | Description |
|---|---|
| `file_path` | Full path to the matching file |
| `file_kind` | File type: `sql`, `python`, or `ipynb` |
| `needle` | Search term that matched |
| `location` | Source line or notebook cell location |
| `start_index` | Zero-based character position where the match begins |
| `line_preview` | Preview of the matching line |

The CSV uses UTF-8 encoding with a byte-order mark so it opens correctly in Microsoft Excel.

## Ignored Directories

The application does not search these directories:

```text
.git
.venv
venv
__pycache__
.ipynb_checkpoints
```

The ignored directories are defined in the script:

```python
IGNORE_DIRS = {
    ".git",
    ".venv",
    "venv",
    "__pycache__",
    ".ipynb_checkpoints",
}
```

Add additional directory names to this set when needed.

## Searchable Extensions

The supported extensions are defined in the script:

```python
SEARCHABLE_SUFFIXES = {".sql", ".py", ".ipynb"}
```

Additional text-based file types may be added to this set, but the search-routing logic must also send those files to the appropriate search function.

## Search-Term Rules

Enter multiple terms as a comma-separated list:

```text
release_version, employee number, final_cluster
```

The application:

- Removes leading and trailing spaces
- Ignores blank entries
- Removes duplicate terms case-insensitively
- Treats commas as separators

The current version cannot search for a literal phrase that contains a comma.

## Error Handling

The application displays an error message when:

- No folder is selected
- The selected path is invalid
- No search terms are entered
- The results CSV cannot be written

If an individual file cannot be read or a notebook cannot be parsed, the application records the error in the results and continues scanning the remaining files.
