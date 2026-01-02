# ASTM Scribd Extraction - Development Guide

## Overview

Extract ASTM standard documents from Scribd.com using Crawlbase API (10,000 free requests) and save as markdown for future DSPy/Cleanlab processing.

---

## Quick Start

```bash
# 1. Install dependencies
pip install -r requirements.txt

# 2. Set API token (get from https://crawlbase.com)
export CRAWLBASE_JS_TOKEN="your_js_token_here"

# 3. Verify configuration
python config.py

# 4. Run tests
pytest tests/ -v

# 5. Run Phase 1 (single document test)
python pipeline.py --phase 1
```

---

## Architecture

```
ASTM_SCRIBD/
├── config.py              # Configuration & environment
├── load_astm_list.py      # Load 11,109 ASTM standards from master JSON
├── crawlbase_client.py    # Crawlbase API client with rate limiting
├── scribd_search.py       # Search Scribd & find official documents
├── markdown_converter.py  # Convert HTML to clean markdown
├── pipeline.py            # Main extraction pipeline (phases 1-3)
├── requirements.txt       # Python dependencies
├── DEVELOPMENT_GUIDE.md   # This file
├── LLM_CONTEXT.md         # Quick reference for loading ASTM standards
│
├── output/
│   ├── markdown/          # Extracted markdown files
│   ├── logs/              # Batch processing logs (JSON)
│   └── checkpoints/       # Resume checkpoints
│
└── tests/
    ├── __init__.py
    └── test_pipeline.py   # Unit & integration tests
```

---

## Extraction Pipeline

### Phase 1: Single Standard Test
**Purpose:** Validate API connection and basic extraction

```bash
python pipeline.py --phase 1
```

Validates:
- [x] Crawlbase API connection works
- [x] Scribd search returns results
- [x] Document can be fetched with JS rendering
- [x] HTML converts to valid markdown

### Phase 2: Small Batch Test
**Purpose:** Test multiple standards and edge cases

```bash
python pipeline.py --phase 2 --count 10
```

Tests:
- [x] Batch processing logic
- [x] Different standard types (A-series, B-series, etc.)
- [x] Error handling and logging
- [x] Rate limiting compliance

### Phase 3: Full Batch Processing
**Purpose:** Production extraction of all 11,109 standards

```bash
# Process batch 0 (standards 0-199)
python pipeline.py --phase 3 --batch 0 --batch-size 200

# Process batch 1
python pipeline.py --phase 3 --batch 1

# Dry run (no API calls)
python pipeline.py --phase 3 --batch 0 --dry-run
```

Features:
- [x] Checkpoint every 25 standards (resumable)
- [x] Detailed logging with JSON output
- [x] API usage stats tracking
- [x] Error consolidation

---

## Crawlbase API

### Setup

1. Create account at https://crawlbase.com
2. Get JavaScript token (required for Scribd's dynamic content)
3. Set environment variable:
   ```bash
   export CRAWLBASE_JS_TOKEN="your_token"
   ```

### Rate Limits

| Limit | Value |
|-------|-------|
| Max requests/second | 20 |
| Recommended delay | 200ms (5 req/sec) |
| Timeout | 90 seconds |
| Free tier | 10,000 requests |

### Billing

- Only **successful** requests are billed
- Check `pc_status` and `original_status` in response headers
- Track usage in API dashboard

---

## ASTM Standards Format

### Identifier Pattern
```
{SERIES}{ZERO_PADDED_NUMBER}-{YEAR}{REVISION}

Examples:
  A0106-22     -> A-series #106, year 2022
  A0001-00R18  -> A-series #1, year 2000, revision 18
  D1234-20E01  -> D-series #1234, year 2020, edition 01
```

### Series Breakdown

| Series | Count | Domain |
|--------|-------|--------|
| A | 208 | Ferrous Metals (Steel, Iron) |
| B | 590 | Nonferrous Metals |
| C | 1,097 | Cementitious, Ceramic, Masonry |
| D | 4,768 | Miscellaneous Materials |
| E | 2,120 | Testing Methods |
| F | 2,137 | Specific Applications |
| G | 188 | Corrosion, Deterioration |
| **Total** | **11,109** | |

---

## Priority Standards

For initial testing (welding/piping focus):

| Code | Description |
|------|-------------|
| A0105 | Carbon Steel Forgings |
| A0106 | Seamless Carbon Steel Pipe |
| A0182 | Forged Alloy/Stainless Fittings |
| A0193 | Alloy Steel Bolting |
| A0194 | Carbon/Alloy Steel Nuts |
| A0234 | Wrought Carbon Steel Fittings |
| A0312 | Austenitic Stainless Steel Pipe |
| A0333 | Low-Temperature Pipe |
| A0350 | Low-Temperature Forgings |
| A0403 | Wrought Austenitic SS Fittings |
| A0516 | Pressure Vessel Plate |

---

## Output Format

### Markdown Structure

```markdown
<!-- ASTM Standard: ASTM A0106-22 -->
<!-- Source: Scribd -->
<!-- Document ID: 123456789 -->
<!-- URL: https://www.scribd.com/document/123456789 -->
<!-- Extracted: 2024-01-15T10:30:00 -->

# ASTM A0106-22

**Standard Specification for Seamless Carbon Steel Pipe**

---

[Document content...]
```

### Log Files

```json
{
  "batch_id": "phase3_batch_0000",
  "phase": 3,
  "started_at": "2024-01-15T10:00:00",
  "completed_at": "2024-01-15T11:30:00",
  "total": 200,
  "successful": 185,
  "failed": 15,
  "results": [...],
  "api_stats": {
    "total_requests": 400,
    "successful_requests": 370,
    "success_rate": 0.925
  }
}
```

---

## Testing

```bash
# Run all tests
pytest tests/ -v

# Run specific test class
pytest tests/test_pipeline.py::TestLoadASTMList -v

# Run with coverage
pytest tests/ --cov=. --cov-report=html
```

Key test areas:
- Configuration validation
- ASTM list loading and filtering
- Standard code parsing (year, revision)
- Relevance scoring for document matching
- HTML to markdown conversion
- Table and heading handling

---

## Error Handling

### Common Errors

| Error | Cause | Solution |
|-------|-------|----------|
| No API token | CRAWLBASE_JS_TOKEN not set | Export environment variable |
| Rate limited (429) | Too many requests | Automatic retry with backoff |
| Timeout | Scribd slow/blocked | Increase timeout, retry |
| No results | Document not on Scribd | Log and skip |
| Parse error | Unexpected HTML format | Check selectors, update converter |

### Recovery

1. Check logs in `output/logs/`
2. Find checkpoint in `output/checkpoints/`
3. Identify failed batch range
4. Re-run specific batch: `python pipeline.py --phase 3 --batch N`

---

## Future Enhancements

- [ ] PostgreSQL storage for structured data
- [ ] DSPy extraction pipeline
- [ ] Cleanlab data quality validation
- [ ] Parallel batch processing
- [ ] Alternative API fallbacks

---

## Success Criteria

1. All 11,109 ASTM standards attempted
2. Markdown saved with proper formatting
3. Failed extractions logged with details
4. Extraction success rate > 90%
5. API usage stays within 10,000 free requests (may need batching strategy)

---

## Resource Links

- Crawlbase Docs: https://crawlbase.com/docs/crawling-api/
- ASTM Master List: `tutorials/agent-with-tavily-web-access/output/astm_lists/astm_standards_list.json`
- Scribd Search: https://www.scribd.com/search?query=ASTM
