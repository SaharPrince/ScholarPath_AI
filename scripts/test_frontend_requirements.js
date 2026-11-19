const fs = require("node:fs");
const path = require("node:path");
const vm = require("node:vm");
const assert = require("node:assert/strict");

const html = fs.readFileSync(path.join(process.cwd(), "app/static/index.html"), "utf8");
const inlineScript = html.match(/<script\b[^>]*>([\s\S]*?)<\/script>/i)?.[1];
assert.ok(inlineScript, "the page must contain its inline browser script");

const start = inlineScript.indexOf("function hasMultipleClauses(");
const end = inlineScript.indexOf("\nfunction renderRequirements(", start);
assert.ok(start >= 0 && end > start, "requirement helpers must remain available for testing");

const sandbox = {};
vm.runInNewContext(
  inlineScript.slice(start, end) + "\nglobalThis.requirementHelpers = { summarizeRequirement, requirementPairs };",
  sandbox
);
const { summarizeRequirement, requirementPairs } = sandbox.requirementHelpers;

const rosaGermanRequirement =
  "Sehr gute Deutschkenntnisse (Nachweis des Spracherwerbs - Niveau B2, auch wenn die Dissertation auf Englisch verfasst wird)";
assert.equal(
  summarizeRequirement(rosaGermanRequirement),
  "Provide proof of very good German-language skills at B2 level, even if your dissertation is written in English."
);

assert.equal(
  summarizeRequirement("Sehr gute deutsche Sprachkenntnisse"),
  "Have very good German-language skills. The provider does not state a clear level here, so confirm what level they accept."
);
assert.equal(
  summarizeRequirement("Gute Deutschkenntnisse (Niveau B2)"),
  "Have good German-language skills at B2 level."
);


assert.equal(
  summarizeRequirement("gesellschaftspolitisch engagiert sein"),
  "Be actively engaged in social and political issues."
);
assert.equal(
  summarizeRequirement("sich mit den Werten der sozialen Demokratie identifizieren"),
  "Identify with the values of social democracy."
);

const compound =
  "Students of all disciplines may apply, and must study full-time at a state-recognized university.";
assert.equal(summarizeRequirement(compound), compound);
const compoundPairs = requirementPairs("study_level", "Study requirements", compound);
assert.equal(compoundPairs.length, 1, "compound requirements must not be split into partial summaries");
assert.match(compoundPairs[0][1], /all disciplines.*full-time.*state-recognized university/i);

process.stdout.write("Frontend requirement-summary tests passed.\n");
