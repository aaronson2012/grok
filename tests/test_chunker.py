import pytest
from src.utils.chunker import chunk_text


class TestChunkText:
    def test_short_text_returns_single_chunk(self):
        text = "Hello, world!"
        result = chunk_text(text)
        assert result == ["Hello, world!"]

    def test_text_at_limit_returns_single_chunk(self):
        text = "a" * 2000
        result = chunk_text(text)
        assert len(result) == 1
        assert result[0] == text

    def test_long_text_splits_at_word_boundary(self):
        text = "word " * 500
        result = chunk_text(text, chunk_size=100)
        assert len(result) > 1
        for chunk in result:
            assert len(chunk) <= 100

    def test_custom_chunk_size(self):
        text = "a" * 100
        result = chunk_text(text, chunk_size=30)
        assert len(result) > 1
        for chunk in result:
            assert len(chunk) <= 30

    def test_empty_string(self):
        result = chunk_text("")
        assert result == [""]

    def test_no_spaces_forces_split(self):
        text = "a" * 150
        result = chunk_text(text, chunk_size=50)
        assert len(result) == 3
        assert result[0] == "a" * 50
        assert result[1] == "a" * 50
        assert result[2] == "a" * 50

    def test_respects_word_boundaries(self):
        text = "hello world test message"
        result = chunk_text(text, chunk_size=12)
        assert "hello" in result[0]
        assert "world" in result[1] or "world" in result[0]

    def test_strips_leading_whitespace_from_chunks(self):
        text = "word " * 50
        result = chunk_text(text, chunk_size=20)
        for chunk in result:
            assert not chunk.startswith(" ")

    def test_default_chunk_size_is_2000(self):
        text = "a " * 1500
        result = chunk_text(text)
        for chunk in result:
            assert len(chunk) <= 2000

    def test_exact_boundary_split(self):
        text = "ab " * 100
        result = chunk_text(text, chunk_size=9)
        assert len(result) > 1
