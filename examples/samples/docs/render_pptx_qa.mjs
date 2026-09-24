import fs from "node:fs/promises";
import path from "node:path";
import { FileBlob, PresentationFile } from "@oai/artifact-tool";

const root = path.resolve(process.argv[2] ?? ".");
const qaDir = path.join(root, ".qa-pptx");
await fs.mkdir(qaDir, { recursive: true });
const files = (await fs.readdir(path.join(root, "pptx"))).filter((name) => name.endsWith(".pptx")).sort();
for (const name of files) {
  const presentation = await PresentationFile.importPptx(await FileBlob.load(path.join(root, "pptx", name)));
  let slideNo = 0;
  for (const slide of presentation.slides.items) {
    slideNo += 1;
    const preview = await presentation.export({ slide, format: "png", scale: 1 });
    await fs.writeFile(path.join(qaDir, `${name.replace(/\.pptx$/u, "")}-${slideNo}.png`), new Uint8Array(await preview.arrayBuffer()));
  }
}
console.log(JSON.stringify({ pptx_rendered: files.length, slides_rendered: files.length * 4 }));
