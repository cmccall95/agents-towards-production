"""
ASTM Grades and Materials Extractor using Gemini Flash

This module processes the master list of ASTM standards and extracts:
- Applicable grades for each standard
- Material types for each grade combination
- Additional metadata (scope, applications, etc.)

Uses:
- Tavily Search API to find web content about each ASTM standard
- Google's Gemini Flash model for efficient, cost-effective extraction

Input: astm_standards_list.json (from agent-with-tavily-web-access module)
Output: astm_grades_materials.json (enriched with grades and materials)
"""

import os
import json
import time
import logging
import re
from datetime import datetime
from pathlib import Path
from dataclasses import dataclass, asdict
from typing import Optional

from dotenv import load_dotenv
from tavily import TavilyClient
import google.generativeai as genai
from bs4 import BeautifulSoup, MarkupResemblesLocatorWarning
from markdownify import markdownify as md
import warnings

# Suppress BeautifulSoup warning for URL-like strings
warnings.filterwarnings("ignore", category=MarkupResemblesLocatorWarning)

# Load environment variables
load_dotenv()

# Configure logging
LOG_DIR = Path(__file__).parent / "output"
LOG_DIR.mkdir(exist_ok=True)

# Set up detailed logging with DEBUG level for file, INFO for console
file_handler = logging.FileHandler(LOG_DIR / "extraction.log")
file_handler.setLevel(logging.DEBUG)
file_handler.setFormatter(logging.Formatter("%(asctime)s [%(levelname)s] %(name)s - %(message)s"))

console_handler = logging.StreamHandler()
console_handler.setLevel(logging.INFO)
console_handler.setFormatter(logging.Formatter("%(asctime)s [%(levelname)s] %(message)s"))

logging.basicConfig(
    level=logging.DEBUG,
    handlers=[file_handler, console_handler]
)
logger = logging.getLogger(__name__)

# Validate API keys
TAVILY_API_KEY = os.environ.get("TAVILY_API_KEY")
GOOGLE_API_KEY = os.environ.get("GOOGLE_API_KEY")

if not TAVILY_API_KEY:
    raise ValueError("TAVILY_API_KEY not found in environment variables")
if not GOOGLE_API_KEY:
    raise ValueError("GOOGLE_API_KEY not found in environment variables")

# Initialize clients
tavily_client = TavilyClient(api_key=TAVILY_API_KEY)
genai.configure(api_key=GOOGLE_API_KEY)

# Use Gemini Flash for speed and cost efficiency
GEMINI_MODEL = "gemini-2.0-flash-exp"

# Paths
INPUT_DIR = Path(__file__).parent.parent / "output" / "astm_lists"
OUTPUT_DIR = Path(__file__).parent / "output" / "grade_extractions"
RAW_CONTENT_DIR = OUTPUT_DIR / "raw_content"
MARKDOWN_DIR = OUTPUT_DIR / "markdown"

# Ensure output directories exist
OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
RAW_CONTENT_DIR.mkdir(parents=True, exist_ok=True)
MARKDOWN_DIR.mkdir(parents=True, exist_ok=True)

# Rate limiting settings
TAVILY_DELAY = 0.5  # seconds between Tavily requests
GEMINI_DELAY = 0.2  # seconds between Gemini requests

# Processing limits (set to None for full processing)
MAX_STANDARDS_TO_PROCESS =5  # Start with 50 for testing


@dataclass
class GradeInfo:
    """Information about a specific grade within a standard."""
    grade: str
    material: Optional[str] = None
    chemical_composition: Optional[str] = None
    mechanical_properties: Optional[str] = None
    applications: Optional[str] = None


@dataclass
class StandardInfo:
    """Complete information about an ASTM standard."""
    designation: str
    code: str
    series: str
    title: Optional[str] = None
    scope: Optional[str] = None
    grades: Optional[list[dict]] = None  # Each grade has: grade, material, chemical_composition, mechanical_properties, applications
    extraction_status: str = "pending"
    extraction_error: Optional[str] = None
    extracted_at: Optional[str] = None


def search_standard_info(designation: str) -> tuple[Optional[str], Optional[list[dict]], Optional[str]]:
    """
    Search the web for information about an ASTM standard using Tavily Search.

    Args:
        designation: Full designation like "ASTM A0105-21"

    Returns:
        tuple: (combined_content, sources_list, error_message)
               - content is None if failed
               - sources_list contains {url, title} for each source
    """
    # Build search query focused on grades and materials
    search_query = f"{designation} grades materials specification"

    logger.debug(f"Tavily Search query: {search_query}")

    try:
        # Use Tavily Search API (not Extract)
        response = tavily_client.search(
            query=search_query,
            search_depth="advanced",  # More thorough search
            max_results=5,  # Get top 5 results
            include_raw_content=True,  # Get full page content
        )

        logger.debug(f"Tavily response type: {type(response)}")

        if not response:
            error_msg = "Tavily returned empty/null response"
            logger.error(f"{error_msg} for {designation}")
            return None, None, error_msg

        if not isinstance(response, dict):
            error_msg = f"Tavily returned unexpected type: {type(response)}"
            logger.error(f"{error_msg} for {designation}")
            return None, None, error_msg

        # Check for results
        results = response.get("results", [])
        logger.debug(f"Search results count: {len(results)}")

        if len(results) == 0:
            error_msg = "Tavily search returned no results"
            logger.warning(f"{error_msg} for {designation}")
            return None, None, error_msg

        # Combine content from all results
        combined_content = []
        sources = []

        for i, result in enumerate(results):
            title = result.get("title", "Unknown")
            url = result.get("url", "")
            content = result.get("raw_content") or result.get("content", "")

            if content:
                combined_content.append(f"--- Source {i+1}: {title} ---\nURL: {url}\n\n{content}\n")
                sources.append({"url": url, "title": title})
                logger.debug(f"Result {i+1}: {title} ({len(content)} chars)")

        if not combined_content:
            error_msg = "No content found in any search results"
            logger.warning(f"{error_msg} for {designation}")
            return None, None, error_msg

        full_content = "\n".join(combined_content)
        logger.info(f"Collected {len(full_content)} chars from {len(sources)} sources for {designation}")
        logger.debug(f"Sources: {[s['url'] for s in sources]}")

        return full_content, sources, None

    except ConnectionError as e:
        error_msg = f"Network connection error: {e}"
        logger.error(f"{error_msg} for {designation}")
        return None, None, error_msg

    except TimeoutError as e:
        error_msg = f"Request timeout: {e}"
        logger.error(f"{error_msg} for {designation}")
        return None, None, error_msg

    except Exception as e:
        exc_type = type(e).__name__
        error_msg = f"{exc_type}: {e}"
        logger.error(f"Tavily search error for {designation}: {error_msg}")

        import traceback
        logger.debug(f"Full traceback:\n{traceback.format_exc()}")

        # Check for common error patterns
        error_str = str(e).lower()
        if "401" in error_str or "unauthorized" in error_str:
            error_msg = f"Authentication error (401): Check TAVILY_API_KEY - {e}"
        elif "429" in error_str or "rate limit" in error_str:
            error_msg = f"Rate limited (429): Too many requests - {e}"

        return None, None, error_msg


def save_raw_content(code: str, content: str, sources: list[dict]) -> Path:
    """
    Save raw content fetched from Tavily to a text file.

    Args:
        code: Standard code (e.g., "A0001-00R18")
        content: Combined raw content from all sources
        sources: List of source metadata (url, title)

    Returns:
        Path to the saved file
    """
    filename = f"{code.lower()}.txt"
    filepath = RAW_CONTENT_DIR / filename

    # Build header with source information
    header = f"# Raw Content for {code}\n"
    header += f"# Fetched: {datetime.now().isoformat()}\n"
    header += "# Sources:\n"
    for i, src in enumerate(sources, 1):
        header += f"#   {i}. {src.get('title', 'Unknown')} - {src.get('url', 'N/A')}\n"
    header += "#" + "=" * 70 + "\n\n"

    with open(filepath, "w", encoding="utf-8") as f:
        f.write(header + content)

    logger.debug(f"Saved raw content to: {filepath}")
    return filepath


def clean_html_to_markdown(html_content: str) -> str:
    """
    Parse HTML with BeautifulSoup and convert to clean, structured Markdown.

    Args:
        html_content: Raw HTML or mixed content from web scraping

    Returns:
        Clean, well-structured markdown text
    """
    # Parse with BeautifulSoup (use lxml for speed, fall back to html.parser)
    try:
        soup = BeautifulSoup(html_content, 'lxml')
    except Exception:
        soup = BeautifulSoup(html_content, 'html.parser')

    # Remove non-content elements
    for tag in soup.find_all(['script', 'style', 'nav', 'header', 'footer',
                               'aside', 'iframe', 'noscript', 'meta', 'link']):
        tag.decompose()

    # Remove comments
    from bs4 import Comment
    for comment in soup.find_all(string=lambda text: isinstance(text, Comment)):
        comment.extract()

    # Remove empty tags
    for tag in soup.find_all():
        if not tag.get_text(strip=True) and tag.name not in ['br', 'hr', 'img']:
            tag.decompose()

    # Convert to markdown using markdownify
    # Configure for clean output with proper heading structure
    markdown_text = md(
        str(soup),
        heading_style="ATX",           # Use # style headings
        bullets="-",                    # Use - for lists
        strip=['a'] if not soup.find('a') else [],  # Keep links if present
        newline_style="backslash",      # Clean line breaks
    )

    # Post-process: clean up excessive whitespace and normalize formatting
    lines = markdown_text.split('\n')
    cleaned_lines = []
    prev_blank = False

    for line in lines:
        line = line.rstrip()
        is_blank = not line.strip()

        # Skip multiple consecutive blank lines
        if is_blank and prev_blank:
            continue

        # Clean up common artifacts
        line = re.sub(r'\s+', ' ', line) if not line.startswith('#') and not line.startswith('-') else line
        line = re.sub(r'^\s*[\*\-]\s*$', '', line)  # Remove empty list items

        if line or not prev_blank:
            cleaned_lines.append(line)

        prev_blank = is_blank

    return '\n'.join(cleaned_lines).strip()


def save_markdown(code: str, designation: str, title: str, content: str, sources: list[dict]) -> Path:
    """
    Parse HTML content with BeautifulSoup, convert to clean Markdown, and save.

    Args:
        code: Standard code (e.g., "A0001-00R18")
        designation: Full designation (e.g., "ASTM A0001-00R18")
        title: Standard title if available
        content: Raw content (may contain HTML) to convert
        sources: List of source metadata (url, title)

    Returns:
        Path to the saved Markdown file
    """
    filename = f"{code.lower()}.md"
    filepath = MARKDOWN_DIR / filename

    # Build structured Markdown header
    md_content = f"# {designation}\n\n"
    if title:
        md_content += f"**{title}**\n\n"
    md_content += "---\n\n"

    # Add source references section
    md_content += "## Sources\n\n"
    for i, src in enumerate(sources, 1):
        url = src.get('url', '#')
        title_text = src.get('title', 'Unknown Source')
        md_content += f"{i}. [{title_text}]({url})\n"
    md_content += "\n---\n\n"

    # Process each source's content separately for better structure
    md_content += "## Content\n\n"

    # Split content by source markers and process each
    source_pattern = r'--- Source \d+: (.+?) ---\nURL: (.+?)\n\n'
    source_splits = re.split(source_pattern, content)

    if len(source_splits) > 1:
        # Content has source markers - process each section
        i = 0
        source_num = 1
        while i < len(source_splits):
            if i == 0 and source_splits[i].strip():
                # Content before first source marker
                cleaned = clean_html_to_markdown(source_splits[i])
                if cleaned:
                    md_content += cleaned + "\n\n"
            elif i + 2 < len(source_splits):
                # Source title, URL, and content
                source_title = source_splits[i]
                source_url = source_splits[i + 1]
                source_content = source_splits[i + 2] if i + 2 < len(source_splits) else ""

                md_content += f"### Source {source_num}: {source_title}\n\n"
                md_content += f"*URL: {source_url}*\n\n"

                cleaned = clean_html_to_markdown(source_content)
                if cleaned:
                    md_content += cleaned + "\n\n"

                source_num += 1
                i += 2
            i += 1
    else:
        # No source markers - process entire content
        cleaned = clean_html_to_markdown(content)
        md_content += cleaned

    # Final cleanup - remove excessive blank lines
    md_content = re.sub(r'\n{3,}', '\n\n', md_content)

    with open(filepath, "w", encoding="utf-8") as f:
        f.write(md_content)

    logger.debug(f"Saved Markdown to: {filepath}")
    return filepath


def extract_grades_with_gemini(content: str, designation: str) -> dict:
    """
    Use Gemini Flash to extract grades and materials from standard content.

    Returns a dict with:
        - title: Standard title
        - scope: Brief scope description
        - grades: List of grade objects with material properties
    """
    prompt = f"""Analyze the following ASTM standard content for {designation} and extract structured information.

CONTENT:
{content[:15000]}  # Limit content to avoid token limits

EXTRACT THE FOLLOWING (respond in JSON format only):
{{
    "title": "Full title of the standard (e.g., 'Standard Specification for Carbon Steel...')",
    "scope": "Brief 1-2 sentence scope description",
    "grades": [
        {{
            "grade": "Grade designation (e.g., 'Grade A', 'Grade B', 'Type 304', 'Class 1')",
            "material": "Material type (e.g., 'Carbon Steel', 'Stainless Steel 304', 'Aluminum Alloy')",
            "chemical_composition": "Key chemical elements and ranges if available (e.g., 'C: 0.25-0.35%, Mn: 0.60-0.90%')",
            "mechanical_properties": "Key mechanical properties if available (e.g., 'Tensile: 70 ksi min, Yield: 36 ksi min')",
            "applications": "Typical applications if mentioned"
        }}
    ]
}}

IMPORTANT:
- Extract EVERY grade, class, type, or designation mentioned for this standard
- Each grade MUST have its specific material linked (not a general list)
- Include chemical composition if percentages or ranges are mentioned
- Include mechanical properties (tensile strength, yield strength, hardness, elongation) if available
- If no specific grades are defined, return an empty grades array
- Return ONLY valid JSON, no markdown formatting"""

    try:
        model = genai.GenerativeModel(GEMINI_MODEL)
        response = model.generate_content(prompt)

        # Extract JSON from response
        response_text = response.text.strip()

        # Handle markdown code blocks
        if response_text.startswith("```"):
            # Remove markdown code block markers
            response_text = re.sub(r"^```(?:json)?\n?", "", response_text)
            response_text = re.sub(r"\n?```$", "", response_text)

        result = json.loads(response_text)
        return result

    except json.JSONDecodeError as e:
        logger.error(f"JSON parse error for {designation}: {e}")
        logger.debug(f"Raw response: {response.text[:500]}")
        return {"error": f"JSON parse error: {e}"}
    except Exception as e:
        logger.error(f"Gemini extraction error for {designation}: {e}")
        return {"error": str(e)}


def load_standards_list(filepath: Path) -> list[dict]:
    """Load the master list of ASTM standards."""
    logger.info(f"Loading standards from {filepath}")

    with open(filepath, "r", encoding="utf-8") as f:
        data = json.load(f)

    standards = data.get("standards", [])
    logger.info(f"Loaded {len(standards)} standards")

    return standards


def process_standard(standard: dict) -> StandardInfo:
    """Process a single standard: fetch content, save raw/markdown, and extract grades."""
    designation = standard.get("designation", "Unknown")
    code = standard.get("code", "")
    series = standard.get("series", "")

    logger.debug(f"Processing standard: {designation} (code: {code}, series: {series})")

    info = StandardInfo(
        designation=designation,
        code=code,
        series=series
    )

    # Search the web for information about this standard
    logger.info(f"Searching web for: {designation}")

    content, sources, search_error = search_standard_info(designation)
    time.sleep(TAVILY_DELAY)

    if not content:
        info.extraction_status = "failed"
        info.extraction_error = search_error or "Could not find content (unknown error)"
        logger.error(f"Failed to find content for {designation}: {info.extraction_error}")
        return info

    # Save raw content and markdown
    try:
        save_raw_content(code, content, sources or [])
        # We'll get the title after extraction, but save markdown now with placeholder
        save_markdown(code, designation, None, content, sources or [])
        logger.debug(f"Saved raw content and markdown for {code}")
    except Exception as e:
        logger.warning(f"Failed to save content files for {code}: {e}")

    # Extract grades using Gemini
    logger.info(f"Extracting grades for: {designation} (content size: {len(content)} chars)")
    extracted = extract_grades_with_gemini(content, designation)
    time.sleep(GEMINI_DELAY)

    if "error" in extracted:
        info.extraction_status = "partial"
        info.extraction_error = extracted["error"]
        logger.warning(f"Partial extraction for {designation}: {info.extraction_error}")
    else:
        info.extraction_status = "success"
        info.title = extracted.get("title")
        info.scope = extracted.get("scope")
        info.grades = extracted.get("grades", [])
        logger.info(f"Successfully extracted {designation}: {len(info.grades or [])} grades")

        # Update markdown with title now that we have it
        if info.title:
            try:
                save_markdown(code, designation, info.title, content, sources or [])
            except Exception as e:
                logger.warning(f"Failed to update markdown with title for {code}: {e}")

    info.extracted_at = datetime.now().isoformat()

    return info


def save_results(results: list[StandardInfo], filename: str) -> Path:
    """Save extraction results to JSON file."""
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    output_path = OUTPUT_DIR / filename

    output_data = {
        "timestamp": datetime.now().isoformat(),
        "model_used": GEMINI_MODEL,
        "total_processed": len(results),
        "successful": sum(1 for r in results if r.extraction_status == "success"),
        "failed": sum(1 for r in results if r.extraction_status == "failed"),
        "partial": sum(1 for r in results if r.extraction_status == "partial"),
        "standards": [asdict(r) for r in results]
    }

    with open(output_path, "w", encoding="utf-8") as f:
        json.dump(output_data, f, indent=2, ensure_ascii=False)

    logger.info(f"Results saved to: {output_path}")
    return output_path


def save_checkpoint(results: list[StandardInfo], checkpoint_num: int) -> Path:
    """Save intermediate checkpoint during long runs."""
    filename = f"checkpoint_{checkpoint_num}_{datetime.now().strftime('%Y%m%d_%H%M%S')}.json"
    return save_results(results, filename)


def main():
    """Main entry point for the grades extractor."""
    print("\n" + "=" * 60)
    print("ASTM Grades & Materials Extractor")
    print(f"Using: {GEMINI_MODEL}")
    print("=" * 60 + "\n")

    # Load standards list
    input_file = INPUT_DIR / "astm_standards_list.json"
    if not input_file.exists():
        logger.error(f"Input file not found: {input_file}")
        logger.info("Run the astm_scraper.py first to generate the standards list")
        return

    standards = load_standards_list(input_file)

    # Apply processing limit if set
    if MAX_STANDARDS_TO_PROCESS:
        standards = standards[:MAX_STANDARDS_TO_PROCESS]
        logger.info(f"Processing limited to first {MAX_STANDARDS_TO_PROCESS} standards")

    # Process standards
    results = []
    checkpoint_interval = 25  # Save checkpoint every 25 standards

    for i, standard in enumerate(standards, 1):
        print(f"\n[{i}/{len(standards)}] Processing: {standard.get('designation', 'Unknown')}")

        try:
            result = process_standard(standard)
            results.append(result)

            # Print summary
            if result.extraction_status == "success":
                grade_count = len(result.grades) if result.grades else 0
                print(f"  Success: {grade_count} grades extracted")
            else:
                print(f"  {result.extraction_status.upper()}: {result.extraction_error}")

            # Save checkpoint
            if i % checkpoint_interval == 0:
                save_checkpoint(results, i)

        except KeyboardInterrupt:
            logger.warning("Interrupted by user")
            break
        except Exception as e:
            logger.error(f"Unexpected error processing {standard}: {e}")
            continue

    # Save final results
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    output_file = f"astm_grades_materials_{timestamp}.json"
    output_path = save_results(results, output_file)

    # Print summary
    print("\n" + "=" * 60)
    print("EXTRACTION SUMMARY")
    print("=" * 60)
    print(f"Total processed: {len(results)}")
    print(f"Successful: {sum(1 for r in results if r.extraction_status == 'success')}")
    print(f"Failed: {sum(1 for r in results if r.extraction_status == 'failed')}")
    print(f"Partial: {sum(1 for r in results if r.extraction_status == 'partial')}")
    print(f"\nOutput: {output_path}")

    # Sample output
    successful = [r for r in results if r.extraction_status == "success"]
    if successful:
        print("\nSample extractions:")
        for r in successful[:3]:
            print(f"\n  {r.designation}:")
            print(f"    Title: {r.title[:60] if r.title else 'N/A'}...")
            print(f"    Grades: {len(r.grades) if r.grades else 0}")
            if r.grades:
                for g in r.grades[:2]:  # Show first 2 grades
                    print(f"      - {g.get('grade', 'N/A')}: {g.get('material', 'N/A')}")


if __name__ == "__main__":
    main()
