# ASTM/ASME Standards Scraper - Development Context

> **Last Updated**: 2025-11-28
> **Status**: Phase 2 Complete - Ready for URL Generation from Official List

---

## Project Overview

Scrapes ASTM and ASME standard pages from `https://store.astm.org/` using the Tavily API for RAG database ingestion.

**Goal**: Extract structured content from all available .html standard pages for:
- RAG (Retrieval-Augmented Generation) operations
- Custom database population with structured fields

---

## What We've Completed

### Phase 1: Diagnostics & Discovery Method

The ASTM Store is a **Next.js/React application** - traditional crawling doesn't work.

| Tavily Method | Result |
|---------------|--------|
| `map()` | ❌ Found 0 .html pages (only navigation) |
| `crawl()` | ❌ Redirected to www.astm.org |
| **`search()`** | ✅ Finds .html pages via indexed content |
| `extract()` | ✅ Extracts content from known URLs |

**Key Insight**: Pages exist and are indexed, but links are rendered via JavaScript.

### Phase 2: Coverage Analysis

**Problem Identified**: Search-based discovery only finds ~2.9% of standards.

| Metric | Value |
|--------|-------|
| Official ASTM List | **11,109 standards** |
| Discovered via Tavily search | **324 pages** |
| Coverage | **2.9%** |
| Gap | **10,785 standards** |

**Root Cause**: Tavily `search()` returns max 20 results per query. Even with 43 different queries, most standards are not discoverable this way.

### Phase 3: Official Standards List Obtained

Scraped complete ASTM standards list from `https://la.astm.org/standards/astm-standards-list/`

**Saved to**: `output/astm_lists/astm_standards_list.json`

```json
{
  "source_url": "https://la.astm.org/standards/astm-standards-list/",
  "total_count": 11109,
  "series_breakdown": {
    "A": 208, "B": 590, "C": 1097, "D": 4768,
    "E": 2120, "F": 2137, "G": 188, "SI": 1
  },
  "standards": [
    {"designation": "ASTM A0001-00R18", "code": "A0001-00R18", "series": "A", "has_metric": false},
    {"designation": "ASTM A0105_A0105M-23", "code": "A0105_A0105M-23", "series": "A", "has_metric": true},
    {"designation": "ASTM G0170-06R20E01", "code": "G0170-06R20E01", "series": "G", "has_metric": false},
    ...
  ]
}
```

---

## URL Pattern Analysis

### Standard Designation → URL Mapping

| Official Designation | URL Pattern | Example URL |
|---------------------|-------------|-------------|
| `ASTM A0105_A0105M-23` | Lowercase, keep underscores | `a0105_a0105m-23.html` |
| `ASTM A0001-00R18` | Lowercase, no underscore | `a0001-00r18.html` |
| `ASTM G0170-06R20E01` | Lowercase | `g0170-06r20e01.html` |

**URL Construction Rule**:
```python
code = "A0105_A0105M-23"
url = f"https://store.astm.org/{code.lower()}.html"
# Result: https://store.astm.org/a0105_a0105m-23.html
```

### Variations to Handle

1. **With metric suffix**: `A0105_A0105M-23` → has `_A0105M` part
2. **Without metric**: `A0001-00R18` → no underscore
3. **Reapproved**: `G0170-06R20E01` → has `R20` (reapproved 2020)
4. **Edition suffix**: `A0351_A0351M-24E01` → has `E01` edition marker

---

## Current Files Structure

```
tutorials/agent-with-tavily-web-access/
├── .env                      # API keys
├── DEV_CONTEXT.md            # This file (LLM context)
├── astm_scraper.py           # Original search-based scraper
├── extract_experiment.py     # Content extraction testing (5 pages)
├── save_astm_list.py         # Fetches official list from la.astm.org
├── coverage_analysis.py      # Analyzes search coverage gap
└── output/
    ├── astm_lists/
    │   ├── astm_standards_list.json   # ⭐ 11,109 standards
    │   └── astm_standards_list.md     # Markdown table
    ├── coverage_analysis.json         # Search coverage report
    ├── a0105_a0105m-21.md             # Extracted markdown content
    ├── a0182_a0182m-23.md
    └── extraction_experiment_*.json   # Extraction results
```

---

## Content Extraction (Working)

`extract_experiment.py` successfully extracts:

| Field | Source | Status |
|-------|--------|--------|
| `designation` | Parsed from filename | ✅ `A105/A105M-21` |
| `title` | Tavily `title` field | ✅ |
| `abstract` | Regex from `raw_content` | ✅ |
| `scope` | Regex from `raw_content` | ✅ |
| `standard_type` | Parsed (`ASTM`/`ASME`) | ✅ |
| `markdown_file` | Saved `.md` file path | ✅ |

**Output per standard**:
- JSON with structured metadata
- Markdown file with full content (for RAG)

---

## ⭐ NEXT STEP: Generate URLs from Official List

### Task

Create a script that:

1. **Reads** `output/astm_lists/astm_standards_list.json` (11,109 standards)
2. **Converts** each `code` to a `store.astm.org` URL
3. **Validates** URLs exist (HEAD request or Tavily extract)
4. **Outputs** verified URLs for extraction

### URL Conversion Logic

```python
def code_to_url(code: str) -> str:
    """
    Convert ASTM code to store.astm.org URL.

    Examples:
    - "A0105_A0105M-23" → "https://store.astm.org/a0105_a0105m-23.html"
    - "A0001-00R18" → "https://store.astm.org/a0001-00r18.html"
    - "G0170-06R20E01" → "https://store.astm.org/g0170-06r20e01.html"
    """
    return f"https://store.astm.org/{code.lower()}.html"
```

### Validation Strategy

Option A: **Tavily extract()** - Returns content if page exists
Option B: **HTTP HEAD request** - Faster, just checks if URL returns 200

### Expected Output

```json
{
  "total_in_list": 11109,
  "valid_urls": [...],
  "invalid_urls": [...],
  "validation_rate": "85%"
}
```

---

## API Notes

- **Tavily API Key**: Required in `.env` as `TAVILY_API_KEY`
- **Rate Limiting**: Use 200-500ms delays between requests
- **Extract Cost**: ~0.01 credits per URL (estimate)
- **Batch Size**: Process in batches of 50-100 for progress tracking

---

## Running Scripts

```powershell
cd tutorials\agent-with-tavily-web-access
.venv\Scripts\activate
python <script_name>.py
```

| Script | Purpose |
|--------|---------|
| `save_astm_list.py` | Fetch official list |
| `coverage_analysis.py` | Analyze search coverage |
| `extract_experiment.py` | Test extraction (5 pages) |
| `astm_scraper.py` | Original search-based scraper |

