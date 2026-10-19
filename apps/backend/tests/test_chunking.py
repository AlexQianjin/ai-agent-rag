"""Markdown chunking stays inside the embedding limit and keeps headings."""

from backend.chunking import chunk_markdown, estimate_tokens


def test_headings_stay_with_their_sections() -> None:
    markdown = """# Animals

## Cats

The cat sat on the mat.

## Dogs

The dog ran through the park.
"""
    chunks = chunk_markdown(markdown, target_tokens=20, overlap_tokens=0, max_tokens=40)

    assert [chunk.headings for chunk in chunks] == [["Animals", "Cats"], ["Animals", "Dogs"]]
    assert "cat sat" in chunks[0].text
    assert "dog ran" in chunks[1].text
    assert chunks[0].text.startswith("Animals\nCats\n")
    assert [chunk.index for chunk in chunks] == [0, 1]


def test_long_section_overlaps_the_previous_window() -> None:
    words = [f"word{number}" for number in range(40)]
    chunks = chunk_markdown(
        " ".join(words),
        target_tokens=12,
        overlap_tokens=4,
        max_tokens=20,
    )

    assert len(chunks) >= 3
    assert all(estimate_tokens(chunk.text) <= 20 for chunk in chunks)
    first_words = chunks[0].text.split()
    second_words = chunks[1].text.split()
    assert first_words[-1] in second_words
    assert second_words[0] in first_words
    assert chunks[-1].text.split()[-1] == "word39"


def test_empty_markdown_has_no_chunks() -> None:
    assert chunk_markdown("", target_tokens=10, overlap_tokens=2, max_tokens=20) == []
    assert chunk_markdown("# Only a heading\n", target_tokens=10, overlap_tokens=2, max_tokens=20) == []
