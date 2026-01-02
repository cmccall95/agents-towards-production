"""
Crawlbase API client for fetching web pages with JavaScript rendering.

See: https://crawlbase.com/docs/crawling-api/

Usage:
    from crawlbase_client import CrawlbaseClient

    client = CrawlbaseClient()
    result = client.fetch("https://example.com")
"""
import time
import logging
from dataclasses import dataclass
from typing import Optional
from urllib.parse import urlencode, quote

import requests

from config import crawlbase_config

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
)
logger = logging.getLogger(__name__)


@dataclass
class CrawlbaseResponse:
    """Response from Crawlbase API."""

    success: bool
    url: str
    original_status: Optional[int] = None
    pc_status: Optional[int] = None
    content: Optional[str] = None
    error: Optional[str] = None
    request_cost: int = 0  # 1 for success, 0 for failure

    @property
    def is_billable(self) -> bool:
        """Check if this request was billable (successful)."""
        return self.original_status == 200 and self.pc_status == 200


class CrawlbaseClient:
    """
    Client for Crawlbase Crawling API.

    Features:
        - JavaScript rendering support (for dynamic pages like Scribd)
        - Rate limiting (default 5 requests/sec)
        - Automatic retries with exponential backoff
        - Response caching headers support
    """

    def __init__(
        self,
        token: Optional[str] = None,
        use_js: bool = True,
        rate_limit: Optional[float] = None,
    ):
        """
        Initialize Crawlbase client.

        Args:
            token: API token (uses JS token from config if not specified)
            use_js: Whether to use JavaScript rendering
            rate_limit: Requests per second limit (default from config)
        """
        # Token selection
        if token:
            self.token = token
        elif use_js:
            self.token = crawlbase_config.js_token
        else:
            self.token = crawlbase_config.normal_token

        self.use_js = use_js
        self.base_url = crawlbase_config.base_url

        # Rate limiting
        self.request_delay = rate_limit or crawlbase_config.request_delay
        self._last_request_time = 0.0

        # Session for connection pooling
        self.session = requests.Session()
        self.session.headers.update({"Accept-Encoding": "gzip"})

        # Stats
        self.total_requests = 0
        self.successful_requests = 0
        self.failed_requests = 0

    def _wait_for_rate_limit(self):
        """Enforce rate limiting between requests."""
        elapsed = time.time() - self._last_request_time
        if elapsed < self.request_delay:
            time.sleep(self.request_delay - elapsed)
        self._last_request_time = time.time()

    def fetch(
        self,
        url: str,
        timeout: Optional[int] = None,
        retries: Optional[int] = None,
    ) -> CrawlbaseResponse:
        """
        Fetch a URL through Crawlbase API.

        Args:
            url: Target URL to fetch
            timeout: Request timeout in seconds
            retries: Number of retries on failure

        Returns:
            CrawlbaseResponse with content or error
        """
        if not self.token:
            return CrawlbaseResponse(
                success=False,
                url=url,
                error="No API token configured. Set CRAWLBASE_JS_TOKEN environment variable.",
            )

        timeout = timeout or crawlbase_config.timeout
        retries = retries if retries is not None else crawlbase_config.max_retries

        # Build API URL
        params = {
            "token": self.token,
            "url": url,
        }
        api_url = f"{self.base_url}?{urlencode(params, quote_via=quote)}"

        last_error = None
        for attempt in range(retries + 1):
            try:
                self._wait_for_rate_limit()
                self.total_requests += 1

                logger.debug(f"Fetching {url} (attempt {attempt + 1}/{retries + 1})")

                response = self.session.get(api_url, timeout=timeout)

                # Extract Crawlbase status codes from headers
                original_status = int(response.headers.get("original_status", 0))
                pc_status = int(response.headers.get("pc_status", response.status_code))

                # Check for rate limiting
                if response.status_code == 429:
                    wait_time = crawlbase_config.retry_delay * (2**attempt)
                    logger.warning(f"Rate limited. Waiting {wait_time}s before retry...")
                    time.sleep(wait_time)
                    continue

                # Check for success
                if pc_status == 200 and original_status == 200:
                    self.successful_requests += 1
                    return CrawlbaseResponse(
                        success=True,
                        url=url,
                        original_status=original_status,
                        pc_status=pc_status,
                        content=response.text,
                        request_cost=1,
                    )

                # Handle non-success status
                self.failed_requests += 1
                return CrawlbaseResponse(
                    success=False,
                    url=url,
                    original_status=original_status,
                    pc_status=pc_status,
                    error=f"Status: original={original_status}, pc={pc_status}",
                    request_cost=0 if pc_status != 200 else 1,
                )

            except requests.Timeout as e:
                last_error = f"Timeout after {timeout}s"
                logger.warning(f"Timeout fetching {url}: {e}")

            except requests.RequestException as e:
                last_error = str(e)
                logger.warning(f"Request error fetching {url}: {e}")

            # Exponential backoff before retry
            if attempt < retries:
                wait_time = crawlbase_config.retry_delay * (2**attempt)
                logger.info(f"Retrying in {wait_time}s...")
                time.sleep(wait_time)

        self.failed_requests += 1
        return CrawlbaseResponse(
            success=False,
            url=url,
            error=f"Failed after {retries + 1} attempts: {last_error}",
        )

    def fetch_scribd_search(self, query: str) -> CrawlbaseResponse:
        """
        Search Scribd for a document.

        Args:
            query: Search query (e.g., "ASTM A106")

        Returns:
            CrawlbaseResponse with search results HTML
        """
        search_url = f"https://www.scribd.com/search?query={quote(query)}"
        return self.fetch(search_url)

    def fetch_scribd_document(self, doc_id: str) -> CrawlbaseResponse:
        """
        Fetch a Scribd document by ID.

        Args:
            doc_id: Scribd document ID

        Returns:
            CrawlbaseResponse with document HTML
        """
        doc_url = f"https://www.scribd.com/document/{doc_id}"
        return self.fetch(doc_url)

    def get_stats(self) -> dict:
        """Get request statistics."""
        return {
            "total_requests": self.total_requests,
            "successful_requests": self.successful_requests,
            "failed_requests": self.failed_requests,
            "success_rate": (
                self.successful_requests / self.total_requests
                if self.total_requests > 0
                else 0.0
            ),
        }

    def close(self):
        """Close the session."""
        self.session.close()

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc_val, exc_tb):
        self.close()


def test_connection() -> bool:
    """Test Crawlbase API connection with a simple request."""
    client = CrawlbaseClient()

    if not client.token:
        print("ERROR: No Crawlbase token configured")
        print("Set CRAWLBASE_JS_TOKEN environment variable")
        return False

    print("Testing Crawlbase API connection...")
    print(f"Token: {client.token[:8]}...{client.token[-4:]}")

    # Test with a simple, fast-loading page
    result = client.fetch("https://httpbin.org/html")

    if result.success:
        print(f"SUCCESS: Fetched {len(result.content)} bytes")
        print(f"Status: original={result.original_status}, pc={result.pc_status}")
        return True
    else:
        print(f"FAILED: {result.error}")
        return False


if __name__ == "__main__":
    test_connection()
