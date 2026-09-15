import * as pdfjsLib from './pdf.min.mjs';

pdfjsLib.GlobalWorkerOptions.workerSrc = '/static/pdfjs/pdf.worker.min.mjs';

const viewers = new Map();

function decodeBase64(value) {
  const binary = atob(value);
  const bytes = new Uint8Array(binary.length);
  for (let index = 0; index < binary.length; index += 1) bytes[index] = binary.charCodeAt(index);
  return bytes;
}

async function render(id) {
  const state = viewers.get(id);
  if (!state) return;
  const page = await state.document.getPage(state.page);
  const viewport = page.getViewport({scale: state.scale});
  const canvas = document.getElementById(id);
  if (!canvas) return;
  const ratio = window.devicePixelRatio || 1;
  canvas.width = Math.floor(viewport.width * ratio);
  canvas.height = Math.floor(viewport.height * ratio);
  canvas.style.width = `${Math.floor(viewport.width)}px`;
  canvas.style.height = `${Math.floor(viewport.height)}px`;
  await page.render({canvasContext: canvas.getContext('2d'), viewport, transform: ratio === 1 ? null : [ratio, 0, 0, ratio, 0, 0]}).promise;
  const status = document.getElementById(`${id}-status`);
  if (status) status.textContent = `Page ${state.page} of ${state.document.numPages} · ${Math.round(state.scale * 100)}%`;
}

window.ermsPdfViewer = {
  async open(id, encoded) {
    const document = await pdfjsLib.getDocument({data: decodeBase64(encoded)}).promise;
    viewers.set(id, {document, page: 1, scale: 1.2});
    await render(id);
  },
  async previous(id) { const state = viewers.get(id); if (state && state.page > 1) { state.page -= 1; await render(id); } },
  async next(id) { const state = viewers.get(id); if (state && state.page < state.document.numPages) { state.page += 1; await render(id); } },
  async zoomIn(id) { const state = viewers.get(id); if (state && state.scale < 3) { state.scale += 0.2; await render(id); } },
  async zoomOut(id) { const state = viewers.get(id); if (state && state.scale > 0.4) { state.scale -= 0.2; await render(id); } },
  close(id) { const state = viewers.get(id); if (state) state.document.destroy(); viewers.delete(id); },
};
