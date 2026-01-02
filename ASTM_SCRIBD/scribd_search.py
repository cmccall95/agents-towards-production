"""
Scribd document search and extraction module.

Finds official ASTM documents on Scribd and extracts content.

Usage:
    from scribd_search import ScribdSearcher

    searcher = ScribdSearcher()
    results = searcher.find_astm_document("A106")
"""
import re
import logging
from dataclasses import dataclass, field
from typing import Optional
from urllib.parse import urljoin

from bs4 import BeautifulSoup

from crawlbase_client import CrawlbaseClient, CrawlbaseResponse
from load_astm_list import ASTMStandard

logger = logging.getLogger(__name__)


@dataclass
class ScribdDocument:
    """Represents a Scribd document found via search."""

    doc_id: str
    title: str
    url: str
    author: Optional[str] = None
    pages: Optional[int] = None
    is_official: bool = False  # Whether it appears to be official ASTM
    relevance_score: float = 0.0

    @property
    def full_url(self) -> str:
        """Get full Scribd document URL."""
        return f"https://www.scribd.com/document/{self.doc_id}"


@dataclass
class SearchResult:
    """Result of an ASTM document search."""

    standard: ASTMStandard
    success: bool
    documents: list[ScribdDocument] = field(default_factory=list)
    best_match: Optional[ScribdDocument] = None
    error: Optional[str] = None
    search_url: Optional[str] = None


class ScribdSearcher:
    """
    Searches Scribd for ASTM documents and identifies official copies.

    Uses Crawlbase API for JavaScript rendering (required for Scribd).
    """

    # Patterns indicating official ASTM documents
    OFFICIAL_PATTERNS = [
        r"ASTM\s*[A-Z]\d+",  # ASTM A106, ASTM D1234
        r"Standard\s+Specification",
        r"Standard\s+Test\s+Method",
        r"Standard\s+Practice",
        r"Standard\s+Guide",
        r"American\s+Society\s+for\s+Testing",
    ]

    # Patterns suggesting unofficial/summary documents (lower score)
    UNOFFICIAL_PATTERNS = [
        r"summary",
        r"overview",
        r"presentation",
        r"lecture",
        r"notes",
        r"comparison",
    ]

    def __init__(self, client: Optional[CrawlbaseClient] = None):
        """
        Initialize searcher.

        Args:
            client: CrawlbaseClient instance (creates new if not provided)
        """
        self.client = client or CrawlbaseClient(use_js=True)
        self._compiled_official = [re.compile(p, re.IGNORECASE) for p in self.OFFICIAL_PATTERNS]
        self._compiled_unofficial = [re.compile(p, re.IGNORECASE) for p in self.UNOFFICIAL_PATTERNS]

    def _calculate_relevance(self, title: str, standard: ASTMStandard) -> tuple[float, bool]:
        """
        Calculate relevance score for a document title.

        Args:
            title: Document title
            standard: ASTM standard being searched

        Returns:
            Tuple of (score, is_official)
        """
        score = 0.0
        title_lower = title.lower()

        # Check for standard number match
        base_number = standard.base_number.lower()
        if base_number in title_lower:
            score += 50.0

        # Check for exact code match
        if standard.code.lower() in title_lower:
            score += 30.0

        # Check for official patterns
        is_official = False
        for pattern in self._compiled_official:
            if pattern.search(title):
                score += 10.0
                is_official = True

        # Penalize unofficial patterns
        for pattern in self._compiled_unofficial:
            if pattern.search(title):
                score -= 20.0
                is_official = False

        return score, is_official

    def _parse_search_results(
        self,
        html: str,
        standard: ASTMStandard,
    ) -> list[ScribdDocument]:
        """
        Parse Scribd search results HTML.

        Args:
            html: Raw HTML from search page
            standard: Standard being searched

        Returns:
            List of ScribdDocument objects
        """
        soup = BeautifulSoup(html, "html.parser")
        documents = []

        # Look for document links in search results
        # Scribd uses various selectors, try multiple patterns
        selectors = [
            'a[href*="/document/"]',
            'a[href*="/doc/"]',
            ".search-result a",
            '[data-e2e="search-result-title"]',
        ]

        seen_ids = set()

        for selector in selectors:
            for link in soup.select(selector):
                href = link.get("href", "")

                # Extract document ID
                match = re.search(r"/(?:document|doc)/(\d+)", href)
                if not match:
                    continue

                doc_id = match.group(1)
                if doc_id in seen_ids:
                    continue
                seen_ids.add(doc_id)

                # Get title
                title = link.get_text(strip=True)
                if not title:
                    title = link.get("title", f"Document {doc_id}")

                # Calculate relevance
                score, is_official = self._calculate_relevance(title, standard)

                documents.append(
                    ScribdDocument(
                        doc_id=doc_id,
                        title=title,
                        url=href if href.startswith("http") else urljoin("https://www.scribd.com", href),
                        is_official=is_official,
                        relevance_score=score,
                    )
                )

        # Sort by relevance
        documents.sort(key=lambda d: d.relevance_score, reverse=True)

        return documents

    def search(self, standard: ASTMStandard) -> SearchResult:
        """
        Search Scribd for an ASTM standard document.

        Args:
            standard: ASTMStandard to search for

        Returns:
            SearchResult with found documents
        """
        query = standard.scribd_search_query
        logger.info(f"Searching Scribd for: {query}")

        # Perform search
        response = self.client.fetch_scribd_search(query)

        if not response.success:
            return SearchResult(
                standard=standard,
                success=False,
                error=response.error,
                search_url=f"https://www.scribd.com/search?query={query}",
            )

        # Parse results
        documents = self._parse_search_results(response.content, standard)

        if not documents:
            return SearchResult(
                standard=standard,
                success=True,
                documents=[],
                error="No documents found",
                search_url=f"https://www.scribd.com/search?query={query}",
            )

        # Find best match (highest relevance, preferably official)
        official_docs = [d for d in documents if d.is_official]
        best_match = official_docs[0] if official_docs else documents[0]

        return SearchResult(
            standard=standard,
            success=True,
            documents=documents,
            best_match=best_match,
            search_url=f"https://www.scribd.com/search?query={query}",
        )

    def fetch_document(self, document: ScribdDocument) -> CrawlbaseResponse:
        """
        Fetch full document content from Scribd.

        Args:
            document: ScribdDocument to fetch

        Returns:
            CrawlbaseResponse with document HTML
        """
        logger.info(f"Fetching document: {document.title} ({document.doc_id})")
        return self.client.fetch_scribd_document(document.doc_id)

    def find_and_fetch(self, standard: ASTMStandard) -> tuple[SearchResult, Optional[CrawlbaseResponse]]:
        """
        Search for a standard and fetch the best match.

        Args:
            standard: ASTM standard to find

        Returns:
            Tuple of (SearchResult, optional document content)
        """
        result = self.search(standard)

        if not result.success or not result.best_match:
            return result, None

        content = self.fetch_document(result.best_match)
        return result, content

    def close(self):
        """Close the client."""
        self.client.close()

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc_val, exc_tb):
        self.close()


if __name__ == "__main__":
    # Demo usage
    from load_astm_list import load_standards

    logging.basicConfig(level=logging.INFO)

    print("=== Scribd Search Demo ===\n")

    # Load a test standard
    standards = load_standards()
    test_standard = None

    # Find A106 (common piping standard)
    for s in standards:
        if s.code.startswith("A0106"):
            test_standard = s
            break

    if not test_standard:
        test_standard = standards[0]

    print(f"Testing with: {test_standard.designation}")
    print(f"Search query: {test_standard.scribd_search_query}")
    print()

    # Note: This will only work with a valid Crawlbase token
    with ScribdSearcher() as searcher:
        result = searcher.search(test_standard)

        if result.success:
            print(f"Found {len(result.documents)} documents")
            if result.best_match:
                print(f"\nBest match:")
                print(f"  Title: {result.best_match.title}")
                print(f"  URL: {result.best_match.url}")
                print(f"  Official: {result.best_match.is_official}")
                print(f"  Score: {result.best_match.relevance_score}")
        else:
            print(f"Search failed: {result.error}")
