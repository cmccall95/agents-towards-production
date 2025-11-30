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
BASE_DELAY = 0.06  # Base delay between requests (supports ~1000 req/min)
MAX_RETRIES = 5  # Maximum retry attempts for 429 errors
INITIAL_BACKOFF = 1.0  # Initial backoff delay in seconds


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


def is_rate_limit_error(error: Exception) -> bool:
    """Check if the error is a 429 rate limit error."""
    error_str = str(error).lower()
    return "429" in error_str or "rate limit" in error_str or "too many requests" in error_str


def extract_content_with_retry(url: str) -> dict:
    """
    Extract content from a single ASTM standard page using Tavily.
    Implements exponential backoff retry logic for 429 rate limit errors.
    """
    last_error = None

    for attempt in range(MAX_RETRIES):
        try:
            response = tavily_client.extract(urls=[url])

            if response and "results" in response and len(response["results"]) > 0:
                result = response["results"][0]
                raw_content = result.get("raw_content", "")
                title = result.get("title", "")

                if len(raw_content.strip()) < 100:
                    return {"success": False, "error": "Empty or insufficient content", "retries": attempt}

                return {
                    "success": True,
                    "url": url,
                    "title": title,
                    "raw_content": raw_content,
                    "retries": attempt
                }
            else:
                return {"success": False, "error": "No results from Tavily", "retries": attempt}

        except Exception as e:
            last_error = e

            # Check if it's a rate limit error
            if is_rate_limit_error(e):
                if attempt < MAX_RETRIES - 1:
                    # Calculate exponential backoff delay
                    backoff_delay = INITIAL_BACKOFF * (2 ** attempt)
                    print(f"         ⏳ Rate limited (429). Retry {attempt + 1}/{MAX_RETRIES} in {backoff_delay:.1f}s...")
                    time.sleep(backoff_delay)
                    continue
            else:
                # Non-rate-limit error, don't retry
                return {"success": False, "error": str(e), "retries": attempt}

    # All retries exhausted
    return {
        "success": False,
        "error": f"Rate limit exceeded after {MAX_RETRIES} retries: {str(last_error)}",
        "retries": MAX_RETRIES
    }


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


def get_completed_batches() -> set:
    """
    Scan the output directory for completed batch files and return a set of batch numbers.
    Batch files are named: batch_{batch_num:04d}_{timestamp}.json
    """
    completed = set()
    if JSON_DIR.exists():
        for file in JSON_DIR.glob("batch_*.json"):
            # Extract batch number from filename like "batch_0011_20251128_123456.json"
            match = re.match(r"batch_(\d{4})_", file.name)
            if match:
                batch_num = int(match.group(1))
                completed.add(batch_num)
    return completed


def get_next_batch_to_process(total_batches: int) -> int:
    """
    Determine the next batch to process based on completed batches.
    Returns the first batch number that hasn't been completed, or -1 if all done.
    """
    completed = get_completed_batches()
    for batch_num in range(total_batches):
        if batch_num not in completed:
            return batch_num
    return -1  # All batches completed


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

        # Extract content with retry logic
        extract_result = extract_content_with_retry(url)
        time.sleep(BASE_DELAY)  # Base rate limiting between requests

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
    parser.add_argument("--resume", action="store_true", help="Resume from next incomplete batch")
    parser.add_argument("--resume-through", type=int, metavar="N", help="Resume and process through batch N")
    parser.add_argument("--status", action="store_true", help="Show progress status and exit")
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

    # Get completed batches for status display
    completed_batches = get_completed_batches()
    next_batch = get_next_batch_to_process(total_batches)

    print(f"✅ Completed batches: {len(completed_batches)}/{total_batches}")
    if completed_batches:
        print(f"   Batches done: {sorted(completed_batches)}")
    if next_batch >= 0:
        print(f"➡️  Next batch to process: {next_batch} (standards {next_batch * BATCH_SIZE}-{min((next_batch + 1) * BATCH_SIZE, total_standards) - 1})")
    else:
        print("🎉 All batches completed!")

    # Status mode - just show progress and exit
    if args.status:
        return

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
        # All batches mode (skip already completed)
        batches_to_process = [
            (b, b * BATCH_SIZE, min((b + 1) * BATCH_SIZE, total_standards))
            for b in range(total_batches) if b not in completed_batches
        ]
        if not batches_to_process:
            print("\n✅ All batches already completed!")
            return
    elif args.resume:
        # Resume mode - process just the next incomplete batch
        if next_batch < 0:
            print("\n✅ All batches already completed!")
            return
        start_idx = next_batch * BATCH_SIZE
        end_idx = min(start_idx + BATCH_SIZE, total_standards)
        batches_to_process = [(next_batch, start_idx, end_idx)]
    elif args.resume_through is not None:
        # Resume through batch N - process all incomplete batches up to N
        if next_batch < 0:
            print("\n✅ All batches already completed!")
            return
        end_batch = min(args.resume_through, total_batches - 1)
        batches_to_process = [
            (b, b * BATCH_SIZE, min((b + 1) * BATCH_SIZE, total_standards))
            for b in range(next_batch, end_batch + 1) if b not in completed_batches
        ]
        if not batches_to_process:
            print(f"\n✅ All batches through {end_batch} already completed!")
            return
    else:
        # Default: show help and suggest resume
        print("\n⚠️  No arguments provided.")
        print("    Use --resume to continue from where you left off")
        print("    Use --resume-through N to process through batch N")
        print("    Use --batch N for a specific batch")
        print("    Use --status to see progress\n")
        return

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

