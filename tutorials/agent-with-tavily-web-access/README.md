![](https://europe-west1-atp-views-tracker.cloudfunctions.net/working-analytics?notebook=tutorials--agent-with-tavily-web-access--readme)

# Supercharge Your Agent with Web Access Using Tavily


## Overview

This tutorial series is designed for Python developers who want to empower their AI agents with real-time web access, enabling agents to utilize up-to-date information as context. Live web information is critical for AI agents tasked with performing research, answering questions accurately, monitoring trends, or providing up-to-date recommendations. You'll learn how to build AI agents that search the web, extract valuable content, navigate websites intelligently, and integrate real-time web information into private knowledge bases. 

## Agenda

This tutorial series follows a step-by-step learning path with three stand-alone tutorials:
1. In [tutorial #1](./search-extract-crawl.ipynb), we'll cover the **basics of web access**.

2. In [tutorial #2](./web-agent-tutorial.ipynb), we'll **build a web agent** that can search, scrape, and crawl the web.

3. Finally, In [tutorial #3](./hybrid-agent-tutorial.ipynb), we'll develop a system that **combines real-time web information with private knowledge base data**.


## Directory Structure

```
📁 agent-with-tavily-web-access/
├── 📓 search-extract-crawl.ipynb  # Tutorial notebook 1
├── 📓 web-agent-tutorial.ipynb    # Tutorial notebook 2
├── 📓 hybrid-agent-tutorial.ipynb # Tutorial notebook 3
├── 📄 fetch_astm_standards.py     # ASTM standards batch fetcher
├── 📁 assets/                     # Diagrams and screenshots
│   ├── 🖼️ web-agent.svg
|   ├── 🖼️ hybrid.svg
|   ├── 🖼️ api-key.png
│   └── 🖼️ sign-up.png
├── 📁 supplemental/                # Supplemental materials
│   ├── 📓 vectorize_tutorial.ipynb # Vectorize your own documents
│   ├── 📁 docs/                    # Sample CRM documents
│   └── 📁 db/                      # Pre-built Chroma vector database
├── 📁 output/astm_lists/          # ASTM extraction output
│   ├── 📄 astm_standards_list.json # Official list of 11,109 standards
│   └── 📁 full_summary/json/       # Batch results and markdown files
└── 📄 README.md                    # This file
```

---

## ASTM Standards Fetcher

The `fetch_astm_standards.py` script extracts content from ASTM standard pages using the Tavily API. It processes standards in batches of 200 with automatic resume capability and dynamic rate limiting.

### Features

- **Batch Processing**: Processes 11,109 ASTM standards in batches of 200
- **Automatic Resume**: Detects completed batches and resumes from where you left off
- **Dynamic Rate Limiting**: Supports ~1000 requests/minute with exponential backoff for 429 errors
- **Error Logging**: Failed extractions are logged separately for review

### Usage

```bash
# Check current progress
python fetch_astm_standards.py --status

# Resume processing the next incomplete batch
python fetch_astm_standards.py --resume

# Resume and process through a specific batch (e.g., batch 20)
python fetch_astm_standards.py --resume-through 20

# Process a specific batch
python fetch_astm_standards.py --batch 15

# Process all remaining batches
python fetch_astm_standards.py --all

# Process a custom range of standards
python fetch_astm_standards.py --start 500 --end 700
```

### Command-Line Arguments

| Argument | Description |
|----------|-------------|
| `--status` | Show progress status (completed batches) and exit |
| `--resume` | Process just the next incomplete batch |
| `--resume-through N` | Resume and process all incomplete batches through batch N |
| `--batch N` | Process a specific batch number (0-indexed) |
| `--all` | Process all remaining incomplete batches |
| `--start N` | Start index for custom range (inclusive) |
| `--end N` | End index for custom range (exclusive) |

### Output

- **JSON Results**: `output/astm_lists/full_summary/json/batch_XXXX_TIMESTAMP.json`
- **Markdown Files**: `output/astm_lists/full_summary/json/md/{code}.md`
- **Error Logs**: `output/astm_lists/full_summary/json/errors_batch_XXXX_TIMESTAMP.json`

### Rate Limiting

The script implements intelligent rate limiting:
- **Base delay**: 0.06 seconds between requests (~1000 req/min)
- **429 Handling**: Exponential backoff (1s → 2s → 4s → 8s → 16s)
- **Max retries**: 5 attempts per request