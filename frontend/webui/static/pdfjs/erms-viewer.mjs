import * as pdfjsLib from './pdf.min.mjs';

pdfjsLib.GlobalWorkerOptions.workerSrc = '/static/pdfjs/pdf.worker.min.mjs';

const viewers = new Map();
let pendingPrintWindow = null;

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

async function printDocument(encoded, mimeType = 'application/pdf') {
  const printWindow = pendingPrintWindow || window.__ermsPrintWindow;
  pendingPrintWindow = null;
  window.__ermsPrintWindow = null;
  if (!printWindow || printWindow.closed) {
    window.alert('The print window was blocked. Allow pop-ups for Wathiq and try again.');
    return;
  }
  const printDocument = printWindow.document;
  printDocument.open();
  printDocument.write(`<!doctype html><html><head><title>Print document</title><style>
    * { box-sizing: border-box; }
    body { margin: 0; padding: 76px 20px 24px; background: #e8eef5; font-family: Arial, sans-serif; }
    #toolbar { position: fixed; inset: 0 0 auto; z-index: 2; height: 60px; padding: 10px 20px;
      display: flex; align-items: center; justify-content: space-between; background: white;
      border-bottom: 1px solid #d9e2ec; color: #334155; }
    #print { border: 0; border-radius: 7px; padding: 10px 18px; background: #1976d2;
      color: white; font-weight: 700; cursor: pointer; }
    #pages canvas, #pages img { display: block; max-width: 100%; height: auto; margin: 0 auto 18px;
      background: white; box-shadow: 0 4px 14px rgba(15, 23, 42, .16); }
    @media print { @page { margin: 0; } body { padding: 0; background: white; }
      #toolbar { display: none; } #pages canvas, #pages img { width: 100% !important; max-width: none;
      margin: 0; box-shadow: none; break-after: page; page-break-after: always; }
      #pages canvas:last-child, #pages img:last-child { break-after: auto; page-break-after: auto; } }
  </style></head><body><div id="toolbar"><strong id="status">Preparing pages…</strong>
  <button id="print" type="button" disabled>Print</button></div><main id="pages"></main></body></html>`);
  printDocument.close();
  const root = printDocument.getElementById('pages');
  const status = printDocument.getElementById('status');
  const printButton = printDocument.getElementById('print');
  let pdfDocument;
  try {
    if (mimeType.startsWith('image/')) {
      const image = printDocument.createElement('img');
      image.alt = 'Printable document image';
      image.src = `data:${mimeType};base64,${encoded}`;
      await image.decode();
      root.appendChild(image);
      status.textContent = '1 page ready';
      printButton.disabled = false;
      printButton.addEventListener('click', () => printWindow.print());
      printWindow.focus();
      window.setTimeout(() => printWindow.print(), 100);
      return;
    }
    pdfDocument = await pdfjsLib.getDocument({data: decodeBase64(encoded)}).promise;
    for (let pageNumber = 1; pageNumber <= pdfDocument.numPages; pageNumber += 1) {
      const page = await pdfDocument.getPage(pageNumber);
      const viewport = page.getViewport({scale: 2});
      const canvas = printDocument.createElement('canvas');
      canvas.width = Math.floor(viewport.width);
      canvas.height = Math.floor(viewport.height);
      root.appendChild(canvas);
      await page.render({canvasContext: canvas.getContext('2d'), viewport}).promise;
      status.textContent = `Preparing page ${pageNumber} of ${pdfDocument.numPages}…`;
    }
    status.textContent = `${pdfDocument.numPages} page${pdfDocument.numPages === 1 ? '' : 's'} ready`;
    printButton.disabled = false;
    printButton.addEventListener('click', () => printWindow.print());
    printWindow.focus();
    window.setTimeout(() => printWindow.print(), 100);
  } catch (error) {
    console.error('Could not prepare PDF for printing', error);
    status.textContent = 'The document could not be prepared for printing.';
  }
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
  beginPrint() {
    pendingPrintWindow = window.open('', '_blank');
    if (pendingPrintWindow) {
      pendingPrintWindow.document.write('<title>Preparing print view…</title><p style="font:16px Arial;padding:24px">Preparing print view…</p>');
      pendingPrintWindow.document.close();
    }
    return Boolean(pendingPrintWindow);
  },
  print(encoded, mimeType = 'application/pdf') {
    void printDocument(encoded, mimeType);
    return true;
  },
  close(id) { const state = viewers.get(id); if (state) state.document.destroy(); viewers.delete(id); },
};
