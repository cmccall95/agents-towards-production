"""
Tests for ASTM Scribd extraction pipeline.

Run with: pytest tests/test_pipeline.py -v
"""
import json
import pytest
from pathlib import Path
from unittest.mock import Mock, patch, MagicMock

import sys
sys.path.insert(0, str(Path(__file__).parent.parent))

from config import ASTM_LIST_PATH, validate_config
from load_astm_list import (
    load_standards,
    load_standards_metadata,
    get_priority_standards,
    get_batch,
    filter_by_series,
    search_standards,
    ASTMStandard,
)
from crawlbase_client import CrawlbaseClient, CrawlbaseResponse
from scribd_search import ScribdSearcher, ScribdDocument
from markdown_converter import ScribdMarkdownConverter


class TestConfig:
    """Test configuration module."""

    def test_astm_list_path_exists(self):
        """ASTM list file should exist."""
        assert ASTM_LIST_PATH.exists(), f"ASTM list not found at {ASTM_LIST_PATH}"

    def test_validate_config_reports_missing_tokens(self):
        """Config validation should report missing API tokens."""
        with patch.dict("os.environ", {}, clear=True):
            from config import CrawlbaseConfig
            config = CrawlbaseConfig()
            # Token should be None without env var
            assert config.normal_token is None or config.js_token is None


class TestLoadASTMList:
    """Test ASTM list loading utilities."""

    def test_load_standards_returns_list(self):
        """Should load standards as list of ASTMStandard."""
        standards = load_standards()
        assert isinstance(standards, list)
        assert len(standards) > 0
        assert isinstance(standards[0], ASTMStandard)

    def test_load_standards_has_expected_count(self):
        """Should have approximately 11,109 standards."""
        standards = load_standards()
        assert len(standards) > 10000
        assert len(standards) < 15000

    def test_load_standards_metadata(self):
        """Should load metadata with expected fields."""
        meta = load_standards_metadata()
        assert "total_count" in meta
        assert "series_breakdown" in meta
        assert meta["total_count"] > 10000

    def test_astm_standard_base_number(self):
        """Base number should strip leading zeros."""
        s = ASTMStandard("ASTM A0106-22", "A0106-22", "A", False)
        assert s.base_number == "A106"

        s2 = ASTMStandard("ASTM D1234-20", "D1234-20", "D", False)
        assert s2.base_number == "D1234"

    def test_astm_standard_year_extraction(self):
        """Should extract year from code."""
        s = ASTMStandard("ASTM A0106-22", "A0106-22", "A", False)
        assert s.year == "22"

    def test_astm_standard_revision_extraction(self):
        """Should extract revision from code."""
        s = ASTMStandard("ASTM A0001-00R18", "A0001-00R18", "A", False)
        assert s.revision == "R18"

        s2 = ASTMStandard("ASTM A0106-22", "A0106-22", "A", False)
        assert s2.revision is None

    def test_astm_standard_filename_safe(self):
        """Filename should be lowercase and safe."""
        s = ASTMStandard("ASTM A0106-22", "A0106-22", "A", False)
        assert s.filename_safe == "a0106-22"

    def test_astm_standard_search_query(self):
        """Should generate valid search query."""
        s = ASTMStandard("ASTM A0106-22", "A0106-22", "A", False)
        assert s.scribd_search_query == "ASTM A106"

    def test_get_priority_standards(self):
        """Should return priority standards for testing."""
        priority = get_priority_standards()
        assert len(priority) > 0
        # Should include common standards like A106, A312
        codes = [s.code for s in priority]
        assert any("A0106" in c for c in codes) or any("A0312" in c for c in codes)

    def test_filter_by_series(self):
        """Should filter standards by series letter."""
        standards = load_standards()
        a_series = filter_by_series(standards, "A")
        assert all(s.series == "A" for s in a_series)
        assert len(a_series) > 100

    def test_get_batch(self):
        """Should return correct batch slice."""
        standards = load_standards()

        batch0 = get_batch(standards, 0, 100)
        assert len(batch0) == 100
        assert batch0[0] == standards[0]

        batch1 = get_batch(standards, 1, 100)
        assert len(batch1) == 100
        assert batch1[0] == standards[100]

    def test_search_standards(self):
        """Should search by code or designation."""
        standards = load_standards()

        results = search_standards(standards, "A106")
        assert len(results) > 0
        assert all("A106" in s.code.upper() or "A106" in s.base_number.upper() for s in results)


class TestCrawlbaseClient:
    """Test Crawlbase API client."""

    def test_client_initialization(self):
        """Client should initialize without error."""
        with patch.dict("os.environ", {"CRAWLBASE_JS_TOKEN": "test_token"}):
            from config import CrawlbaseConfig
            # Re-create config to pick up env var
            client = CrawlbaseClient(token="test_token")
            assert client.token == "test_token"

    def test_client_no_token_returns_error(self):
        """Fetch should return error if no token."""
        client = CrawlbaseClient(token=None)
        result = client.fetch("https://example.com")
        assert not result.success
        assert "token" in result.error.lower()

    def test_crawlbase_response_billable(self):
        """Should correctly identify billable requests."""
        success = CrawlbaseResponse(
            success=True,
            url="https://example.com",
            original_status=200,
            pc_status=200,
        )
        assert success.is_billable

        failure = CrawlbaseResponse(
            success=False,
            url="https://example.com",
            original_status=404,
            pc_status=200,
        )
        assert not failure.is_billable


class TestScribdSearcher:
    """Test Scribd search and document handling."""

    def test_scribd_document_url(self):
        """Document should have correct full URL."""
        doc = ScribdDocument(
            doc_id="12345",
            title="Test Doc",
            url="/document/12345/test",
        )
        assert doc.full_url == "https://www.scribd.com/document/12345"

    def test_relevance_calculation(self):
        """Should calculate relevance scores correctly."""
        mock_client = Mock()
        searcher = ScribdSearcher(mock_client)

        standard = ASTMStandard("ASTM A0106-22", "A0106-22", "A", False)

        # Title with standard number should score high
        score1, official1 = searcher._calculate_relevance(
            "ASTM A106 Standard Specification",
            standard,
        )
        assert score1 > 50
        assert official1

        # Title without standard should score low
        score2, official2 = searcher._calculate_relevance(
            "Some random document",
            standard,
        )
        assert score2 < score1


class TestMarkdownConverter:
    """Test HTML to Markdown conversion."""

    def test_basic_conversion(self):
        """Should convert simple HTML to markdown."""
        html = """
        <html>
        <head><title>ASTM A106 - Scribd</title></head>
        <body>
            <div class="text_layer">
                <h1>Standard Specification</h1>
                <p>This is a test paragraph.</p>
            </div>
        </body>
        </html>
        """
        standard = ASTMStandard("ASTM A0106-22", "A0106-22", "A", False)
        converter = ScribdMarkdownConverter()

        result = converter.convert(html, standard)

        assert result.success
        assert "Standard Specification" in result.markdown
        assert "test paragraph" in result.markdown

    def test_table_conversion(self):
        """Should convert HTML tables to markdown."""
        html = """
        <html>
        <body>
            <div class="text_layer">
                <table>
                    <tr><th>Grade</th><th>Carbon</th></tr>
                    <tr><td>A</td><td>0.25</td></tr>
                </table>
            </div>
        </body>
        </html>
        """
        standard = ASTMStandard("ASTM A0106-22", "A0106-22", "A", False)
        converter = ScribdMarkdownConverter()

        result = converter.convert(html, standard)

        assert result.success
        assert "| Grade | Carbon |" in result.markdown
        assert "| A | 0.25 |" in result.markdown

    def test_title_extraction(self):
        """Should extract title from various sources."""
        html = """
        <html>
        <head>
            <meta property="og:title" content="ASTM A106 Seamless Pipe">
            <title>Different Title - Scribd</title>
        </head>
        <body><div class="text_layer">Content</div></body>
        </html>
        """
        standard = ASTMStandard("ASTM A0106-22", "A0106-22", "A", False)
        converter = ScribdMarkdownConverter()

        result = converter.convert(html, standard)

        assert result.success
        # Should prefer og:title
        assert result.title == "ASTM A106 Seamless Pipe"

    def test_empty_content_fails(self):
        """Should fail gracefully on empty content."""
        html = "<html><body></body></html>"
        standard = ASTMStandard("ASTM A0106-22", "A0106-22", "A", False)
        converter = ScribdMarkdownConverter()

        result = converter.convert(html, standard)

        assert not result.success
        assert "No text content" in result.error


class TestIntegration:
    """Integration tests (require manual run with API token)."""

    @pytest.mark.skip(reason="Requires API token - run manually")
    def test_full_extraction_flow(self):
        """Test complete extraction of one standard."""
        from pipeline import ExtractionPipeline

        pipeline = ExtractionPipeline()
        standards = load_standards()

        # Find A106
        test_standard = None
        for s in standards:
            if s.code.startswith("A0106"):
                test_standard = s
                break

        if test_standard:
            result = pipeline.extract_single(test_standard)
            print(f"Result: {result}")
            # Don't assert success since it depends on API availability


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
