"""
HTML to Markdown converter for Scribd documents.

Extracts readable content from Scribd HTML and converts to clean markdown.

Usage:
    from markdown_converter import ScribdMarkdownConverter

    converter = ScribdMarkdownConverter()
    markdown = converter.convert(html_content, standard)
"""
import re
import logging
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Optional

from bs4 import BeautifulSoup, NavigableString

from load_astm_list import ASTMStandard
from scribd_search import ScribdDocument
from config import MARKDOWN_DIR

logger = logging.getLogger(__name__)


@dataclass
class ConversionResult:
    """Result of markdown conversion."""

    success: bool
    markdown: Optional[str] = None
    word_count: int = 0
    error: Optional[str] = None
    title: Optional[str] = None


class ScribdMarkdownConverter:
    """
    Converts Scribd document HTML to clean markdown.

    Handles:
        - Text extraction from document layers
        - Table detection and formatting
        - Heading detection
        - List formatting
        - Metadata headers
    """

    # Content selectors in order of preference
    CONTENT_SELECTORS = [
        ".text_layer",
        ".document_text",
        "[data-document-content]",
        ".content_section",
        ".auto_mobile_layout",
        "article",
        ".reader_column",
    ]

    # Elements to skip
    SKIP_ELEMENTS = {
        "script",
        "style",
        "noscript",
        "nav",
        "header",
        "footer",
        "aside",
        "iframe",
        "button",
    }

    def __init__(self):
        """Initialize converter."""
        pass

    def _extract_text_content(self, soup: BeautifulSoup) -> str:
        """
        Extract main text content from Scribd HTML.

        Args:
            soup: BeautifulSoup object

        Returns:
            Extracted text content
        """
        # Try each selector in order
        for selector in self.CONTENT_SELECTORS:
            content = soup.select_one(selector)
            if content:
                return self._process_element(content)

        # Fallback: get body text
        body = soup.find("body")
        if body:
            return self._process_element(body)

        return ""

    def _process_element(self, element, depth: int = 0) -> str:
        """
        Recursively process an element to markdown.

        Args:
            element: BeautifulSoup element
            depth: Current nesting depth

        Returns:
            Markdown text
        """
        if element is None:
            return ""

        # Handle NavigableString (text nodes)
        if isinstance(element, NavigableString):
            text = str(element).strip()
            return text if text else ""

        # Skip certain elements
        if element.name in self.SKIP_ELEMENTS:
            return ""

        result = []

        # Handle specific elements
        if element.name in ("h1", "h2", "h3", "h4", "h5", "h6"):
            level = int(element.name[1])
            text = element.get_text(strip=True)
            if text:
                result.append(f"\n{'#' * level} {text}\n")

        elif element.name == "p":
            text = element.get_text(strip=True)
            if text:
                result.append(f"\n{text}\n")

        elif element.name in ("ul", "ol"):
            for i, li in enumerate(element.find_all("li", recursive=False)):
                prefix = "- " if element.name == "ul" else f"{i + 1}. "
                text = li.get_text(strip=True)
                if text:
                    result.append(f"{prefix}{text}\n")

        elif element.name == "table":
            result.append(self._process_table(element))

        elif element.name == "br":
            result.append("\n")

        elif element.name in ("strong", "b"):
            text = element.get_text(strip=True)
            if text:
                result.append(f"**{text}**")

        elif element.name in ("em", "i"):
            text = element.get_text(strip=True)
            if text:
                result.append(f"*{text}*")

        elif element.name == "a":
            text = element.get_text(strip=True)
            href = element.get("href", "")
            if text and href:
                result.append(f"[{text}]({href})")
            elif text:
                result.append(text)

        else:
            # Process children for container elements
            for child in element.children:
                child_text = self._process_element(child, depth + 1)
                if child_text:
                    result.append(child_text)

        return " ".join(result)

    def _process_table(self, table) -> str:
        """
        Convert HTML table to markdown table.

        Args:
            table: BeautifulSoup table element

        Returns:
            Markdown table string
        """
        rows = []

        for tr in table.find_all("tr"):
            cells = []
            for td in tr.find_all(["td", "th"]):
                cell_text = td.get_text(strip=True)
                cells.append(cell_text or " ")
            if cells:
                rows.append(cells)

        if not rows:
            return ""

        # Build markdown table
        lines = []

        # Header row
        if rows:
            header = rows[0]
            lines.append("| " + " | ".join(header) + " |")
            lines.append("| " + " | ".join(["---"] * len(header)) + " |")

        # Data rows
        for row in rows[1:]:
            # Pad row if needed
            while len(row) < len(rows[0]):
                row.append(" ")
            lines.append("| " + " | ".join(row[: len(rows[0])]) + " |")

        return "\n" + "\n".join(lines) + "\n"

    def _extract_title(self, soup: BeautifulSoup) -> str:
        """Extract document title from HTML."""
        # Try meta title
        meta_title = soup.find("meta", property="og:title")
        if meta_title and meta_title.get("content"):
            return meta_title["content"]

        # Try title tag
        title_tag = soup.find("title")
        if title_tag:
            title = title_tag.get_text(strip=True)
            # Remove " - Scribd" suffix
            title = re.sub(r"\s*[-|]\s*Scribd.*$", "", title)
            return title

        # Try h1
        h1 = soup.find("h1")
        if h1:
            return h1.get_text(strip=True)

        return ""

    def _clean_markdown(self, text: str) -> str:
        """
        Clean up markdown text.

        Args:
            text: Raw markdown text

        Returns:
            Cleaned markdown
        """
        # Remove excessive whitespace
        text = re.sub(r"\n{3,}", "\n\n", text)

        # Remove leading/trailing whitespace from lines
        lines = [line.strip() for line in text.split("\n")]
        text = "\n".join(lines)

        # Remove empty list items
        text = re.sub(r"^[-*]\s*$", "", text, flags=re.MULTILINE)

        # Normalize spaces
        text = re.sub(r" +", " ", text)

        return text.strip()

    def convert(
        self,
        html: str,
        standard: ASTMStandard,
        document: Optional[ScribdDocument] = None,
    ) -> ConversionResult:
        """
        Convert Scribd HTML to markdown.

        Args:
            html: Raw HTML content
            standard: ASTM standard being processed
            document: Optional ScribdDocument with metadata

        Returns:
            ConversionResult with markdown content
        """
        try:
            soup = BeautifulSoup(html, "html.parser")

            # Extract title
            title = self._extract_title(soup)
            if not title and document:
                title = document.title

            # Extract content
            content = self._extract_text_content(soup)

            if not content:
                return ConversionResult(
                    success=False,
                    error="No text content found in document",
                )

            # Clean content
            content = self._clean_markdown(content)

            # Build markdown with header
            header = self._build_header(standard, document, title)
            markdown = f"{header}\n\n{content}"

            word_count = len(content.split())

            return ConversionResult(
                success=True,
                markdown=markdown,
                word_count=word_count,
                title=title,
            )

        except Exception as e:
            logger.exception(f"Error converting HTML for {standard.code}")
            return ConversionResult(
                success=False,
                error=str(e),
            )

    def _build_header(
        self,
        standard: ASTMStandard,
        document: Optional[ScribdDocument],
        title: str,
    ) -> str:
        """Build markdown header with metadata."""
        lines = [
            f"<!-- ASTM Standard: {standard.designation} -->",
            f"<!-- Source: Scribd -->",
        ]

        if document:
            lines.append(f"<!-- Document ID: {document.doc_id} -->")
            lines.append(f"<!-- URL: {document.url} -->")

        lines.append(f"<!-- Extracted: {datetime.now().isoformat()} -->")
        lines.append("")
        lines.append(f"# {standard.designation}")
        lines.append("")

        if title and title != standard.designation:
            lines.append(f"**{title}**")
            lines.append("")

        lines.append("---")

        return "\n".join(lines)

    def save(
        self,
        result: ConversionResult,
        standard: ASTMStandard,
        output_dir: Optional[Path] = None,
    ) -> Path:
        """
        Save markdown to file.

        Args:
            result: ConversionResult to save
            standard: ASTM standard
            output_dir: Output directory (defaults to MARKDOWN_DIR)

        Returns:
            Path to saved file
        """
        output_dir = output_dir or MARKDOWN_DIR
        output_dir.mkdir(parents=True, exist_ok=True)

        filename = f"{standard.filename_safe}.md"
        filepath = output_dir / filename

        with open(filepath, "w", encoding="utf-8") as f:
            f.write(result.markdown)

        logger.info(f"Saved: {filepath} ({result.word_count} words)")
        return filepath


if __name__ == "__main__":
    # Demo with sample HTML
    sample_html = """
    <!DOCTYPE html>
    <html>
    <head>
        <title>ASTM A106 Standard Specification - Scribd</title>
        <meta property="og:title" content="ASTM A106 Standard Specification for Seamless Carbon Steel Pipe">
    </head>
    <body>
        <div class="text_layer">
            <h1>Standard Specification for Seamless Carbon Steel Pipe</h1>
            <p>This specification covers seamless carbon steel pipe for high-temperature service.</p>
            <h2>Scope</h2>
            <p>1.1 This specification covers seamless carbon steel pipe for high-temperature service (Note 1) in NPS 1⁄8 to NPS 48 inclusive, with nominal (average) wall thickness as given in ASME B 36.10.</p>
            <h2>Chemical Requirements</h2>
            <table>
                <tr><th>Grade</th><th>Carbon</th><th>Manganese</th></tr>
                <tr><td>A</td><td>0.25</td><td>0.27-0.93</td></tr>
                <tr><td>B</td><td>0.30</td><td>0.29-1.06</td></tr>
                <tr><td>C</td><td>0.35</td><td>0.29-1.06</td></tr>
            </table>
        </div>
    </body>
    </html>
    """

    from load_astm_list import ASTMStandard

    # Create test standard
    test_standard = ASTMStandard(
        designation="ASTM A0106-22",
        code="A0106-22",
        series="A",
        has_metric=False,
    )

    converter = ScribdMarkdownConverter()
    result = converter.convert(sample_html, test_standard)

    if result.success:
        print("=== Conversion Result ===\n")
        print(f"Title: {result.title}")
        print(f"Word count: {result.word_count}")
        print("\n--- Markdown ---\n")
        print(result.markdown)
    else:
        print(f"Conversion failed: {result.error}")
