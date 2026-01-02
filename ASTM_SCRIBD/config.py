"""
Configuration for ASTM Scribd Scraper using Crawlbase API.

Environment Variables:
    CRAWLBASE_TOKEN: Normal token for static pages
    CRAWLBASE_JS_TOKEN: JavaScript token for dynamic pages (Scribd)
"""
import os
from pathlib import Path
from dataclasses import dataclass
from typing import Optional

# Base paths
PROJECT_ROOT = Path(__file__).parent.parent
ASTM_SCRIBD_ROOT = Path(__file__).parent
ASTM_LIST_PATH = PROJECT_ROOT / "tutorials/agent-with-tavily-web-access/output/astm_lists/astm_standards_list.json"

# Output directories
OUTPUT_DIR = ASTM_SCRIBD_ROOT / "output"
MARKDOWN_DIR = OUTPUT_DIR / "markdown"
LOGS_DIR = OUTPUT_DIR / "logs"
CHECKPOINTS_DIR = OUTPUT_DIR / "checkpoints"


@dataclass
class CrawlbaseConfig:
    """Crawlbase API configuration."""

    # API endpoints
    base_url: str = "https://api.crawlbase.com/"

    # Authentication tokens (from environment)
    normal_token: Optional[str] = None
    js_token: Optional[str] = None

    # Rate limiting (20 requests/sec max, we use conservative 5/sec)
    requests_per_second: float = 5.0
    request_delay: float = 0.2  # 200ms between requests

    # Timeout settings (Crawlbase recommends 90 seconds minimum)
    timeout: int = 90

    # Retry settings
    max_retries: int = 3
    retry_delay: float = 2.0  # seconds between retries

    def __post_init__(self):
        """Load tokens from environment."""
        self.normal_token = os.environ.get("CRAWLBASE_TOKEN")
        self.js_token = os.environ.get("CRAWLBASE_JS_TOKEN")

    @property
    def has_tokens(self) -> bool:
        """Check if any token is configured."""
        return bool(self.normal_token or self.js_token)

    @property
    def has_js_token(self) -> bool:
        """Check if JavaScript token is configured (needed for Scribd)."""
        return bool(self.js_token)


@dataclass
class ScribdConfig:
    """Scribd-specific configuration."""

    # Base URL for Scribd document search
    search_url: str = "https://www.scribd.com/search"

    # Document URL pattern
    document_url_pattern: str = "https://www.scribd.com/document/{doc_id}"

    # Search query templates
    search_template: str = "ASTM {designation} site:scribd.com"

    # Content selectors (for parsing)
    content_selectors: tuple = (
        ".document_content",
        ".text_layer",
        "[data-document-content]",
    )


@dataclass
class ProcessingConfig:
    """Batch processing configuration."""

    # Batch sizes for different phases
    test_batch_size: int = 5  # Phase 1: Initial testing
    small_batch_size: int = 50  # Phase 2: Validation
    full_batch_size: int = 200  # Phase 3: Production

    # Checkpointing
    checkpoint_interval: int = 25  # Save progress every N standards

    # Parallel processing
    max_workers: int = 4  # Conservative for API limits

    # Priority standards for initial testing (welding/piping)
    priority_codes: tuple = (
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
    )


# Global config instances
crawlbase_config = CrawlbaseConfig()
scribd_config = ScribdConfig()
processing_config = ProcessingConfig()


def ensure_directories():
    """Create all required directories."""
    for dir_path in [OUTPUT_DIR, MARKDOWN_DIR, LOGS_DIR, CHECKPOINTS_DIR]:
        dir_path.mkdir(parents=True, exist_ok=True)


def validate_config() -> list[str]:
    """Validate configuration and return list of issues."""
    issues = []

    if not ASTM_LIST_PATH.exists():
        issues.append(f"ASTM list not found: {ASTM_LIST_PATH}")

    if not crawlbase_config.has_tokens:
        issues.append("No Crawlbase tokens configured. Set CRAWLBASE_TOKEN or CRAWLBASE_JS_TOKEN")

    if not crawlbase_config.has_js_token:
        issues.append("No JavaScript token configured. Scribd requires JS rendering (CRAWLBASE_JS_TOKEN)")

    return issues


if __name__ == "__main__":
    # Print configuration status when run directly
    print("=== ASTM Scribd Scraper Configuration ===\n")

    print(f"Project Root: {PROJECT_ROOT}")
    print(f"ASTM List: {ASTM_LIST_PATH} (exists: {ASTM_LIST_PATH.exists()})")
    print(f"Output Dir: {OUTPUT_DIR}")
    print()

    print("Crawlbase Config:")
    print(f"  Normal Token: {'[SET]' if crawlbase_config.normal_token else '[NOT SET]'}")
    print(f"  JS Token: {'[SET]' if crawlbase_config.js_token else '[NOT SET]'}")
    print(f"  Request Delay: {crawlbase_config.request_delay}s")
    print(f"  Timeout: {crawlbase_config.timeout}s")
    print()

    issues = validate_config()
    if issues:
        print("Configuration Issues:")
        for issue in issues:
            print(f"  - {issue}")
    else:
        print("Configuration OK!")
