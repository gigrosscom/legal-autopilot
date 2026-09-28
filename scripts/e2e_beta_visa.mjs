// E2E (Playwright, Chromium): a person opens the site, describes a Schengen-visa trip, answers the interview on
// the case screen and reaches the prepared document package. Runs against a local app with the mock LLM:
//
//   API:  EXPERIMENTAL_SCENARIOS=true LLM_PROVIDER=mock uvicorn --factory konsilier.main:app_factory --port 18011
//   Web:  NEXT_PUBLIC_API_URL=http://localhost:18011 npx next dev -p 3471
//   Run:  WEB=http://localhost:3471 SHOTS=/tmp/claude-0/beta-shots node scripts/e2e_beta_visa.mjs
//
// Playwright is not a project dependency: the script takes it from the global install (npm i -g playwright).
import { createRequire } from "node:module";
import { execSync } from "node:child_process";
import fs from "node:fs";
import path from "node:path";

const require = createRequire(import.meta.url);
const globalRoot = execSync("npm root -g").toString().trim();
const { chromium } = require(path.join(globalRoot, "playwright"));

const WEB = process.env.WEB ?? "http://localhost:3471";
const SHOTS = process.env.SHOTS ?? "/tmp/claude-0/beta-shots";
const EXE = process.env.CHROMIUM ?? "/opt/pw-browsers/chromium";
fs.mkdirSync(SHOTS, { recursive: true });

// answer by the question text; optional questions without an answer here are skipped with «Пропустить»
const ANSWERS = [
  [/даты поездки/i, "10.11.2026 — 20.11.2026"],
  [/маршрут/i, "10–14.11 Берлин, отель; 14–20.11 Мюнхен, отель. Германия — основная цель."],
  [/где будете жить/i, "Отель Adlon, Берлин; Hotel Bayer, Мюнхен — брони оплачены при заезде"],
  [/цель поездки/i, "Туризм: музеи Берлина и Мюнхена. Работаю бухгалтером, в Алматы семья и квартира, вернусь к работе 23.11.2026."],
  [/где работаете/i, "ТОО «Альфа», главный бухгалтер"],
  [/оплачивает/i, "Иванов Серик, супруг"],
  [/номер загранпаспорта/i, "N12345678"],
  [/(фио|имя|фамили)/i, "Иванова Айгуль Серикқызы"],
  [/адрес/i, "Алматы, ул. Абая 1, кв. 5"],
  [/телефон/i, "+7 701 123 45 67"],
  [/e-mail/i, "aigul@example.com"],
];

const shot = async (page, name) => {
  await page.screenshot({ path: path.join(SHOTS, `${name}.png`), fullPage: true });
  console.log("screenshot", name);
};

const browser = await chromium.launch({ executablePath: EXE, headless: true });
const page = await (await browser.newContext({ viewport: { width: 420, height: 900 }, locale: "ru-RU" })).newPage();
page.on("pageerror", (e) => console.log("pageerror:", e.message));

// 1. the story in the free chat opens a case
await page.goto(`${WEB}/start`);
const box = page.locator("textarea").first();
await box.fill("Нужна шенгенская виза в Германию для туристической поездки, какие документы собрать");
await shot(page, "01-start");
await page.getByRole("button", { name: "Отправить" }).click();
await page.waitForURL(/\/chat\/[0-9a-f-]{36}/, { timeout: 60_000 });
const caseId = page.url().match(/[0-9a-f-]{36}/)[0];
console.log("case", caseId);

// 2. the case screen: «Бета» mark and the interview
await page.goto(`${WEB}/case/${caseId}`);
await page.getByTestId("beta-notice").waitFor({ timeout: 60_000 });
await page.waitForTimeout(800);
await page.evaluate(() => document.querySelectorAll("*").forEach((e) => { if (e.scrollTop > 0) e.scrollTop = 0; }));
await shot(page, "02-case-beta");

for (let i = 0; i < 25; i++) {
  const prepare = page.getByRole("button", { name: "Подготовить документ" });
  if (await prepare.isVisible().catch(() => false)) break;
  const form = page.locator("form").filter({ has: page.getByRole("button", { name: "Ответить" }) }).last();
  await form.waitFor({ timeout: 30_000 });
  const question = (await form.locator("label .sr-only").last().textContent())?.trim() ?? "";
  const hit = ANSWERS.find(([re]) => re.test(question));
  const skip = form.getByRole("button", { name: "Пропустить" });
  if (!hit && (await skip.isVisible().catch(() => false))) {
    console.log("skip:", question);
    await skip.click();
  } else {
    const answer = hit ? hit[1] : "Ответ";
    console.log("answer:", question, "→", answer);
    await form.locator("input:not([type=file]), textarea").first().fill(answer);
    await form.getByRole("button", { name: "Ответить" }).click();
  }
  await page.waitForTimeout(700);
  if (i === 3) await shot(page, "03-interview");
}

// 3. the plan with the personal checklist → prepare the package
const prepare = page.getByRole("button", { name: "Подготовить документ" });
await prepare.waitFor({ timeout: 30_000 });
await shot(page, "04-plan-checklist");
await prepare.click();
await page.getByRole("button", { name: /Документ подан/ }).waitFor({ timeout: 120_000 });
await shot(page, "05-documents");

// 4. the document itself: the API serves DOCX (and PDF when LibreOffice is available)
const res = await page.evaluate(async (id) => {
  const token = localStorage.getItem("konsilier.token");
  const api = (window.__API_URL__) || "http://localhost:18011";
  const c = await (await fetch(`${api}/v1/cases/${id}`, { headers: { Authorization: `Bearer ${token}` } })).json();
  const a = c.actions[0];
  return { status: a.status, has_docx: a.has_docx, has_pdf: a.has_pdf, beta: c.scenario.beta, scenario: c.scenario.id,
           checklist: (c.plan?.attachments ?? []).length };
}, caseId);
console.log("result", JSON.stringify(res));
await browser.close();
if (!(res.status === "ready" && res.has_docx && res.beta && res.scenario === "kz.services.visa_schengen_de")) {
  console.error("E2E FAILED");
  process.exit(1);
}
console.log("E2E OK");
