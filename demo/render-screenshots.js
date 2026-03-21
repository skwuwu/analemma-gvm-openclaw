const puppeteer = require("puppeteer");
const path = require("path");
const fs = require("fs");

const ASSETS = path.join(__dirname, "..", "assets");
const files = ["01-shadow-deny", "02-allow-flow", "03-dashboard"];

(async () => {
  const browser = await puppeteer.launch({ headless: "new" });

  for (const name of files) {
    const htmlPath = path.join(ASSETS, `${name}.html`);
    if (!fs.existsSync(htmlPath)) {
      console.log(`Skip: ${htmlPath} not found`);
      continue;
    }

    const page = await browser.newPage();
    await page.setViewport({ width: 720, height: 900, deviceScaleFactor: 2 });
    await page.goto(`file://${htmlPath}`, { waitUntil: "load" });

    // Auto-size height to content
    const height = await page.evaluate(() => document.body.scrollHeight + 48);
    await page.setViewport({ width: 720, height: Math.min(height, 1200), deviceScaleFactor: 2 });

    const outPath = path.join(ASSETS, `${name}.png`);
    await page.screenshot({ path: outPath, fullPage: true });
    console.log(`Rendered: ${outPath}`);
    await page.close();
  }

  await browser.close();
})();
