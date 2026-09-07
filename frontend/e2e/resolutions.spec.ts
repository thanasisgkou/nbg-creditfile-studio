import { expect, test } from "@playwright/test";

test("two saved source resolutions survive individual and bulk field confirmation", async ({
  page,
  context,
}) => {
  test.setTimeout(150000);
  await page.goto("/");
  await expect(
    page.getByRole("heading", { name: "Κάθε φάκελος. Μια καθαρή εικόνα." }),
  ).toBeVisible();
  const cases = await (await context.request.get("/api/v1/cases")).json();
  const c = cases[3];
  const base = `/api/v1/cases/${c.id}/runs/${c.run_id}`;
  await page.goto(`/cases/${c.id}/review?run=${c.run_id}`);
  await page.getByRole("button", { name: /Ασυμφωνίες/ }).click();
  await expect(
    page.getByText("2 εκκρεμείς έλεγχοι", { exact: true }),
  ).toBeVisible();
  for (const label of ["Κύκλος εργασιών", "Δανεισμός"]) {
    await page
      .locator(".conflict-tabs")
      .getByRole("button", { name: label, exact: true })
      .click();
    await page.getByLabel("Καταγραφή επίλυσης").fill("OK");
    await page
      .getByRole("button", { name: "Αποθήκευση επίλυσης", exact: true })
      .click();
    await expect(page.locator(".notice.green")).toHaveText("OK");
  }
  await expect(
    page.getByText("0 εκκρεμείς έλεγχοι", { exact: true }),
  ).toBeVisible();
  await page.goto(
    `/cases/${c.id}/review?run=${c.run_id}&field=application.tax_id`,
  );
  await page
    .getByRole("button", { name: "Επιβεβαίωση πεδίου", exact: true })
    .click();
  await expect(
    page.getByRole("status").filter({ hasText: "Η επιβεβαίωση αποθηκεύτηκε." }),
  ).toBeVisible();
  for (const label of ["Επωνυμία", "Νομική μορφή"]) {
    await page
      .getByRole("checkbox", {
        name: `Επιλογή ${label} Αίτηση χρηματοδότησης`,
        exact: true,
      })
      .check();
  }
  await page
    .locator(".review-actions")
    .getByRole("button", { name: "Επιβεβαίωση όλων (2)", exact: true })
    .click();
  await page
    .getByRole("button", { name: "Επιβεβαίωση 2 στοιχείων", exact: true })
    .click();
  await expect(
    page
      .getByRole("status")
      .filter({ hasText: "Τα επιλεγμένα στοιχεία επιβεβαιώθηκαν." }),
  ).toBeVisible();
  await page.reload();
  await page.getByRole("button", { name: /Ασυμφωνίες/ }).click();
  await expect(
    page.getByText("0 εκκρεμείς έλεγχοι", { exact: true }),
  ).toBeVisible();
  const workspace = await (await context.request.get(base)).json();
  expect(workspace.report.conflicts).toHaveLength(2);
  expect(
    workspace.report.conflicts.every((c: any) => c.resolution?.reason === "OK"),
  ).toBeTruthy();
});
