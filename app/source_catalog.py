"""Curated official scholarship information sources.

These are source homepages/indexes, not scholarship records. They must be
rechecked periodically and their contents are treated as unverified evidence.
"""

from app.database import get_connection


OFFICIAL_SOURCES = (
    {
        "name": "Higher Education Commission Pakistan",
        "official_url": "https://www.hec.gov.pk/Site/Scholarship/default.aspx",
        "source_type": "government",
        "country": "Pakistan",
    },
    {
        "name": "Ministry of Federal Education and Professional Training",
        "official_url": "https://www.mofept.gov.pk/Detail/ZjBhMDA4MGItNmE2MC00NTE5LThiYTAtOWUyODk0Yzc5OWQ1",
        "source_type": "government",
        "country": "Pakistan",
    },
    {
        "name": "United States Educational Foundation in Pakistan",
        "official_url": "https://usefp.org/",
        "source_type": "official_programme",
        "country": "Pakistan",
    },
    {
        "name": "DAAD Pakistan Funding Opportunities",
        "official_url": "https://www.daad.pk/en/find-funding/",
        "source_type": "official_programme",
        "country": "Germany",
    },
)


def seed_official_sources() -> int:
    """Insert curated source indexes without overwriting user changes."""
    inserted = 0
    with get_connection() as connection:
        for source in OFFICIAL_SOURCES:
            cursor = connection.execute(
                """INSERT OR IGNORE INTO sources
                   (name, official_url, source_type, country)
                   VALUES (?, ?, ?, ?)""",
                (
                    source["name"],
                    source["official_url"],
                    source["source_type"],
                    source["country"],
                ),
            )
            inserted += cursor.rowcount
    return inserted
