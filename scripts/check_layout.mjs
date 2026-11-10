/** Real browser regression for public Arabic/English viewport clipping. */
import assert from "node:assert/strict";
import { chromium } from "../frontend/node_modules/playwright-core/index.mjs";

const browser = await chromium.launch({ channel: "chrome", headless: true });
let checks = 0;
try {
  for (const width of [320, 390, 768, 1024, 1440]) {
    const context = await browser.newContext({
      viewport: { width, height: 1000 },
    });
    const page = await context.newPage();
    await page.goto(process.env.DEMO_BASE_URL || "http://127.0.0.1:5173", {
      waitUntil: "networkidle",
    });
    for (const locale of ["ar", "en"]) {
      await page.locator(`.locale-switch button[lang=${locale}]`).click();
      const dimensions = await page.evaluate(() => ({
        content: document.documentElement.scrollWidth,
        viewport: document.documentElement.clientWidth,
      }));
      assert.ok(
        dimensions.content <= dimensions.viewport,
        `${locale} at ${width}px: content ${dimensions.content}px exceeds viewport ${dimensions.viewport}px`,
      );
      checks++;
    }
    await context.close();
  }
  console.log(`${checks} Arabic/English viewport checks passed.`);
} finally {
  await browser.close();
}
