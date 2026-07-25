"""Optional ops CLI: `python -m app.rag.backfill_maps`.

Lazy-upgrades ready source documents that lack a teaching_map (rag-context §5.2.1).
Not required for cutover — `ensure_knowledge_tree` also runs on demand.
"""
from __future__ import annotations

import argparse
import asyncio
import os


async def _main(limit: int) -> int:
    # Offline-friendly: do not require live provider validation for this ops command.
    os.environ.setdefault("SKIP_PROVIDER_VALIDATION", "1")
    from ..core.db import SessionLocal, init_db
    from .ensure import backfill_maps

    init_db()
    with SessionLocal() as db:
        n = await backfill_maps(db, limit=limit)
    print(f"backfilled teaching maps for {n} document(s)")
    return n


def main() -> None:
    p = argparse.ArgumentParser(description="Backfill teaching maps for legacy source documents")
    p.add_argument("--limit", type=int, default=50, help="Max documents to upgrade")
    args = p.parse_args()
    asyncio.run(_main(args.limit))


if __name__ == "__main__":
    main()
