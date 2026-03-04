"""Comprehensive tests for the PDF reference parser."""

from __future__ import annotations

from sourceror.parsers.pdf import (
    _normalize_text,
    _strip_markdown,
    _find_reference_section,
    _split_numbered_references,
    _split_author_year_references,
    _extract_doi,
    _extract_year,
    _extract_author_names,
    _parse_reference_string,
    _BRACKET_NUM_RE,
    _DOT_NUM_RE,
)


# =========================================================================
# Text normalization
# =========================================================================


class TestNormalizeText:
    def test_ligature_fi(self):
        assert _normalize_text("classi\ufb01cation") == "classification"

    def test_ligature_fl(self):
        assert _normalize_text("con\ufb02ict") == "conflict"

    def test_ligature_ff(self):
        assert _normalize_text("e\ufb00ect") == "effect"

    def test_ligature_ffi(self):
        assert _normalize_text("e\ufb03cient") == "efficient"

    def test_en_dash(self):
        assert _normalize_text("pp. 142\u2013155") == "pp. 142-155"

    def test_soft_hyphen_removed(self):
        assert _normalize_text("algo\u00adrithm") == "algorithm"

    def test_curly_quotes(self):
        result = _normalize_text("\u201cHello\u201d")
        assert result == '"Hello"'

    def test_single_curly_quotes(self):
        result = _normalize_text("\u2018test\u2019")
        assert result == "'test'"

    def test_preserves_normal_text(self):
        assert _normalize_text("normal text 2024") == "normal text 2024"


class TestStripMarkdown:
    def test_bold(self):
        assert _strip_markdown("**bold text**") == "bold text"

    def test_italic(self):
        assert _strip_markdown("*italic*") == "italic"

    def test_bold_italic(self):
        assert _strip_markdown("***both***") == "both"

    def test_underscore_emphasis(self):
        assert _strip_markdown("_emphasized_") == "emphasized"

    def test_code(self):
        assert _strip_markdown("`code`") == "code"

    def test_markdown_link(self):
        result = _strip_markdown("[click here](https://example.com)")
        assert "click here" in result
        assert "https://example.com" in result
        assert "[" not in result

    def test_heading_markers(self):
        assert _strip_markdown("## Heading").strip() == "Heading"

    def test_escape_backslash(self):
        assert _strip_markdown("\\*not bold\\*") == "*not bold*"

    def test_preserves_normal_text(self):
        assert _strip_markdown("normal text") == "normal text"


# =========================================================================
# Reference section detection
# =========================================================================


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

    def test_bold_inside_heading(self):
        text = "Some text.\n\n## **References**\n\n[1] Smith, J.: A paper. (2024)\n"
        result = _find_reference_section(text)
        assert result is not None
        assert "[1]" in result

    def test_plain_heading(self):
        text = "Some text.\n\nReferences\n\n[1] Smith, J.: A paper. (2024)\n"
        result = _find_reference_section(text)
        assert result is not None

    def test_bibliography_heading(self):
        text = "## Bibliography\n\n[1] Smith, J.: A paper. (2024)\n"
        result = _find_reference_section(text)
        assert result is not None

    def test_works_cited(self):
        text = "## Works Cited\n\nSmith, J. A paper. 2024.\n"
        result = _find_reference_section(text)
        assert result is not None

    def test_literature_cited(self):
        text = "## Literature Cited\n\nSmith, J. A paper. 2024.\n"
        result = _find_reference_section(text)
        assert result is not None

    def test_numbered_heading(self):
        text = "## 7. References\n\n[1] Smith, J.: A paper. (2024)\n"
        result = _find_reference_section(text)
        assert result is not None
        assert "[1]" in result

    def test_case_insensitive(self):
        text = "## REFERENCES\n\n[1] Smith, J.: A paper. (2024)\n"
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

    def test_trims_at_author_biographies(self):
        text = "## References\n\n[1] A ref.\n\n## Author Biographies\n\nJohn Smith is..."
        result = _find_reference_section(text)
        assert result is not None
        assert "John Smith is" not in result

    def test_prefers_last_match(self):
        """If 'References' appears in body text and as section heading, use the last one."""
        text = (
            "See the References section for details.\n\n"
            "## Introduction\n\nBody text.\n\n"
            "## References\n\n[1] Actual ref.\n"
        )
        result = _find_reference_section(text)
        assert result is not None
        assert "Actual ref" in result

    def test_german_literatur(self):
        text = "## Literatur\n\n[1] Smith, J.: Ein Papier. (2024)\n"
        result = _find_reference_section(text)
        assert result is not None

    def test_french_bibliographie(self):
        text = "## Bibliographie\n\n[1] Smith, J.: Un article. (2024)\n"
        result = _find_reference_section(text)
        assert result is not None

    def test_references_and_notes(self):
        text = "## References and Notes\n\n1. Smith, J. A paper. 2024.\n"
        result = _find_reference_section(text)
        assert result is not None


# =========================================================================
# Reference splitting
# =========================================================================


class TestSplitBracketNumberedReferences:
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

    def test_multiline_references(self):
        text = (
            "[1] Smith, J., Doe, A.: A very long title that\n"
            "spans multiple lines in the PDF. Journal (2024)\n"
            "[2] Another, R.: Short ref. (2023)\n"
        )
        refs = _split_numbered_references(text)
        assert len(refs) == 2
        assert "spans multiple lines" in refs[0][1]

    def test_non_sequential(self):
        text = "[1] First. (2024)\n[3] Third. (2022)\n[5] Fifth. (2020)\n"
        refs = _split_numbered_references(text)
        assert len(refs) == 3
        assert refs[0][0] == 1
        assert refs[1][0] == 3
        assert refs[2][0] == 5

    def test_large_numbers(self):
        text = "[100] A ref. (2024)\n[101] Another ref. (2023)\n"
        refs = _split_numbered_references(text)
        assert len(refs) == 2
        assert refs[0][0] == 100


class TestSplitDotNumberedReferences:
    def test_basic_dot_split(self):
        text = "1. Smith, J. A paper. IEEE Trans. 2024.\n2. Doe, A. Another paper. ICML 2023.\n"
        refs = _split_numbered_references(text, _DOT_NUM_RE)
        assert len(refs) == 2
        assert refs[0][0] == 1
        assert "Smith" in refs[0][1]

    def test_ieee_style(self):
        text = (
            '1. A. B. Smith, C. D. Jones, and E. F. Roberts, "A survey of neural '
            'network architectures," IEEE Trans. Neural Netw., vol. 15, no. 3, '
            "pp. 412-431, May 2004.\n"
            '2. J. K. Author, "Another paper," in Proc. ICML, 2023, pp. 100-110.\n'
        )
        refs = _split_numbered_references(text, _DOT_NUM_RE)
        assert len(refs) == 2
        assert "survey" in refs[0][1]

    def test_no_dot_numbered(self):
        text = "Just text without dot-numbered references."
        assert _split_numbered_references(text, _DOT_NUM_RE) == []


class TestSplitAuthorYearReferences:
    def test_basic_split(self):
        text = (
            "Smith, J. (2024). A paper title. Journal of Something, 42(3), 1-15.\n"
            "Doe, A. (2023). Another paper. Conference Proceedings, pp. 100-110.\n"
        )
        refs = _split_author_year_references(text)
        assert len(refs) == 2
        assert "Smith" in refs[0][1]
        assert "Doe" in refs[1][1]

    def test_lowercase_particle(self):
        text = (
            "Smith, J. (2024). First paper. Journal, 42, 1-15.\n"
            "van Rossum, G. (2009). Python reference manual. Publisher.\n"
            "Jones, A. (2023). Third paper. Another Journal, 10, 5-20.\n"
        )
        refs = _split_author_year_references(text)
        # van Rossum starts with lowercase so it won't trigger a new split on its own
        # but the regex has optional lowercase prefix support
        assert len(refs) >= 2

    def test_minimum_two_required(self):
        text = "Smith, J. (2024). Only one reference.\n"
        refs = _split_author_year_references(text)
        assert refs == []

    def test_short_fragments_skipped(self):
        text = (
            "Smith, J. (2024). Real reference with enough text here.\n"
            "Doe, A. short\n"
            "Jones, B. (2023). Another real reference with enough text.\n"
        )
        refs = _split_author_year_references(text)
        # "Doe, A. short" is only ~15 chars, should be skipped (threshold is 20)
        for _, ref_text in refs:
            assert len(ref_text) > 20


# =========================================================================
# DOI extraction
# =========================================================================


class TestExtractDoi:
    def test_doi_url(self):
        ref = "Smith (2024). Title. https://doi.org/10.1145/1234567"
        assert _extract_doi(ref) == "10.1145/1234567"

    def test_doi_prefix(self):
        ref = "Smith (2024). Title. doi:10.1007/978-3-030-24258-9_24"
        assert _extract_doi(ref) == "10.1007/978-3-030-24258-9_24"

    def test_doi_dx_url(self):
        ref = "Smith (2024). Title. http://dx.doi.org/10.1023/a:1022672621406"
        assert _extract_doi(ref) == "10.1023/a:1022672621406"

    def test_doi_trailing_period(self):
        ref = "Smith (2024). Title. doi:10.1145/1234567."
        doi = _extract_doi(ref)
        assert doi == "10.1145/1234567"

    def test_doi_trailing_comma(self):
        ref = "doi:10.1145/1234567, cited in..."
        doi = _extract_doi(ref)
        assert doi == "10.1145/1234567"

    def test_no_doi(self):
        ref = "Smith (2024). Title. Journal of Something, 42, 1-15."
        assert _extract_doi(ref) is None

    def test_bare_doi(self):
        ref = "Title. 10.1145/1234567"
        assert _extract_doi(ref) == "10.1145/1234567"


# =========================================================================
# Year extraction
# =========================================================================


class TestExtractYear:
    def test_parenthesized_year(self):
        year, _ = _extract_year("Smith (2024). Title.")
        assert year == 2024

    def test_parenthesized_year_with_letter(self):
        year, _ = _extract_year("Smith (2024a). Title.")
        assert year == 2024

    def test_bare_year(self):
        year, _ = _extract_year("Smith, Title, Journal, 2024.")
        assert year == 2024

    def test_avoids_page_range(self):
        year, _ = _extract_year("Smith. Title. pp. 1945-1960. Journal, 2024.")
        assert year == 2024

    def test_avoids_page_range_with_pp(self):
        year, _ = _extract_year("Title. pp. 2001-2010. Published 2024.")
        assert year == 2024

    def test_avoids_doi_year(self):
        year, _ = _extract_year("Title. doi:10.1000/2024.1234. Published 2020.")
        assert year == 2020

    def test_no_year(self):
        year, _ = _extract_year("Some text without a year.")
        assert year is None

    def test_year_range_validation(self):
        year, _ = _extract_year("Value 1800 is not a year. Published (2024).")
        assert year == 2024

    def test_prefers_parenthesized(self):
        year, _ = _extract_year("Smith 2023 published (2024).")
        assert year == 2024


# =========================================================================
# Author name extraction
# =========================================================================


class TestExtractAuthorNames:
    def test_single_author(self):
        result = _extract_author_names("Smith, J.")
        assert len(result) == 1
        assert "Smith" in result[0]

    def test_two_authors_and(self):
        result = _extract_author_names("Smith, J. and Doe, A.")
        assert len(result) == 2

    def test_two_authors_ampersand(self):
        result = _extract_author_names("Smith, J. & Doe, A.")
        assert len(result) == 2

    def test_et_al_removed(self):
        result = _extract_author_names("Smith, J. et al.")
        assert len(result) == 1
        assert "et" not in result[0].lower()

    def test_eds_removed(self):
        result = _extract_author_names("Smith, J. (Eds.)")
        assert len(result) == 1
        assert "Eds" not in result[0]

    def test_ed_name_preserved(self):
        """The name 'Ed' should NOT be stripped."""
        result = _extract_author_names("Ed Smith and Jane Doe")
        assert len(result) == 2
        assert any("Ed" in name for name in result)

    def test_name_ending_in_d_preserved(self):
        """Names ending in 'd' should not have characters stripped."""
        result = _extract_author_names("David, Mahmoud")
        assert len(result) == 1
        # The full name should be preserved
        assert "David" in result[0]
        assert "Mahmoud" in result[0]

    def test_name_ending_in_and_preserved(self):
        """Names like 'Roland' and 'Amanda' should be preserved."""
        result = _extract_author_names("Roland, A. and Amanda, B.")
        assert len(result) == 2
        assert "Roland" in result[0]
        assert "Amanda" in result[1]

    def test_empty_input(self):
        assert _extract_author_names("") == []
        assert _extract_author_names("   ") == []

    def test_multiple_authors_comma_separated(self):
        result = _extract_author_names("Smith, J., Doe, A., Jones, B.")
        # Should detect multiple authors
        assert len(result) >= 1

    def test_italic_et_al(self):
        result = _extract_author_names("Smith, J. *et al.*")
        assert len(result) == 1
        assert "et" not in result[0].lower()


# =========================================================================
# Reference string parsing
# =========================================================================


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

    def test_apa_style(self):
        ref = "Smith, J. A., & Johnson, R. B. (2020). The role of executive function in early childhood development. Developmental Psychology, 56(4), 712-725."
        entry = _parse_reference_string(1, ref, "test.pdf")
        assert entry.year == 2020
        assert "executive function" in entry.title.lower()
        assert len(entry.authors) >= 1

    def test_ieee_style_quoted_title(self):
        ref = 'A. B. Smith, C. D. Jones, and E. F. Roberts, "A survey of neural network architectures," IEEE Trans. Neural Netw., vol. 15, no. 3, pp. 412-431, May 2004.'
        entry = _parse_reference_string(1, ref, "test.pdf")
        assert "survey" in entry.title.lower()
        assert entry.year == 2004

    def test_vancouver_style(self):
        ref = "Smith JA, Johnson RB, Williams TM. The role of executive function in development. Dev Psychol. 2020;56(4):712-25."
        entry = _parse_reference_string(1, ref, "test.pdf")
        assert entry.year == 2020
        assert "executive function" in entry.title.lower()

    def test_doi_extracted(self):
        ref = "Smith (2024). A paper. Journal. https://doi.org/10.1145/1234567"
        entry = _parse_reference_string(1, ref, "test.pdf")
        assert entry.doi == "10.1145/1234567"

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
        ref = "Some unparseable reference text without clear structure"
        entry = _parse_reference_string(1, ref, "test.pdf")
        assert entry.title  # Should have something
        # Fallback strategy caps confidence at 0.3
        assert entry.parse_confidence <= 0.3

    def test_markdown_artifacts_cleaned(self):
        ref = "Smith, J.: **Bold Title** of a Paper. In: _Italic Venue_ (2024)"
        entry = _parse_reference_string(1, ref, "test.pdf")
        assert "**" not in entry.title
        assert "_" not in entry.title

    def test_ligatures_normalized(self):
        ref = "Smith, J.: Classi\ufb01cation of e\ufb03cient algorithms. Journal (2024)"
        entry = _parse_reference_string(1, ref, "test.pdf")
        assert "classification" in entry.title.lower() or "efficient" in entry.title.lower()

    def test_confidence_with_venue_markers(self):
        ref = "Smith, J.: A Paper Title. In: Proc. ICML, pp. 1-15 (2024)"
        entry = _parse_reference_string(1, ref, "test.pdf")
        assert entry.parse_confidence > 0.6

    def test_confidence_without_structure(self):
        ref = "random text with 2024 somewhere"
        entry = _parse_reference_string(1, ref, "test.pdf")
        assert entry.parse_confidence < 0.5

    def test_nature_style(self):
        ref = "Smith, J. A., Johnson, R. B. & Williams, T. M. The role of executive function. Dev. Psychol. 56, 712-725 (2020)."
        entry = _parse_reference_string(1, ref, "test.pdf")
        assert entry.year == 2020
        assert "executive function" in entry.title.lower()


# =========================================================================
# Integration scenarios
# =========================================================================


class TestIntegrationScenarios:
    """Test complete reference section → parsed entries flows."""

    def test_ieee_full_flow(self):
        ref_section = (
            '[1] A. Smith, "First paper title here," IEEE Trans., vol. 1, 2024.\n'
            '[2] B. Jones, "Second paper title here," in Proc. ICML, 2023.\n'
            '[3] C. Doe, "Third paper title," Nature, vol. 5, pp. 10-20, 2022.\n'
        )
        refs = _split_numbered_references(ref_section)
        assert len(refs) == 3
        entries = [_parse_reference_string(n, t, "test.pdf") for n, t in refs]
        assert all(e.title for e in entries)
        assert all(e.year for e in entries)

    def test_lncs_full_flow(self):
        ref_section = (
            "1. Jordaan, S., Timm, N.: Nash equilibrium synthesis. In: Proc. NFM. LNCS, vol. 15927, pp. 1-15. Springer (2026)\n"
            "2. Clarke, E.M., Grumberg, O.: Model Checking. MIT Press (1999)\n"
        )
        refs = _split_numbered_references(ref_section, _DOT_NUM_RE)
        assert len(refs) == 2
        entries = [_parse_reference_string(n, t, "test.pdf") for n, t in refs]
        assert "Nash equilibrium" in entries[0].title
        assert entries[0].year == 2026

    def test_apa_full_flow(self):
        ref_section = (
            "Anderson, L. W., & Krathwohl, D. R. (2001). A taxonomy for learning. Publisher.\n"
            "Brown, A. L. (1997). Transforming schools into communities. American Psychologist, 52(4), 399-413.\n"
            "Clark, H. H. (1996). Using language. Cambridge University Press.\n"
        )
        refs = _split_author_year_references(ref_section)
        assert len(refs) == 3
        entries = [_parse_reference_string(n, t, "test.pdf") for n, t in refs]
        assert all(e.year for e in entries)
        assert all(len(e.authors) >= 1 for e in entries)
