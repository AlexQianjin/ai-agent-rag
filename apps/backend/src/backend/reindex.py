"""Rebuild hybrid vectors from stored Markdown.

Run this after upgrading a dense-only Qdrant collection:

    uv run --directory apps/backend python -m backend.reindex

Compose also does this on startup when HYBRID_BACKFILL is on.
"""

from backend.indexing import backfill_hybrid_index


def main() -> None:
    backfill_hybrid_index(force=True)


if __name__ == "__main__":
    main()
