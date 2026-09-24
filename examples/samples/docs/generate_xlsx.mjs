import fs from "node:fs/promises";
import path from "node:path";
import { SpreadsheetFile, Workbook } from "@oai/artifact-tool";

const root = path.resolve(process.argv[2] ?? ".");
const payload = JSON.parse(await fs.readFile(path.join(root, ".xlsx-payload.json"), "utf8"));

for (const spec of payload) {
  const workbook = Workbook.create();
  const sheet = workbook.worksheets.add("Document");
  sheet.showGridLines = false;
  const tokens = spec.body.split(/\s+/u);
  const rows = [];
  for (let start = 0; start < 200; start += 20) rows.push([tokens.slice(start, start + 20).join(" ")]);

  sheet.getRange("A1").values = [[spec.title]];
  // Explicit bidi embedding keeps the Arabic title in natural reading order
  // in renderers that do not infer cell direction from the script.
  sheet.getRange("A2").values = [[`\u202B${spec.arabic_title}\u202C`]];
  sheet.getRange("A3").values = [[`Synthetic reference ${spec.reference}`]];
  sheet.getRange("A5:A14").values = rows;
  sheet.getRange("A1:A14").format.font = { name: "Arial", size: 11, color: "#172033" };
  sheet.getRange("A1").format.font = { name: "Arial", size: 16, bold: true, color: "#000000" };
  sheet.getRange("A2").format = { font: { name: "Arial", size: 14, bold: true, color: "#000000" }, horizontalAlignment: "right" };
  sheet.getRange("A3").format.font = { name: "Arial", size: 9, italic: true, color: "#526174" };
  sheet.getRange("A5:A14").format.wrapText = true;
  sheet.getRange("A5:A14").format.verticalAlignment = "top";
  sheet.getRange("A1:A14").format.columnWidth = 105;
  sheet.getRange("A1").format.rowHeight = 24;
  sheet.getRange("A2").format.rowHeight = 22;
  sheet.getRange("A3").format.rowHeight = 18;
  sheet.getRange("A5:A14").format.rowHeight = 34;
  workbook.recalculate();
  const output = await SpreadsheetFile.exportXlsx(workbook);
  await output.save(path.join(root, spec.path));
}

console.log(JSON.stringify({ xlsx_created: payload.length }));
