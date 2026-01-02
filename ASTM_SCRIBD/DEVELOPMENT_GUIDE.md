# ASTM Scribd Extraction - Development Guide

## Overview

Extract ASTM standard documents from Scribd.com API and save to PostgreSQL database as markdown for future DSPy/Cleanlab processing.

---

## Phase 1: Setup & Validation

- [ ] **1.1** Create directory structure (`/output`, `/logs`, `/tests`)
- [ ] **1.2** Create `config.py` with API keys, database connection, paths
- [ ] **1.3** Create `load_astm_list.py` - utility to load ASTM standards from master JSON
- [ ] **1.4** Validate ASTM list loading (11,109 standards available)
- [ ] **1.5** Test Scribd API connection with single standard

---

## Phase 2: Small Batch Test (5-10 Standards)

- [ ] **2.1** Create `scribd_extractor.py` - core extraction logic
- [ ] **2.2** Test extraction on 5 A-series standards (A106, A312, A182, A333, A234)
- [ ] **2.3** Validate markdown output format and content quality
- [ ] **2.4** Create `db_handler.py` - PostgreSQL save/update logic
- [ ] **2.5** Test saving markdown to PG database
- [ ] **2.6** Verify retrieval from database

---

## Phase 3: Multiprocessing Implementation

- [ ] **3.1** Add `ProcessPoolExecutor` to extraction script
- [ ] **3.2** Implement rate limiting per API requirements
- [ ] **3.3** Add progress tracking and logging
- [ ] **3.4** Test with 50 standards to validate parallelism
- [ ] **3.5** Add checkpoint/resume capability

---

## Phase 4: Batch Extraction

- [ ] **4.1** Create `batch_runner.py` with CLI for batch ranges
- [ ] **4.2** Run Batch 1: Standards 1-1000
- [ ] **4.3** Run Batch 2: Standards 1001-2000
- [ ] **4.4** Continue batches until complete (11,109 total)
- [ ] **4.5** Generate extraction summary report
- [ ] **4.6** Handle and log failed extractions for retry

---

## Future: DSPy + Cleanlab Processing

> **Note:** Separate implementation after markdown extraction complete

- [ ] Create DSPy extraction pipeline for structured data
- [ ] Implement Cleanlab validation for data quality
- [ ] Extract: grades, chemical composition, mechanical properties, applications

---

## Files Structure

```
ASTM_SCRIBD/
├── DEVELOPMENT_GUIDE.md      # This file
├── LLM_CONTEXT.md            # How to load ASTM standards
├── config.py                 # Configuration
├── load_astm_list.py         # Load ASTM master list
├── scribd_extractor.py       # Core Scribd API extraction
├── db_handler.py             # PostgreSQL operations
├── batch_runner.py           # Batch processing CLI
├── output/                   # Local markdown backup
├── logs/                     # Extraction logs
└── tests/                    # Test scripts
```

---

## ASTM Standards Source

| Item | Value |
|------|-------|
| Master JSON | `tutorials/agent-with-tavily-web-access/output/astm_lists/astm_standards_list.json` |
| Total Standards | 11,109 |
| Series | A (208), B (590), C (1097), D (4768), E (2120), F (2137), G (188) |

---

## API Notes

Keep extraction scripts modular - we may test multiple APIs:
- Scribd API (primary)
- Alternative sources TBD

Each API implementation should be in its own file with consistent interface.

---

## Success Criteria

1. ✅ All 11,109 ASTM standards attempted
2. ✅ Markdown saved to PostgreSQL with metadata
3. ✅ Failed extractions logged with error details
4. ✅ Extraction rate > 90% success
5. ✅ Ready for DSPy/Cleanlab phase

