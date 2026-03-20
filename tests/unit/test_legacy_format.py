"""Tests for legacy receipt line formatting/parsing."""

from src.printing.legacy_format import parse_topics_from_receipt_content


def test_parse_topics_from_old_receipt_item_lines() -> None:
    content = "\n".join(
        [
            "REEL RECEIPT",
            "Reel 1 [Cooking Tutorial]..............$4.64",
            "Reel 2 [Not Touching Grass]............$4.29",
        ]
    )

    parsed = parse_topics_from_receipt_content(content)

    assert parsed == {1: "Cooking Tutorial", 2: "Not Touching Grass"}


def test_parse_topics_from_new_receipt_item_lines() -> None:
    content = "\n".join(
        [
            "REEL RECEIPT",
            "[working hard at the data]............$4.64",
            "[not touching grass]..................$4.29",
        ]
    )

    parsed = parse_topics_from_receipt_content(content)

    assert parsed == {1: "working hard at the data", 2: "not touching grass"}


def test_parse_topics_from_plain_receipt_item_lines() -> None:
    content = "\n".join(
        [
            "REEL RECEIPT",
            "working hard at the data............$4.64",
            "not touching grass..................$4.29",
            "TOTAL...............................$8.93",
        ]
    )

    parsed = parse_topics_from_receipt_content(content)

    assert parsed == {1: "working hard at the data", 2: "not touching grass"}
