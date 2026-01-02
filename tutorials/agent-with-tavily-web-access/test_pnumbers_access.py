"""
Test script to verify web scraping access to https://www.pnumbers.com/

This site contains material standards tables that could reduce manual research workload.
The script tests:
1. Basic site accessibility via Tavily extract()
2. Table data extraction and parsing
3. Rate limiting and access restrictions detection
4. Sample data extraction to verify structure
5. Direct HTTP access as fallback

Usage:
    python test_pnumbers_access.py

Based on patterns from fetch_astm_standards.py and astm_scraper.py
"""

import json
import os
import re
import time
from datetime import datetime
from pathlib import Path

from dotenv import load_dotenv
from tavily import TavilyClient

# Try to import requests for fallback testing
try:
    import requests
    REQUESTS_AVAILABLE = True
except ImportError:
    REQUESTS_AVAILABLE = False
    print("Note: 'requests' library not available for fallback testing")

# Load environment variables
load_dotenv()

# Validate API key
if not os.environ.get("TAVILY_API_KEY"):
    raise ValueError("TAVILY_API_KEY not found in environment variables")

# Initialize Tavily client
tavily_client = TavilyClient(api_key=os.getenv("TAVILY_API_KEY"))

# Configuration - try both http and https
TARGET_URLS = [
    "https://www.pnumbers.com/",
    "http://www.pnumbers.com/",
    "https://pnumbers.com/",
    "http://pnumbers.com/",
]
TARGET_DOMAIN = "pnumbers.com"
OUTPUT_DIR = Path(__file__).parent / "output"
MAX_RETRIES = 3
INITIAL_BACKOFF = 1.0


def is_rate_limit_error(error: Exception) -> bool:
    """Check if the error is a 429 rate limit error."""
    error_str = str(error).lower()
    return "429" in error_str or "rate limit" in error_str or "too many requests" in error_str


def test_site_access() -> dict:
    """Test basic site accessibility using Tavily extract with multiple URL variants."""
    print(f"\n{'='*60}")
    print("🔍 TEST 1: Site Accessibility (Tavily)")
    print(f"{'='*60}")

    result = {
        "test": "site_access",
        "urls_tested": TARGET_URLS,
        "timestamp": datetime.now().isoformat(),
        "success": False,
        "successful_url": None,
        "error": None,
        "content_length": 0,
        "title": None,
        "raw_content_preview": None,
        "full_raw_content": None,
    }

    # Try each URL variant
    for url in TARGET_URLS:
        print(f"\n  Testing: {url}")

        for attempt in range(MAX_RETRIES):
            try:
                response = tavily_client.extract(urls=[url])

                if response and "results" in response and len(response["results"]) > 0:
                    page = response["results"][0]
                    raw_content = page.get("raw_content", "")
                    title = page.get("title", "")

                    if len(raw_content.strip()) > 100:  # Meaningful content
                        result["success"] = True
                        result["successful_url"] = url
                        result["title"] = title
                        result["content_length"] = len(raw_content)
                        result["raw_content_preview"] = raw_content[:2000] if raw_content else None
                        result["full_raw_content"] = raw_content

                        print(f"    ✓ SUCCESS!")
                        print(f"      Title: {title}")
                        print(f"      Content length: {len(raw_content)} characters")
                        return result
                    else:
                        print(f"    ✗ Empty/insufficient content ({len(raw_content)} chars)")
                else:
                    print(f"    ✗ No results returned")

            except Exception as e:
                if is_rate_limit_error(e):
                    if attempt < MAX_RETRIES - 1:
                        backoff = INITIAL_BACKOFF * (2 ** attempt)
                        print(f"    ⏳ Rate limited. Waiting {backoff}s...")
                        time.sleep(backoff)
                        continue
                print(f"    ✗ Error: {e}")
                result["error"] = str(e)
                break
            break  # Move to next URL if no rate limit

        time.sleep(0.3)  # Brief pause between URL attempts

    result["error"] = result.get("error") or "No URL variants returned usable content"
    return result


def test_direct_http_access() -> dict:
    """Test direct HTTP access as fallback (bypassing Tavily)."""
    print(f"\n{'='*60}")
    print("🔍 TEST 1b: Direct HTTP Access (Fallback)")
    print(f"{'='*60}")

    result = {
        "test": "direct_http_access",
        "timestamp": datetime.now().isoformat(),
        "success": False,
        "available": REQUESTS_AVAILABLE,
        "error": None,
        "status_code": None,
        "content_length": 0,
        "content_preview": None,
        "full_content": None,
    }

    if not REQUESTS_AVAILABLE:
        result["error"] = "requests library not installed"
        print("  ⚠️ requests library not available")
        return result

    headers = {
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36"
    }

    for url in TARGET_URLS:
        print(f"\n  Testing: {url}")
        try:
            response = requests.get(url, headers=headers, timeout=30, allow_redirects=True)
            result["status_code"] = response.status_code

            if response.status_code == 200:
                content = response.text
                result["success"] = True
                result["content_length"] = len(content)
                result["content_preview"] = content[:2000]
                result["full_content"] = content
                result["final_url"] = response.url

                print(f"    ✓ SUCCESS! Status: {response.status_code}")
                print(f"      Final URL: {response.url}")
                print(f"      Content length: {len(content)} characters")
                return result
            else:
                print(f"    ✗ Status code: {response.status_code}")

        except Exception as e:
            print(f"    ✗ Error: {e}")
            result["error"] = str(e)

        time.sleep(0.3)

    return result


def test_search_discovery() -> dict:
    """Test if Tavily search can discover pages on the site."""
    print(f"\n{'='*60}")
    print("🔍 TEST 2: Search Discovery")
    print(f"{'='*60}")

    result = {
        "test": "search_discovery",
        "domain": TARGET_DOMAIN,
        "timestamp": datetime.now().isoformat(),
        "success": False,
        "error": None,
        "pages_found": 0,
        "sample_urls": []
    }

    queries = [
        f"site:{TARGET_DOMAIN} P-Number material",
        f"site:{TARGET_DOMAIN} ASME welding groups",
        f"site:{TARGET_DOMAIN} material standards table"
    ]

    discovered_urls = set()

    for query in queries:
        print(f"\n  Query: {query}")
        try:
            search_result = tavily_client.search(
                query=query,
                max_results=10,
                include_domains=[TARGET_DOMAIN]
            )

            if search_result and "results" in search_result:
                for r in search_result["results"]:
                    url = r.get("url", "")
                    if url and TARGET_DOMAIN in url:
                        discovered_urls.add(url)
                        print(f"    Found: {url}")

            time.sleep(0.3)  # Rate limiting

        except Exception as e:
            print(f"    ✗ Error: {e}")
            result["error"] = str(e)

    result["pages_found"] = len(discovered_urls)
    result["sample_urls"] = list(discovered_urls)[:10]
    result["success"] = len(discovered_urls) > 0

    print(f"\n  Total unique pages found: {len(discovered_urls)}")
    return result


def test_table_extraction(content: str) -> dict:
    """Analyze extracted content for table structures."""
    print(f"\n{'='*60}")
    print("🔍 TEST 3: Table Structure Analysis")
    print(f"{'='*60}")

    result = {
        "test": "table_extraction",
        "timestamp": datetime.now().isoformat(),
        "has_table_content": False,
        "table_indicators": [],
        "material_keywords_found": [],
        "sample_rows": []
    }

    if not content:
        print("  ✗ No content to analyze")
        return result

    # Look for table indicators in markdown content
    table_patterns = [
        (r'\|[^|]+\|', "Markdown table pipes"),
        (r'P-Number', "P-Number reference"),
        (r'Group\s*Number', "Group Number reference"),
        (r'Material\s+Type', "Material Type header"),
        (r'Nominal\s+Composition', "Nominal Composition"),
        (r'ASME', "ASME reference"),
        (r'UNS\s*[A-Z]\d+', "UNS material code"),
        (r'SA-\d+', "SA specification"),
        (r'SB-\d+', "SB specification"),
    ]

    print("\n  Checking for table structures...")
    for pattern, description in table_patterns:
        matches = re.findall(pattern, content, re.IGNORECASE)
        if matches:
            result["table_indicators"].append({
                "indicator": description,
                "count": len(matches),
                "sample": matches[:3]
            })
            print(f"    ✓ {description}: {len(matches)} occurrences")

    # Extract potential table rows (lines with multiple pipe separators)
    table_rows = re.findall(r'^\|[^|]+(?:\|[^|]+)+\|$', content, re.MULTILINE)
    if table_rows:
        result["has_table_content"] = True
        result["sample_rows"] = table_rows[:5]
        print(f"\n  ✓ Found {len(table_rows)} potential table rows")
        print("  Sample rows:")
        for row in table_rows[:3]:
            print(f"    {row[:100]}...")

    # Check for material-related keywords
    material_keywords = ['carbon steel', 'stainless', 'alloy', 'nickel', 'chromium',
                         'copper', 'aluminum', 'titanium', 'ferritic', 'austenitic']
    for keyword in material_keywords:
        if keyword.lower() in content.lower():
            result["material_keywords_found"].append(keyword)

    if result["material_keywords_found"]:
        print(f"\n  Material keywords found: {', '.join(result['material_keywords_found'])}")

    return result


def save_results(results: dict, filename: str) -> Path:
    """Save test results to JSON file."""
    OUTPUT_DIR.mkdir(exist_ok=True)
    output_path = OUTPUT_DIR / filename

    with open(output_path, 'w', encoding='utf-8') as f:
        json.dump(results, f, indent=2, ensure_ascii=False)

    print(f"\n💾 Results saved: {output_path}")
    return output_path


def print_summary(results: dict):
    """Print a summary of all test results."""
    print(f"\n{'='*60}")
    print("📊 TEST SUMMARY")
    print(f"{'='*60}")

    site_test = results.get("site_access", {})
    http_test = results.get("direct_http_access", {})
    search_test = results.get("search_discovery", {})
    table_test = results.get("table_extraction", {})
    content_source = results.get("content_source_for_analysis")

    print(f"\n1a. Tavily Extract: {'✓ PASS' if site_test.get('success') else '✗ FAIL'}")
    if site_test.get('success'):
        print(f"    - URL: {site_test.get('successful_url')}")
        print(f"    - Content: {site_test.get('content_length', 0)} characters")
    else:
        print(f"    - Error: {site_test.get('error', 'Unknown')}")

    print(f"\n1b. Direct HTTP: {'✓ PASS' if http_test.get('success') else '✗ FAIL'}")
    if http_test.get('success'):
        print(f"    - Status: {http_test.get('status_code')}")
        print(f"    - Content: {http_test.get('content_length', 0)} characters")
    elif not http_test.get('available'):
        print(f"    - requests library not installed")
    else:
        print(f"    - Error: {http_test.get('error', 'Unknown')}")

    print(f"\n2. Search Discovery: {'✓ PASS' if search_test.get('success') else '✗ FAIL'}")
    print(f"   - Pages discovered: {search_test.get('pages_found', 0)}")

    print(f"\n3. Table Structure: {'✓ PASS' if table_test.get('has_table_content') else '✗ FAIL'}")
    print(f"   - Content source: {content_source or 'None'}")
    print(f"   - Table indicators: {len(table_test.get('table_indicators', []))}")
    print(f"   - Material keywords: {len(table_test.get('material_keywords_found', []))}")

    # Overall assessment
    any_access = site_test.get('success') or http_test.get('success')
    has_tables = table_test.get('has_table_content') or len(table_test.get('table_indicators', [])) > 0

    print(f"\n{'='*60}")
    print("🎯 INTEGRATION ASSESSMENT")
    print(f"{'='*60}")

    if any_access and has_tables:
        print("\n✅ RECOMMENDED FOR INTEGRATION")
        print("   The site is accessible and contains parseable table data.")
        print("   This can likely reduce manual standards research workload.")
        if http_test.get('success') and not site_test.get('success'):
            print("   ⚠️ Note: Tavily extract() doesn't work - use direct HTTP requests")
    elif any_access:
        print("\n⚠️ PARTIAL ACCESS")
        print("   Site is accessible but table structure needs further analysis.")
        if http_test.get('success') and not site_test.get('success'):
            print("   Note: Direct HTTP works, but Tavily extract() does not.")
            print("   Consider using BeautifulSoup or similar for parsing.")
    else:
        print("\n❌ NOT ACCESSIBLE")
        print("   Neither Tavily nor direct HTTP could retrieve content.")
        print("   The site may have anti-scraping measures.")


def main():
    """Main entry point - run all tests."""
    print("\n" + "="*60)
    print("🔬 PNUMBERS.COM ACCESS TEST")
    print("    Material Standards Table Scraping Feasibility")
    print("="*60)

    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")

    results = {
        "test_run": timestamp,
        "target_urls": TARGET_URLS,
        "target_domain": TARGET_DOMAIN,
    }

    # Test 1a: Site access via Tavily
    site_result = test_site_access()
    results["site_access"] = site_result

    # Test 1b: Direct HTTP access (fallback)
    time.sleep(0.5)
    http_result = test_direct_http_access()
    results["direct_http_access"] = http_result

    # Test 2: Search discovery
    time.sleep(0.5)
    search_result = test_search_discovery()
    results["search_discovery"] = search_result

    # Test 3: Table extraction analysis - use whichever content source worked
    content_for_analysis = ""
    content_source = None

    if site_result.get("success") and site_result.get("full_raw_content"):
        content_for_analysis = site_result["full_raw_content"]
        content_source = "tavily"
    elif http_result.get("success") and http_result.get("full_content"):
        content_for_analysis = http_result["full_content"]
        content_source = "direct_http"

    results["content_source_for_analysis"] = content_source
    table_result = test_table_extraction(content_for_analysis)
    results["table_extraction"] = table_result

    # Save results (excluding large content fields to keep file manageable)
    results_for_save = results.copy()
    if "site_access" in results_for_save:
        results_for_save["site_access"] = {k: v for k, v in results_for_save["site_access"].items()
                                           if k != "full_raw_content"}
    if "direct_http_access" in results_for_save:
        results_for_save["direct_http_access"] = {k: v for k, v in results_for_save["direct_http_access"].items()
                                                   if k != "full_content"}

    output_file = f"pnumbers_access_test_{timestamp}.json"
    save_results(results_for_save, output_file)

    # Save raw content separately if successful
    if content_for_analysis:
        content_file = OUTPUT_DIR / f"pnumbers_raw_content_{timestamp}.txt"
        with open(content_file, 'w', encoding='utf-8') as f:
            f.write(f"Source: {content_source}\n")
            f.write(f"Timestamp: {timestamp}\n")
            f.write("="*60 + "\n\n")
            f.write(content_for_analysis)
        print(f"💾 Raw content saved: {content_file}")

    # Print summary
    print_summary(results)

    return results


if __name__ == "__main__":
    main()

