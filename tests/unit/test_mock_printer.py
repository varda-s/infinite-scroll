"""Tests for mock printer."""

from pathlib import Path

import pytest
from PIL import Image

from src.printing.mock_printer import MockPrinter
from src.printing.base import BasePrinter


class TestMockPrinter:
    """Tests for MockPrinter class."""

    def test_init_creates_output_dir(self, temp_dir: Path) -> None:
        """Test that init creates output directory."""
        output_dir = temp_dir / "new_dir"
        printer = MockPrinter(output_dir=output_dir, verbose=False)

        assert output_dir.exists()

    def test_inherits_from_base_printer(self, temp_dir: Path) -> None:
        """Test that MockPrinter inherits from BasePrinter."""
        printer = MockPrinter(output_dir=temp_dir, verbose=False)
        assert isinstance(printer, BasePrinter)

    def test_print_header(self, mock_printer: MockPrinter) -> None:
        """Test printing header."""
        mock_printer.print_header("2024-01-01 12:00:00")

        content = mock_printer.get_receipt_content()
        assert "[IMAGE] header_" in content

    def test_print_reel_saves_screenshot(
        self, mock_printer: MockPrinter, sample_image: Image.Image, temp_dir: Path
    ) -> None:
        """Test that print_reel saves screenshot to file."""
        mock_printer.print_reel(
            screenshot=sample_image,
            duration_seconds=5.5,
            reel_number=1,
        )

        # Check screenshot was saved
        screenshots = list(temp_dir.glob("reel_*.png"))
        assert len(screenshots) == 1

    def test_print_reel_includes_duration(
        self, mock_printer: MockPrinter, sample_image: Image.Image
    ) -> None:
        """Test that print_reel includes duration in output."""
        mock_printer.print_reel(
            screenshot=sample_image,
            duration_seconds=5.5,
            reel_number=1,
        )

        content = mock_printer.get_receipt_content()
        assert "Started:" in content
        assert "Time Spent: 5.50s" in content

    def test_print_reel_includes_image_marker(
        self, mock_printer: MockPrinter, sample_image: Image.Image
    ) -> None:
        """Test that print_reel includes screenshot marker in receipt text."""
        mock_printer.print_reel(
            screenshot=sample_image,
            duration_seconds=5.0,
            reel_number=1,
        )

        content = mock_printer.get_receipt_content()
        assert "[IMAGE] reel_" in content

    def test_print_summary(self, mock_printer: MockPrinter) -> None:
        """Test printing summary."""
        mock_printer.print_summary(total_reels=5, total_time_seconds=125.5)

        content = mock_printer.get_receipt_content()
        assert "REEL RECEIPT" in content
        assert "TOTAL" in content
        assert "$125.50" in content

    def test_print_summary_with_average(self, mock_printer: MockPrinter) -> None:
        """Test that summary includes average time."""
        mock_printer.print_summary(total_reels=4, total_time_seconds=40.0)

        content = mock_printer.get_receipt_content()
        assert "Average attention span" in content

    def test_print_summary_includes_peak_fixation(self, mock_printer: MockPrinter) -> None:
        """Test that summary includes peak fixation line."""
        mock_printer.print_summary(total_reels=3, total_time_seconds=60.0)

        content = mock_printer.get_receipt_content()
        assert "Peak fixation" in content

    def test_full_session_output(
        self, mock_printer: MockPrinter, sample_image: Image.Image
    ) -> None:
        """Test complete session output with header, reels, and summary."""
        # Simulate complete session
        mock_printer.print_header("2024-01-15 14:30:00")
        mock_printer.print_reel(sample_image, duration_seconds=10.5, reel_number=1)
        mock_printer.print_reel(sample_image, duration_seconds=5.2, reel_number=2)
        mock_printer.print_summary(total_reels=2, total_time_seconds=15.7)
        mock_printer.cut()

        content = mock_printer.get_receipt_content()

        # Verify session structure
        assert "[IMAGE] header_" in content
        assert "Started:" in content
        assert "Time Spent: 10.50s" in content
        assert "Time Spent: 5.20s" in content
        assert "REEL RECEIPT" in content
        assert "Reel 1 [" in content
        assert "Reel 2 [" in content
        assert "TOTAL" in content
        assert "Peak fixation" in content
        assert "✂" in content  # Cut

    def test_cut(self, mock_printer: MockPrinter) -> None:
        """Test paper cut simulation."""
        mock_printer.cut()

        content = mock_printer.get_receipt_content()
        assert "✂" in content or "-" in content

    def test_close_saves_receipt(self, mock_printer: MockPrinter, temp_dir: Path) -> None:
        """Test that close saves receipt to file."""
        mock_printer.print_header("2024-01-01 12:00:00")
        mock_printer.close()

        receipts = list(temp_dir.glob("receipt_*.txt"))
        assert len(receipts) == 1

        with open(receipts[0]) as f:
            content = f.read()
            assert "header_" in content

    def test_context_manager(self, temp_dir: Path) -> None:
        """Test using printer as context manager."""
        with MockPrinter(output_dir=temp_dir, verbose=False) as printer:
            printer.print_header("2024-01-01 12:00:00")

        # Should have saved receipt after exiting context
        receipts = list(temp_dir.glob("receipt_*.txt"))
        assert len(receipts) == 1

    def test_format_duration_seconds(self) -> None:
        """Test duration formatting for seconds."""
        assert BasePrinter.format_duration(5.0) == "5.0s"
        assert BasePrinter.format_duration(0.5) == "0.5s"
        assert BasePrinter.format_duration(59.9) == "59.9s"

    def test_format_duration_minutes(self) -> None:
        """Test duration formatting for minutes."""
        assert BasePrinter.format_duration(60.0) == "1m 0s"
        assert BasePrinter.format_duration(90.0) == "1m 30s"
        assert BasePrinter.format_duration(125.0) == "2m 5s"
