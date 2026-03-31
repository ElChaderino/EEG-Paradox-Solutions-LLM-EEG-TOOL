import puppeteer from "puppeteer";
import { fileURLToPath } from "url";
import path from "path";

const __dirname = path.dirname(fileURLToPath(import.meta.url));
const htmlPath = path.resolve(__dirname, "..", "doc", "technical-reference.html");
const pdfPath = path.resolve(__dirname, "..", "doc", "technical-reference.pdf");

(async () => {
  const browser = await puppeteer.launch({ headless: true });
  const page = await browser.newPage();

  await page.goto(`file:///${htmlPath.replace(/\\/g, "/")}`, {
    waitUntil: "networkidle0",
  });

  // Expand all <details> so the PDF captures everything
  await page.evaluate(() => {
    document.querySelectorAll("details").forEach((d) => d.setAttribute("open", ""));
  });

  // Collapse the fixed nav into a static block for print,
  // and remove the main left-margin so content fills the page.
  await page.addStyleTag({
    content: `
      nav {
        position: static !important;
        width: 100% !important;
        height: auto !important;
        max-height: none !important;
        border-right: none !important;
        border-bottom: 1px solid var(--border) !important;
        page-break-after: always;
      }
      main {
        margin-left: 0 !important;
        max-width: 100% !important;
        padding: 1rem 1.5rem 2rem 1.5rem !important;
      }
    `,
  });

  await page.pdf({
    path: pdfPath,
    format: "A4",
    printBackground: true,          // keeps all dark backgrounds + colours
    preferCSSPageSize: false,
    margin: { top: "12mm", bottom: "12mm", left: "10mm", right: "10mm" },
    displayHeaderFooter: false,
  });

  await browser.close();
  console.log(`PDF written to ${pdfPath}`);
})();
