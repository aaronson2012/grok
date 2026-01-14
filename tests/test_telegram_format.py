import pytest
from src.utils.telegram_format import markdown_to_telegram_html, _fix_tag_nesting


class TestMarkdownToTelegramHtml:
    def test_bold_conversion(self):
        result = markdown_to_telegram_html("**bold text**")
        assert "<b>bold text</b>" in result

    def test_italic_conversion(self):
        result = markdown_to_telegram_html("*italic text*")
        assert "<i>italic text</i>" in result

    def test_inline_code_conversion(self):
        result = markdown_to_telegram_html("`inline code`")
        assert "<code>inline code</code>" in result

    def test_code_block_conversion(self):
        result = markdown_to_telegram_html("```python\nprint('hello')\n```")
        assert "<pre>" in result
        assert "print" in result
        assert "</pre>" in result

    def test_strikethrough_conversion(self):
        result = markdown_to_telegram_html("~~strikethrough~~")
        assert "<s>strikethrough</s>" in result

    def test_link_conversion(self):
        result = markdown_to_telegram_html("[click here](https://example.com)")
        assert '<a href="https://example.com">click here</a>' in result

    def test_header_conversion(self):
        result = markdown_to_telegram_html("### Header Text")
        assert "<b>Header Text</b>" in result

    def test_html_escape(self):
        result = markdown_to_telegram_html("<script>alert('xss')</script>")
        assert "&lt;script&gt;" in result
        assert "<script>" not in result

    def test_nested_bold_italic(self):
        result = markdown_to_telegram_html("**bold *italic* text**")
        assert "<b>" in result
        assert "<i>" in result

    def test_multiple_formatting(self):
        result = markdown_to_telegram_html("**bold** and *italic* and `code`")
        assert "<b>bold</b>" in result
        assert "<i>italic</i>" in result
        assert "<code>code</code>" in result

    def test_empty_string(self):
        result = markdown_to_telegram_html("")
        assert result == ""

    def test_plain_text(self):
        result = markdown_to_telegram_html("plain text")
        assert result == "plain text"


class TestFixTagNesting:
    def test_properly_nested_tags(self):
        result = _fix_tag_nesting("<b><i>text</i></b>")
        assert result == "<b><i>text</i></b>"

    def test_improperly_nested_tags(self):
        result = _fix_tag_nesting("<b><i>text</b></i>")
        assert "</i>" in result
        assert "</b>" in result

    def test_unclosed_tags(self):
        result = _fix_tag_nesting("<b>text")
        assert "</b>" in result

    def test_no_tags(self):
        result = _fix_tag_nesting("plain text")
        assert result == "plain text"

    def test_link_tag_preserved(self):
        result = _fix_tag_nesting('<a href="url">text</a>')
        assert '<a href="url">' in result
        assert "</a>" in result
