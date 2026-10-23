"use strict";
/* service/static/app.js — конструктор картин из бисера (2N).
   Шаги: загрузка → формат/цвета/кроп → правка пикселей → рендер+цена →
   заказ. Сетка приходит с сервера (/api/digitize), рендер и цена —
   только с сервера (/api/render), заказ — /api/order. */

const $ = (id) => document.getElementById(id);

let cfg = null;            // ответ /api/config (форматы, уровни)
let file = null;           // File — исходная загрузка
let img = null;            // HTMLImageElement исходника
let fmt = "A5", orient = "portrait", level = "detailed";
let crop = null;           // {x, y, w, h} в экранных px кроп-канваса
let scale = 1;             // экранные px → px оригинала: /scale
let grid = null;           // {uploadId, cols, rows, colors, cells,
                           //  initial}
let cell = 12;             // px клетки в редакторе
let tool = "paint";        // paint | revert
let selColor = 0;
let history = [], future = [];
let stroke = null;         // текущий штрих: [{i, from, to}]
let renderInfo = null;     // ответ /api/render


async function api(url, opts) {
  const r = await fetch(url, opts);
  let j = null;
  try { j = await r.json(); } catch (e) { /* ниже */ }
  if (!j) throw new Error(`Сервер ответил ${r.status} без данных.`);
  if (j.ok === false) throw new Error(j.error || `Ошибка ${r.status}.`);
  return j;
}


function showErr(msg) {
  const box = $("err");
  box.textContent = msg;
  box.classList.remove("hidden");
  box.scrollIntoView({ behavior: "smooth", block: "center" });
}


function hideErr() { $("err").classList.add("hidden"); }


function show(id) {
  $(id).classList.remove("hidden");
  $(id).scrollIntoView({ behavior: "smooth", block: "start" });
}


function clamp(v, lo, hi) { return Math.max(lo, Math.min(hi, v)); }


function gridDims() {
  const f = cfg.formats[fmt];
  return orient === "portrait" ? [f.cols, f.rows] : [f.rows, f.cols];
}


/* ---------- конфиг и радиокнопки ---------- */

async function loadConfig() {
  try {
    cfg = await api("/api/config");
  } catch (e) {
    showErr("Не удалось получить настройки: " + e.message);
    return;
  }
  const fr = $("fmt-radios");
  fr.innerHTML = "";
  for (const [key, f] of Object.entries(cfg.formats)) {
    const lb = document.createElement("label");
    lb.innerHTML = `<input type="radio" name="fmt" value="${key}">
                    <span>${key}</span>
                    <small>${f.label} · ${f.cols}×${f.rows}</small>`;
    fr.appendChild(lb);
  }
  const lr = $("lvl-radios");
  lr.innerHTML = "";
  for (const l of cfg.levels) {
    const lb = document.createElement("label");
    lb.innerHTML = `<input type="radio" name="lvl" value="${l.id}">
                    <span>${l.label}</span><small>${l.colors} цвета</small>`;
    lr.appendChild(lb);
  }
  fr.addEventListener("change", (e) => {
    fmt = e.target.value;
    selectFmt();
  });
  lr.addEventListener("change", (e) => { level = e.target.value; });
  document.querySelectorAll('input[name="orient"]').forEach((r) =>
    r.addEventListener("change", (e) => {
      orient = e.target.value;
      initCrop();                 // пропорции рамки изменились
    }));
  fmt = Object.keys(cfg.formats)[1] || fmt;      // по умолчанию средний
  level = (cfg.levels[1] || cfg.levels[0]).id;
  fr.querySelector(`input[value="${fmt}"]`).checked = true;
  lr.querySelector(`input[value="${level}"]`).checked = true;
  $("drop-meta").textContent =
    `jpg · png · webp · gif · bmp · до ${cfg.upload_max_mb} МБ`;
  selectFmt();
}


function selectFmt() {
  const [c, r] = gridDims();
  const f = cfg.formats[fmt];
  $("fmt-info").textContent =
    `${f.label} · ${c}×${r} бисерин · всего ${c * r} шт · шаг ${cfg.pitch_mm} мм`;
  if (img) initCrop();
}


/* ---------- шаг 2: кроп-рамка ---------- */

function initCrop() {
  const cv = $("crop-canvas");
  const maxW = 640, maxH = 480;
  scale = Math.min(maxW / img.width, maxH / img.height, 1);
  cv.width = Math.max(1, Math.round(img.width * scale));
  cv.height = Math.max(1, Math.round(img.height * scale));
  const [cols, rows] = gridDims();
  let w = cv.width;
  let h = w * rows / cols;
  if (h > cv.height) { h = cv.height; w = h * cols / rows; }
  crop = { x: (cv.width - w) / 2, y: (cv.height - h) / 2, w, h };
  drawCrop();
}


function drawCrop() {
  const cv = $("crop-canvas"), ctx = cv.getContext("2d");
  ctx.clearRect(0, 0, cv.width, cv.height);
  ctx.drawImage(img, 0, 0, cv.width, cv.height);
  ctx.fillStyle = "rgba(15, 18, 30, 0.55)";        // затемнение вокруг
  ctx.fillRect(0, 0, cv.width, crop.y);
  ctx.fillRect(0, crop.y + crop.h, cv.width, cv.height - crop.y - crop.h);
  ctx.fillRect(0, crop.y, crop.x, crop.h);
  ctx.fillRect(crop.x + crop.w, crop.y, cv.width - crop.x - crop.w, crop.h);
  ctx.lineWidth = 2;
  ctx.strokeStyle = "#2e4fd8";
  ctx.strokeRect(crop.x, crop.y, crop.w, crop.h);
  ctx.fillStyle = "#2e4fd8";                       // уголок для растяжки
  ctx.fillRect(crop.x + crop.w - 7, crop.y + crop.h - 7, 14, 14);
  ctx.fillStyle = "#fff";
  ctx.fillRect(crop.x + crop.w - 4, crop.y + crop.h - 4, 8, 8);
  const [cols, rows] = gridDims();
  $("tip").textContent =
    `в рамке ${Math.round(crop.w / scale)}×${Math.round(crop.h / scale)}` +
    ` px → ${cols}×${rows} бисерин — двигайте рамку, тяните за уголок`;
}


function cropToOriginal() {
  return { x: Math.round(crop.x / scale),
           y: Math.round(crop.y / scale),
           w: Math.round(crop.w / scale),
           h: Math.round(crop.h / scale) };
}


function cropPointer(e, cv) {
  const b = cv.getBoundingClientRect();
  return { x: (e.clientX - b.left) * (cv.width / b.width),
           y: (e.clientY - b.top) * (cv.height / b.height) };
}


function wireCrop() {
  const cv = $("crop-canvas");
  let mode = null, start = null, orig = null;

  cv.addEventListener("pointerdown", (e) => {
    if (!img || !crop) return;
    const p = cropPointer(e, cv);
    const nearHandle = Math.abs(p.x - (crop.x + crop.w)) < 18 &&
                       Math.abs(p.y - (crop.y + crop.h)) < 18;
    const inside = p.x >= crop.x && p.x <= crop.x + crop.w &&
                   p.y >= crop.y && p.y <= crop.y + crop.h;
    mode = nearHandle || !inside ? "resize" : "move";
    start = p;
    orig = { x: crop.x, y: crop.y, w: crop.w, h: crop.h };
    cv.setPointerCapture(e.pointerId);
    e.preventDefault();
  });

  cv.addEventListener("pointermove", (e) => {
    if (!mode) return;
    const p = cropPointer(e, cv);
    if (mode === "move") {
      crop.x = clamp(orig.x + p.x - start.x, 0, cv.width - crop.w);
      crop.y = clamp(orig.y + p.y - start.y, 0, cv.height - crop.h);
    } else {                        // размер с фиксированной пропорцией
      const [cols, rows] = gridDims();
      let w = clamp(orig.w + (p.x - start.x + p.y - start.y) / 2,
                    24, cv.width);
      let h = w * rows / cols;
      if (h > cv.height) { h = cv.height; w = h * cols / rows; }
      crop.w = w;
      crop.h = h;
      crop.x = clamp(orig.x, 0, cv.width - w);
      crop.y = clamp(orig.y, 0, cv.height - h);
    }
    drawCrop();
  });

  const end = () => { mode = null; };
  cv.addEventListener("pointerup", end);
  cv.addEventListener("pointercancel", end);
}


/* ---------- шаг «Собрать картину» ---------- */

async function doDigitize() {
  hideErr();
  const btn = $("build");
  btn.disabled = true;
  btn.textContent = "Собираем…";
  try {
    const fd = new FormData();
    fd.append("image", file);
    fd.append("format", fmt);
    fd.append("orient", orient);
    fd.append("level", level);
    fd.append("crop", JSON.stringify(cropToOriginal()));
    const res = await api("/api/digitize", { method: "POST", body: fd });
    grid = { uploadId: res.upload_id, cols: res.cols, rows: res.rows,
             colors: res.colors, cells: res.cells.slice(),
             initial: res.cells.slice() };
    history = [];
    future = [];
    selColor = 0;
    show("step-edit");
    buildPalette();
    setTool("paint");
    fitZoom();
  } catch (e) {
    showErr(e.message);
  } finally {
    btn.disabled = false;
    btn.textContent = "Собрать картину";
  }
}


/* ---------- шаг 3: мини-редактор пикселей ---------- */

function buildPalette() {
  const pal = $("palette");
  pal.innerHTML = "";
  grid.colors.forEach((hex, i) => {
    const b = document.createElement("button");
    b.type = "button";
    b.className = "sw" + (i === selColor ? " active" : "");
    b.style.background = hex;
    b.title = hex;
    b.addEventListener("click", () => {
      selColor = i;
      pal.querySelectorAll(".sw").forEach((el, j) =>
        el.classList.toggle("active", j === i));
      setTool("paint");
    });
    pal.appendChild(b);
  });
}


function setTool(t) {
  tool = t;
  $("tool-paint").classList.toggle("active", t === "paint");
  $("tool-revert").classList.toggle("active", t === "revert");
}


function fitZoom() {
  cell = clamp(Math.floor(($("edit-scroll").clientWidth - 6) / grid.cols),
               3, 28);
  renderGrid();
}


function renderGrid() {
  const cv = $("edit-canvas"), ctx = cv.getContext("2d");
  cv.width = grid.cols * cell;
  cv.height = grid.rows * cell;
  for (let r = 0; r < grid.rows; r++)
    for (let c = 0; c < grid.cols; c++) {
      ctx.fillStyle = grid.colors[grid.cells[r * grid.cols + c]];
      ctx.fillRect(c * cell, r * cell, cell, cell);
    }
  if (cell >= 6) {
    ctx.strokeStyle = "rgba(0, 0, 0, 0.10)";
    ctx.lineWidth = 1;
    ctx.beginPath();
    for (let c = 0; c <= grid.cols; c++) {
      ctx.moveTo(c * cell + 0.5, 0);
      ctx.lineTo(c * cell + 0.5, cv.height);
    }
    for (let r = 0; r <= grid.rows; r++) {
      ctx.moveTo(0, r * cell + 0.5);
      ctx.lineTo(cv.width, r * cell + 0.5);
    }
    ctx.stroke();
  }
  $("zoom-val").textContent = cell + " px";
  updateEditedInfo();
}


function drawCell(i) {                 // перерисовать одну клетку
  const cv = $("edit-canvas"), ctx = cv.getContext("2d");
  const c = i % grid.cols, r = (i - c) / grid.cols;
  ctx.fillStyle = grid.colors[grid.cells[i]];
  ctx.fillRect(c * cell, r * cell, cell, cell);
  if (cell >= 6) {
    ctx.strokeStyle = "rgba(0, 0, 0, 0.10)";
    ctx.lineWidth = 1;
    ctx.strokeRect(c * cell + 0.5, r * cell + 0.5, cell - 1, cell - 1);
  }
}


function updateEditedInfo() {
  let n = 0;
  for (let i = 0; i < grid.cells.length; i++)
    if (grid.cells[i] !== grid.initial[i]) n++;
  $("edited-info").textContent =
    n ? `правок: ${n}` : "без правок — как собралось";
}


function cellAt(e) {
  const cv = $("edit-canvas");
  const b = cv.getBoundingClientRect();
  const x = (e.clientX - b.left) * (cv.width / b.width);
  const y = (e.clientY - b.top) * (cv.height / b.height);
  const c = Math.floor(x / cell), r = Math.floor(y / cell);
  if (c < 0 || r < 0 || c >= grid.cols || r >= grid.rows) return -1;
  return r * grid.cols + c;
}


function applyCell(i) {
  const v = tool === "paint" ? selColor : grid.initial[i];
  if (grid.cells[i] === v) return;
  stroke.push({ i, from: grid.cells[i], to: v });
  grid.cells[i] = v;
  drawCell(i);
}


function wireEditor() {
  const cv = $("edit-canvas");
  let down = false;
  cv.addEventListener("pointerdown", (e) => {
    if (!grid) return;
    const i = cellAt(e);
    if (i < 0) return;
    down = true;
    stroke = [];
    cv.setPointerCapture(e.pointerId);
    applyCell(i);
    updateEditedInfo();
    e.preventDefault();
  });
  cv.addEventListener("pointermove", (e) => {
    if (!down || !stroke) return;
    const i = cellAt(e);
    if (i >= 0) {
      applyCell(i);
      updateEditedInfo();
    }
  });
  const up = () => {
    if (down && stroke && stroke.length) {
      history.push(stroke);
      if (history.length > 100) history.shift();
      future = [];
    }
    down = false;
    stroke = null;
  };
  cv.addEventListener("pointerup", up);
  cv.addEventListener("pointercancel", up);

  $("tool-paint").addEventListener("click", () => setTool("paint"));
  $("tool-revert").addEventListener("click", () => setTool("revert"));
  $("undo").addEventListener("click", undo);
  $("redo").addEventListener("click", redo);
  $("reset-edits").addEventListener("click", resetEdits);
  $("zoom-in").addEventListener("click", () => {
    cell = clamp(cell + 2, 3, 28);
    renderGrid();
  });
  $("zoom-out").addEventListener("click", () => {
    cell = clamp(cell - 2, 3, 28);
    renderGrid();
  });
  $("zoom-fit").addEventListener("click", fitZoom);
}


function undo() {
  const s = history.pop();
  if (!s) return;
  for (let k = s.length - 1; k >= 0; k--) grid.cells[s[k].i] = s[k].from;
  future.push(s);
  renderGrid();
}


function redo() {
  const s = future.pop();
  if (!s) return;
  for (const ch of s) grid.cells[ch.i] = ch.to;
  history.push(s);
  renderGrid();
}


function resetEdits() {
  if (!grid) return;
  if (!grid.cells.some((v, i) => v !== grid.initial[i])) return;
  if (!confirm("Вернуть картинку к исходной сборке?")) return;
  grid.cells = grid.initial.slice();
  history = [];
  future = [];
  renderGrid();
}


/* ---------- шаг 4: рендер, цена, заказ ---------- */

async function doRender() {
  hideErr();
  const btn = $("to-render");
  btn.disabled = true;
  btn.textContent = "Рисуем…";
  try {
    renderInfo = await api("/api/render", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({
        format: fmt, orient: orient, level: level,
        colors: grid.colors, cells: grid.cells,
        cols: grid.cols, rows: grid.rows }),
    });
    $("render-img").src = renderInfo.url;
    $("price").textContent = renderInfo.price.toLocaleString("ru-RU") + " ₽";
    $("price-meta").textContent =
      `${renderInfo.format} · ${renderInfo.level_label} · ` +
      `${renderInfo.beads} бисерин`;
    $("order-form").classList.remove("hidden");
    $("order-ok").classList.add("hidden");
    show("step-final");
  } catch (e) {
    showErr(e.message);
  } finally {
    btn.disabled = false;
    btn.textContent = "Готово — показать рендер и цену";
  }
}


async function doOrder(e) {
  e.preventDefault();
  hideErr();
  const form = $("order-form");
  const btn = form.querySelector('button[type="submit"]');
  btn.disabled = true;
  try {
    const fd = new FormData(form);
    const res = await api("/api/order", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({
        format: fmt, orient: orient, level: level,
        colors: grid.colors, cells: grid.cells,
        cols: grid.cols, rows: grid.rows,
        upload_id: grid.uploadId, render_id: renderInfo.render_id,
        name: fd.get("name"), contact: fd.get("contact"),
        comment: fd.get("comment") || "" }),
    });
    form.classList.add("hidden");
    const ok = $("order-ok");
    ok.textContent =
      `Заказ № ${res.order} принят! Цена ` +
      `${res.price.toLocaleString("ru-RU")} ₽. Мы свяжемся с вами ` +
      `по указанному контакту.`;
    ok.classList.remove("hidden");
    ok.scrollIntoView({ behavior: "smooth", block: "center" });
  } catch (e2) {
    showErr(e2.message);
    btn.disabled = false;
  }
}


/* ---------- шаг 1: файл ---------- */

function acceptFile(f) {
  hideErr();
  if (!f) return;
  if (!cfg) {
    showErr("Настройки не загрузились — обновите страницу.");
    return;
  }
  if (!/\.(png|jpe?g|gif|bmp|webp)$/i.test(f.name)) {
    showErr("Нужен файл картинки: png, jpg, jpeg, gif, bmp или webp.");
    return;
  }
  if (f.size > cfg.upload_max_mb * 1024 * 1024) {
    showErr(`Файл больше ${cfg.upload_max_mb} МБ — уменьшите картинку.`);
    return;
  }
  file = f;
  const rd = new FileReader();
  rd.onload = () => {
    img = new Image();
    img.onload = () => {
      show("step-setup");
      initCrop();
    };
    img.onerror = () => showErr("Картинка не читается браузером.");
    img.src = rd.result;
  };
  rd.onerror = () => showErr("Не удалось прочитать файл.");
  rd.readAsDataURL(f);
}


/* ---------- запуск ---------- */

document.addEventListener("DOMContentLoaded", () => {
  loadConfig();
  wireCrop();
  wireEditor();

  $("file").addEventListener("change", (e) => acceptFile(e.target.files[0]));
  const drop = $("drop");
  for (const n of ["dragenter", "dragover"])
    drop.addEventListener(n, (e) => {
      e.preventDefault();
      drop.classList.add("over");
    });
  for (const n of ["dragleave", "drop"])
    drop.addEventListener(n, (e) => {
      e.preventDefault();
      drop.classList.remove("over");
    });
  drop.addEventListener("drop", (e) => acceptFile(e.dataTransfer.files[0]));

  $("build").addEventListener("click", doDigitize);
  $("to-render").addEventListener("click", doRender);
  $("order-form").addEventListener("submit", doOrder);
  $("restart").addEventListener("click", () => location.reload());

  document.addEventListener("keydown", (e) => {
    const t = e.target;
    if (t && /^(input|textarea|select)$/i.test(t.tagName)) return;
    if ((e.ctrlKey || e.metaKey) && e.key.toLowerCase() === "z") {
      e.preventDefault();
      if (e.shiftKey) { redo(); } else { undo(); }
    }
    if ((e.ctrlKey || e.metaKey) && e.key.toLowerCase() === "y") {
      e.preventDefault();
      redo();
    }
  });
});
