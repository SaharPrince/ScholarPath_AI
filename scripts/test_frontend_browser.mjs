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
  application_url: "javascript:alert(1)",
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
      evidence_url: "data:text/html,<script>alert(1)</script>"
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
    await page.route("**/api/currency-rates**", route => {
      const url = new URL(route.request().url());
      const amount = Number(url.searchParams.get("amount") || 1);
      const from = url.searchParams.get("from_currency") || "PKR";
      const to = url.searchParams.get("to_currency") || "EUR";
      const rates = { PKR: 1, EUR: 0.003, USD: 0.004 };
      return route.fulfill({
        status: 200,
        contentType: "application/json",
        body: JSON.stringify({
          amount, from_currency: from, to_currency: to,
          rate: rates[to] / rates[from],
          converted_amount: amount * rates[to] / rates[from],
          updated_at: "2026-11-22T00:00:00+00:00",
          next_update_at: "2026-11-23T00:00:00+00:00",
          source: { name: "Test provider", url: "https://example.com" },
          is_stale: false
        })
      });
    });

    await page.route("**/api/discovery-status", route => route.fulfill({
      status: 200,
      contentType: "application/json",
      body: JSON.stringify({
        status: "partial",
        partial: true,
        total_sources: 5,
        completed_sources: 3,
        pages_attempted: 8,
        pages_succeeded: 6,
        pages_unavailable: 1,
        pages_cancelled: 1,
        failed_sources: [],
        timed_out_sources: ["Slow official provider"],
        sources_with_unavailable_pages: ["Restricted provider"]
      })
    }));

    let matchRequestCount = 0;
    const alternativeTestScoreResult = {
      total: 1,
      likely_eligible: 0,
      needs_more_information: 1,
      not_eligible: 0,
      notice: "Preliminary matching only.",
      results: [{
        id: 501,
        title: "Adaptive Test Scholarship",
        provider_name: "Official Provider",
        deadline_text: "Not stated",
        source_url: sourceUrl,
        match_status: "needs_more_information",
        checks_passed: 0,
        checks_unknown: 1,
        checks: [{
          criterion_label: "GRE / HEC-HAT",
          requirement_text: "Applicants need a GRE score of at least 300 or a HEC-HAT score of at least 60.",
          status: "unknown",
          explanation: "Add your GRE or HEC-HAT score to check this alternative requirement.",
          evidence_url: sourceUrl
        }]
      }]
    };
    await page.route("**/api/match", async route => {
      matchRequestCount += 1;
      const submitted = route.request().postDataJSON();
      if (matchRequestCount === 1) {
        assert.equal(submitted.age, undefined, "age should be requested only when a live criterion needs it");
        return route.fulfill({
          status: 200,
          contentType: "application/json",
          body: JSON.stringify({
            total: 1,
            likely_eligible: 0,
            needs_more_information: 1,
            not_eligible: 0,
            notice: "Preliminary matching only.",
            results: [{
              id: 501,
              title: "Adaptive Test Scholarship",
              provider_name: "Official Provider",
              deadline_text: "Not stated",
              source_url: sourceUrl,
              match_status: "needs_more_information",
              checks_passed: 0,
              checks_unknown: 1,
              checks: [{
                criterion_label: "Age limit",
                requirement_text: "Applicants must meet the provider's age limit.",
                status: "unknown",
                explanation: "Add your age to check the published age limit.",
                evidence_url: sourceUrl
              }]
            }]
          })
        });
      }
      if (matchRequestCount === 2) {
        assert.equal(submitted.age, 20, "the adaptive answer should be included in the next matching request");
        return route.fulfill({status:200,contentType:"application/json",body:JSON.stringify(alternativeTestScoreResult)});
      }
      if (matchRequestCount === 3) {
        assert.equal(submitted.test_score_type, "hat", "the selected test type should be submitted");
        assert.equal(submitted.hat_score, undefined, "the score should be asked separately");
        return route.fulfill({status:200,contentType:"application/json",body:JSON.stringify(alternativeTestScoreResult)});
      }
      assert.equal(submitted.test_score_type, "hat");
      assert.equal(submitted.hat_score, 65, "the selected HEC-HAT score should be submitted as a HAT value");
      return route.fulfill({
        status: 200,
        contentType: "application/json",
        body: JSON.stringify({
          total: 1,
          likely_eligible: 1,
          needs_more_information: 0,
          not_eligible: 0,
          notice: "Preliminary matching only.",
          results: [{
            id: 501,
            title: "Adaptive Test Scholarship",
            provider_name: "Official Provider",
            deadline_text: "Not stated",
            source_url: "javascript:alert(1)",
            match_status: "likely_eligible",
            checks_passed: 1,
            checks_unknown: 0,
            checks: [{
              criterion_label: "Test criterion",
              requirement_text: "A published condition.",
              status: "unknown",
              explanation: "Confirm the condition with the provider.",
              evidence_url: "javascript:alert(1)"
            }]
          }]
        })
      });
    });

    await page.route("**/api/germany-guide", route => route.fulfill({
      status: 200,
      contentType: "application/json",
      body: JSON.stringify({
        version: "2026-11-22",
        country: "Germany",
        notice: "Confirm details with official authorities.",
        sections: [{
          id: "flight-from-pakistan",
          title: "Travelling from Pakistan to Germany",
          subtitle: "Prepare before departure.",
          items: [{
            title: "Pack your documents",
            bullets: ["Keep your passport and admission letter in hand luggage."],
            links: [
              { label: "Official travel guidance", url: "https://www.make-it-in-germany.com/" },
              { label: "Unsafe test link", url: "javascript:alert(1)" }
            ]
          }]
        }]
      })
    }));

    await page.goto("http://127.0.0.1:8000/", { waitUntil: "domcontentloaded" });
    await page.waitForSelector(".card");

    await page.waitForSelector(".guide-section");
    await page.waitForFunction(() => document.querySelector("#discoveryCoverage")?.textContent?.includes("Some official pages could not be reached"));
    assert.match(await page.locator("#discoveryCoverage").innerText(), /6 of 8 pages checked successfully/);
    await page.locator("#discoveryCoverage details summary").click();
    assert.match(await page.locator("#discoveryCoverage").innerText(), /Slow official provider/);

    await page.waitForFunction(() => document.querySelector("#currencyResult strong")?.textContent?.length > 0);
    assert.match(await page.locator("#currencyResult").innerText(), /EUR/);
    await page.locator("#currencySwap").click();
    await page.waitForFunction(() => document.querySelector("#currencyResult strong")?.textContent?.length > 0);
    assert.equal(await page.locator("#currencyFrom").inputValue(), "EUR");
    assert.equal(await page.locator("#currencyTo").inputValue(), "PKR");

    assert.match(await page.locator("#germanyGuideTitle").innerText(), /Germany preparation guide/);
    assert.match(await page.locator(".guide-section summary").innerText(), /Travelling from Pakistan/);
    assert.equal(await page.locator(".guide-links a").count(), 1, "unsafe guide URLs must not become links");
    assert.match(await page.locator(".guide-links a").first().getAttribute("href"), /^https:\/\//);
    const guideTask = page.locator("[data-guide-task]");
    await guideTask.check();
    assert.equal(await page.locator("#guideProgressText").innerText(), "Preparation checklist complete");
    await guideTask.uncheck();
    assert.match(await page.locator("#guideProgressText").innerText(), /0 of 1 tasks completed/);
    await guideTask.check();
    assert.equal(await page.locator("#guideProgressText").innerText(), "Preparation checklist complete");
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
    assert.equal(await page.locator(".links a").count(), 1, "unsafe application URLs must be omitted");
    assert.equal(await page.locator(".criterion a").count(), 1, "unsafe evidence URLs must be omitted");
    assert.equal(await page.locator('a[href^="javascript:"], a[href^="data:"]').count(), 0);
    await page.locator("#close").click();
    await page.waitForFunction(() => !document.querySelector("#overlay")?.classList.contains("show"));

    assert.equal(await page.locator('#profileForm label[for="profile-nationality"]').count(), 1, "profile inputs should have associated labels");
    assert.equal(await page.locator('#profileForm label[for="profile-current_education_level"]').count(), 1, "study-level select should have an associated label");
    for (const name of ["age", "education_field", "german_language_level", "professional_experience_years", "residence_country", "admission_confirmed", "current_university_name", "domicile_region"]) {
      const field = page.locator('#profileForm [name="' + name + '"]').locator("xpath=ancestor::div[contains(@class,'profile-field')][1]");
      assert.equal(await field.isVisible(), false, name + " should be requested only when a published criterion needs it");
    }
    assert.equal(await page.locator('#profileForm [name="nationality"]').isVisible(), true, "nationality should remain in the short starter form");
    assert.equal(await page.locator('#profileForm [name="current_education_level"]').isVisible(), true, "highest education should remain in the short starter form");
    const education = page.locator('#profileForm [name="current_education_level"]');
    const marksField = page.locator('#profileForm [name="academic_percentage"]').locator("xpath=ancestor::div[contains(@class,'profile-field')][1]");
    const cgpaField = page.locator('#profileForm [name="cgpa"]').locator("xpath=ancestor::div[contains(@class,'profile-field')][1]");
    await education.selectOption("intermediate");
    assert.equal(await marksField.isVisible(), true, "Intermediate applicants should see percentage marks");
    assert.equal(await cgpaField.isVisible(), false, "Intermediate applicants should not see CGPA");
    await education.selectOption("bachelors");
    assert.equal(await marksField.isVisible(), false, "University applicants should not see school percentage marks");
    assert.equal(await cgpaField.isVisible(), true, "University applicants should see CGPA");
    await education.selectOption("intermediate");
    await page.locator('#profileForm [name="nationality"]').fill("Pakistani");
    await page.locator('#profileForm [name="target_study_level"]').selectOption("bachelors");
    await page.locator("#matchButton").click();
    await page.waitForSelector("#adaptiveContinue");
    assert.equal(await page.locator("#matchResults h3").innerText(), "One more thing");
    assert.equal(await page.locator('#matchResults label[for="adaptiveAnswer"]').innerText(), "How old are you?");
    assert.equal(await page.locator("#adaptiveAnswer").getAttribute("aria-describedby"), "adaptiveScholarship");
    assert.equal(await page.locator("#adaptiveAnswer").getAttribute("step"), "any", "adaptive numeric answers should accept decimal values when relevant");
    assert.equal(await page.locator("#matchResults input").count(), 1, "only one adaptive question should be shown at a time");
    await page.locator("#matchResults input").fill("20");
    await page.locator("#adaptiveContinue").click();
    await page.waitForFunction(() => document.querySelector("#adaptiveLabel")?.textContent === "Which test score would you like to use?");
    await page.locator("#adaptiveAnswer").selectOption("hat");
    await page.locator("#adaptiveContinue").click();
    await page.waitForFunction(() => document.querySelector("#adaptiveLabel")?.textContent === "What was your HEC-HAT score?");
    await page.locator("#adaptiveAnswer").fill("65");
    await page.locator("#adaptiveContinue").click();
    await page.waitForFunction(() => document.querySelector("#matchResults h3")?.textContent === "Your scholarship matches");
    assert.equal(matchRequestCount, 4, "each adaptive answer should trigger exactly one fresh match");
    assert.match(await page.locator("#matchResults").innerText(), /Adaptive Test Scholarship/);
    await page.locator("#matchResults button[data-match]").click();
    await page.waitForSelector("#overlay.show");
    assert.equal(await page.locator("#detailBody a").count(), 0, "unsafe match-result source and evidence URLs must be omitted");
    assert.equal(await page.locator('a[href^="javascript:"], a[href^="data:"]').count(), 0);

    await page.close();
  }
} finally {
  await browser.close();
}

process.stdout.write("Scholarship detail and adaptive eligibility browser checks passed at desktop and mobile viewports.\n");
