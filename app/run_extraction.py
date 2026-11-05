import argparse
import asyncio
import json

from app.database import init_db
from app.source_catalog import seed_official_sources
from app.extraction import extract_candidate_details


async def main() -> None:
    init_db()
    seed_official_sources()
    parser = argparse.ArgumentParser()
    parser.add_argument('--reprocess', action='store_true')
    args = parser.parse_args()
    results = await extract_candidate_details(reprocess=args.reprocess)
    print(json.dumps(results, indent=2))


if __name__ == "__main__":
    asyncio.run(main())
