"""
ASTM/ASME Standards Coverage Analysis

Investigates the gap between:
- 11,109 standards in official ASTM list (la.astm.org)
- Standards discoverable via Tavily search on store.astm.org

Uses the existing search-based approach from astm_scraper.py.
Does NOT extract content - only performs discovery.
"""

import os
import json
import re
import time
import string
from datetime import datetime
from pathlib import Path
from collections import defaultdict
from dotenv import load_dotenv
from tavily import TavilyClient

# Load environment variables
load_dotenv()
tavily_client = TavilyClient(api_key=os.getenv("TAVILY_API_KEY"))

TARGET_SITE = "store.astm.org"
OUTPUT_DIR = Path(__file__).parent / "output"

# All possible series A-Z (expanded from original A-G)
ALL_SERIES = list(string.ascii_uppercase)

# ASME equivalents for A-series
ASME_PREFIXES = ['SA', 'SB', 'SC', 'SD', 'SE', 'SF', 'SG']


def is_html_standard_page(url: str) -> bool:
    """
    Check if URL is a valid .html standard page.
    FIXED: Now checks if .html appears ANYWHERE in URL (not just at end).
    This handles URLs like: a0105_a0105m-21.html?param=value
    """
    # Check if .html appears anywhere in the URL
    if '.html' not in url.lower():
        return False
    if TARGET_SITE not in url:
        return False
    # Filter out non-standard pages
    exclude_patterns = ['products-services', 'bos-standards', 'checkout', 'customer', 'cart', 'account', 'login']
    return not any(p in url.lower() for p in exclude_patterns)


def extract_series_from_url(url: str) -> tuple[str, str]:
    """
    Extract standard type and series from URL.
    Returns: (type, series) e.g., ('ASTM', 'A') or ('ASME', 'SA')
    """
    # Extract filename part (before .html and any query params)
    match = re.search(r'/([a-z]+\d+[^/]*?)\.html', url, re.IGNORECASE)
    if not match:
        return ('Unknown', 'Unknown')
    
    filename = match.group(1).lower()
    
    # Check for ASME SA/SB/etc prefix
    if filename.startswith('sa'):
        return ('ASME', 'SA')
    elif filename.startswith('sb'):
        return ('ASME', 'SB')
    elif filename.startswith('sc'):
        return ('ASME', 'SC')
    elif filename.startswith('sd'):
        return ('ASME', 'SD')
    elif filename.startswith('se'):
        return ('ASME', 'SE')
    elif filename.startswith('sf'):
        return ('ASME', 'SF')
    elif filename.startswith('sg'):
        return ('ASME', 'SG')
    elif filename.startswith('si'):
        return ('ASTM', 'SI')
    else:
        # ASTM single letter prefix
        series_match = re.match(r'^([a-z])', filename)
        if series_match:
            return ('ASTM', series_match.group(1).upper())
    
    return ('Unknown', 'Unknown')


def search_standards(query: str, max_results: int = 20) -> list[dict]:
    """Search for standards using Tavily search API."""
    try:
        result = tavily_client.search(
            query=query,
            max_results=max_results,
            include_domains=[TARGET_SITE]
        )
        if result and 'results' in result:
            return result['results']
    except Exception as e:
        print(f"  ⚠️ Search error: {e}")
    return []


def run_coverage_analysis():
    """Run comprehensive coverage analysis."""
    print(f"\n{'='*70}")
    print("🔍 ASTM/ASME Standards Coverage Analysis")
    print(f"{'='*70}")
    print(f"Target: https://{TARGET_SITE}/")
    print(f"Official List Count: 11,109 standards")
    print(f"{'='*70}\n")

    discovered_urls = {}  # url -> metadata
    series_counts = defaultdict(int)
    search_count = 0
    
    # Search all ASTM series A-Z
    print("📂 Phase 1: Searching ASTM series A-Z...")
    for series in ALL_SERIES:
        query = f"site:{TARGET_SITE} ASTM {series} standard specification"
        results = search_standards(query, max_results=20)
        
        new_found = 0
        for r in results:
            url = r.get('url', '')
            if is_html_standard_page(url) and url not in discovered_urls:
                std_type, std_series = extract_series_from_url(url)
                discovered_urls[url] = {
                    'url': url,
                    'type': std_type,
                    'series': std_series,
                    'title': r.get('title', '')
                }
                series_counts[std_series] += 1
                new_found += 1
        
        if new_found > 0:
            print(f"  ASTM {series}: +{new_found} pages (total: {len(discovered_urls)})")
        search_count += 1
        time.sleep(0.25)
    
    print(f"\n  Subtotal after A-Z: {len(discovered_urls)} pages\n")

    # Search ASME series (SA, SB, etc.)
    print("📂 Phase 2: Searching ASME series (SA, SB, SC, SD, SE, SF, SG)...")
    for prefix in ASME_PREFIXES:
        query = f"site:{TARGET_SITE} ASME {prefix} standard specification"
        results = search_standards(query, max_results=20)

        new_found = 0
        for r in results:
            url = r.get('url', '')
            if is_html_standard_page(url) and url not in discovered_urls:
                std_type, std_series = extract_series_from_url(url)
                discovered_urls[url] = {
                    'url': url,
                    'type': std_type,
                    'series': std_series,
                    'title': r.get('title', '')
                }
                series_counts[std_series] += 1
                new_found += 1

        if new_found > 0:
            print(f"  ASME {prefix}: +{new_found} pages (total: {len(discovered_urls)})")
        search_count += 1
        time.sleep(0.25)

    print(f"\n  Subtotal after ASME: {len(discovered_urls)} pages\n")

    # Search with broader queries
    print("📂 Phase 3: Broader search queries...")
    broad_queries = [
        "site:store.astm.org specification .html",
        "site:store.astm.org standard test method",
        "site:store.astm.org carbon steel",
        "site:store.astm.org stainless steel",
        "site:store.astm.org alloy specification",
        "site:store.astm.org pipe fitting",
        "site:store.astm.org bolt nut fastener",
        "site:store.astm.org welding",
        "site:store.astm.org coating",
        "site:store.astm.org testing",
    ]

    for query in broad_queries:
        results = search_standards(query, max_results=20)

        new_found = 0
        for r in results:
            url = r.get('url', '')
            if is_html_standard_page(url) and url not in discovered_urls:
                std_type, std_series = extract_series_from_url(url)
                discovered_urls[url] = {
                    'url': url,
                    'type': std_type,
                    'series': std_series,
                    'title': r.get('title', '')
                }
                series_counts[std_series] += 1
                new_found += 1

        if new_found > 0:
            short_q = query.replace("site:store.astm.org ", "")
            print(f"  '{short_q}': +{new_found} pages")
        search_count += 1
        time.sleep(0.25)

    print(f"\n  Final total: {len(discovered_urls)} pages after {search_count} searches\n")

    # Build report
    timestamp = datetime.now().isoformat()
    official_count = 11109
    coverage_pct = (len(discovered_urls) / official_count) * 100 if official_count > 0 else 0

    report = {
        "timestamp": timestamp,
        "target_site": TARGET_SITE,
        "total_searches": search_count,
        "official_list_count": official_count,
        "discovered_count": len(discovered_urls),
        "coverage_percentage": round(coverage_pct, 2),
        "gap": official_count - len(discovered_urls),
        "series_breakdown": dict(sorted(series_counts.items())),
        "discovered_urls": list(discovered_urls.values())
    }

    # Save report
    OUTPUT_DIR.mkdir(exist_ok=True)
    report_path = OUTPUT_DIR / "coverage_analysis.json"
    with open(report_path, 'w', encoding='utf-8') as f:
        json.dump(report, f, indent=2)
    print(f"💾 Saved: {report_path}")

    # Print summary
    print(f"\n{'='*70}")
    print("📊 COVERAGE ANALYSIS REPORT")
    print(f"{'='*70}")
    print(f"Official ASTM List:     {official_count:,} standards")
    print(f"Discovered on Store:    {len(discovered_urls):,} pages")
    print(f"Coverage:               {coverage_pct:.1f}%")
    print(f"Gap:                    {official_count - len(discovered_urls):,} standards")
    print(f"\n📂 Series Breakdown:")
    for series, count in sorted(series_counts.items(), key=lambda x: -x[1]):
        print(f"   {series:4}: {count:4} pages")

    print(f"\n💡 Possible reasons for gap:")
    print("   1. Tavily search has per-query result limits (max 20 per query)")
    print("   2. Some standards may not be on store.astm.org (retired, withdrawn)")
    print("   3. Some pages may use different URL patterns")
    print("   4. Search API may not index all pages")

    return report


if __name__ == "__main__":
    run_coverage_analysis()

