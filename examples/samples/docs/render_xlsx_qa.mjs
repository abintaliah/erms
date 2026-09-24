import fs from "node:fs/promises";
import path from "node:path";
import { FileBlob, SpreadsheetFile } from "@oai/artifact-tool";

const root = path.resolve(process.argv[2] ?? ".");
const qaDir = path.join(root, ".qa-xlsx-png");
await fs.mkdir(qaDir, { recursive: true });
const files = (await fs.readdir(path.join(root, "xlsx"))).filter((name) => name.endsWith(".xlsx")).sort();

for (const name of files) {
  const input = await FileBlob.load(path.join(root, "xlsx", name));
  const workbook = await SpreadsheetFile.importXlsx(input);
  const preview = await workbook.render({ sheetName: "Document", range: "A1:A14", scale: 1, format: "png" });
  await fs.writeFile(path.join(qaDir, name.replace(/\.xlsx$/u, ".png")), new Uint8Array(await preview.arrayBuffer()));
}

console.log(JSON.stringify({ xlsx_rendered: files.length }));
