"""
Parse pnumbers.com raw content and extract structured records.

This script parses the extracted content from pnumbers.com and converts
the text-based table into structured JSON data.

Usage:
    python parse_pnumbers_sample.py [--limit N] [--all] [--workers N]
"""

import argparse
import json
import re
from concurrent.futures import ProcessPoolExecutor, as_completed
from datetime import datetime
from multiprocessing import cpu_count
from pathlib import Path

# Find the most recent raw content file
OUTPUT_DIR = Path(__file__).parent / "output"


def find_latest_raw_content() -> Path:
    """Find the most recent pnumbers raw content file."""
    files = list(OUTPUT_DIR.glob("pnumbers_raw_content_*.txt"))
    if not files:
        raise FileNotFoundError("No pnumbers raw content files found in output/")
    return max(files, key=lambda f: f.stat().st_mtime)


def parse_record(line: str) -> dict | None:
    """
    Parse a single line of pnumbers data into a structured record.

    Example lines:
    - "1 1 11.1 A/SA-36......58 (400)Plate, Bar, Shape..."
    - "1 1 1.1 A/SA-53 E, A K02504 48 (330)Resistance Welded Pipe..."
    - "8 1 8.1 A/SA-182 F304 S30400 70 (485)Forging> 5 (125)"
    - "45...45 A/SFA-5.9 ER320 N08021 80 (550)Weld Metal..."  (missing group)
    - "34...34 B/SB-359...C71520 52 (360)Smls. Tube..."  (... as separator)
    """
    line = line.strip()
    if not line or line.startswith('#') or line.startswith('P#'):
        return None

    # Pattern to match the data structure
    # P# G# ISO Spec Type UNS ksi(MPa) ProductForm Thickness

    # Handle both space-separated and ...-separated headers
    # Pattern 1: "1 1 11.1 ..." (normal)
    # Pattern 2: "45...45 ..." (missing group, ... as separator)
    # Pattern 3: "34...34 ..." (P#...ISO without group)

    # Try normal pattern first: P# G# ISO
    header_match = re.match(r'^(\d+[A-Z]?)\s+(\d+)\s+([\d.]+)\s+', line)
    if header_match:
        p_number = header_match.group(1)
        group_number = header_match.group(2)
        iso_group = header_match.group(3)
        remainder = line[header_match.end():]
    else:
        # Try pattern with ... separator: P#...ISO or P#...G#
        dots_match = re.match(r'^(\d+[A-Z]?)\.{2,}([\d.]+)\s+', line)
        if dots_match:
            p_number = dots_match.group(1)
            group_number = None  # Missing
            iso_group = dots_match.group(2)
            remainder = line[dots_match.end():]
        else:
            return None

    # Extract tensile strength pattern: digits (digits) or digits(digits)
    tensile_match = re.search(r'(\d+)\s*\((\d+)\)', remainder)
    if not tensile_match:
        return None

    tensile_ksi = tensile_match.group(1)
    tensile_mpa = tensile_match.group(2)

    # Split at tensile - before is spec/type/uns, after is product form/thickness
    before_tensile = remainder[:tensile_match.start()].strip()
    after_tensile = remainder[tensile_match.end():].strip()

    # Parse before_tensile: Spec Type UNS
    # UNS codes start with letter followed by digits (K, S, N, G, etc.)
    uns_match = re.search(r'\b([KSNGJRCW]\d{5})\b', before_tensile)
    uns_code = uns_match.group(1) if uns_match else None

    if uns_code:
        before_uns = before_tensile[:uns_match.start()].strip()
    else:
        before_uns = before_tensile.rstrip('.')

    # Spec and Type are space-separated in before_uns
    # Spec is usually first token (A/SA-xxx, SB-xxx, etc.)
    spec_parts = before_uns.split()
    if spec_parts:
        spec = spec_parts[0].rstrip('.')  # Clean trailing dots
        type_grade = ' '.join(spec_parts[1:]).strip('.') if len(spec_parts) > 1 else None
        # Clean type_grade of leading/trailing dots
        if type_grade:
            type_grade = type_grade.strip('.')
    else:
        spec = None
        type_grade = None

    # Parse after_tensile: Product Form and Thickness
    # Thickness patterns: "> 5 (125)", "≤ 5 (125)", "≤ 2 (50)", etc.
    thickness_match = re.search(r'([>≤<≥]\s*\d+\.?\d*\s*\(\d+\.?\d*\))$', after_tensile)
    if thickness_match:
        thickness = thickness_match.group(1)
        product_form = after_tensile[:thickness_match.start()].strip().rstrip('.')
    else:
        thickness = None
        product_form = after_tensile.strip().rstrip('.')

    # Clean up product form (remove trailing ...)
    product_form = product_form.rstrip('.') if product_form else None

    return {
        "p_number": p_number,
        "group_number": group_number,
        "iso_group": iso_group,
        "spec": spec,
        "type_grade": type_grade if type_grade else None,
        "uns_code": uns_code,
        "tensile_ksi": int(tensile_ksi),
        "tensile_mpa": int(tensile_mpa),
        "product_form": product_form if product_form else None,
        "thickness": thickness,
        "raw_line": line
    }


def parse_line_with_index(args: tuple) -> tuple:
    """Parse a single line with its index - for multiprocessing."""
    idx, line = args
    record = parse_record(line)
    if record:
        record['_idx'] = idx  # Track original order
        return ('success', idx, record)
    else:
        return ('error', idx, line)


def main():
    parser = argparse.ArgumentParser(description="Parse pnumbers.com data")
    parser.add_argument("--limit", type=int, default=10, help="Number of records to parse")
    parser.add_argument("--start", type=int, default=0, help="Starting record index (0-based)")
    parser.add_argument("--all", action="store_true", help="Parse all records")
    parser.add_argument("--workers", type=int, default=None, help="Number of worker processes")
    args = parser.parse_args()

    num_workers = args.workers or cpu_count()

    print("="*60)
    print("🔬 PNUMBERS.COM DATA PARSER (MULTIPROCESSING)")
    print("="*60)
    print(f"⚡ Workers: {num_workers} CPU cores")

    # Find and load raw content
    raw_file = find_latest_raw_content()
    print(f"📂 Loading: {raw_file.name}")

    with open(raw_file, 'r', encoding='utf-8') as f:
        content = f.read()

    # Split into lines and skip header
    lines = content.split('\n')
    data_lines = [l for l in lines if l.strip() and not l.startswith(('Source:', 'Timestamp:', '===', 'P Numbers', '[![', '[P Numbers]', 'reset', 'P#G#', 'Powered'))]

    print(f"📊 Total data lines: {len(data_lines)}")

    start = args.start
    if args.all:
        end = len(data_lines)
    else:
        end = min(start + args.limit, len(data_lines))

    lines_to_parse = data_lines[start:end]
    total_lines = len(lines_to_parse)
    print(f"🎯 Parsing {total_lines} records with {num_workers} workers...\n")

    records = []
    errors = []

    # Prepare work items with indices
    work_items = [(i + start, line) for i, line in enumerate(lines_to_parse)]

    # Process with multiprocessing
    completed = 0
    with ProcessPoolExecutor(max_workers=num_workers) as executor:
        futures = {executor.submit(parse_line_with_index, item): item for item in work_items}

        for future in as_completed(futures):
            result = future.result()
            status, idx, data = result

            if status == 'success':
                records.append(data)
            else:
                errors.append({"line_num": idx + 1, "line": data})

            completed += 1
            if completed % 500 == 0 or completed == total_lines:
                pct = (completed / total_lines) * 100
                print(f"   Progress: {completed}/{total_lines} ({pct:.1f}%) - ✓{len(records)} ✗{len(errors)}")

    # Sort records by original index to maintain order
    records.sort(key=lambda r: r.get('_idx', 0))
    # Remove the temporary index
    for r in records:
        r.pop('_idx', None)

    # Save results
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    output = {
        "timestamp": timestamp,
        "source_file": raw_file.name,
        "records_parsed": len(records),
        "errors": len(errors),
        "records": records
    }

    output_file = OUTPUT_DIR / f"pnumbers_parsed_{timestamp}.json"
    with open(output_file, 'w', encoding='utf-8') as f:
        json.dump(output, f, indent=2)

    print(f"\n{'='*60}")
    print(f"📊 RESULTS")
    print(f"{'='*60}")
    print(f"✓ Records parsed: {len(records)}")
    print(f"✗ Parse errors: {len(errors)}")
    print(f"💾 Saved to: {output_file.name}")

    # Show sample record
    if records:
        print(f"\n📋 Sample Record:")
        print(json.dumps(records[0], indent=2))

    return records, errors


if __name__ == "__main__":
    main()

