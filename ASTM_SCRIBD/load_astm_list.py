"""
Utility module to load and filter ASTM standards from master JSON.

Usage:
    from load_astm_list import load_standards, get_priority_standards, get_batch
"""
import json
import re
from pathlib import Path
from dataclasses import dataclass
from typing import Optional

from config import ASTM_LIST_PATH, processing_config


@dataclass
class ASTMStandard:
    """Represents a single ASTM standard."""

    designation: str  # Full designation (e.g., "ASTM A0106-22")
    code: str  # Code without ASTM prefix (e.g., "A0106-22")
    series: str  # Series letter (e.g., "A")
    has_metric: bool  # Has metric variant

    @property
    def base_number(self) -> str:
        """Extract base standard number (e.g., 'A106' from 'A0106-22')."""
        match = re.match(r"([A-Z]+)0*(\d+)", self.code)
        if match:
            return f"{match.group(1)}{match.group(2)}"
        return self.code.split("-")[0]

    @property
    def year(self) -> Optional[str]:
        """Extract year from code (e.g., '22' from 'A0106-22')."""
        match = re.search(r"-(\d{2})", self.code)
        return match.group(1) if match else None

    @property
    def revision(self) -> Optional[str]:
        """Extract revision info (e.g., 'R18' from 'A0001-00R18')."""
        match = re.search(r"-\d{2}([A-Z]+\d*(?:E\d+)?)", self.code)
        return match.group(1) if match else None

    @property
    def filename_safe(self) -> str:
        """Return filename-safe version of code (lowercase)."""
        return self.code.lower().replace("/", "_")

    @property
    def scribd_search_query(self) -> str:
        """Generate search query for Scribd."""
        return f"ASTM {self.base_number}"

    def to_dict(self) -> dict:
        """Convert to dictionary."""
        return {
            "designation": self.designation,
            "code": self.code,
            "series": self.series,
            "has_metric": self.has_metric,
            "base_number": self.base_number,
            "year": self.year,
            "revision": self.revision,
        }


def load_standards(path: Optional[Path] = None) -> list[ASTMStandard]:
    """
    Load all ASTM standards from master JSON file.

    Args:
        path: Path to JSON file (defaults to configured path)

    Returns:
        List of ASTMStandard objects
    """
    path = path or ASTM_LIST_PATH

    if not path.exists():
        raise FileNotFoundError(f"ASTM standards list not found: {path}")

    with open(path, "r", encoding="utf-8") as f:
        data = json.load(f)

    standards = []
    for item in data["standards"]:
        standards.append(
            ASTMStandard(
                designation=item["designation"],
                code=item["code"],
                series=item["series"],
                has_metric=item.get("has_metric", False),
            )
        )

    return standards


def load_standards_metadata(path: Optional[Path] = None) -> dict:
    """
    Load metadata about the standards list.

    Returns:
        Dictionary with source_url, scraped_at, total_count, series_breakdown
    """
    path = path or ASTM_LIST_PATH

    with open(path, "r", encoding="utf-8") as f:
        data = json.load(f)

    return {
        "source_url": data.get("source_url"),
        "scraped_at": data.get("scraped_at"),
        "total_count": data.get("total_count"),
        "series_breakdown": data.get("series_breakdown"),
    }


def get_priority_standards(standards: Optional[list[ASTMStandard]] = None) -> list[ASTMStandard]:
    """
    Get priority standards for initial testing (welding/piping related).

    Args:
        standards: List of standards (loads if not provided)

    Returns:
        Filtered list of priority standards
    """
    if standards is None:
        standards = load_standards()

    priority_codes = processing_config.priority_codes

    return [s for s in standards if any(s.code.startswith(code) for code in priority_codes)]


def filter_by_series(standards: list[ASTMStandard], series: str) -> list[ASTMStandard]:
    """Filter standards by series letter (A, B, C, etc.)."""
    return [s for s in standards if s.series == series.upper()]


def get_batch(
    standards: list[ASTMStandard],
    batch_num: int,
    batch_size: int = 200,
) -> list[ASTMStandard]:
    """
    Get a batch of standards for processing.

    Args:
        standards: Full list of standards
        batch_num: Batch number (0-indexed)
        batch_size: Number of standards per batch

    Returns:
        Slice of standards for the batch
    """
    start = batch_num * batch_size
    end = start + batch_size
    return standards[start:end]


def search_standards(
    standards: list[ASTMStandard],
    query: str,
) -> list[ASTMStandard]:
    """
    Search standards by code or designation.

    Args:
        standards: List to search
        query: Search term (case-insensitive)

    Returns:
        Matching standards
    """
    query = query.upper()
    return [
        s
        for s in standards
        if query in s.code.upper() or query in s.designation.upper() or query in s.base_number.upper()
    ]


if __name__ == "__main__":
    # Demo usage
    print("=== ASTM Standards Loader Demo ===\n")

    try:
        # Load metadata
        meta = load_standards_metadata()
        print(f"Source: {meta['source_url']}")
        print(f"Scraped: {meta['scraped_at']}")
        print(f"Total: {meta['total_count']} standards")
        print(f"Series: {meta['series_breakdown']}")
        print()

        # Load standards
        standards = load_standards()
        print(f"Loaded {len(standards)} standards")
        print()

        # Show first 5
        print("First 5 standards:")
        for s in standards[:5]:
            print(f"  {s.code} -> base={s.base_number}, year={s.year}, rev={s.revision}")
        print()

        # Priority standards
        priority = get_priority_standards(standards)
        print(f"Priority standards ({len(priority)}):")
        for s in priority[:5]:
            print(f"  {s.designation}")
        if len(priority) > 5:
            print(f"  ... and {len(priority) - 5} more")
        print()

        # Batch demo
        batch = get_batch(standards, 0, 10)
        print(f"Batch 0 (size=10): {len(batch)} standards")
        print(f"  First: {batch[0].code}")
        print(f"  Last: {batch[-1].code}")

    except FileNotFoundError as e:
        print(f"Error: {e}")
