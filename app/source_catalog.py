"""Curated official German scholarship and funding source indexes.

Source pages are not scholarship records. The evidence-based extractor must
identify a specific opportunity before it is added to the catalogue.
"""

from app.database import get_connection


GERMANY_SOURCES = (
    {"name": "DAAD Pakistan – Scholarship Programmes for Pakistan", "official_url": "https://www.daad.pk/en/find-funding/daad-scholarship-programmes-for-pakistan/", "source_type": "official_programme", "country": "Germany"},
    {"name": "DAAD Pakistan – Scholarship Database", "official_url": "https://www.daad.pk/en/find-funding/scholarship-database/?intention=&onlydaad=0&origin=194&pg=1&q=&status=0&subject=0&tab=&target=194&type=a", "source_type": "official_database", "country": "Germany"},
    {"name": "DAAD – Funding Opportunities from Other Organisations", "official_url": "https://www.daad.de/en/studying-in-germany/scholarships/funding-options/", "source_type": "official_index", "country": "Germany"},
    {"name": "German Federal Foreign Office – Scholarship Providers", "official_url": "https://www.auswaertiges-amt.de/en/visa-service/buergerservice/faq/01-stipendien/606688", "source_type": "government", "country": "Germany"},
    {"name": "Deutschlandstipendium – Federal Scholarship Programme", "official_url": "https://www.deutschlandstipendium.de/deutschlandstipendium/de/home/home_node.html", "source_type": "government", "country": "Germany"},
    {"name": "Heinrich Böll Foundation – Scholarships", "official_url": "https://www.boell.de/en/scholarships", "source_type": "official_programme", "country": "Germany"},
    {"name": "Friedrich Ebert Foundation – Study Funding", "official_url": "https://www.fes.de/studienfoerderung", "source_type": "official_programme", "country": "Germany"},
    {"name": "Konrad Adenauer Foundation – International Scholarships", "official_url": "https://www.kas.de/en/web/begabtenfoerderung", "source_type": "official_programme", "country": "Germany"},
    {"name": "Rosa Luxemburg Foundation – Scholarship Department", "official_url": "https://www.rosalux.de/stiftung/studienwerk", "source_type": "official_programme", "country": "Germany"},
    {"name": "Friedrich Naumann Foundation – Scholarships", "official_url": "https://www.freiheit.org/scholarships", "source_type": "official_programme", "country": "Germany"},
    {"name": "Hanns Seidel Foundation – Scholarships", "official_url": "https://www.hss.de/stipendium/", "source_type": "official_programme", "country": "Germany"},
    {"name": "Catholic Academic Exchange Service (KAAD)", "official_url": "https://www.kaad.de/en/scholarships", "source_type": "official_programme", "country": "Germany"},
    {"name": "Avicenna Studienwerk – Scholarships", "official_url": "https://www.avicenna-studienwerk.de/stipendium/", "source_type": "official_programme", "country": "Germany"},
    {"name": "Evangelisches Studienwerk – Scholarships", "official_url": "https://www.evstudienwerk.de/english/scholarships.html", "source_type": "official_programme", "country": "Germany"},
    {"name": "Alexander von Humboldt Foundation – Funding", "official_url": "https://www.humboldt-foundation.de/en/apply/sponsorship-programmes", "source_type": "official_programme", "country": "Germany"},
    {"name": "German Research Foundation (DFG) – Funding", "official_url": "https://www.dfg.de/en/research-funding", "source_type": "official_programme", "country": "Germany"},
    {"name": "TU Berlin – Scholarships and Funding for International Students", "official_url": "https://www.tu.berlin/en/international/students-1/international-students/international-degree-seeking-students/scholarships-and-other-funding-for-international-students", "source_type": "university", "country": "Germany"},
    {"name": "University of Würzburg – Scholarships by Target Group", "official_url": "https://www.uni-wuerzburg.de/en/scholarships/by-target-group/", "source_type": "university", "country": "Germany"},
    {"name": "University of Kiel – Scholarships", "official_url": "https://www.uni-kiel.de/en/tf/study/scholarships", "source_type": "university", "country": "Germany"},
)


OFFICIAL_DISCOVERY_TARGETS = (
    ("https://www.daad.pk/en/find-funding/daad-scholarship-programmes-for-pakistan/",
     "https://www.daad.pk/en/find-funding/daad-scholarship-programmes-for-pakistan/",
     "DAAD scholarships for Pakistani Master's, PhD and postdoctoral applicants"),
)


def seed_official_sources() -> int:
    """Run a one-time legacy catalogue reset, then sync Germany-only sources."""
    inserted = 0
    with get_connection() as connection:
        migration = connection.execute(
            "SELECT 1 FROM app_migrations WHERE name = ?",
            ("germany_catalog_reset_v1",),
        ).fetchone()
        if migration is None:
            connection.execute("DELETE FROM extraction_attempts")
            connection.execute("DELETE FROM discovery_candidates")
            connection.execute("DELETE FROM scholarships")
            connection.execute("UPDATE sources SET is_active = 0")
            connection.execute(
                "INSERT INTO app_migrations (name) VALUES (?)",
                ("germany_catalog_reset_v1",),
            )

        for source in GERMANY_SOURCES:
            cursor = connection.execute(
                """INSERT INTO sources
                   (name, official_url, source_type, country, is_active)
                   VALUES (?, ?, ?, ?, 1)
                   ON CONFLICT(official_url) DO UPDATE SET
                     name = excluded.name,
                     source_type = excluded.source_type,
                     country = excluded.country,
                     is_active = 1""",
                (source["name"], source["official_url"], source["source_type"], source["country"]),
            )
            inserted += max(cursor.rowcount, 0)
    return inserted


def seed_official_discovery_targets() -> int:
    """Queue curated German programme pages for normal evidence extraction."""
    inserted = 0
    with get_connection() as connection:
        for source_url, candidate_url, title in OFFICIAL_DISCOVERY_TARGETS:
            source = connection.execute(
                "SELECT id FROM sources WHERE official_url = ? AND is_active = 1",
                (source_url,),
            ).fetchone()
            if source is None:
                continue
            cursor = connection.execute(
                """INSERT INTO discovery_candidates
                   (source_id, title, candidate_url, status)
                   VALUES (?, ?, ?, 'candidate')
                   ON CONFLICT(source_id, candidate_url) DO NOTHING""",
                (source["id"], title, candidate_url),
            )
            inserted += max(cursor.rowcount, 0)
    return inserted
