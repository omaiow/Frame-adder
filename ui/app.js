const { invoke } = window.__TAURI__.core;

const $ = (id) => document.getElementById(id);
const ZOOM_STEPS = [0.1, 0.25, 0.33, 0.5, 0.67, 0.75, 1, 1.5, 2, 3, 4];
const state = {
  frame: null,
  photos: [],
  selected: 0,
  outputDir: "output",
  previewTimer: null,
  busy: false,
  zoom: null, // null = fit to canvas, otherwise a scale relative to the frame's pixel size
  fitScale: 1,
  previewResizeObserver: null,
};

function setStatus(message, tone = "") {
  const el = $("status-message");
  el.textContent = message;
  el.title = message;
  el.className = `status-text truncate${tone ? ` ${tone}` : ""}`;
}

function plural(count, word) {
  return `${count} ${word}${count === 1 ? "" : "s"}`;
}

function currentAperture() {
  return {
    x: Math.max(0, Number.parseInt($("aperture-x").value, 10) || 0),
    y: Math.max(0, Number.parseInt($("aperture-y").value, 10) || 0),
    width: Math.max(1, Number.parseInt($("aperture-width").value, 10) || 1),
    height: Math.max(1, Number.parseInt($("aperture-height").value, 10) || 1),
  };
}

function basename(path) {
  return path.split(/[\\/]/).pop() || path;
}

function setAperture(aperture) {
  $("aperture-x").value = aperture.x;
  $("aperture-y").value = aperture.y;
  $("aperture-width").value = aperture.width;
  $("aperture-height").value = aperture.height;
  $("opening-summary").textContent = `Auto-detected at ${aperture.x}, ${aperture.y} · ${aperture.width} × ${aperture.height} px`;
}

function setManualAperture(enabled) {
  $("manual-opening").checked = enabled;
  for (const id of ["aperture-x", "aperture-y", "aperture-width", "aperture-height"]) $(id).disabled = !enabled;
  $("tool-aperture").classList.toggle("active", enabled);
  if (!enabled && state.frame) setAperture(state.frame.aperture);
}

function updateCanvasInfo() {
  if (!state.frame) {
    $("canvas-info").textContent = "—";
    return;
  }
  const a = currentAperture();
  $("canvas-info").textContent = `${state.frame.width} × ${state.frame.height} px  ·  Aperture ${a.width} × ${a.height} at ${a.x}, ${a.y}`;
}

function updateZoomReadout() {
  const label = state.zoom === null ? `${Math.round(state.fitScale * 100)}%` : `${Math.round(state.zoom * 100)}%`;
  $("zoom-readout").textContent = state.frame ? label : "Fit";
  $("tab-zoom").textContent = state.frame ? `@ ${label}` : "";
}

function sizePreviewMat() {
  const stage = $("drop-zone");
  const mat = $("preview-mat");
  if (!state.frame || !stage || !mat) return;
  const { width, height } = state.frame;
  if (!width || !height) return;
  const maxWidth = Math.max(0, stage.clientWidth - 64);
  const maxHeight = Math.max(0, stage.clientHeight - 64);
  const fit = Math.min(maxWidth / width, maxHeight / height);
  if (!Number.isFinite(fit) || fit <= 0) return;
  state.fitScale = fit;
  const scale = state.zoom ?? fit;
  mat.style.width = `${Math.max(1, Math.floor(width * scale))}px`;
  mat.style.height = `${Math.max(1, Math.floor(height * scale))}px`;
  stage.classList.toggle("zoomed", state.zoom !== null && scale > fit);
  updateZoomReadout();
}

function setZoom(zoom) {
  if (!state.frame) return;
  state.zoom = zoom;
  sizePreviewMat();
}

function stepZoom(direction) {
  if (!state.frame) return;
  const current = state.zoom ?? state.fitScale;
  const next = direction > 0
    ? ZOOM_STEPS.find((step) => step > current + 0.001)
    : [...ZOOM_STEPS].reverse().find((step) => step < current - 0.001);
  if (next) setZoom(next);
}

function schedulePreview() {
  clearTimeout(state.previewTimer);
  state.previewTimer = setTimeout(renderPreview, 140);
  updateCanvasInfo();
}

function showEmptyState(show) {
  $("empty-state").classList.toggle("hidden", !show);
  $("preview-mat").classList.toggle("ready", !show);
}

async function renderPreview() {
  if (!state.frame) {
    $("preview-image").classList.remove("visible");
    showEmptyState(true);
    return;
  }
  showEmptyState(false);
  sizePreviewMat();
  const image = $("preview-image");
  const mat = $("preview-mat");
  const oldSource = image.src;
  mat.classList.add("loading");
  try {
    const source = await invoke("preview", {
      request: {
        framePath: state.frame.path,
        photoPath: state.photos[state.selected] || null,
        aperture: currentAperture(),
        fit: $("fit-mode").value,
        layer: $("layer-order").value,
      },
    });
    image.onload = () => {
      image.classList.add("visible");
      mat.classList.remove("loading");
    };
    image.onerror = () => {
      image.classList.remove("visible");
      mat.classList.remove("loading");
      setStatus("Preview could not be displayed.", "error");
    };
    image.src = source;
    if (source === oldSource && image.complete) {
      image.classList.add("visible");
      mat.classList.remove("loading");
    }
  } catch (error) {
    mat.classList.remove("loading");
    image.classList.remove("visible");
    setStatus(`Preview error: ${error}`, "error");
  }
}

function svgIcon(name) {
  const svg = document.createElementNS("http://www.w3.org/2000/svg", "svg");
  const use = document.createElementNS("http://www.w3.org/2000/svg", "use");
  use.setAttribute("href", `#i-${name}`);
  svg.append(use);
  return svg;
}

function refreshQueue() {
  const list = $("photo-list");
  const count = state.photos.length;
  list.replaceChildren();
  $("queue-count").textContent = count ? `${plural(count, "image")} · will export to ${basename(state.outputDir)}` : "No images";
  $("dock-image-count").textContent = plural(count, "photo");
  $("queue-badge").textContent = count;
  $("preview-counter").textContent = count ? `${state.selected + 1} / ${count}` : "0 / 0";
  $("preview-name").textContent = count ? basename(state.photos[state.selected]) : state.frame ? "Frame only" : "No photo selected";
  $("document-title").textContent = state.frame
    ? `${basename(state.frame.path)}${count ? ` — ${basename(state.photos[state.selected])}` : ""}`
    : "Untitled";
  $("clear-queue").disabled = count === 0;
  $("previous-photo").disabled = count < 2;
  $("next-photo").disabled = count < 2;

  if (!count) {
    const empty = document.createElement("div");
    empty.className = "queue-empty";
    const text = document.createElement("span");
    text.textContent = "No photos yet. Add files or drop a folder onto the canvas.";
    const button = document.createElement("button");
    button.className = "secondary-button small";
    button.textContent = "Add photos…";
    button.addEventListener("click", choosePhotos);
    empty.append(text, button);
    list.append(empty);
    schedulePreview();
    return;
  }

  state.photos.forEach((path, index) => {
    const row = document.createElement("div");
    row.className = `queue-item${index === state.selected ? " selected" : ""}`;
    row.title = path;
    const number = document.createElement("span");
    number.className = "queue-index";
    number.textContent = index + 1;
    const icon = document.createElement("span");
    icon.className = "queue-icon";
    icon.append(svgIcon("image"));
    const name = document.createElement("span");
    name.className = "queue-item-name";
    name.textContent = basename(path);
    const remove = document.createElement("button");
    remove.className = "remove-photo";
    remove.type = "button";
    remove.title = "Remove from queue";
    remove.append(svgIcon("close"));
    row.addEventListener("click", () => {
      state.selected = index;
      refreshQueue();
    });
    remove.addEventListener("click", (event) => {
      event.stopPropagation();
      state.photos.splice(index, 1);
      state.selected = Math.min(state.selected, Math.max(0, state.photos.length - 1));
      refreshQueue();
    });
    row.append(number, icon, name, remove);
    list.append(row);
  });
  list.querySelector(".selected")?.scrollIntoView({ block: "nearest" });
  schedulePreview();
}

async function addPhotos(paths) {
  const additions = await invoke("add_paths", { paths });
  const known = new Set(state.photos);
  let added = 0;
  for (const path of additions) {
    if (!known.has(path)) {
      known.add(path);
      state.photos.push(path);
      added += 1;
    }
  }
  state.photos.sort((a, b) => a.localeCompare(b));
  state.selected = Math.min(state.selected, Math.max(0, state.photos.length - 1));
  refreshQueue();
  if (additions.length) setStatus(`Added ${plural(added, "image")} to the queue.`);
}

async function chooseFrame() {
  const path = await invoke("pick_frame");
  if (!path) return;
  try {
    state.frame = await invoke("load_frame", { path });
    state.zoom = null;
    $("frame-name").textContent = basename(path);
    $("frame-name").title = path;
    $("frame-details").textContent = `${state.frame.width} × ${state.frame.height} px`;
    document.querySelector(".status-dot").classList.add("ready");
    setManualAperture(false);
    setAperture(state.frame.aperture);
    setStatus(state.photos.length ? "Frame loaded." : "Frame loaded. Add photos to preview.");
    refreshQueue();
  } catch (error) {
    setStatus(`Frame error: ${error}`, "error");
  }
}

async function choosePhotos() {
  const paths = await invoke("pick_photos");
  if (paths.length) await addPhotos(paths);
}

async function chooseFolder() {
  const path = await invoke("pick_folder");
  if (!path) return;
  const photos = await invoke("scan_folder", { path });
  await addPhotos(photos);
}

function setOutputDir(path) {
  state.outputDir = path;
  $("output-path").textContent = path;
  $("output-path").title = path;
}

async function chooseOutput() {
  const path = await invoke("pick_output_folder", { current: state.outputDir });
  if (!path) return;
  setOutputDir(path);
  refreshQueue();
  setStatus(`Export location set to ${path}`);
}

async function exportPhotos() {
  if (state.busy) return;
  if (!state.frame) {
    setStatus("Open a frame before exporting.", "error");
    return;
  }
  if (!state.photos.length) {
    setStatus("Add at least one photo to export.", "error");
    return;
  }
  state.busy = true;
  const button = $("export-photos");
  button.disabled = true;
  button.classList.add("busy");
  $("export-label").textContent = "Exporting…";
  $("progress-bar").style.width = "0%";
  $("progress-bar").parentElement.classList.add("active");
  $("open-output").classList.add("hidden");
  try {
    const summary = await invoke("export_batch", {
      request: {
        photos: [...state.photos],
        framePath: state.frame.path,
        aperture: currentAperture(),
        fit: $("fit-mode").value,
        layer: $("layer-order").value,
        outputDir: state.outputDir,
        format: $("output-format").value,
        quality: Number($("quality").value),
        naming: $("naming-pattern").value.trim() || "framed_{filename}",
      },
    });
    const failed = summary.total - summary.succeeded;
    setStatus(
      `Export complete — ${summary.succeeded} of ${summary.total} saved${failed ? `, ${failed} failed` : ""}.`,
      failed ? "error" : "success",
    );
    $("open-output").classList.remove("hidden");
  } catch (error) {
    setStatus(`Export failed: ${error}`, "error");
  } finally {
    state.busy = false;
    button.disabled = false;
    button.classList.remove("busy");
    $("export-label").textContent = "Export";
    setTimeout(() => $("progress-bar").parentElement.classList.remove("active"), 1200);
  }
}

function navigate(direction) {
  if (!state.photos.length) return;
  state.selected = (state.selected + direction + state.photos.length) % state.photos.length;
  refreshQueue();
}

function updateQualityFill() {
  const input = $("quality");
  const fill = ((input.value - input.min) / (input.max - input.min)) * 100;
  input.style.setProperty("--fill", `${fill}%`);
  $("quality-value").textContent = `${input.value}%`;
}

function isTyping(event) {
  return ["INPUT", "SELECT", "TEXTAREA"].includes(event.target.tagName) && event.target.type !== "checkbox";
}

function bindShortcuts() {
  document.addEventListener("keydown", (event) => {
    const mod = event.ctrlKey || event.metaKey;
    if (mod && event.key.toLowerCase() === "o") { event.preventDefault(); chooseFrame(); return; }
    if (mod && event.key.toLowerCase() === "i") { event.preventDefault(); choosePhotos(); return; }
    if (mod && event.key.toLowerCase() === "e") { event.preventDefault(); exportPhotos(); return; }
    if (mod && (event.key === "=" || event.key === "+")) { event.preventDefault(); stepZoom(1); return; }
    if (mod && event.key === "-") { event.preventDefault(); stepZoom(-1); return; }
    if (mod && event.key === "0") { event.preventDefault(); setZoom(null); return; }
    if (mod && event.key === "1") { event.preventDefault(); setZoom(1); return; }
    if (isTyping(event)) return;
    if (event.key === "ArrowLeft" || event.key === "ArrowUp") { event.preventDefault(); navigate(-1); }
    if (event.key === "ArrowRight" || event.key === "ArrowDown") { event.preventDefault(); navigate(1); }
    if ((event.key === "Delete" || event.key === "Backspace") && state.photos.length) {
      state.photos.splice(state.selected, 1);
      state.selected = Math.min(state.selected, Math.max(0, state.photos.length - 1));
      refreshQueue();
    }
  });
  $("drop-zone").addEventListener("wheel", (event) => {
    if (!event.ctrlKey) return;
    event.preventDefault();
    stepZoom(event.deltaY < 0 ? 1 : -1);
  }, { passive: false });
}

function bindEvents() {
  for (const id of ["choose-frame", "choose-frame-top", "choose-frame-empty", "tool-frame"]) $(id).addEventListener("click", chooseFrame);
  for (const id of ["add-photos", "add-photos-empty", "add-photos-panel", "tool-photos"]) $(id).addEventListener("click", choosePhotos);
  for (const id of ["add-folder", "tool-folder"]) $(id).addEventListener("click", chooseFolder);
  for (const id of ["export-photos", "tool-export"]) $(id).addEventListener("click", exportPhotos);
  $("choose-output").addEventListener("click", chooseOutput);
  $("previous-photo").addEventListener("click", () => navigate(-1));
  $("next-photo").addEventListener("click", () => navigate(1));
  $("zoom-in").addEventListener("click", () => stepZoom(1));
  $("zoom-out").addEventListener("click", () => stepZoom(-1));
  $("zoom-fit").addEventListener("click", () => setZoom(null));
  $("zoom-readout").addEventListener("click", () => setZoom(state.zoom === null ? 1 : null));
  $("clear-queue").addEventListener("click", () => {
    state.photos = [];
    state.selected = 0;
    refreshQueue();
    setStatus("Queue cleared.");
  });
  $("open-output").addEventListener("click", async () => {
    try {
      await invoke("open_output_folder", { path: state.outputDir });
    } catch (error) {
      setStatus(`Could not open output folder: ${error}`, "error");
    }
  });
  $("manual-opening").addEventListener("change", (event) => {
    setManualAperture(event.target.checked);
    schedulePreview();
  });
  $("tool-aperture").addEventListener("click", () => {
    setManualAperture(!$("manual-opening").checked);
    schedulePreview();
  });
  $("tool-layers").addEventListener("click", () => {
    const select = $("layer-order");
    select.value = select.value === "frame_over" ? "photo_over" : "frame_over";
    setStatus(`Layer order: ${select.selectedOptions[0].textContent}`);
    schedulePreview();
  });
  for (const id of ["aperture-x", "aperture-y", "aperture-width", "aperture-height"]) {
    $(id).addEventListener("input", () => {
      const a = currentAperture();
      $("opening-summary").textContent = `Manual at ${a.x}, ${a.y} · ${a.width} × ${a.height} px`;
      schedulePreview();
    });
  }
  for (const id of ["fit-mode", "layer-order"]) $(id).addEventListener("change", schedulePreview);
  $("output-format").addEventListener("change", (event) => {
    $("quality-control").classList.toggle("hidden", !["jpeg", "webp"].includes(event.target.value));
  });
  $("quality").addEventListener("input", updateQualityFill);
  window.__TAURI__.event.listen("export-progress", ({ payload }) => {
    $("progress-bar").style.width = `${Math.round(payload.completed / Math.max(1, payload.total) * 100)}%`;
    setStatus(payload.success
      ? `Exporting ${payload.completed} of ${payload.total} — ${payload.name}`
      : `Exporting ${payload.completed} of ${payload.total} — failed ${payload.name}: ${payload.detail}`,
      payload.success ? "" : "error");
  });
  window.__TAURI__.webview.getCurrentWebview().onDragDropEvent(async (event) => {
    const type = event.payload.type;
    $("drop-overlay").classList.toggle("visible", type === "enter" || type === "over");
    if (type === "drop" && event.payload.paths.length) {
      try {
        await addPhotos(event.payload.paths);
      } catch (error) {
        setStatus(`Could not add dropped files: ${error}`, "error");
      }
    }
  });
  bindShortcuts();
}

bindEvents();
setManualAperture(false);
updateQualityFill();
state.previewResizeObserver = new ResizeObserver(sizePreviewMat);
state.previewResizeObserver.observe($("drop-zone"));
refreshQueue();
setStatus("Ready — open a frame to begin.");
invoke("default_output_folder").then((path) => {
  setOutputDir(path);
  refreshQueue();
}).catch((error) => setStatus(`Could not determine output folder: ${error}`, "error"));
