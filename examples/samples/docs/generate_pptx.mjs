import fs from "node:fs/promises";
import path from "node:path";
import { pathToFileURL } from "node:url";
import { Presentation, PresentationFile } from "@oai/artifact-tool";

const root = path.resolve(process.argv[2] ?? ".");
const skillDir = "/Users/yahyayai/.codex/plugins/cache/openai-primary-runtime/presentations/26.909.12148/skills/presentations";
const runtimePython = "/Users/yahyayai/.cache/codex-runtimes/codex-primary-runtime/dependencies/python/bin/python3";
const { finalizePresentation } = await import(pathToFileURL(path.join(skillDir, "container_tools/artifact_tool_utils.mjs")).href);
const payload = JSON.parse(await fs.readFile(path.join(root, ".pptx-payload.json"), "utf8"));
const stagingRoot = path.join(root, ".pptx-build");
await fs.mkdir(stagingRoot, { recursive: true });

for (const spec of payload) {
  const presentation = Presentation.create({ slideSize: { width: 1280, height: 720 } });
  const tokens = spec.body.split(/\s+/u);
  for (let part = 0; part < 4; part++) {
    const slide = presentation.slides.add();
    slide.background.fill = "#FFFFFF";
    const title = slide.shapes.add({
      geometry: "textbox", position: { left: 70, top: 45, width: 1140, height: 55 },
      fill: "none", line: { fill: "none", width: 0 },
    });
    title.text = `${spec.title} ${part + 1}`;
    title.text.style = { typeface: "Arial", fontSize: 34, bold: true, color: "#17365D", autoFit: "none" };

    const arTitle = slide.shapes.add({
      geometry: "textbox", position: { left: 70, top: 110, width: 1140, height: 45 },
      fill: "none", line: { fill: "none", width: 0 },
    });
    arTitle.text = `\u202B${spec.arabic_title}\u202C`;
    arTitle.text.style = { typeface: "Arial", fontSize: 25, bold: true, color: "#243B53", autoFit: "none", alignment: "right" };

    const body = slide.shapes.add({
      geometry: "textbox", position: { left: 90, top: 185, width: 1100, height: 400 },
      fill: "none", line: { fill: "none", width: 0 },
    });
    body.text = tokens.slice(part * 50, (part + 1) * 50).join(" ");
    body.text.style = { typeface: "Arial", fontSize: 21, color: "#172033", autoFit: "shrinkText", verticalAlignment: "top" };

    const footer = slide.shapes.add({
      geometry: "textbox", position: { left: 90, top: 640, width: 1100, height: 28 },
      fill: "none", line: { fill: "none", width: 0 },
    });
    footer.text = `Synthetic reference ${spec.reference}  Part ${part + 1} of 4`;
    footer.text.style = { typeface: "Arial", fontSize: 13, color: "#526174", autoFit: "none" };
  }

  const stage = path.join(stagingRoot, spec.stem);
  await fs.mkdir(stage, { recursive: true });
  const candidatePath = path.join(stage, "candidate.pptx");
  const finalPath = path.join(root, spec.path);
  await (await PresentationFile.exportPptx(presentation)).save(candidatePath);
  await finalizePresentation({
    explicitTotalSlideCount: 4,
    requiredNativeTableOwnerSlides: [], requiredNativeChartOwnerSlides: [],
    workspaceDir: root, candidatePath, finalPath,
    pythonExecutable: runtimePython,
    integrityValidatorPath: path.join(skillDir, "container_tools/inspect_presentation_package_integrity.py"),
    layoutValidatorPath: path.join(skillDir, "container_tools/inspect_presentation_layout_geometry.py"),
    layoutArgs: ["--expected-slide-size-emu", "12192000,6858000", "--validate-heading-fit"],
    fontPolicy: { basis: "design", families: ["Arial"], scriptFonts: { cs: "Arial" } },
    verifyArtifactToolImport: true,
    receiptPath: path.join(stage, "validation.json"),
  });
}

console.log(JSON.stringify({ pptx_created: payload.length }));
