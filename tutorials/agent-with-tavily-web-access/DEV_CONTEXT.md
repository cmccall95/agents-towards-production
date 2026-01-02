# ASTM Standards Scraper - Development Context

> **Last Updated**: 2025-12-11
> **Status**: ✅ Complete - 11,107/11,109 standards extracted (99.98%)

---

## Project Overview

Scraped ASTM standard pages from `https://store.astm.org/` using the Tavily API for RAG database ingestion.

**Goal**: Extract structured content from all available .html standard pages for:
- RAG (Retrieval-Augmented Generation) operations
- Custom database population with structured fields

---

## Final Results Summary

| Metric | Value |
|--------|-------|
| Total Standards in List | 11,109 |
| Successfully Extracted | **11,107** |
| Failed Extraction | 2 |
| Success Rate | **99.98%** |

### Failed Standards (Not Relevant to Piping)

These 2 standards failed with "No results from Tavily" - likely page structure issues:

| Code | URL |
|------|-----|
| E2628-20 | https://store.astm.org/e2628-20.html |
| F3238-17R23 | https://store.astm.org/f3238-17r23.html |

---

## Output Structure

All output is located in:
```
tutorials/agent-with-tavily-web-access/output/astm_lists/full_summary/json/
```

### Markdown Files (RAG Content)

```
output/astm_lists/full_summary/json/md/
├── a0001-00r18.md
├── a0105_a0105m-23.md
├── b0016_b0016m-22.md
├── ... (11,107 files total)
└── g0215-16.md
```

Each markdown file contains:
- Standard designation and title
- Full extracted content from the ASTM store page
- Source URL reference

### Batch Result Files

```
output/astm_lists/full_summary/json/
├── batch_0000_20251128_075110.json   # Batch 0 results
├── batch_0001_20251128_080321.json   # Batch 1 results
├── ... (56 batch files)
├── batch_0055_20251129_172314.json   # Batch 55 results
├── all_errors_consolidated.json       # All errors from initial run
├── retry_results_20251211_130737.json # Retry success results
└── retry_errors_20251211_130737.json  # Final 2 failures
```

### Batch JSON Structure

```json
{
  "batch_number": 0,
  "range": "0-199",
  "total_in_batch": 200,
  "successful": 198,
  "failed": 2,
  "results": [
    {
      "code": "A0001-00R18",
      "designation": "ASTM A0001-00R18",
      "url": "https://store.astm.org/a0001-00r18.html",
      "title": "Standard Specification for...",
      "content_length": 4523,
      "md_file": "output/.../md/a0001-00r18.md",
      "success": true
    }
  ],
  "generated_at": "2025-11-28T07:51:10.753832"
}
```

---

## Processing Timeline

| Phase | Date | Description |
|-------|------|-------------|
| Initial Run | Nov 28-29, 2025 | Processed all 56 batches (200 standards each) |
| Error Analysis | Dec 11, 2025 | Consolidated 786 errors from 22 batches |
| Retry Run | Dec 11, 2025 | Batch retry of 786 failed standards → 784 recovered |

### Error Breakdown (Initial Run)

| Category | Count | Cause |
|----------|-------|-------|
| DNS/Network Error | 761 | Temporary internet connectivity issues |
| No Results | 21 | Tavily couldn't extract content |
| Timeout | 3 | Request took too long |
| Other | 1 | Miscellaneous |

**Resolution**: 784 of 786 errors were recovered on retry. Only 2 standards remain unextracted.

---

## Script: `fetch_astm_standards.py`

### Command-Line Usage

```powershell
cd tutorials\agent-with-tavily-web-access
.venv\Scripts\python.exe fetch_astm_standards.py [OPTIONS]
```

### Options

| Option | Description |
|--------|-------------|
| `--status` | Show progress status and exit |
| `--batch N` | Process specific batch number (0-indexed) |
| `--resume` | Process next incomplete batch |
| `--resume-through N` | Resume and process through batch N |
| `--all` | Process all remaining batches |
| `--retry-failed` | Retry only previously failed standards |
| `--start N --end M` | Process custom range of standards |

### Rate Limiting Configuration

| Setting | Value | Purpose |
|---------|-------|---------|
| `BATCH_SIZE` | 200 | Standards per processing batch |
| `BATCH_EXTRACT_SIZE` | 20 | URLs per Tavily API call |
| `BASE_DELAY` | 0.06s | Delay between API calls |
| `MAX_RETRIES` | 5 | Retry attempts for 429 errors |
| `INITIAL_BACKOFF` | 1.0s | Starting backoff delay |

Exponential backoff sequence: 1s → 2s → 4s → 8s → 16s

---

## Files Structure

```
tutorials/agent-with-tavily-web-access/
├── .env                          # API keys (TAVILY_API_KEY)
├── DEV_CONTEXT.md                # This file
├── README.md                     # User documentation
├── fetch_astm_standards.py       # Main batch processing script
├── astm_scraper.py               # Original search-based scraper
├── extract_experiment.py         # Content extraction testing
├── save_astm_list.py             # Fetches official list from la.astm.org
├── coverage_analysis.py          # Analyzes search coverage gap
└── output/
    └── astm_lists/
        ├── astm_standards_list.json    # Source: 11,109 standards
        └── full_summary/json/
            ├── batch_*.json            # 56 batch result files
            ├── all_errors_consolidated.json
            ├── retry_results_*.json
            ├── retry_errors_*.json
            └── md/                     # 11,107 markdown files
```

---

## Technical Notes

### URL Construction

```python
def code_to_url(code: str) -> str:
    return f"https://store.astm.org/{code.lower()}.html"
```

Examples:
- `A0105_A0105M-23` → `https://store.astm.org/a0105_a0105m-23.html`
- `A0001-00R18` → `https://store.astm.org/a0001-00r18.html`

### Why Tavily?

The ASTM Store is a **Next.js/React SPA** - traditional crawling doesn't work because links are rendered via JavaScript. Tavily's `extract()` API can parse JavaScript-rendered content.

### API Requirements

- **Tavily API Key**: Required in `.env` as `TAVILY_API_KEY`
- **Account Tier**: 1000 requests/minute (upgraded from 100)

---

## Potential Next Steps

1. **Database Ingestion**: Load markdown files into a vector database (Pinecone, Weaviate, etc.) for RAG
2. **Structured Parsing**: Extract specific fields (scope, abstract, referenced documents) from markdown content
3. **ASME Standards**: Apply same approach to ASME standards if needed
4. **Incremental Updates**: Periodically re-fetch to capture new/updated standards

