import fs from "node:fs";
import path from "node:path";
import { chromium, firefox, webkit } from "playwright";

const root = process.cwd();
const source = fs.readFileSync(path.join(root, "anna", "bundle", "index.html"), "utf8");
const html = source.replace(/<script\b[^>]*>[\s\S]*?<\/script>/gi, "");
const outputDir = path.join(root, "artifacts", "anna-visual");
fs.mkdirSync(outputDir, { recursive: true });

const viewports = [
  { name: "desktop", width: 1440, height: 900, touch: false },
  { name: "short-laptop", width: 1280, height: 680, touch: false },
  { name: "tablet-portrait", width: 834, height: 1112, touch: true },
  { name: "tablet-landscape", width: 1024, height: 768, touch: true },
  { name: "phone", width: 390, height: 844, touch: true },
  { name: "small-phone", width: 320, height: 700, touch: true },
];

function assert(condition, message) {
  if (!condition) throw new Error(message);
}

async function inspect(browserType, engineName) {
  const browser = await browserType.launch({ headless: true });
  try {
    for (const viewport of viewports) {
      const context = await browser.newContext({
        viewport: { width: viewport.width, height: viewport.height },
        deviceScaleFactor: 1,
        // Firefox does not emulate touchscreen input; its CSS layout is still
        // checked at the same compact viewport widths.
        hasTouch: viewport.touch && engineName !== "firefox",
      });
      const page = await context.newPage();
      const pageErrors = [];
      const consoleErrors = [];
      page.on("pageerror", error => pageErrors.push(error.message));
      page.on("console", message => {
        if (message.type() === "error") consoleErrors.push(message.text());
      });

      await page.setContent(html, { waitUntil: "domcontentloaded" });
      await page.evaluate(() => document.fonts?.ready);
      const width = await page.evaluate(() => window.innerWidth);
      const initial = await page.evaluate(() => ({
        bodyWidth: document.documentElement.scrollWidth,
        gridColumns: getComputedStyle(document.querySelector(".grid")).gridTemplateColumns,
        requestDisplay: getComputedStyle(document.querySelector("#request-panel")).display,
        resultDisplay: getComputedStyle(document.querySelector("#result")).display,
        securityDisplay: getComputedStyle(document.querySelector("#security-model")).display,
        coarsePointer: matchMedia("(pointer: coarse)").matches,
      }));
      assert(initial.bodyWidth <= width, `${engineName}/${viewport.name}: horizontal overflow in request view (${initial.bodyWidth}px > ${width}px)`);
      assert(initial.requestDisplay !== "none", `${engineName}/${viewport.name}: request form is hidden on initial view`);
      assert(initial.resultDisplay === "none", `${engineName}/${viewport.name}: result should start hidden`);
      if (width > 960) {
        assert(initial.gridColumns.trim().split(/\s+/).length === 2, `${engineName}/${viewport.name}: desktop should use two columns`);
      } else {
        assert(initial.securityDisplay === "none", `${engineName}/${viewport.name}: compact request view should hide secondary explainer`);
      }

      // Simulate the same view state classes that the real app toggles after
      // a signed policy result is verified.
      await page.evaluate(() => {
        const view = document.querySelector("#check-view");
        view.classList.remove("editing-request", "showing-how");
        view.classList.add("showing-result");
        document.querySelector("#result").style.display = "block";
        document.querySelector("#security-model").hidden = true;
      });
      const resultState = await page.evaluate(() => {
        const request = document.querySelector("#request-panel");
        const result = document.querySelector("#result");
        const edit = document.querySelector("#edit-request-btn");
        return {
          bodyWidth: document.documentElement.scrollWidth,
          requestDisplay: getComputedStyle(request).display,
          resultDisplay: getComputedStyle(result).display,
          resultBox: result.getBoundingClientRect().toJSON(),
          requestBox: request.getBoundingClientRect().toJSON(),
          editDisplay: getComputedStyle(edit).display,
          editHeight: edit.getBoundingClientRect().height,
          resultOverflow: result.scrollHeight > result.clientHeight + 2,
        };
      });
      assert(resultState.bodyWidth <= width, `${engineName}/${viewport.name}: horizontal overflow in result view`);
      assert(resultState.resultDisplay !== "none", `${engineName}/${viewport.name}: result panel is not visible`);
      if (width <= 960) {
        assert(resultState.requestDisplay === "none", `${engineName}/${viewport.name}: compact result view must hide the request form`);
        assert(resultState.editDisplay !== "none", `${engineName}/${viewport.name}: Edit request action is not visible`);
        assert(resultState.editHeight >= 44, `${engineName}/${viewport.name}: Edit request touch target is below 44px`);
      } else {
        assert(resultState.requestDisplay !== "none", `${engineName}/${viewport.name}: desktop should retain the request beside the result`);
        assert(resultState.requestBox.x < resultState.resultBox.x, `${engineName}/${viewport.name}: result is not positioned to the right of the request`);
      }
      if (viewport.name === "desktop" || viewport.name === "phone") {
        await page.screenshot({
          path: path.join(outputDir, `${engineName}-${viewport.name}-result.png`),
          fullPage: true,
        });
      }

      await page.evaluate(() => {
        const view = document.querySelector("#check-view");
        view.classList.remove("showing-result");
        view.classList.add("editing-request");
        document.querySelector("#result").style.display = "none";
        document.querySelector("#security-model").hidden = false;
      });
      const requestState = await page.evaluate(() => ({
        bodyWidth: document.documentElement.scrollWidth,
        requestDisplay: getComputedStyle(document.querySelector("#request-panel")).display,
        resultDisplay: getComputedStyle(document.querySelector("#result")).display,
      }));
      assert(requestState.bodyWidth <= width, `${engineName}/${viewport.name}: horizontal overflow returning to request`);
      assert(requestState.requestDisplay !== "none" && requestState.resultDisplay === "none",
        `${engineName}/${viewport.name}: request/edit state is inconsistent`);

      await page.evaluate(() => {
        const view = document.querySelector("#check-view");
        view.classList.remove("editing-request");
        view.classList.add("showing-how");
      });
      const howState = await page.evaluate(() => ({
        bodyWidth: document.documentElement.scrollWidth,
        requestDisplay: getComputedStyle(document.querySelector("#request-panel")).display,
        securityDisplay: getComputedStyle(document.querySelector("#security-model")).display,
        resultDisplay: getComputedStyle(document.querySelector("#result")).display,
      }));
      assert(howState.bodyWidth <= width, `${engineName}/${viewport.name}: horizontal overflow in How it works view`);
      if (width <= 960) {
        assert(howState.requestDisplay === "none" && howState.securityDisplay !== "none",
          `${engineName}/${viewport.name}: compact How it works view should stand alone`);
      }

      await page.evaluate(() => {
        document.querySelector("#check-view").hidden = true;
        document.querySelector("#history-view").hidden = false;
      });
      const historyState = await page.evaluate(() => ({
        bodyWidth: document.documentElement.scrollWidth,
        historyDisplay: getComputedStyle(document.querySelector("#history-view")).display,
        filterColumns: getComputedStyle(document.querySelector("#history-filters")).gridTemplateColumns,
      }));
      assert(historyState.bodyWidth <= width, `${engineName}/${viewport.name}: horizontal overflow in Payment history`);
      assert(historyState.historyDisplay !== "none", `${engineName}/${viewport.name}: Payment history view is hidden`);
      if (width <= 420) {
        assert(historyState.filterColumns.trim().split(/\s+/).length === 1,
          `${engineName}/${viewport.name}: phone filters should use one column`);
      }
      if (viewport.name === "tablet-portrait") {
        await page.screenshot({
          path: path.join(outputDir, `${engineName}-tablet-portrait-history.png`),
          fullPage: true,
        });
      }

      assert(pageErrors.length === 0, `${engineName}/${viewport.name}: page errors: ${pageErrors.join("; ")}`);
      assert(consoleErrors.length === 0, `${engineName}/${viewport.name}: console errors: ${consoleErrors.join("; ")}`);
      console.log(`PASS ${engineName}/${viewport.name} (${width}px) request/result/how/history`);
      await context.close();
    }
  } finally {
    await browser.close();
  }
}

await inspect(chromium, "chromium");
await inspect(firefox, "firefox");
await inspect(webkit, "webkit");
console.log("18 viewport/browser combinations passed; screenshots written to artifacts/anna-visual.");
