import { chromium } from "playwright";
import assert from "node:assert/strict";

const sourceUrl = "https://www.rosalux.de/stiftung/studienwerk/stipendien/promotionsstipendium";
const expectedSummary =
  "Provide proof of very good German-language skills at B2 level, even if your dissertation is written in English";

const scholarship = [{
  id: 42,
  title: "Rosa Luxemburg Doctoral Scholarship",
  provider_name: "Rosa-Luxemburg-Stiftung",
  country: "Germany",
  study_destination: "Germany",
  deadline_text: "Not stated by the provider",
  funding_summary: "Funding details are not included in this UI fixture.",
  application_status: "unknown",
  status: "unverified",
  source_name: "Rosa-Luxemburg-Stiftung",
  source_url: sourceUrl,
  application_url: null,
  applicant_category: "doctoral",
  criteria: [
    {
      id: "42-1",
      criterion_type: "language_requirements",
      criterion_label: "German language proficiency",
      requirement_text:
        "Sehr gute Deutschkenntnisse (Nachweis des Spracherwerbs - Niveau B2, auch wenn die Dissertation auf Englisch verfasst wird)",
      is_mandatory: true,
      evidence_url: sourceUrl
    },
    {
      id: "42-2",
      criterion_type: "selection_criteria",
      criterion_label: "Social engagement",
      requirement_text:
        "ausgeprägtes gesellschaftliches Engagement im Sinne der Rosa-Luxemburg-Stiftung",
      is_mandatory: false,
      evidence_url: sourceUrl
    }
  ]
}];

const browser = await chromium.launch({ headless: true });
try {
  for (const viewport of [
    { name: "desktop", width: 1280, height: 900 },
    { name: "mobile", width: 375, height: 812 }
  ]) {
    const page = await browser.newPage({ viewport: { width: viewport.width, height: viewport.height } });
    await page.route("**/api/scholarships**", route => route.fulfill({
      status: 200,
      contentType: "application/json",
      body: JSON.stringify(scholarship)
    }));
    await page.route("**/api/sources", route => route.fulfill({
      status: 200,
      contentType: "application/json",
      body: JSON.stringify([{ name: "Rosa-Luxemburg-Stiftung" }])
    }));

    await page.goto("http://127.0.0.1:8000/", { waitUntil: "domcontentloaded" });
    await page.waitForSelector(".card");
    await page.locator("button.detailbtn").click();
    await page.waitForSelector("#overlay.show");

    assert.equal(await page.locator(".criterion-copy").first().innerText(), expectedSummary);
    const groupHeadings = await page.locator(".requirement-group h4").allInnerTexts();
    assert.deepEqual(groupHeadings, ["Mandatory requirements", "Other information"]);

    const drawerWidth = await page.locator(".drawer").evaluate(el => el.getBoundingClientRect().width);
    assert.ok(drawerWidth <= viewport.width + 1, viewport.name + ": detail panel exceeds viewport width");
    const horizontalOverflow = await page.evaluate(() => document.documentElement.scrollWidth > window.innerWidth);
    assert.equal(horizontalOverflow, false, viewport.name + ": page has horizontal overflow");

    const original = page.locator(".original-wording");
    assert.equal(await original.count(), 1);
    await original.locator("summary").click();
    assert.notEqual(await original.getAttribute("open"), null, viewport.name + ": original wording did not expand");
    assert.match(await original.locator("p").innerText(), /Sehr gute Deutschkenntnisse/);

    const evidenceHref = await page.locator(".criterion a").first().getAttribute("href");
    const sourceHref = await page.locator(".links a").first().getAttribute("href");
    assert.equal(evidenceHref, sourceUrl);
    assert.equal(sourceHref, sourceUrl);

    await page.close();
  }
} finally {
  await browser.close();
}

process.stdout.write("Requirements detail-panel browser checks passed at desktop and mobile viewports.\n");
