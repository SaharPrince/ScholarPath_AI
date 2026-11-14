"""Curated official German scholarship and funding source indexes.

Source pages are not scholarship records. The evidence-based extractor must
identify a specific opportunity before it is added to the catalogue.
"""

from app.database import get_connection


LEGACY_HEC_URL = "https://www.hec.gov.pk/Site/Scholarship/default.aspx"

LEGACY_KIEL_DEUTSCHLANDSTIPENDIUM_PDF_URL = "https://www.uni-kiel.de/gf-praesidium/de/recht/interne-richtlinien/guidelines-of-kiel-university-for-the-award-of-deutschlandstipendium"

GERMANY_SOURCES = (
    {"name": "DAAD Pakistan – Scholarship Programmes for Pakistan", "official_url": "https://www.daad.pk/en/find-funding/daad-scholarship-programmes-for-pakistan/", "source_type": "official_index", "country": "Germany"},
    {"name": "DAAD Pakistan – Scholarship Database", "official_url": "https://www.daad.pk/en/find-funding/scholarship-database/?intention=&onlydaad=0&origin=194&pg=1&q=&status=0&subject=0&tab=&target=194&type=a", "source_type": "official_database", "country": "Germany"},
    {"name": "DAAD – Funding Opportunities from Other Organisations", "official_url": "https://www.daad.de/en/studying-in-germany/scholarships/funding-options/", "source_type": "official_index", "country": "Germany"},
    {"name": "German Federal Foreign Office – Scholarship Providers", "official_url": "https://www.auswaertiges-amt.de/en/visa-service/buergerservice/faq/01-stipendien/606688", "source_type": "official_index", "country": "Germany"},
    {"name": "Deutschlandstipendium – Federal Scholarship Programme", "official_url": "https://www.deutschlandstipendium.de/deutschlandstipendium/de/home/home_node.html", "programme_urls": ("https://www.deutschlandstipendium.de/deutschlandstipendium/de/studierende/stipendiatin-oder-stipendiat-werden/stipendiatin-oder-stipendiat-werden.html",), "source_type": "government", "country": "Germany"},
    {"name": "Heinrich Böll Foundation – Scholarships", "official_url": "https://www.boell.de/en/scholarships", "source_type": "official_programme", "country": "Germany"},
    {"name": "Friedrich Ebert Foundation – Study Funding", "official_url": "https://www.fes.de/studienfoerderung", "programme_urls": ("https://www.fes.de/studienfoerderung/stipendium/stipendien-auszubildende", "https://www.fes.de/studienfoerderung/stipendium/grundfoerderung-fuer-auslaender-innen", "https://www.fes.de/studienfoerderung/stipendium/promotionsfoerderung-fuer-auslaender-innen"), "programme_titles": {"https://www.fes.de/studienfoerderung/stipendium/stipendien-auszubildende": "FES Scholarship for Apprentices", "https://www.fes.de/studienfoerderung/stipendium/grundfoerderung-fuer-auslaender-innen": "FES Scholarship for International Students", "https://www.fes.de/studienfoerderung/stipendium/promotionsfoerderung-fuer-auslaender-innen": "FES Scholarship for International Doctoral Candidates"}, "source_type": "official_index", "country": "Germany"},
    {"name": "Konrad Adenauer Foundation – International Scholarships", "official_url": "https://www.kas.de/en/web/begabtenfoerderung-und-kultur/international-talent-development", "source_type": "official_programme", "country": "Germany"},
    {"name": "Rosa Luxemburg Foundation – Scholarship Department", "official_url": "https://www.rosalux.de/stiftung/studienwerk", "programme_urls": ("https://www.rosalux.de/stiftung/studienwerk/stipendien/studienstipendium", "https://www.rosalux.de/stiftung/studienwerk/stipendien/promotionsstipendium", "https://www.rosalux.de/berufliche-bildung"), "programme_titles": {"https://www.rosalux.de/stiftung/studienwerk/stipendien/studienstipendium": "Rosa Luxemburg Study Scholarship", "https://www.rosalux.de/stiftung/studienwerk/stipendien/promotionsstipendium": "Rosa Luxemburg Doctoral Scholarship", "https://www.rosalux.de/berufliche-bildung": "Lux Like Ausbildung – Apprenticeship Scholarship"}, "source_type": "official_index", "country": "Germany"},
    {"name": "Friedrich Naumann Foundation – Scholarships", "official_url": "https://www.freiheit.org/scholarships", "programme_urls": ("https://www.freiheit.org/student-scholarships", "https://www.freiheit.org/scholarships-for-doctoral-students"), "source_type": "official_index", "country": "Germany"},
    {"name": "Hanns Seidel Foundation – Scholarships", "official_url": "https://www.hss.de/stipendium/", "programme_urls": ("https://www.hss.de/stipendium/foerderung/foerderung-auszubildender/", "https://www.hss.de/stipendium/foerderung/journalistisches-foerderprogramm/"), "programme_titles": {"https://www.hss.de/stipendium/foerderung/foerderung-auszubildender/": "Hanns Seidel Scholarship for Apprentices", "https://www.hss.de/stipendium/foerderung/journalistisches-foerderprogramm/": "Hanns Seidel Journalism Scholarship"}, "source_type": "official_index", "country": "Germany"},
    {"name": "Catholic Academic Exchange Service (KAAD)", "official_url": "https://www.kaad.de/en/stipendien/", "programme_urls": ("https://www.kaad.de/en/stipendien/stipendienprogramm-1", "https://www.kaad.de/en/stipendien/stipendienprogramm-2"), "programme_titles": {"https://www.kaad.de/en/stipendien/stipendienprogramm-1": "KAAD Scholarship Programme 1", "https://www.kaad.de/en/stipendien/stipendienprogramm-2": "KAAD Scholarship Programme 2"}, "source_type": "official_index", "country": "Germany"},
    {"name": "Avicenna Studienwerk – Scholarships", "official_url": "https://www.avicenna-studienwerk.de/stipendium/", "source_type": "official_programme", "country": "Germany"},
    {"name": "Avicenna Studienwerk – International Scholarship Programme", "official_url": "https://www.avicenna-studienwerk.de/internationales-stipendienprogramm/", "source_type": "official_programme", "country": "Germany"},
    {"name": "Evangelisches Studienwerk – Scholarships", "official_url": "https://www.evstudienwerk.de/english/our-mission-statement/", "programme_urls": ("https://www.evstudienwerk.de/english/scholarship-for-students/", "https://www.evstudienwerk.de/english/scholarship-for-doctoral-students/"), "programme_titles": {"https://www.evstudienwerk.de/english/scholarship-for-students/": "Evangelisches Studienwerk Scholarship for Students", "https://www.evstudienwerk.de/english/scholarship-for-doctoral-students/": "Evangelisches Studienwerk Doctoral Scholarship"}, "source_type": "official_index", "country": "Germany"},
    {"name": "Alexander von Humboldt Foundation – Funding", "official_url": "https://www.humboldt-foundation.de/en/apply/sponsorship-programmes", "source_type": "official_index", "country": "Germany"},
    {"name": "German Research Foundation (DFG) – Research Funding Programmes", "official_url": "https://www.dfg.de/en/research-funding", "source_type": "official_index", "country": "Germany"},
    {"name": "TU Berlin – Scholarships and Funding for International Students", "official_url": "https://www.tu.berlin/en/international/students-1/international-students/international-degree-seeking-students/scholarships-and-other-funding-for-international-students", "source_type": "official_index", "country": "Germany"},
    {"name": "TU Berlin – Deutschlandstipendium (Application Requirements)", "official_url": "https://www.tu.berlin/en/careerservice/d-stipendium/application/basic-principles", "source_type": "official_programme", "country": "Germany"},
    {"name": "TU Berlin – STIBET I Equal Opportunities Scholarship", "official_url": "https://www.tu.berlin/en/international/students-1/international-students/international-degree-seeking-students/scholarships-and-other-funding-for-international-students/scholarships-for-promoting-equal-opportunities-stibet-i", "source_type": "official_programme", "country": "Germany"},
    {"name": "University of Würzburg – Scholarships by Target Group", "official_url": "https://www.uni-wuerzburg.de/en/scholarships/by-target-group/", "source_type": "official_index", "country": "Germany"},
    {"name": "University of Würzburg – Oskar Karl Forster Scholarship", "official_url": "https://www.uni-wuerzburg.de/en/stipendien/nach-zielgruppen/oskar-karl-forster-scholarship/", "source_type": "official_programme", "country": "Germany"},
    {"name": "University of Würzburg – Romana Schott Scholarship", "official_url": "https://www.uni-wuerzburg.de/en/equity/wro/scholarships-and-funding-opportunities/romana-schott-scholarships/", "source_type": "official_programme", "country": "Germany"},
    {"name": "University of Würzburg – Amend Medical Scholarship", "official_url": "https://www.med.uni-wuerzburg.de/en/service/stipendien/", "source_type": "official_programme", "country": "Germany"},
    {"name": "University of Kiel – Scholarships", "official_url": "https://www.uni-kiel.de/en/tf/study/scholarships", "source_type": "official_index", "country": "Germany"},
    {"name": "University of Kiel – Deutschlandstipendium", "official_url": "https://deutschlandstipendium-cau-kiel.de/en/infos-fuer-stipendiatinnen/", "source_type": "official_programme", "country": "Germany"},
    {"name": "HAW Kiel – Deutschlandstipendium", "official_url": "https://www.haw-kiel.de/en/studium/studieninteressierte/studienfinanzierung-stipendien/deutschlandstipendium/stipendiatin-werden/", "source_type": "official_programme", "country": "Germany"},
    {"name": "Freie Universität Berlin – Deutschlandstipendium", "official_url": "https://www.fu-berlin.de/en/sites/deutschlandstipendium/index.html", "source_type": "official_programme", "country": "Germany"},
    {"name": "University of Regensburg – Deutschlandstipendium", "official_url": "https://www.uni-regensburg.de/en/studies/deutschlandstipendium/information-for-students", "source_type": "official_programme", "country": "Germany"},
    {"name": "University of Tübingen – Deutschlandstipendium", "official_url": "https://uni-tuebingen.de/en/study/student-life/student-finances/deutschlandstipendium-scholarships", "source_type": "official_programme", "country": "Germany"},
    {"name": "University of Regensburg – International Office Study Grant and Funding", "official_url": "https://www.uni-regensburg.de/en/international/coming-to-regensburg/pursuing-a-degree-program/funding", "source_type": "official_index", "country": "Germany"},
    {"name": "University of Tübingen – DAAD STIBET Grants", "official_url": "https://uni-tuebingen.de/en/international/study-in-tuebingen/degree-seeking-students/getting-started-and-orientation-for-international-students/stibet-grants/", "source_type": "official_index", "country": "Germany"},
    {"name": "University of Göttingen – Scholarships and Funding for International Students", "official_url": "https://uni-goettingen.de/en/575849.html", "source_type": "official_index", "country": "Germany"},
    {"name": "University of Göttingen – Niedersachsenstipendium", "official_url": "https://uni-goettingen.de/en/306042.html", "source_type": "official_programme", "country": "Germany"},
    {"name": "University of Göttingen – DAAD Award and Scholarship for Exceptional Commitment", "official_url": "https://uni-goettingen.de/en/689526.html", "source_type": "official_index", "country": "Germany"},
    {"name": "Kühne Logistics University – Scholarships and Financial Aid", "official_url": "https://www.klu.org/student-life/student-services/scholarships-financial-aid", "source_type": "official_index", "country": "Germany"},
    {"name": "Kühne Logistics University – Deutschlandstipendium", "official_url": "https://www.klu.org/about-klu/student-services/scholarships/deutschlandstipendium", "source_type": "official_programme", "country": "Germany"},
)


# Compatibility name for the live source verification workflow.
OFFICIAL_SOURCES = GERMANY_SOURCES


OFFICIAL_DISCOVERY_TARGETS: tuple[tuple[str, str, str], ...] = ()


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

        # The old source pointed directly to a PDF, which the HTML-only
        # discovery fetcher cannot process. The current English programme page
        # is now the active source; keep the historical PDF row inactive.
        connection.execute(
            "UPDATE sources SET is_active = 0 WHERE official_url = ?",
            (LEGACY_KIEL_DEUTSCHLANDSTIPENDIUM_PDF_URL,),
        )

        for source in GERMANY_SOURCES:
            already_exists = connection.execute(
                "SELECT 1 FROM sources WHERE official_url = ?",
                (source["official_url"],),
            ).fetchone()
            connection.execute(
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
            if already_exists is None:
                inserted += 1
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
