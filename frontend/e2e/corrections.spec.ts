import { expect, test } from "@playwright/test";

test("missing amount remains visible after saving and corrections retain their source", async ({
  page,
  context,
}) => {
  test.setTimeout(150000);
  await page.goto("/");
  await expect(
    page.getByRole("heading", { name: "Κάθε φάκελος. Μια καθαρή εικόνα." }),
  ).toBeVisible();
  const cases = await (await context.request.get("/api/v1/cases")).json();
  const c = cases[2];
  const base = `/api/v1/cases/${c.id}/runs/${c.run_id}`;
  const url = `/cases/${c.id}/review?run=${c.run_id}&filter=pending&field=application.requested_amount`;
  await page.goto(url);
  await page.getByRole("button", { name: "Διόρθωση", exact: true }).click();
  await page.getByLabel("Νέα τιμή σε EUR").fill("750.000,00");
  await page
    .getByLabel("Αιτιολογία")
    .fill("Δοκιμαστική χειροκίνητη συμπλήρωση");
  await page
    .getByRole("button", { name: "Αποθήκευση απόφασης", exact: true })
    .click();
  await expect(page.getByRole("dialog")).toHaveCount(0);
  await expect(page.locator(".selected-card .selected-value")).toHaveText(
    "750.000 €",
  );
  await expect(page.locator(".save-status")).toContainText("αποθηκεύτηκε");
  await expect(page.locator(".selected-card")).toContainText("Εκκρεμεί πηγή");
  await page.reload();
  await expect(page.locator(".selected-card .selected-value")).toHaveText(
    "750.000 €",
  );
  const saved = await (await context.request.get(base)).json();
  expect(
    saved.fields.find((f: any) => f.id === "application.requested_amount")
      .normalized_value,
  ).toBe(750000);
  expect(
    saved.report.fields.find((f: any) => f.key === "requested_amount").complete,
  ).toBe(false);
  await page
    .getByRole("button", { name: "Ιστορικό στοιχείου", exact: true })
    .click();
  await expect(page.locator(".review-history")).toContainText("750.000 €");
  await page.getByRole("button", { name: "Κλείσιμο", exact: true }).click();

  // An existing documented correction must not silently lose its selected
  // evidence when the analyst edits only the value or comment a second time.
  await page.goto(
    `/cases/${c.id}/review?run=${c.run_id}&field=application.tenor_months`,
  );
  await page.getByRole("button", { name: "Διόρθωση", exact: true }).click();
  await page.getByLabel("Νέα τιμή").fill("60");
  await page.getByLabel("Τεκμηρίωση από το έγγραφο").selectOption("0");
  await page.getByLabel("Αιτιολογία").fill("Δοκιμαστική τεκμηριωμένη διόρθωση");
  await page
    .getByRole("button", { name: "Αποθήκευση απόφασης", exact: true })
    .click();
  await expect(page.getByRole("dialog")).toHaveCount(0);
  await expect(page.locator(".save-status")).toContainText("αποθηκεύτηκε");
  await page.getByRole("button", { name: "Διόρθωση", exact: true }).click();
  await expect(page.getByLabel("Τεκμηρίωση από το έγγραφο")).toHaveValue("0");
  await page.getByLabel("Αιτιολογία").fill("Ενημέρωση αιτιολογίας, ίδια πηγή");
  await page
    .getByRole("button", { name: "Αποθήκευση απόφασης", exact: true })
    .click();
  await expect(page.getByRole("dialog")).toHaveCount(0);
  await expect(page.locator(".save-status")).toContainText("αποθηκεύτηκε");
  await page.reload();
  const updated = await (await context.request.get(base)).json();
  const duration = updated.fields.find(
    (f: any) => f.id === "application.tenor_months",
  );
  expect(duration.normalized_value).toBe(60);
  expect(duration.sources).toHaveLength(1);
  expect(
    updated.report.fields.find((f: any) => f.key === "duration_months")
      .complete,
  ).toBe(true);
  expect(
    updated.reviews.filter((e: any) => e.field === "requested_amount"),
  ).toHaveLength(1);
  expect(
    updated.reviews.filter((e: any) => e.field === "tenor_months"),
  ).toHaveLength(2);
});
