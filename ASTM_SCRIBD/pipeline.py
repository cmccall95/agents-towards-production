"""
Main extraction pipeline for ASTM documents from Scribd.

Orchestrates search, fetch, and conversion in testable phases.

Usage:
    # Phase 1: Test single standard
    python pipeline.py --phase 1

    # Phase 2: Test batch of 5-10
    python pipeline.py --phase 2

    # Phase 3: Full batch processing
    python pipeline.py --phase 3 --batch 0
"""
import argparse
import json
import logging
import time
from dataclasses import dataclass, field, asdict
from datetime import datetime
from pathlib import Path
from typing import Optional

from config import (
    ensure_directories,
    validate_config,
    MARKDOWN_DIR,
    LOGS_DIR,
    CHECKPOINTS_DIR,
    processing_config,
)
from load_astm_list import (
    load_standards,
    get_priority_standards,
    get_batch,
    ASTMStandard,
)
from crawlbase_client import CrawlbaseClient
from scribd_search import ScribdSearcher, SearchResult
from markdown_converter import ScribdMarkdownConverter, ConversionResult

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(levelname)s - %(message)s",
)
logger = logging.getLogger(__name__)


@dataclass
class ExtractionResult:
    """Result of extracting a single standard."""

    code: str
    designation: str
    success: bool
    scribd_doc_id: Optional[str] = None
    scribd_title: Optional[str] = None
    scribd_url: Optional[str] = None
    markdown_file: Optional[str] = None
    word_count: int = 0
    error: Optional[str] = None
    timestamp: str = field(default_factory=lambda: datetime.now().isoformat())


@dataclass
class BatchResult:
    """Result of processing a batch of standards."""

    batch_id: str
    phase: int
    started_at: str
    completed_at: Optional[str] = None
    total: int = 0
    successful: int = 0
    failed: int = 0
    results: list[ExtractionResult] = field(default_factory=list)
    api_stats: dict = field(default_factory=dict)


class ExtractionPipeline:
    """
    Main pipeline for extracting ASTM documents from Scribd.

    Phases:
        1. Single standard test (validates API connection)
        2. Small batch test (5-10 standards, validates parsing)
        3. Full batch processing (production mode)
    """

    def __init__(self, dry_run: bool = False):
        """
        Initialize pipeline.

        Args:
            dry_run: If True, simulate without actual API calls
        """
        self.dry_run = dry_run
        self.client: Optional[CrawlbaseClient] = None
        self.searcher: Optional[ScribdSearcher] = None
        self.converter = ScribdMarkdownConverter()

        # Ensure directories exist
        ensure_directories()

    def _init_client(self):
        """Initialize Crawlbase client and searcher."""
        if self.client is None:
            self.client = CrawlbaseClient(use_js=True)
            self.searcher = ScribdSearcher(self.client)

    def _close_client(self):
        """Close client connections."""
        if self.searcher:
            self.searcher.close()
            self.searcher = None
            self.client = None

    def extract_single(self, standard: ASTMStandard) -> ExtractionResult:
        """
        Extract a single ASTM standard from Scribd.

        Args:
            standard: ASTM standard to extract

        Returns:
            ExtractionResult with outcome
        """
        logger.info(f"Extracting: {standard.designation}")

        if self.dry_run:
            return ExtractionResult(
                code=standard.code,
                designation=standard.designation,
                success=True,
                error="DRY RUN - no actual extraction",
            )

        self._init_client()

        try:
            # Step 1: Search for document
            search_result, doc_response = self.searcher.find_and_fetch(standard)

            if not search_result.success:
                return ExtractionResult(
                    code=standard.code,
                    designation=standard.designation,
                    success=False,
                    error=f"Search failed: {search_result.error}",
                )

            if not search_result.best_match:
                return ExtractionResult(
                    code=standard.code,
                    designation=standard.designation,
                    success=False,
                    error="No matching documents found on Scribd",
                )

            if not doc_response or not doc_response.success:
                return ExtractionResult(
                    code=standard.code,
                    designation=standard.designation,
                    success=False,
                    scribd_doc_id=search_result.best_match.doc_id,
                    scribd_title=search_result.best_match.title,
                    scribd_url=search_result.best_match.url,
                    error=f"Fetch failed: {doc_response.error if doc_response else 'No response'}",
                )

            # Step 2: Convert to markdown
            conversion = self.converter.convert(
                doc_response.content,
                standard,
                search_result.best_match,
            )

            if not conversion.success:
                return ExtractionResult(
                    code=standard.code,
                    designation=standard.designation,
                    success=False,
                    scribd_doc_id=search_result.best_match.doc_id,
                    scribd_title=search_result.best_match.title,
                    scribd_url=search_result.best_match.url,
                    error=f"Conversion failed: {conversion.error}",
                )

            # Step 3: Save markdown
            filepath = self.converter.save(conversion, standard)

            return ExtractionResult(
                code=standard.code,
                designation=standard.designation,
                success=True,
                scribd_doc_id=search_result.best_match.doc_id,
                scribd_title=search_result.best_match.title,
                scribd_url=search_result.best_match.url,
                markdown_file=str(filepath.relative_to(MARKDOWN_DIR.parent)),
                word_count=conversion.word_count,
            )

        except Exception as e:
            logger.exception(f"Error extracting {standard.code}")
            return ExtractionResult(
                code=standard.code,
                designation=standard.designation,
                success=False,
                error=str(e),
            )

    def run_phase1(self) -> BatchResult:
        """
        Phase 1: Test single standard.

        Validates:
            - API connection works
            - Search returns results
            - Document can be fetched
            - Conversion produces valid markdown
        """
        logger.info("=" * 50)
        logger.info("PHASE 1: Single Standard Test")
        logger.info("=" * 50)

        # Validate configuration
        issues = validate_config()
        if issues:
            for issue in issues:
                logger.error(f"Config issue: {issue}")
            return BatchResult(
                batch_id="phase1_config_error",
                phase=1,
                started_at=datetime.now().isoformat(),
                completed_at=datetime.now().isoformat(),
                total=0,
                failed=1,
                results=[
                    ExtractionResult(
                        code="CONFIG",
                        designation="Configuration",
                        success=False,
                        error="; ".join(issues),
                    )
                ],
            )

        # Load a test standard (A106 - common piping standard)
        standards = load_standards()
        test_standard = None
        for s in standards:
            if s.code.startswith("A0106"):
                test_standard = s
                break

        if not test_standard:
            test_standard = standards[0]

        batch = BatchResult(
            batch_id="phase1_test",
            phase=1,
            started_at=datetime.now().isoformat(),
            total=1,
        )

        result = self.extract_single(test_standard)
        batch.results.append(result)

        if result.success:
            batch.successful = 1
            logger.info(f"SUCCESS: {result.code}")
            logger.info(f"  Document: {result.scribd_title}")
            logger.info(f"  Words: {result.word_count}")
            logger.info(f"  File: {result.markdown_file}")
        else:
            batch.failed = 1
            logger.error(f"FAILED: {result.code} - {result.error}")

        batch.completed_at = datetime.now().isoformat()

        if self.client:
            batch.api_stats = self.client.get_stats()

        self._save_batch_result(batch)
        return batch

    def run_phase2(self, count: int = 5) -> BatchResult:
        """
        Phase 2: Small batch test.

        Tests priority standards to validate:
            - Batch processing works
            - Different standard types parse correctly
            - Error handling is robust
        """
        logger.info("=" * 50)
        logger.info(f"PHASE 2: Small Batch Test ({count} standards)")
        logger.info("=" * 50)

        # Get priority standards
        standards = load_standards()
        priority = get_priority_standards(standards)[:count]

        if len(priority) < count:
            # Add more from A-series if needed
            a_series = [s for s in standards if s.series == "A"]
            priority.extend(a_series[: count - len(priority)])

        batch = BatchResult(
            batch_id=f"phase2_batch_{count}",
            phase=2,
            started_at=datetime.now().isoformat(),
            total=len(priority),
        )

        for i, standard in enumerate(priority):
            logger.info(f"[{i + 1}/{len(priority)}] Processing {standard.code}")

            result = self.extract_single(standard)
            batch.results.append(result)

            if result.success:
                batch.successful += 1
                logger.info(f"  SUCCESS: {result.word_count} words")
            else:
                batch.failed += 1
                logger.error(f"  FAILED: {result.error}")

            # Small delay between requests
            time.sleep(0.5)

        batch.completed_at = datetime.now().isoformat()

        if self.client:
            batch.api_stats = self.client.get_stats()

        self._save_batch_result(batch)
        self._close_client()

        logger.info("=" * 50)
        logger.info(f"Phase 2 Complete: {batch.successful}/{batch.total} successful")
        logger.info("=" * 50)

        return batch

    def run_phase3(
        self,
        batch_num: int = 0,
        batch_size: int = 200,
    ) -> BatchResult:
        """
        Phase 3: Full batch processing.

        Args:
            batch_num: Batch number (0-indexed)
            batch_size: Standards per batch
        """
        logger.info("=" * 50)
        logger.info(f"PHASE 3: Full Batch Processing (Batch {batch_num})")
        logger.info("=" * 50)

        standards = load_standards()
        batch_standards = get_batch(standards, batch_num, batch_size)

        if not batch_standards:
            logger.warning(f"No standards for batch {batch_num}")
            return BatchResult(
                batch_id=f"phase3_batch_{batch_num:04d}_empty",
                phase=3,
                started_at=datetime.now().isoformat(),
                completed_at=datetime.now().isoformat(),
            )

        batch = BatchResult(
            batch_id=f"phase3_batch_{batch_num:04d}",
            phase=3,
            started_at=datetime.now().isoformat(),
            total=len(batch_standards),
        )

        checkpoint_interval = processing_config.checkpoint_interval

        for i, standard in enumerate(batch_standards):
            logger.info(f"[{i + 1}/{len(batch_standards)}] {standard.code}")

            result = self.extract_single(standard)
            batch.results.append(result)

            if result.success:
                batch.successful += 1
            else:
                batch.failed += 1
                logger.warning(f"  Failed: {result.error}")

            # Checkpoint save
            if (i + 1) % checkpoint_interval == 0:
                self._save_checkpoint(batch, i + 1)
                logger.info(f"  Checkpoint saved ({batch.successful} successful)")

        batch.completed_at = datetime.now().isoformat()

        if self.client:
            batch.api_stats = self.client.get_stats()

        self._save_batch_result(batch)
        self._close_client()

        logger.info("=" * 50)
        logger.info(f"Batch {batch_num} Complete: {batch.successful}/{batch.total}")
        logger.info("=" * 50)

        return batch

    def _save_batch_result(self, batch: BatchResult):
        """Save batch result to JSON file."""
        LOGS_DIR.mkdir(parents=True, exist_ok=True)
        filename = f"{batch.batch_id}_{datetime.now().strftime('%Y%m%d_%H%M%S')}.json"
        filepath = LOGS_DIR / filename

        with open(filepath, "w", encoding="utf-8") as f:
            # Convert results to dicts
            data = asdict(batch)
            json.dump(data, f, indent=2, default=str)

        logger.info(f"Results saved: {filepath}")

    def _save_checkpoint(self, batch: BatchResult, progress: int):
        """Save checkpoint for resume capability."""
        CHECKPOINTS_DIR.mkdir(parents=True, exist_ok=True)
        filename = f"{batch.batch_id}_checkpoint.json"
        filepath = CHECKPOINTS_DIR / filename

        data = asdict(batch)
        data["checkpoint_progress"] = progress

        with open(filepath, "w", encoding="utf-8") as f:
            json.dump(data, f, indent=2, default=str)


def main():
    """CLI entry point."""
    parser = argparse.ArgumentParser(
        description="ASTM Scribd Extraction Pipeline",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Phases:
  1  Single standard test (validates API connection)
  2  Small batch test (5-10 standards)
  3  Full batch processing

Examples:
  python pipeline.py --phase 1
  python pipeline.py --phase 2 --count 10
  python pipeline.py --phase 3 --batch 0 --batch-size 100
  python pipeline.py --phase 3 --batch 0 --dry-run
        """,
    )

    parser.add_argument(
        "--phase",
        type=int,
        choices=[1, 2, 3],
        default=1,
        help="Pipeline phase to run",
    )
    parser.add_argument(
        "--count",
        type=int,
        default=5,
        help="Number of standards for phase 2",
    )
    parser.add_argument(
        "--batch",
        type=int,
        default=0,
        help="Batch number for phase 3",
    )
    parser.add_argument(
        "--batch-size",
        type=int,
        default=200,
        help="Batch size for phase 3",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Simulate without API calls",
    )

    args = parser.parse_args()

    pipeline = ExtractionPipeline(dry_run=args.dry_run)

    if args.phase == 1:
        result = pipeline.run_phase1()
    elif args.phase == 2:
        result = pipeline.run_phase2(count=args.count)
    else:
        result = pipeline.run_phase3(batch_num=args.batch, batch_size=args.batch_size)

    # Print summary
    print("\n" + "=" * 50)
    print("SUMMARY")
    print("=" * 50)
    print(f"Phase: {result.phase}")
    print(f"Total: {result.total}")
    print(f"Successful: {result.successful}")
    print(f"Failed: {result.failed}")

    if result.api_stats:
        print(f"\nAPI Stats:")
        print(f"  Total requests: {result.api_stats.get('total_requests', 0)}")
        print(f"  Success rate: {result.api_stats.get('success_rate', 0):.1%}")

    return 0 if result.failed == 0 else 1


if __name__ == "__main__":
    exit(main())
