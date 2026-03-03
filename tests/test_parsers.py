"""Tests for parsers."""

from __future__ import annotations

from pathlib import Path
from textwrap import dedent

from sourceror.parsers.bibtex import strip_latex, _parse_authors, _safe_int, parse_bib_file
from sourceror.parsers.latex import extract_citation_contexts
from sourceror.parsers.pdf import (
    _find_reference_section,
    _split_numbered_references,
    _parse_reference_string,
    extract_citation_contexts_from_pdf,
)


class TestStripLatex:
    def test_basic_command(self):
        assert strip_latex(r"\textbf{bold}") == "bold"

    def test_math_delimiters(self):
        assert strip_latex("$x + y$") == "x + y"

    def test_braces(self):
        assert strip_latex("{Foo} Bar") == "Foo Bar"

    def test_nested(self):
        assert strip_latex(r"\emph{hello} world") == "hello world"

    def test_plain_text(self):
        assert strip_latex("no latex here") == "no latex here"


class TestParseAuthors:
    def test_single_author(self):
        result = _parse_authors("Smith, John")
        assert result == ["John Smith"]

    def test_multiple_authors(self):
        result = _parse_authors("Smith, John and Doe, Jane")
        assert result == ["John Smith", "Jane Doe"]

    def test_empty(self):
        assert _parse_authors("") == []

    def test_braces_stripped(self):
        result = _parse_authors("{Van der Berg}, Jan")
        assert result == ["Jan Van der Berg"]


class TestSafeInt:
    def test_valid(self):
        assert _safe_int("2024") == 2024

    def test_with_whitespace(self):
        assert _safe_int(" 42 ") == 42

    def test_invalid(self):
        assert _safe_int("abc") is None

    def test_none(self):
        assert _safe_int(None) is None


class TestParseBibFile:
    def test_parse_simple_bib(self, tmp_path: Path):
        bib_content = dedent("""\
            @article{smith2024,
                author = {Smith, John and Doe, Jane},
                title = {A Great Paper},
                journal = {Nature},
                year = {2024},
                volume = {42},
                doi = {10.1234/test},
            }
        """)
        bib_file = tmp_path / "test.bib"
        bib_file.write_text(bib_content)

        entries = parse_bib_file(bib_file)
        assert len(entries) == 1
        entry = entries[0]
        assert entry.key == "smith2024"
        assert entry.entry_type == "article"
        assert entry.title == "A Great Paper"
        assert entry.year == 2024
        assert entry.doi == "10.1234/test"
        assert entry.journal == "Nature"
        assert len(entry.authors) == 2

    def test_parse_multiple_entries(self, tmp_path: Path):
        bib_content = dedent("""\
            @article{first2024,
                author = {First, Author},
                title = {Paper One},
                year = {2024},
            }
            @inproceedings{second2024,
                author = {Second, Author},
                title = {Paper Two},
                year = {2024},
                booktitle = {ICML},
            }
        """)
        bib_file = tmp_path / "test.bib"
        bib_file.write_text(bib_content)

        entries = parse_bib_file(bib_file)
        assert len(entries) == 2
        assert entries[0].entry_type == "article"
        assert entries[1].entry_type == "inproceedings"


class TestExtractCitationContexts:
    def test_single_cite(self, tmp_path: Path):
        tex = tmp_path / "test.tex"
        tex.write_text(r"Some text about Nash equilibria \cite{nash1950} and more text here.")

        contexts = extract_citation_contexts(tex)
        assert "nash1950" in contexts
        assert len(contexts["nash1950"]) == 1
        assert "Nash equilibria" in contexts["nash1950"][0]

    def test_multiple_keys(self, tmp_path: Path):
        tex = tmp_path / "test.tex"
        tex.write_text(r"See \cite{foo,bar} for details.")

        contexts = extract_citation_contexts(tex)
        assert "foo" in contexts
        assert "bar" in contexts

    def test_citep_variant(self, tmp_path: Path):
        tex = tmp_path / "test.tex"
        tex.write_text(r"Results shown \citep{jones2020} clearly.")

        contexts = extract_citation_contexts(tex)
        assert "jones2020" in contexts

    def test_no_citations(self, tmp_path: Path):
        tex = tmp_path / "test.tex"
        tex.write_text("No citations here at all.")

        contexts = extract_citation_contexts(tex)
        assert contexts == {}


class TestFindReferenceSection:
    def test_markdown_heading(self):
        text = "# Introduction\n\nSome text.\n\n## References\n\n[1] Smith, J.: A paper. (2024)\n"
        result = _find_reference_section(text)
        assert result is not None
        assert "[1]" in result

    def test_bold_heading(self):
        text = "Some text.\n\n**References**\n\n[1] Smith, J.: A paper. (2024)\n"
        result = _find_reference_section(text)
        assert result is not None

    def test_plain_heading(self):
        text = "Some text.\n\nReferences\n\n[1] Smith, J.: A paper. (2024)\n"
        result = _find_reference_section(text)
        assert result is not None

    def test_no_reference_section(self):
        text = "Just some text with no references section."
        result = _find_reference_section(text)
        assert result is None

    def test_trims_at_appendix(self):
        text = "## References\n\n[1] A ref.\n\n## Appendix\n\nExtra stuff."
        result = _find_reference_section(text)
        assert result is not None
        assert "Extra stuff" not in result
        assert "[1]" in result


class TestSplitNumberedReferences:
    def test_basic_split(self):
        text = "[1] Smith, J.: First paper. (2024)\n[2] Doe, J.: Second paper. (2023)\n"
        refs = _split_numbered_references(text)
        assert len(refs) == 2
        assert refs[0][0] == 1
        assert "First paper" in refs[0][1]
        assert refs[1][0] == 2
        assert "Second paper" in refs[1][1]

    def test_no_markers(self):
        text = "Just some text without numbered references."
        assert _split_numbered_references(text) == []

    def test_single_reference(self):
        text = "[1] Only one reference here. (2024)\n"
        refs = _split_numbered_references(text)
        assert len(refs) == 1
        assert refs[0][0] == 1


class TestParseReferenceString:
    def test_lncs_style(self):
        ref = "Smith, J., Doe, A.: Nash Equilibrium Synthesis for Multi-Agent Systems. In: Proc. NFM, pp. 1-15 (2024)"
        entry = _parse_reference_string(1, ref, "test.pdf")
        assert entry.key == "pdf_ref_1"
        assert entry.year == 2024
        assert entry.input_format == "pdf"
        assert "Nash Equilibrium" in entry.title
        assert len(entry.authors) > 0
        assert entry.parse_confidence > 0.5

    def test_year_extraction(self):
        ref = "Author, A.: Some title here. Journal (2020)"
        entry = _parse_reference_string(5, ref, "test.pdf")
        assert entry.year == 2020
        assert entry.key == "pdf_ref_5"

    def test_low_confidence_for_bad_input(self):
        ref = "???"
        entry = _parse_reference_string(1, ref, "test.pdf")
        assert entry.parse_confidence < 0.5

    def test_fallback_title(self):
        # When parsing fails, the whole string becomes the title
        ref = "Some unparseable reference text without clear structure"
        entry = _parse_reference_string(1, ref, "test.pdf")
        assert entry.title  # Should have something
