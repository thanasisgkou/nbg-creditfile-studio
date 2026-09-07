import { expect, test } from "@playwright/test";
import { mkdirSync } from "node:fs";
import { resolve } from "node:path";
import AxeBuilder from "@axe-core/playwright";
const out = resolve("../output/studio");
mkdirSync(out, { recursive: true });

test("review, source, persisted decision, local chat and frozen bulletin", async ({
  page,
  request,
}) => {
  const errors: string[] = [];
  page.on("pageerror", (e) => errors.push(e.message));
  const { id } = (await (await request.get("/api/v1/cases")).json())[0];
  const summary = await (await request.get("/api/v1/cases/" + id)).json();
  const run = summary.run_id;
  await page.goto("/cases/" + id + "/overview");
  await expect(
    page.getByRole("heading", { name: "Το επόμενο βήμα είναι ξεκάθαρο." }),
  ).toBeVisible();
  await page.screenshot({ path: out + "/overview-1366.png" });
  await page.goto(`/cases/${id}/review?run=${run}&field=application.tax_id`);
  await expect(page.locator(".pdf-highlight").first()).toBeVisible({
    timeout: 30000,
  });
  await expect(page.locator(".textLayer span").first()).toBeVisible();
  await page.screenshot({ path: out + "/review-1366.png" });
  await page
    .getByRole("button", { name: "Επιβεβαίωση πεδίου", exact: true })
    .click();
  await expect(
    page.getByRole("status").filter({ hasText: "Η επιβεβαίωση αποθηκεύτηκε." }),
  ).toBeVisible();
  await page.reload();
  await expect(
    page.getByRole("button", { name: "Επιβεβαίωση πεδίου", exact: true }),
  ).toBeDisabled();
  await page
    .getByRole("button", { name: "Βοηθός φακέλου", exact: true })
    .click();
  await page
    .getByRole("button", { name: "Ποιο ποσό χρηματοδότησης ζητείται;" })
    .click();
  await expect(page.locator(".chat-answer")).toBeVisible({ timeout: 20000 });
  await page.getByRole("button", { name: "Κλείσιμο βοηθού" }).click();
  await page
    .getByRole("button", { name: "Βοηθός φακέλου", exact: true })
    .click();
  await expect(page.locator(".chat-answer")).toBeVisible();
  await page.goto("/");
  await page.goto(`/cases/${id}/review?run=${run}`);
  await page
    .getByRole("button", { name: "Βοηθός φακέλου", exact: true })
    .click();
  await expect(page.locator(".chat-welcome")).toBeVisible();
  await expect(page.locator(".chat-answer")).toHaveCount(0);
  await page.getByRole("button", { name: "Κλείσιμο βοηθού" }).click();
  await page.getByRole("link", { name: "Δελτίο προετοιμασίας" }).click();
  await expect(page.locator(".pdf-paper canvas")).toBeVisible();
  await page.getByRole("button", { name: "Έκδοση προσχεδίου" }).click();
  await page.getByRole("button", { name: "Αποθήκευση έκδοσης" }).click();
  await expect(
    page.getByRole("heading", { name: "Αποθηκευμένο προσχέδιο" }),
  ).toBeVisible({ timeout: 20000 });
  await expect(
    page.getByRole("link", { name: "Αίτηση χρηματοδότησης", exact: true }),
  ).toBeVisible();
  await page.screenshot({ path: out + "/bulletin-1366.png" });
  expect(errors).toEqual([]);
});

test("empty/import flows and responsive navigation without horizontal overflow", async ({
  page,
}) => {
  await page.goto("/");
  await expect(
    page.getByRole("heading", { name: "Κάθε φάκελος. Μια καθαρή εικόνα." }),
  ).toBeVisible();
  await page.screenshot({ path: out + "/library-1366.png" });
  await expect(page.getByText("Αντιγραφή από το παλιό app")).toHaveCount(0);
  await page.goto("/new");
  await expect(page.getByLabel("Επωνυμία / όνομα φακέλου")).toHaveCount(0);
  await expect(
    page.getByRole("heading", { name: "Ξεκινήστε από τα έγγραφα." }),
  ).toBeVisible();
  await page.screenshot({ path: out + "/import-1366.png" });
  await page.setViewportSize({ width: 390, height: 844 });
  await expect(page.getByRole("button", { name: "Επιλογή PDF" })).toBeVisible();
  expect(
    await page.evaluate(
      () => document.documentElement.scrollWidth <= window.innerWidth + 1,
    ),
  ).toBeTruthy();
  await page.screenshot({ path: out + "/mobile-390.png", fullPage: true });
});

test("bulk review, discrepancy evidence and correction history", async ({
  page,
  request,
}) => {
  const { id } = (await (await request.get("/api/v1/cases")).json())[1];
  const { run_id } = await (await request.get("/api/v1/cases/" + id)).json();
  await page.goto(
    `/cases/${id}/review?run=${run_id}&field=application.tenor_months`,
  );
  await page
    .getByRole("checkbox", {
      name: "Επιλογή ΑΦΜ Αίτηση χρηματοδότησης",
      exact: true,
    })
    .check();
  await page
    .getByRole("checkbox", {
      name: "Επιλογή Νομική μορφή Αίτηση χρηματοδότησης",
      exact: true,
    })
    .check();
  await page
    .locator(".review-actions")
    .getByRole("button", { name: "Επιβεβαίωση όλων (2)", exact: true })
    .click();
  await page.getByRole("button", { name: "Επιβεβαίωση 2 στοιχείων" }).click();
  await expect(
    page
      .getByRole("status")
      .filter({ hasText: "Τα επιλεγμένα στοιχεία επιβεβαιώθηκαν." }),
  ).toBeVisible();
  await page.getByRole("button", { name: "Διόρθωση", exact: true }).click();
  await page.getByLabel("Νέα τιμή").fill("60");
  await expect(
    page.getByLabel("Τεκμηρίωση από το έγγραφο").locator("option"),
  ).not.toHaveCount(1);
  const sourceOption = page
    .getByLabel("Τεκμηρίωση από το έγγραφο")
    .locator("option")
    .filter({ hasText: "Συνολική διάρκεια" })
    .first();
  await page
    .getByLabel("Τεκμηρίωση από το έγγραφο")
    .selectOption((await sourceOption.getAttribute("value"))!);
  await page
    .getByLabel("Αιτιολογία", { exact: true })
    .fill("Επαληθεύτηκε η συνολική διάρκεια στην αίτηση.");
  await page.getByRole("button", { name: "Αποθήκευση απόφασης" }).click();
  await expect(page.getByRole("dialog")).toHaveCount(0);
  await page.getByRole("button", { name: "Ιστορικό στοιχείου" }).click();
  await expect(
    page.getByText("Επαληθεύτηκε η συνολική διάρκεια στην αίτηση.", {
      exact: true,
    }),
  ).toBeVisible();
  await page.keyboard.press("Escape");
  await page.getByRole("button", { name: /Ασυμφωνίες/ }).click();
  await expect(
    page.locator(".comparison-readers .pdf-highlight").first(),
  ).toBeVisible({ timeout: 30000 });
  await page
    .getByLabel("Καταγραφή επίλυσης")
    .fill(
      "Οι δύο δηλώσεις αφορούν διαφορετική βάση αναφοράς. Καταγράφηκαν και οι δύο πηγές για διευκρίνιση.",
    );
  await page.getByRole("button", { name: "Αποθήκευση επίλυσης" }).click();
  await expect(page.locator(".notice.green")).toBeVisible();
  await page.screenshot({ path: out + "/comparison-1366.png" });
});

test("main screens accessibility", async ({ page, request }) => {
  await page.emulateMedia({ reducedMotion: "reduce" });
  const { id } = (await (await request.get("/api/v1/cases")).json())[2];
  for (const path of ["/", "/new", `/cases/${id}/review`]) {
    await page.goto(path);
    await expect(page.locator("main")).toBeVisible();
    await page.locator(".page-loading").waitFor({ state: "detached" });
    await page.evaluate(() => document.fonts.ready);
    const result = await new AxeBuilder({ page })
      .withTags(["wcag2a", "wcag2aa", "wcag21aa"])
      .analyze();
    expect(
      result.violations.map((v) => ({
        id: v.id,
        nodes: v.nodes.map((n) => ({
          target: n.target,
          summary: n.failureSummary,
        })),
      })),
    ).toEqual([]);
  }
});

test("production branding serves PNGs and missing assets return 404", async ({
  page,
  request,
}) => {
  for (const name of ["nbg-logo.png", "nbg-favicon.png"]) {
    const response = await request.get("/branding/" + name);
    expect(response.status()).toBe(200);
    expect(response.headers()["content-type"]).toContain("image/png");
    expect((await response.body()).subarray(0, 8).toString("hex")).toBe(
      "89504e470d0a1a0a",
    );
  }
  expect((await request.get("/branding/missing.png")).status()).toBe(404);
  expect((await request.get("/missing.png")).status()).toBe(404);
  await page.goto("/");
  const logo = page.locator('img[src="/branding/nbg-logo.png"]').first();
  await expect(logo).toBeVisible();
  expect(
    await logo.evaluate((img: HTMLImageElement) => img.naturalWidth),
  ).toBeGreaterThan(0);
});
