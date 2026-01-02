# LLM Context: Loading ASTM Standards

## Quick Reference

```python
import json
from pathlib import Path

# Path to master ASTM list (relative to repo root)
ASTM_LIST_PATH = Path("tutorials/agent-with-tavily-web-access/output/astm_lists/astm_standards_list.json")

def load_astm_standards() -> list[dict]:
    """Load all ASTM standards from master JSON."""
    with open(ASTM_LIST_PATH, "r", encoding="utf-8") as f:
        data = json.load(f)
    return data["standards"]  # Returns list of 11,109 standards
```

---

## JSON Structure

```json
{
  "source_url": "https://la.astm.org/standards/astm-standards-list/",
  "scraped_at": "2025-11-28T06:32:55.805820",
  "total_count": 11109,
  "series_breakdown": {
    "A": 208, "B": 590, "C": 1097, "D": 4768,
    "E": 2120, "F": 2137, "G": 188, "SI": 1
  },
  "standards": [...]
}
```

---

## Standard Record Format

Each standard in the `standards` array:

```json
{
  "designation": "ASTM A0106-22",   // Full designation with "ASTM" prefix
  "code": "A0106-22",               // Code only (use for filenames/searches)
  "series": "A",                     // Series letter (A-G, SI)
  "has_metric": false                // True if has metric variant (_M suffix)
}
```

---

## Field Descriptions

| Field | Type | Description | Example |
|-------|------|-------------|---------|
| `designation` | str | Full ASTM designation | `"ASTM A0312-24"` |
| `code` | str | Code without "ASTM" prefix | `"A0312-24"` |
| `series` | str | Series letter | `"A"`, `"B"`, `"D"` |
| `has_metric` | bool | Has metric variant | `false` |

---

## Common Operations

### Load All Standards
```python
standards = load_astm_standards()
print(f"Total: {len(standards)}")  # 11,109
```

### Filter by Series
```python
a_series = [s for s in standards if s["series"] == "A"]
print(f"A-Series: {len(a_series)}")  # 208
```

### Get Batch Range
```python
batch_start, batch_end = 0, 1000
batch = standards[batch_start:batch_end]
```

### Extract Base Standard Number
```python
import re

def get_base_number(code: str) -> str:
    """Extract base standard number (e.g., 'A106' from 'A0106-22')."""
    match = re.match(r"([A-Z]+)0*(\d+)", code)
    if match:
        return f"{match.group(1)}{match.group(2)}"
    return code

# Example: "A0106-22" -> "A106"
```

### Build Search Query
```python
def build_search_query(standard: dict) -> str:
    """Build search query for Scribd or other APIs."""
    designation = standard["designation"]
    base = get_base_number(standard["code"])
    return f"ASTM {base} specification"
```

---

## Series Reference

| Series | Count | Domain |
|--------|-------|--------|
| A | 208 | Ferrous Metals (Steel, Iron) |
| B | 590 | Nonferrous Metals (Copper, Aluminum, Nickel) |
| C | 1,097 | Cementitious, Ceramic, Concrete, Masonry |
| D | 4,768 | Miscellaneous Materials (Plastics, Rubber, etc.) |
| E | 2,120 | Miscellaneous Subjects (Testing Methods) |
| F | 2,137 | Materials for Specific Applications |
| G | 188 | Corrosion, Deterioration, Degradation |
| SI | 1 | SI Units |

---

## Priority Standards (Welding/Piping)

For WPS/PQR development, focus on A-series and B-series:

```python
PRIORITY_CODES = [
    "A0105",  # Carbon Steel Forgings
    "A0106",  # Seamless Carbon Steel Pipe
    "A0182",  # Forged Alloy/Stainless Fittings
    "A0193",  # Alloy Steel Bolting
    "A0194",  # Carbon/Alloy Steel Nuts
    "A0234",  # Wrought Carbon Steel Fittings
    "A0312",  # Austenitic Stainless Steel Pipe
    "A0333",  # Low-Temperature Pipe
    "A0350",  # Low-Temperature Forgings
    "A0403",  # Wrought Austenitic SS Fittings
    "A0516",  # Pressure Vessel Plate
]

priority = [s for s in standards if any(s["code"].startswith(p) for p in PRIORITY_CODES)]
```

