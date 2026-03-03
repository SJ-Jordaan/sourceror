"""Tests for CLI argument parsing and main entry point."""

from __future__ import annotations

from pathlib import Path
from textwrap import dedent

from sourceror.cli import build_parser, main


class TestBuildParser:
    def test_default_args(self):
        parser = build_parser()
        args = parser.parse_args([])
        assert args.files == []
        assert args.verbose is False
        assert args.check_relevance is False
        assert args.fix is False
        assert args.dry_run is False

    def test_files_arg(self):
        parser = build_parser()
        args = parser.parse_args(["a.bib", "b.pdf"])
        assert args.files == ["a.bib", "b.pdf"]

    def test_output_flag(self):
        parser = build_parser()
        args = parser.parse_args(["-o", "report.md"])
        assert args.output == "report.md"

    def test_token_flags(self):
        parser = build_parser()
        args = parser.parse_args(["--set-token"])
        assert args.set_token is True

        args = parser.parse_args(["--clear-token"])
        assert args.clear_token is True

        args = parser.parse_args(["--show-config"])
        assert args.show_config is True

    def test_api_key_flag(self):
        parser = build_parser()
        args = parser.parse_args(["--api-key", "sk-test-123"])
        assert args.api_key == "sk-test-123"

    def test_email_flag(self):
        parser = build_parser()
        args = parser.parse_args(["--email", "test@example.com"])
        assert args.email == "test@example.com"


class TestMain:
    def test_clear_cache(self, tmp_path: Path):
        cache_dir = tmp_path / ".sourceror_cache"
        cache_dir.mkdir()
        result = main(["--clear-cache"])
        assert result == 0

    def test_file_not_found(self):
        result = main(["nonexistent.bib"])
        assert result == 1

    def test_show_config(self):
        result = main(["--show-config"])
        assert result == 0

    def test_bib_verification(self, tmp_path: Path):
        """Test that a simple bib file can be parsed (no API calls)."""
        bib = tmp_path / "test.bib"
        bib.write_text(dedent("""\
            @online{website,
                url = {https://example.com},
            }
        """))
        # This entry will be skipped (online type), so no API calls needed
        result = main([str(bib)])
        assert result == 0
