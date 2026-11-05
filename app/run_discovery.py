import asyncio
import json

from app.database import init_db
from app.discovery import discover_from_active_sources
from app.source_catalog import seed_official_sources


async def main() -> None:
    init_db()
    seed_official_sources()
    results = await discover_from_active_sources()
    print(json.dumps([result.__dict__ for result in results], indent=2))


if __name__ == "__main__":
    asyncio.run(main())
