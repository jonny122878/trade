#!/usr/bin/env python3
"""Compare two Excel files and export detailed diff reports.

Usage:
  python tools/compare_excel.py --a old.xlsx --b new.xlsx
  python tools/compare_excel.py --a old.xlsx --b new.xlsx --sheets Sheet1 Sheet2 --ignore-space

Output:
  - summary.txt
  - differences.csv

The script compares sheet existence and each cell value.
"""

from __future__ import annotations

import argparse
import csv
import datetime as dt
import math
from decimal import Decimal, InvalidOperation
from pathlib import Path
from typing import Iterable
from difflib import SequenceMatcher

from openpyxl import load_workbook


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Compare two Excel files (.xlsx/.xlsm) and output differences.")
    parser.add_argument("--a", required=True, help="Path to the first Excel file or folder")
    parser.add_argument("--b", required=False, help="Path to the second Excel file (for file-vs-file mode)")
    parser.add_argument(
        "--compare-mode",
        choices=["file-vs-file", "file-vs-folder", "folder-vs-folder"],
        default="file-vs-file",
        help="Comparison mode: file-vs-file (two Excel files), file-vs-folder (Excel file vs folder), or folder-vs-folder (two folders)"
    )
    parser.add_argument("--folder-b", required=False, help="Path to folder containing Excel files (for file-vs-folder or folder-vs-folder mode)")
    parser.add_argument(
        "--sheets",
        nargs="*",
        default=None,
        help="Optional list of sheet names to compare. If omitted, compares all common sheets.",
    )
    parser.add_argument(
        "--ignore-space",
        action="store_true",
        help="Trim leading/trailing spaces before comparison.",
    )
    parser.add_argument(
        "--report-dir",
        default=None,
        help="Directory for report output. Default: ./excel_compare_report_YYYYmmdd_HHMMSS",
    )
    return parser.parse_args()


def normalize_value(value: object, ignore_space: bool) -> str:
    if value is None:
        return ""

    if isinstance(value, bool):
        return "TRUE" if value else "FALSE"

    if isinstance(value, (dt.datetime, dt.date, dt.time)):
        return value.isoformat(sep=" ") if isinstance(value, dt.datetime) else value.isoformat()

    if isinstance(value, (int, float, Decimal)):
        if isinstance(value, float):
            if math.isnan(value):
                return "NaN"
            if math.isinf(value):
                return "Infinity" if value > 0 else "-Infinity"
        try:
            normalized = Decimal(str(value)).normalize()
            text = format(normalized, "f")
            if "." in text:
                text = text.rstrip("0").rstrip(".")
            return text
        except (InvalidOperation, ValueError):
            pass

    text = str(value)
    return text.strip() if ignore_space else text


def sheet_sequence(sheet_names_a: list[str], sheet_names_b: list[str], requested: Iterable[str] | None) -> tuple[list[str], list[str]]:
    set_a = set(sheet_names_a)
    set_b = set(sheet_names_b)

    only_a = sorted(set_a - set_b)
    only_b = sorted(set_b - set_a)

    if requested:
        common = [name for name in requested if name in set_a and name in set_b]
    else:
        common = [name for name in sheet_names_a if name in set_b]

    return only_a + only_b, common


def _normalize_for_match(name: str) -> str:
    """Strip common prefixes/suffixes before fuzzy matching.

    - Sheet names often have a leading numeric prefix like ``01_`` or ``02_``.
    - File names often have a leading year-month prefix like ``115年05月``.
    Both are stripped so the meaningful keyword is compared directly.
    """
    import re
    name = re.sub(r"^\d+_", "", name)          # e.g. "02_中彰投苗月票" → "中彰投苗月票"
    name = re.sub(r"^\d{2,3}年\d{1,2}月", "", name)  # e.g. "115年05月台中月票" → "台中月票"
    return name


def fuzzy_match(sheet_name: str, names: list[str], threshold: float = 0.2, is_filename: bool = True) -> str | None:
    """Fuzzy match sheet name to file name or sheet name using sequence matching.
    
    Args:
        sheet_name: The name to match (e.g., sheet name in A)
        names: List of names to match against (e.g., sheet names in B or file names)
        threshold: Similarity threshold (default 0.2 for loose matching)
        is_filename: If True, strip file extensions before matching. If False, match as-is.
    
    Returns:
        Best matched name or None if no match found above threshold
    """
    best_match = None
    best_ratio = threshold
    norm_sheet = _normalize_for_match(sheet_name)

    for name in names:
        # Remove .xlsx/.xls extension if it's a filename
        if is_filename:
            name_base = Path(name).stem
        else:
            name_base = name
        
        norm_name = _normalize_for_match(name_base)
        ratio = SequenceMatcher(None, norm_sheet, norm_name).ratio()
        if ratio > best_ratio:
            best_ratio = ratio
            best_match = name

    return best_match


def get_excel_files(folder_path: Path) -> list[Path]:
    """Get all Excel files (.xlsx, .xls) from a folder."""
    excel_files = []
    for ext in ["*.xlsx", "*.xls"]:
        excel_files.extend(folder_path.glob(ext))
    return sorted(excel_files)


def ensure_report_dir(report_dir_arg: str | None) -> Path:
    if report_dir_arg:
        report_dir = Path(report_dir_arg)
    else:
        stamp = dt.datetime.now().strftime("%Y%m%d_%H%M%S")
        report_dir = Path(f"excel_compare_report_{stamp}")
    report_dir.mkdir(parents=True, exist_ok=True)
    return report_dir


def compare_workbooks(file_a: Path, file_b: Path, sheets: list[str] | None, ignore_space: bool) -> tuple[list[dict[str, object]], list[str], list[tuple[str, str]]]:
    wb_a = load_workbook(filename=file_a, data_only=True)
    wb_b = load_workbook(filename=file_b, data_only=True)

    diffs: list[dict[str, object]] = []
    notes: list[str] = []
    sheet_mappings: list[tuple[str, str]] = []  # (sheet_a, sheet_b) mappings

    # Strategy: For each sheet in A, find corresponding sheet in B
    # 1. Try exact name match
    # 2. If B has only 1 sheet, use it regardless of name
    # 3. Otherwise try fuzzy match
    
    compare_sheets = sheets if sheets else wb_a.sheetnames
    
    for sheet_a in compare_sheets:
        if sheet_a not in wb_a.sheetnames:
            notes.append(f"Sheet not found in A: {sheet_a}")
            continue
        
        # Try exact match first
        if sheet_a in wb_b.sheetnames:
            sheet_b = sheet_a
        # If B has only 1 sheet, use it
        elif len(wb_b.sheetnames) == 1:
            sheet_b = wb_b.sheetnames[0]
            if sheet_a != sheet_b:
                notes.append(f"Sheet mapping: {sheet_a} (A) → {sheet_b} (B, only sheet in B)")
        # Try fuzzy match for multi-sheet file B
        else:
            matched = fuzzy_match(sheet_a, wb_b.sheetnames, threshold=0.2, is_filename=False)
            if matched:
                sheet_b = matched
                notes.append(f"Sheet fuzzy match: {sheet_a} (A) → {sheet_b} (B)")
            else:
                notes.append(f"No matching sheet found for: {sheet_a}")
                continue
        
        sheet_mappings.append((sheet_a, sheet_b))
        
        # Compare cells
        ws_a = wb_a[sheet_a]
        ws_b = wb_b[sheet_b]
        
        max_row = max(ws_a.max_row, ws_b.max_row)
        max_col = max(ws_a.max_column, ws_b.max_column)
        
        for row_idx in range(1, max_row + 1):
            for col_idx in range(1, max_col + 1):
                a_val = normalize_value(ws_a.cell(row=row_idx, column=col_idx).value, ignore_space)
                b_val = normalize_value(ws_b.cell(row=row_idx, column=col_idx).value, ignore_space)
                if a_val != b_val:
                    diffs.append(
                        {
                            "sheet": sheet_a,
                            "sheet_b": sheet_b if sheet_a != sheet_b else None,
                            "row": row_idx,
                            "column": col_idx,
                            "cell": ws_a.cell(row=row_idx, column=col_idx).coordinate,
                            "value_a": a_val,
                            "value_b": b_val,
                        }
                    )

    return diffs, notes, sheet_mappings


def compare_file_vs_folder(file_a: Path, folder_b: Path, ignore_space: bool) -> tuple[list[dict[str, object]], list[str], list[tuple[str, str]]]:
    """Compare multi-sheet Excel file (A) against folder of Excel files (B)."""
    wb_a = load_workbook(filename=file_a, data_only=True)
    sheet_names_a = wb_a.sheetnames
    
    # Get all Excel files in folder
    excel_files_b = get_excel_files(folder_b)
    file_names_b = [f.name for f in excel_files_b]
    
    diffs: list[dict[str, object]] = []
    notes: list[str] = []
    matches: list[tuple[str, str]] = []  # (sheet_name, matched_file)
    
    if not excel_files_b:
        notes.append(f"No Excel files found in folder: {folder_b}")
        return diffs, notes, matches
    
    # Fuzzy match sheets to files
    for sheet_name in sheet_names_a:
        matched_file = fuzzy_match(sheet_name, file_names_b)
        
        if matched_file:
            matches.append((sheet_name, matched_file))
            file_path_b = folder_b / matched_file
            
            try:
                wb_b = load_workbook(filename=file_path_b, data_only=True)
                # Compare first sheet of file B with sheet A
                ws_a = wb_a[sheet_name]
                ws_b = wb_b.active
                
                max_row = max(ws_a.max_row, ws_b.max_row)
                max_col = max(ws_a.max_column, ws_b.max_column)
                
                for row_idx in range(1, max_row + 1):
                    for col_idx in range(1, max_col + 1):
                        a_val = normalize_value(ws_a.cell(row=row_idx, column=col_idx).value, ignore_space)
                        b_val = normalize_value(ws_b.cell(row=row_idx, column=col_idx).value, ignore_space)
                        if a_val != b_val:
                            diffs.append(
                                {
                                    "sheet": sheet_name,
                                    "file_b": matched_file,
                                    "row": row_idx,
                                    "column": col_idx,
                                    "cell": ws_a.cell(row=row_idx, column=col_idx).coordinate,
                                    "value_a": a_val,
                                    "value_b": b_val,
                                }
                            )
            except Exception as e:
                notes.append(f"Error comparing {sheet_name} with {matched_file}: {e}")
        else:
            notes.append(f"No matching file found for sheet: {sheet_name}")
    
    # Check for unmatched files
    matched_files = {m[1] for m in matches}
    unmatched_files = set(file_names_b) - matched_files
    if unmatched_files:
        notes.append("Unmatched files in folder:")
        for file_name in sorted(unmatched_files):
            notes.append(f"- {file_name}")
    
    return diffs, notes, matches


def compare_folder_vs_folder(folder_a: Path, folder_b: Path, ignore_space: bool) -> tuple[list[dict[str, object]], list[str], list[tuple[str, str, str]]]:
    """Compare two folders with Excel files (A) and (B).
    
    Fuzzy match files by name, compare first sheet of each matched pair.
    Returns: (diffs, notes, matches)
    matches: list of (file_a, file_b, match_status) tuples
    """
    excel_files_a = get_excel_files(folder_a)
    excel_files_b = get_excel_files(folder_b)
    
    file_names_a = [f.name for f in excel_files_a]
    file_names_b = [f.name for f in excel_files_b]
    
    diffs: list[dict[str, object]] = []
    notes: list[str] = []
    matches: list[tuple[str, str, str]] = []  # (file_a, file_b, status)
    
    if not file_names_a:
        notes.append(f"No Excel files found in folder A: {folder_a}")
    if not file_names_b:
        notes.append(f"No Excel files found in folder B: {folder_b}")
    
    if not file_names_a or not file_names_b:
        return diffs, notes, matches
    
    # Fuzzy match files from A to files in B
    matched_b = set()
    for file_a in file_names_a:
        matched_file_b = fuzzy_match(file_a, file_names_b, is_filename=True)
        
        if matched_file_b:
            matched_b.add(matched_file_b)
            matches.append((file_a, matched_file_b, "matched"))
            
            file_path_a = folder_a / file_a
            file_path_b = folder_b / matched_file_b
            
            try:
                wb_a = load_workbook(filename=file_path_a, data_only=True)
                wb_b = load_workbook(filename=file_path_b, data_only=True)
                
                # Compare first (active) sheet
                ws_a = wb_a.active
                ws_b = wb_b.active
                
                max_row = max(ws_a.max_row, ws_b.max_row)
                max_col = max(ws_a.max_column, ws_b.max_column)
                
                for row_idx in range(1, max_row + 1):
                    for col_idx in range(1, max_col + 1):
                        a_val = normalize_value(ws_a.cell(row=row_idx, column=col_idx).value, ignore_space)
                        b_val = normalize_value(ws_b.cell(row=row_idx, column=col_idx).value, ignore_space)
                        if a_val != b_val:
                            diffs.append(
                                {
                                    "file_a": file_a,
                                    "file_b": matched_file_b,
                                    "row": row_idx,
                                    "column": col_idx,
                                    "cell": ws_a.cell(row=row_idx, column=col_idx).coordinate,
                                    "value_a": a_val,
                                    "value_b": b_val,
                                }
                            )
            except Exception as e:
                notes.append(f"Error comparing {file_a} with {matched_file_b}: {e}")
        else:
            matches.append((file_a, "", "unmatched"))
            notes.append(f"No matching file found for: {file_a}")
    
    # Check for unmatched files in B
    for file_b in file_names_b:
        if file_b not in matched_b:
            matches.append(("", file_b, "unmatched_b"))
            notes.append(f"Unmatched file in folder B: {file_b}")
    
    return diffs, notes, matches


def write_report(report_dir: Path, file_a: Path, file_b: Path, diffs: list[dict[str, object]], notes: list[str], sheet_mappings: list[tuple[str, str]]) -> None:
    summary_path = report_dir / "summary.txt"
    diff_csv_path = report_dir / "differences.csv"

    with summary_path.open("w", encoding="utf-8") as f:
        f.write("Excel Compare Summary\n")
        f.write("=====================\n")
        f.write(f"File A: {file_a}\n")
        f.write(f"File B: {file_b}\n")
        if sheet_mappings:
            f.write(f"Compared sheets: {len(sheet_mappings)}\n")
            f.write("Sheet mappings:\n")
            for sheet_a, sheet_b in sheet_mappings:
                if sheet_a == sheet_b:
                    f.write(f"  {sheet_a}\n")
                else:
                    f.write(f"  {sheet_a} (A) → {sheet_b} (B)\n")
            f.write("\n")
        f.write(f"Total differences: {len(diffs)}\n\n")
        if notes:
            f.write("Notes:\n")
            for line in notes:
                f.write(f"{line}\n")

    # Determine fieldnames based on whether sheet mapping differs
    has_different_sheets = any(sheet_a != sheet_b for sheet_a, sheet_b in sheet_mappings)
    
    # Prepare diff rows: remove sheet_b key if all sheets have same name
    if has_different_sheets:
        fieldnames = ["sheet", "sheet_b", "row", "column", "cell", "value_a", "value_b"]
        diff_rows = diffs
    else:
        fieldnames = ["sheet", "row", "column", "cell", "value_a", "value_b"]
        # Remove sheet_b from rows
        diff_rows = [{k: v for k, v in row.items() if k != "sheet_b"} for row in diffs]
    
    with diff_csv_path.open("w", newline="", encoding="utf-8-sig") as f:
        writer = csv.DictWriter(f, fieldnames=fieldnames)
        writer.writeheader()
        writer.writerows(diff_rows)


def write_report_file_vs_folder(report_dir: Path, file_a: Path, folder_b: Path, diffs: list[dict[str, object]], notes: list[str], matches: list[tuple[str, str]]) -> None:
    summary_path = report_dir / "summary.txt"
    diff_csv_path = report_dir / "differences.csv"

    with summary_path.open("w", encoding="utf-8") as f:
        f.write("Excel Compare Summary (File vs Folder)\n")
        f.write("======================================\n")
        f.write(f"File A: {file_a}\n")
        f.write(f"Folder B: {folder_b}\n")
        f.write(f"Total sheets compared: {len(matches)}\n")
        f.write(f"Total differences: {len(diffs)}\n\n")
        
        if matches:
            f.write("Sheet-to-File Mappings:\n")
            for sheet_name, file_name in matches:
                f.write(f"  {sheet_name} -> {file_name}\n")
            f.write("\n")
        
        if notes:
            f.write("Notes:\n")
            for line in notes:
                f.write(f"{line}\n")

    with diff_csv_path.open("w", newline="", encoding="utf-8-sig") as f:
        fieldnames = ["sheet", "file_b", "row", "column", "cell", "value_a", "value_b"]
        writer = csv.DictWriter(f, fieldnames=fieldnames)
        writer.writeheader()
        writer.writerows(diffs)


def write_report_folder_vs_folder(report_dir: Path, folder_a: Path, folder_b: Path, diffs: list[dict[str, object]], notes: list[str], matches: list[tuple[str, str, str]]) -> None:
    summary_path = report_dir / "summary.txt"
    diff_csv_path = report_dir / "differences.csv"

    with summary_path.open("w", encoding="utf-8") as f:
        f.write("Excel Compare Summary (Folder vs Folder)\n")
        f.write("=========================================\n")
        f.write(f"Folder A: {folder_a}\n")
        f.write(f"Folder B: {folder_b}\n")
        
        matched_count = sum(1 for m in matches if m[2] == "matched")
        f.write(f"Total files compared: {matched_count}\n")
        f.write(f"Total differences: {len(diffs)}\n\n")
        
        if matches:
            f.write("File Mappings:\n")
            for file_a, file_b, status in matches:
                if status == "matched":
                    f.write(f"  {file_a} <-> {file_b}\n")
                elif status == "unmatched":
                    f.write(f"  {file_a} (NO MATCH in folder B)\n")
                elif status == "unmatched_b":
                    f.write(f"  {file_b} (ONLY in folder B)\n")
            f.write("\n")
        
        if notes:
            f.write("Notes:\n")
            for line in notes:
                f.write(f"{line}\n")

    with diff_csv_path.open("w", newline="", encoding="utf-8-sig") as f:
        fieldnames = ["file_a", "file_b", "row", "column", "cell", "value_a", "value_b"]
        writer = csv.DictWriter(f, fieldnames=fieldnames)
        writer.writeheader()
        writer.writerows(diffs)


def main() -> int:
    args = parse_args()

    path_a = Path(args.a)

    report_dir = ensure_report_dir(args.report_dir)

    # File-vs-File mode
    if args.compare_mode == "file-vs-file":
        if not args.b:
            print("[ERROR] --b is required for file-vs-file mode")
            return 1
        
        if not path_a.exists():
            print(f"[ERROR] File A not found: {path_a}")
            return 1
        
        if not path_a.is_file():
            print(f"[ERROR] A must be a file for file-vs-file mode: {path_a}")
            return 1
        
        file_b = Path(args.b)
        if not file_b.exists():
            print(f"[ERROR] File B not found: {file_b}")
            return 1
        
        if not file_b.is_file():
            print(f"[ERROR] B must be a file for file-vs-file mode: {file_b}")
            return 1

        diffs, notes, sheet_mappings = compare_workbooks(path_a, file_b, args.sheets, args.ignore_space)

        write_report(report_dir, path_a, file_b, diffs, notes, sheet_mappings)

        print(f"Report directory: {report_dir.resolve()}")
        print(f"Differences: {len(diffs)}")
        print("Result: IDENTICAL" if len(diffs) == 0 and not notes else "Result: DIFFERENT")

        return 0 if len(diffs) == 0 and not notes else 2

    # File-vs-Folder mode
    elif args.compare_mode == "file-vs-folder":
        if not args.folder_b:
            print("[ERROR] --folder-b is required for file-vs-folder mode")
            return 1
        
        if not path_a.exists():
            print(f"[ERROR] File A not found: {path_a}")
            return 1
        
        if not path_a.is_file():
            print(f"[ERROR] A must be a file for file-vs-folder mode: {path_a}")
            return 1
        
        folder_b = Path(args.folder_b)
        if not folder_b.is_dir():
            print(f"[ERROR] Folder B not found or is not a directory: {folder_b}")
            return 1

        diffs, notes, matches = compare_file_vs_folder(path_a, folder_b, args.ignore_space)

        write_report_file_vs_folder(report_dir, path_a, folder_b, diffs, notes, matches)

        print(f"Report directory: {report_dir.resolve()}")
        print(f"Sheets compared: {len(matches)}")
        print(f"Differences: {len(diffs)}")
        print("Result: IDENTICAL" if len(diffs) == 0 and not notes else "Result: DIFFERENT")

        return 0 if len(diffs) == 0 and not notes else 2
    
    # Folder-vs-Folder mode
    elif args.compare_mode == "folder-vs-folder":
        if not args.folder_b:
            print("[ERROR] --folder-b is required for folder-vs-folder mode")
            return 1
        
        if not path_a.exists():
            print(f"[ERROR] Folder A not found: {path_a}")
            return 1
        
        if not path_a.is_dir():
            print(f"[ERROR] A must be a folder for folder-vs-folder mode: {path_a}")
            return 1
        
        folder_b = Path(args.folder_b)
        if not folder_b.is_dir():
            print(f"[ERROR] Folder B not found or is not a directory: {folder_b}")
            return 1

        diffs, notes, matches = compare_folder_vs_folder(path_a, folder_b, args.ignore_space)

        write_report_folder_vs_folder(report_dir, path_a, folder_b, diffs, notes, matches)

        print(f"Report directory: {report_dir.resolve()}")
        matched_count = sum(1 for m in matches if m[2] == "matched")
        print(f"Files compared: {matched_count}")
        print(f"Differences: {len(diffs)}")
        print("Result: IDENTICAL" if len(diffs) == 0 and not notes else "Result: DIFFERENT")

        return 0 if len(diffs) == 0 and not notes else 2
    
    else:
        print(f"[ERROR] Unknown compare mode: {args.compare_mode}")
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
