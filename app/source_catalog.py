"""Curated official scholarship information sources.

These are source homepages/indexes, not scholarship records. They must be
rechecked periodically and their contents are treated as unverified evidence.
"""

from app.database import get_connection


LEGACY_HEC_URL = "https://www.hec.gov.pk/Site/Scholarship/default.aspx"

OFFICIAL_SOURCES = (
    {
        "name": "HEC International Scholarships",
        "official_url": "https://www.hec.gov.pk/english/scholarshipsgrants/Pages/internationalScholarships.aspx",
        "source_type": "government",
        "country": "Pakistan",
    },
    {
        "name": "HEC National Scholarships",
        "official_url": "https://www.hec.gov.pk/english/scholarshipsgrants/Pages/NationalScholarships.aspx",
        "source_type": "government",
        "country": "Pakistan",
    },
    {
        "name": "HEC Learning Opportunities Abroad",
        "official_url": "https://www.hec.gov.pk/english/scholarshipsgrants/lao/pages/default.aspx",
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
    {
        "name": "British Council Pakistan Scholarships",
        "official_url": "https://www.britishcouncil.pk/programmes/education/scholarships",
        "source_type": "official_programme",
        "country": "Pakistan",
    },
    {
        "name": "Commonwealth Scholarship Commission",
        "official_url": "https://cscuk.fcdo.gov.uk/scholarships-filter-search/",
        "source_type": "official_programme",
        "country": "United Kingdom",
    },
    {
        "name": "Türkiye Scholarships",
        "official_url": "https://www.turkiyeburslari.gov.tr/scholarshipsprograms",
        "source_type": "official_programme",
        "country": "Türkiye",
    },
    {
        "name": "Erasmus+ Opportunities for Individuals",
        "official_url": "https://erasmus-plus.ec.europa.eu/opportunities/individuals",
        "source_type": "government",
        "country": "European Union",
    },
    {
        "name": "Stipendium Hungaricum",
        "official_url": "https://stipendiumhungaricum.hu/apply/",
        "source_type": "official_programme",
        "country": "Hungary",
    },
)


def seed_official_sources() -> int:
    """Idempotently add curated source indexes and retire the obsolete HEC index."""
    inserted = 0
    with get_connection() as connection:
        # Preserve old scholarship/candidate records, but stop repeatedly
        # crawling the legacy URL that returns an empty anti-bot response.
        connection.execute(
            "UPDATE sources SET is_active = 0 WHERE official_url = ?",
            (LEGACY_HEC_URL,),
        )
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
