"""
Fetch ASTM standards from store.astm.org using the official standards list.

Reads the complete list from astm_standards_list.json and:
1. Constructs URLs from the code field (lowercase)
2. Extracts content using Tavily extract()
3. Saves JSON results and Markdown files
4. Logs any failures for later review

Usage:
    python fetch_astm_standards.py                    # Process all in batches of 200
    python fetch_astm_standards.py --batch 0          # Process first batch (0-199)
    python fetch_astm_standards.py --batch 5          # Process batch 5 (1000-1199)
    python fetch_astm_standards.py --start 500 --end 700  # Process standards 500-699
"""

import argparse
import json
import os
import re
import time
from datetime import datetime
from pathlib import Path

from dotenv import load_dotenv
from tavily import TavilyClient

load_dotenv()
tavily_client = TavilyClient(api_key=os.getenv("TAVILY_API_KEY"))

# Paths
INPUT_JSON = Path(__file__).parent / "output/astm_lists/astm_standards_list.json"
OUTPUT_DIR = Path(__file__).parent / "output/astm_lists/full_summary"
JSON_DIR = OUTPUT_DIR / "json"
MD_DIR = OUTPUT_DIR / "json" / "md"

# Ensure output directories exist
JSON_DIR.mkdir(parents=True, exist_ok=True)
MD_DIR.mkdir(parents=True, exist_ok=True)

# Processing configuration
BATCH_SIZE = 200
RATE_LIMIT_DELAY = 0.5  # seconds between requests


def code_to_url(code: str) -> str:
    """
    Convert ASTM code to store.astm.org URL.
    
    Examples:
    - "A0105_A0105M-23" → "https://store.astm.org/a0105_a0105m-23.html"
    - "A0001-00R18" → "https://store.astm.org/a0001-00r18.html"
    - "G0170-06R20E01" → "https://store.astm.org/g0170-06r20e01.html"
    """
    return f"https://store.astm.org/{code.lower()}.html"


def parse_designation(code: str) -> str:
    """Parse ASTM designation from code for display purposes."""
    # Pattern: prefix + number + optional underscore variant + hyphen + year
    match = re.match(r"([A-Z]+)0*(\d+)(?:_([A-Z]+)0*(\d+[A-Z]?))?-(\d+[A-Z0-9]*)", code, re.I)
    if match:
        groups = match.groups()
        p1, n1, p2, n2, year = groups
        if p2 and n2:
            return f"{p1.upper()}{n1}/{p2.upper()}{n2}-{year}"
        return f"{p1.upper()}{n1}-{year}"
    return code.upper()


def extract_content(url: str) -> dict:
    """Extract content from a single ASTM standard page using Tavily."""
    try:
        response = tavily_client.extract(urls=[url])
        
        if response and "results" in response and len(response["results"]) > 0:
            result = response["results"][0]
            raw_content = result.get("raw_content", "")
            title = result.get("title", "")
            
            if len(raw_content.strip()) < 100:
                return {"success": False, "error": "Empty or insufficient content"}
            
            return {
                "success": True,
                "url": url,
                "title": title,
                "raw_content": raw_content,
            }
        else:
            return {"success": False, "error": "No results from Tavily"}
            
    except Exception as e:
        return {"success": False, "error": str(e)}


def save_markdown(code: str, designation: str, title: str, content: str, url: str) -> Path:
    """Save content as a Markdown file."""
    md_path = MD_DIR / f"{code.lower()}.md"
    
    header = f"<!-- Source: {url} -->\n\n"
    header += f"# {designation}\n\n"
    if title:
        header += f"**{title}**\n\n---\n\n"
    
    with open(md_path, "w", encoding="utf-8") as f:
        f.write(header + content)
    
    return md_path


def load_standards_list() -> list:
    """Load the official ASTM standards list."""
    with open(INPUT_JSON, "r", encoding="utf-8") as f:
        data = json.load(f)
    return data.get("standards", [])


def process_batch(standards: list, start_idx: int, end_idx: int, batch_num: int) -> tuple:
    """Process a batch of standards and return results and errors."""
    batch = standards[start_idx:end_idx]
    total_in_batch = len(batch)

    print(f"\n{'=' * 60}")
    print(f"📦 BATCH {batch_num}: Standards {start_idx} to {end_idx - 1}")
    print(f"{'=' * 60}")

    results = []
    errors = []

    for i, standard in enumerate(batch, 1):
        code = standard["code"]
        designation = standard["designation"]
        url = code_to_url(code)
        global_idx = start_idx + i

        print(f"[{i}/{total_in_batch}] (#{global_idx}) {code}")

        # Extract content
        extract_result = extract_content(url)
        time.sleep(RATE_LIMIT_DELAY)  # Rate limiting

        if extract_result["success"]:
            # Save markdown
            md_path = save_markdown(
                code,
                parse_designation(code),
                extract_result.get("title", ""),
                extract_result.get("raw_content", ""),
                url
            )

            results.append({
                "code": code,
                "designation": designation,
                "url": url,
                "title": extract_result.get("title", ""),
                "content_length": len(extract_result.get("raw_content", "")),
                "markdown_file": str(md_path.relative_to(OUTPUT_DIR)),
                "success": True
            })
            print(f"         ✓ Saved: {md_path.name}")
        else:
            error_entry = {
                "code": code,
                "designation": designation,
                "url": url,
                "error": extract_result["error"],
                "success": False
            }
            errors.append(error_entry)
            results.append(error_entry)
            print(f"         ✗ Error: {extract_result['error']}")

    return results, errors


def save_batch_results(results: list, errors: list, batch_num: int, start_idx: int, end_idx: int):
    """Save batch results to JSON files."""
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")

    summary = {
        "generated_at": datetime.now().isoformat(),
        "batch_number": batch_num,
        "range": f"{start_idx}-{end_idx - 1}",
        "total_processed": len(results),
        "successful": len([r for r in results if r.get("success")]),
        "failed": len(errors),
        "results": results
    }

    json_path = JSON_DIR / f"batch_{batch_num:04d}_{timestamp}.json"
    with open(json_path, "w", encoding="utf-8") as f:
        json.dump(summary, f, indent=2)

    # Save error log for this batch if there are errors
    if errors:
        error_log_path = JSON_DIR / f"errors_batch_{batch_num:04d}_{timestamp}.json"
        with open(error_log_path, "w", encoding="utf-8") as f:
            json.dump({
                "batch_number": batch_num,
                "range": f"{start_idx}-{end_idx - 1}",
                "errors": errors,
                "generated_at": datetime.now().isoformat()
            }, f, indent=2)
        print(f"❌ Error log: {error_log_path.name}")

    return json_path, summary


def main():
    parser = argparse.ArgumentParser(description="Fetch ASTM standards in batches")
    parser.add_argument("--batch", type=int, help="Process specific batch number (0-indexed)")
    parser.add_argument("--start", type=int, help="Start index (inclusive)")
    parser.add_argument("--end", type=int, help="End index (exclusive)")
    parser.add_argument("--all", action="store_true", help="Process all standards in batches")
    args = parser.parse_args()

    print("=" * 60)
    print("🔍 ASTM Standards URL Generator & Fetcher (Batch Mode)")
    print("=" * 60)

    # Load standards
    standards = load_standards_list()
    total_standards = len(standards)
    total_batches = (total_standards + BATCH_SIZE - 1) // BATCH_SIZE

    print(f"📋 Loaded {total_standards} standards")
    print(f"📦 Batch size: {BATCH_SIZE}")
    print(f"📦 Total batches: {total_batches}")

    # Determine what to process
    if args.batch is not None:
        # Single batch mode
        start_idx = args.batch * BATCH_SIZE
        end_idx = min(start_idx + BATCH_SIZE, total_standards)
        batches_to_process = [(args.batch, start_idx, end_idx)]
    elif args.start is not None and args.end is not None:
        # Custom range mode
        start_idx = args.start
        end_idx = min(args.end, total_standards)
        batch_num = start_idx // BATCH_SIZE
        batches_to_process = [(batch_num, start_idx, end_idx)]
    elif args.all:
        # All batches mode
        batches_to_process = [
            (b, b * BATCH_SIZE, min((b + 1) * BATCH_SIZE, total_standards))
            for b in range(total_batches)
        ]
    else:
        # Default: first batch only
        print("\n⚠️  No arguments provided. Processing first batch only.")
        print("    Use --all to process all standards, or --batch N for a specific batch.\n")
        batches_to_process = [(0, 0, min(BATCH_SIZE, total_standards))]

    # Process batches
    all_results = []
    all_errors = []

    for batch_num, start_idx, end_idx in batches_to_process:
        results, errors = process_batch(standards, start_idx, end_idx, batch_num)
        json_path, summary = save_batch_results(results, errors, batch_num, start_idx, end_idx)

        all_results.extend(results)
        all_errors.extend(errors)

        # Batch summary
        print(f"\n📊 Batch {batch_num} Summary:")
        print(f"  ✓ Successful: {summary['successful']}/{summary['total_processed']}")
        print(f"  ✗ Failed: {summary['failed']}/{summary['total_processed']}")
        print(f"  💾 Saved: {json_path.name}")

    # Overall summary
    if len(batches_to_process) > 1:
        print(f"\n{'=' * 60}")
        print("📊 OVERALL SUMMARY")
        print(f"{'=' * 60}")
        print(f"  📦 Batches processed: {len(batches_to_process)}")
        print(f"  ✓ Total successful: {len([r for r in all_results if r.get('success')])}")
        print(f"  ✗ Total failed: {len(all_errors)}")
        print(f"  💾 Markdown files: {MD_DIR}/")


if __name__ == "__main__":
    main()

