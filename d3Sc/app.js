/* d3Sc — редактор бисерной сферы (мозаичное/gourd плетение)
 * Данные: model = { R, rows:[{n, th, beads:[{c,s}]}] }  s: 0 крупный, 1 мелкий
 * Правки в 3D и 2D синхронны: единая модель, обе панели перерисовываются.
 */
'use strict';

// ---- Калибры бисера, мм (ширина вдоль нити × высота поперёк) ----
const BEAD = {
  0: { w: 2.2, h: 2.5 },   // крупный, цилиндр Delica 11/0
  1: { w: 1.3, h: 1.5 },   // мелкий, круглый 15/0
};

// Паттерн оплетения бусины (по site.txt): пары/одиночки Delica и 15/0,
// зеркальные убавки сверху. middle — число средних рядов Delica.
function patternRows(middle) {
  const D = 0, S = 1;
  const seq = [
    [D, 4], [S, 4], [D, 8], [S, 8], [S, 16], [D, 8], [S, 16], [S, 16],
  ];
  for (let i = 0; i < middle; i++) seq.push([D, 16]);
  seq.push([S, 16], [S, 16], [D, 8], [S, 16], [S, 8], [D, 8], [S, 4], [D, 4]);
  return seq.map(([sz, n]) => ({ sizes: Array(n).fill(sz) }));
}

// Геометрия кольца ряда: радиус центральной линии и центры бисерин по φ.
// Бисерины в кольце размещаются равномерно, шаг >= ширины бисерины
// (касание без наложений).
function ringGeom(row, R) {
  const ws = row.beads.map(b => BEAD[b.s].w);
  const hmax = Math.max(...row.beads.map(b => BEAD[b.s].h));
  const rc = R + hmax / 2;
  const C = 2 * Math.PI * rc * Math.sin(row.th);
  const n = ws.length;
  const gap = Math.max(0, (C - ws.reduce((a, x) => a + x, 0)) / n);
  let acc = 0;
  const cent = ws.map(w => { const c = acc + (w + gap) / 2; acc += w + gap; return c / rc / Math.sin(row.th); });
  return { rc, C, cent };
}

// Углы θ рядов: кольцо ряда садится на бусину так, что его окружность
// равна суммарной ширине бисерин (asin), ряды не ближе шага (h_i+h_j)/2.
// Если ряды не помещаются на бусину — fitBall увеличивает радиус.
const rowH = r => BEAD[r.beads[0].s].h;
const rowC = r => r.beads.reduce((a, b) => a + BEAD[b.s].w, 0);
// мозаичное переплетение: соседние ряды утапливаются друг в друга,
// фактический шаг меньше (h_i+h_j)/2
const NEST = 0.55;
const rowPitch = (a, b, R) => NEST * (rowH(a) + rowH(b)) / 2 / (R + (rowH(a) + rowH(b)) / 4);
const alpha_i = (r, R) => Math.asin(Math.min(1, rowC(r) / (2 * Math.PI * (R + rowH(r) / 2))));

// возвращает { th, ok } — ok=false, если ряды наезжают друг на друга
function layoutThetas(rows, R) {
  const n = rows.length;
  const up = new Array(n), down = new Array(n);
  for (let i = 0; i < n; i++) {
    const nat = alpha_i(rows[i], R);
    up[i] = i === 0 ? nat : Math.max(nat, up[i - 1] + rowPitch(rows[i - 1], rows[i], R));
  }
  for (let i = n - 1; i >= 0; i--) {
    const nat = Math.PI - alpha_i(rows[i], R);
    down[i] = i === n - 1 ? nat : Math.min(nat, down[i + 1] - rowPitch(rows[i], rows[i + 1], R));
  }
  let ok = true;
  const th = new Array(n);
  for (let i = 0; i < n; i++) {
    if (down[i] < up[i]) ok = false;
    th[i] = (up[i] + down[i]) / 2;
  }
  return { th, ok };
}

function fitBall(rows, R0) {
  let R = R0;
  rows.forEach(r => { R = Math.max(R, rowC(r) / (2 * Math.PI) - rowH(r) / 2); });
  for (let it = 0; it < 500; it++) {
    const { th, ok } = layoutThetas(rows, R);
    if (ok) return { R, th };
    R *= 1.02;   // не влезли — бусина чуть больше
  }
  const { th } = layoutThetas(rows, R);
  return { R, th };
}


const DEF_COLORS = [
  { c: '#c22a1e', b: 1 },
  { c: '#20486e', b: 2 },
  { c: '#e9dfc9', b: 3 },
  { c: '#d8a013', b: 4 },
];

const state = {
  palette: DEF_COLORS.map(x => ({ ...x })),
  activeColor: 0,
  small: false,           // что ставится кликом
  sel: null,              // {row, idx}
  model: null,
};

function beadCount(m) { return m.rows.reduce((a, r) => a + r.beads.length, 0); }

// ================= генерация модели =================
function generate(ballMm, middle) {
  ballMm = Math.max(5, ballMm || 14.5);
  middle = Math.max(1, Math.min(40, middle || 11));
  const rows = patternRows(middle).map(r => ({
    th: 0,
    beads: r.sizes.map(s => ({ c: 0, s })),
  }));
  const { R, th } = fitBall(rows, ballMm / 2);
  rows.forEach((r, i) => r.th = th[i]);
  state.model = { R, middle, rows };
  state.sel = null;
  rebuild3D();
  updateCam();
  draw2D();
  updateStat();
}
// ================= 3D =================
let renderer, scene, camera, meshes, beadList, selMarker, ballMesh, rot = { x: 0.4, y: 0 }, drag = null;

function init3D() {
  const canvas = document.getElementById('c3d');
  renderer = new THREE.WebGLRenderer({ canvas, antialias: true, preserveDrawingBuffer: true });
  scene = new THREE.Scene();
  scene.background = new THREE.Color(0xf7f5f0);
  scene.add(new THREE.AmbientLight(0xffffff, 0.65));
  const d1 = new THREE.DirectionalLight(0xffffff, 0.7); d1.position.set(3, 5, 4); scene.add(d1);
  const d2 = new THREE.DirectionalLight(0xffffff, 0.3); d2.position.set(-3, -2, -4); scene.add(d2);
  camera = new THREE.PerspectiveCamera(45, 1, 1, 1000);
  selMarker = new THREE.Mesh(
    new THREE.SphereGeometry(1, 16, 12),
    new THREE.MeshBasicMaterial({ color: 0x00ff00, wireframe: true }));
  selMarker.visible = false;
  scene.add(selMarker);
  // внутренняя бусина (каркас) — видна сквозь оплётку
  ballMesh = new THREE.Mesh(
    new THREE.SphereGeometry(1, 32, 24),
    new THREE.MeshBasicMaterial({ color: 0x99a, wireframe: true, transparent: true, opacity: 0.25 }));
  scene.add(ballMesh);
  resize3D();
  window.addEventListener('resize', () => { resize3D(); draw2D(); });

  canvas.addEventListener('pointerdown', e => {
    drag = { x: e.clientX, y: e.clientY, moved: false };
  });
  canvas.addEventListener('pointermove', e => {
    if (!drag) return;
    const dx = e.clientX - drag.x, dy = e.clientY - drag.y;
    if (Math.abs(dx) + Math.abs(dy) > 3) drag.moved = true;
    rot.y += dx * 0.01; rot.x = Math.max(-1.4, Math.min(1.4, rot.x + dy * 0.01));
    drag.x = e.clientX; drag.y = e.clientY;
    updateCam();
  });
  canvas.addEventListener('pointerup', e => {
    const wasDrag = drag && drag.moved; drag = null;
    if (!wasDrag) pick3D(e);
  });
  canvas.addEventListener('wheel', e => {
    e.preventDefault();
    camera.position.multiplyScalar(e.deltaY > 0 ? 1.1 : 0.9);
    camera.updateMatrixWorld();
  }, { passive: false });
}

function resize3D() {
  const el = document.getElementById('panel3d');
  const wpx = el.clientWidth, hpx = el.clientHeight;
  renderer.setSize(wpx, hpx, false);
  renderer.setPixelRatio(window.devicePixelRatio || 1);
  camera.aspect = wpx / Math.max(1, hpx);
  camera.updateProjectionMatrix();
  updateCam();
}

function updateCam() {
  const R = state.model ? state.model.R : 20;
  const d = R * 3.2;
  const cx = Math.cos(rot.x);
  camera.position.set(d * cx * Math.sin(rot.y), d * Math.sin(rot.x), d * cx * Math.cos(rot.y));
  camera.lookAt(0, 0, 0);
}

function beadPos(m, ri, j) {
  const row = m.rows[ri], th = row.th;
  const { cent } = ringGeom(row, m.R);
  const phi = cent[j];
  const rr = m.R + BEAD[row.beads[j].s].h / 2;
  return { phi, v: new THREE.Vector3(
    rr * Math.sin(th) * Math.cos(phi), rr * Math.cos(th), rr * Math.sin(th) * Math.sin(phi)) };
}

function rebuild3D() {
  if (meshes) meshes.forEach(m => { scene.remove(m); m.geometry.dispose(); m.material.dispose(); });
  const m = state.model;
  meshes = []; beadList = [];
  if (ballMesh) ballMesh.scale.setScalar(m.R);
  for (const s of [0, 1]) {
    const list = [];
    m.rows.forEach((row, ri) => row.beads.forEach((b, j) => {
      if (b.s === s) list.push({ ri, j, b });
    }));
    if (!list.length) continue;
    const im = new THREE.InstancedMesh(
      new THREE.CylinderGeometry(1, 1, 1, 10),
      new THREE.MeshPhongMaterial({ shininess: 40 }), list.length);
    im.userData.size = s;
    const dummy = new THREE.Object3D(), col = new THREE.Color(), up = new THREE.Vector3(0, 1, 0);
    list.forEach((it, k) => {
      const { phi, v } = beadPos(m, it.ri, it.j);
      dummy.position.copy(v);
      // ось цилиндра (Y) вдоль касательной к окружности ряда (восток)
      const east = new THREE.Vector3(-Math.sin(phi), 0, Math.cos(phi));
      dummy.quaternion.setFromUnitVectors(up, east);
      dummy.scale.set(BEAD[it.b.s].h / 2, BEAD[it.b.s].w / 2, BEAD[it.b.s].h / 2);
      dummy.updateMatrix();
      im.setMatrixAt(k, dummy.matrix);
      im.setColorAt(k, col.set(state.palette[it.b.c].c));
      beadList.push({ ri: it.ri, j: it.j, mesh: im, inst: k, v });
    });
    if (im.instanceColor) im.instanceColor.needsUpdate = true;
    scene.add(im); meshes.push(im);
  }
}

// перекраска одной бисерины без пересборки
function repaintBead(ri, j) {
  const b = state.model.rows[ri].beads[j];
  for (const im of meshes) {
    if (im.userData.size !== b.s) continue;
    const rec = beadList.find(r => r.ri === ri && r.j === j && r.mesh === im);
    if (rec) {
      im.setColorAt(rec.inst, new THREE.Color(state.palette[b.c].c));
      im.instanceColor.needsUpdate = true;
    }
  }
}

const ray = new THREE.Raycaster();
function pick3D(e) {
  if (!state.model) return;
  const r = renderer.domElement.getBoundingClientRect();
  const p = new THREE.Vector2(
    ((e.clientX - r.left) / r.width) * 2 - 1, -((e.clientY - r.top) / r.height) * 2 + 1);
  ray.setFromCamera(p, camera);
  const hits = ray.intersectObjects(meshes.filter(m => m.count > 0));
  if (!hits.length) { select(null); return; }
  const h = hits[0];
  const rec = beadList.find(r => r.mesh === h.object && r.inst === h.instanceId);
  if (rec) editBead(rec.ri, rec.j);
}

function select(sel) {
  state.sel = sel;
  if (sel) {
    const rec = beadList.find(r => r.ri === sel.row && r.j === sel.idx);
    if (rec) {
      selMarker.position.copy(rec.v);
      selMarker.scale.setScalar(BEAD[state.model.rows[sel.row].beads[sel.idx].s].w * 1.2);
      selMarker.visible = true;
    }
    document.getElementById('selSmall').checked = !!state.model.rows[sel.row].beads[sel.idx].s;
  } else selMarker.visible = false;
  draw2D();
}

// применить текущий цвет/размер к бисерине и выбрать её
function editBead(ri, j) {
  const b = state.model.rows[ri].beads[j];
  const sizeChanged = b.s !== (state.small ? 1 : 0);
  b.c = state.activeColor;
  b.s = state.small ? 1 : 0;
  if (sizeChanged) rebuild3D(); else repaintBead(ri, j);
  select({ row: ri, idx: j });
  updateStat();
}
// ================= 2D развёртка =================
const c2d = document.getElementById('c2d'), ctx = c2d.getContext('2d');
let d2 = null; // геометрия развертки

function draw2D() {
  const m = state.model;
  const wrap = document.getElementById('panel2d');
  const W = Math.max(400, wrap.clientWidth - 20);
  if (!m) { c2d.width = W; c2d.height = 100; return; }
  // масштаб: мм -> px по самому широкому ряду (по длине кольца)
  const maxC = Math.max(...m.rows.map(r => ringGeom(r, m.R).C));
  const pxmm = Math.min((W - 70) / maxC, 20 / BEAD[0].w);
  const rh = BEAD[0].h * pxmm * 1.35;
  c2d.width = W; c2d.height = m.rows.length * rh + 30;
  ctx.clearRect(0, 0, c2d.width, c2d.height);
  d2 = { pxmm, rh, rows: [] };
  m.rows.forEach((row, ri) => {
    const y = 15 + ri * rh + rh / 2;
    const { C, cent } = ringGeom(row, m.R);
    const rowW = C * pxmm;
    const x0 = (W - rowW) / 2;
    // центры бисерин — как в 3D (равномерно, без наложений)
    const xs = row.beads.map((b, j) => x0 + cent[j] * rowW / (2 * Math.PI));
    d2.rows.push({ y, x0, xs, n: row.beads.length, rowW });
    row.beads.forEach((b, j) => {
      const x = xs[j];
      const r = BEAD[b.s].w * pxmm * 0.46;
      ctx.beginPath(); ctx.arc(x, y, r, 0, Math.PI * 2);
      ctx.fillStyle = state.palette[b.c].c; ctx.fill();
      ctx.lineWidth = 1;
      ctx.strokeStyle = b.s ? '#888' : '#000';
      if (b.s) ctx.setLineDash([2, 2]);
      ctx.stroke(); ctx.setLineDash([]);
      if (state.sel && state.sel.row === ri && state.sel.idx === j) {
        ctx.beginPath(); ctx.arc(x, y, r + 2.5, 0, Math.PI * 2);
        ctx.strokeStyle = '#00c000'; ctx.lineWidth = 2.5; ctx.stroke();
      }
      if (r >= 5) {
        ctx.fillStyle = '#000'; ctx.font = `${Math.max(7, Math.floor(r))}px sans-serif`;
        ctx.textAlign = 'center'; ctx.textBaseline = 'middle';
        ctx.fillText(state.palette[b.c].b, x, y);
      }
    });
    ctx.fillStyle = '#aaa'; ctx.font = '9px sans-serif'; ctx.textAlign = 'right';
    ctx.fillText(ri + 1, x0 - 6, y);
  });
}

c2d.addEventListener('pointerdown', e => {
  if (!state.model || !d2) return;
  const r = c2d.getBoundingClientRect();
  const px = (e.clientX - r.left) * (c2d.width / r.width);
  const py = (e.clientY - r.top) * (c2d.height / r.height);
  const ri = Math.floor((py - 15) / d2.rh);
  if (ri < 0 || ri >= d2.rows.length) return;
  const g = d2.rows[ri];
  if (px < g.x0 - 10 || px > g.x0 + g.rowW + 10) return;
  let best = -1, bd = 1e9;
  g.xs.forEach((x, j) => { const d = Math.abs(px - x); if (d < bd) { bd = d; best = j; } });
  if (best >= 0) editBead(ri, best);
});
// ================= интерфейс =================
function renderPalette() {
  const el = document.getElementById('palette');
  el.innerHTML = '';
  state.palette.forEach((p, i) => {
    const d = document.createElement('div');
    d.className = 'swatch' + (i === state.activeColor ? ' active' : '');
    d.style.background = p.c;
    d.textContent = p.b;
    d.title = `Коробочка ${p.b}` + (i === state.activeColor ? ' (выбран)' : '');
    d.onclick = () => { state.activeColor = i; renderPalette(); };
    el.appendChild(d);
  });
}

function updateStat() {
  const m = state.model;
  if (!m) { document.getElementById('stat').textContent = ''; return; }
  let small = 0;
  m.rows.forEach(r => r.beads.forEach(b => { if (b.s) small++; }));
  document.getElementById('stat').textContent =
    `рядов: ${m.rows.length}, бисерин: ${beadCount(m)} (15/0 — ${small}), ` +
    `бусина ⌀ ${(2 * m.R).toFixed(1)} мм (средних рядов Delica: ${m.middle})`;
}

function saveJSON() {
  const m = state.model;
  if (!m) return alert('Модель не сгенерирована');
  const data = {
    type: 'd3sc-sphere-v2',
    palette: state.palette,
    R: m.R,
    middle: m.middle,
    rows: m.rows.map(r => ({ th: r.th, beads: r.beads.map(b => [b.c, b.s]) })),
  };
  const a = document.createElement('a');
  a.href = URL.createObjectURL(new Blob([JSON.stringify(data)], { type: 'application/json' }));
  a.download = 'd3sc_сфера.json';
  a.click();
}

function loadJSON(file) {
  const rd = new FileReader();
  rd.onload = () => {
    try {
      const d = JSON.parse(rd.result);
      if (d.type !== 'd3sc-sphere-v2') throw new Error('не файл d3sc v2');
      state.palette = d.palette;
      state.model = {
        R: d.R,
        middle: d.middle || 11,
        rows: d.rows.map(r => ({
          th: r.th, beads: r.beads.map(a => ({ c: a[0], s: a[1] })),
        })),
      };
      state.sel = null;
      renderPalette(); rebuild3D(); updateCam(); draw2D(); updateStat();
    } catch (e) { alert('Не удалось открыть: ' + e.message); }
  };
  rd.readAsText(file);
}

// ================= печать =================
function buildPrint() {
  const m = state.model;
  if (!m) return false;
  const grid = document.getElementById('prGrid');
  grid.innerHTML = '';
  m.rows.forEach((row, ri) => {
    const div = document.createElement('div'); div.className = 'pr-row';
    for (let j = 0; j < row.n; j++) {
      const b = row.beads[j];
      const s = document.createElement('span');
      s.className = 'pr-bead' + (b.s ? ' small' : '');
      s.style.background = state.palette[b.c].c;
      s.textContent = state.palette[b.c].b;
      s.title = `ряд ${ri + 1}, №${j + 1}`;
      div.appendChild(s);
    }
    grid.appendChild(div);
  });
  const used = new Set(); m.rows.forEach(r => r.beads.forEach(b => used.add(b.c)));
  document.getElementById('prLegend').innerHTML =
    [...used].map(i => {
      const p = state.palette[i];
      return `<span><i style="background:${p.c}"></i>${p.b} — ${p.c}</span>`;
    }).join('') +
    `<br><span style="font-size:10px">Пунктирный кружок = мелкий бисер. Кружок = одна бисерина, цифра = номер коробочки.</span>`;
  document.getElementById('prMeta').textContent =
    `Рядов: ${m.rows.length}, бисерин: ${beadCount(m)}, диаметр ≈ ${(2 * m.R).toFixed(1)} мм. Ряды сверху вниз от полюса.`;
  return true;
}

// ================= каркас =================
function animate() {
  requestAnimationFrame(animate);
  renderer.render(scene, camera);
}

function eqFromInputs() {
  return [
    parseFloat(document.getElementById('ballMm').value) || 14.5,
    parseInt(document.getElementById('midRows').value, 10) || 11,
  ];
}

document.getElementById('btnGen').onclick = () => generate(...eqFromInputs());
document.getElementById('btnSave').onclick = saveJSON;
document.getElementById('btnLoad').onclick = () => document.getElementById('fileJson').click();
document.getElementById('fileJson').onchange = e => {
  if (e.target.files[0]) loadJSON(e.target.files[0]);
  e.target.value = '';
};
document.getElementById('btnPng').onclick = () => {
  renderer.render(scene, camera);
  const a = document.createElement('a');
  a.href = renderer.domElement.toDataURL('image/png');
  a.download = 'd3sc_3d.png'; a.click();
};
document.getElementById('btnPrint').onclick = () => { if (buildPrint()) window.print(); };
document.getElementById('btnAddColor').onclick = () => {
  state.palette.push({
    c: document.getElementById('newColor').value,
    b: parseInt(document.getElementById('newBox').value, 10) || (state.palette.length + 1),
  });
  renderPalette();
};
document.getElementById('btnDelColor').onclick = () => {
  if (state.palette.length <= 1) return alert('Нужен хотя бы один цвет');
  const del = state.palette.length - 1;
  if (state.activeColor === del) state.activeColor = 0;
  if (state.model) state.model.rows.forEach(r => r.beads.forEach(b => {
    if (b.c === del) b.c = 0; else if (b.c > del) b.c--;
  }));
  state.palette.pop();
  renderPalette(); if (state.model) { rebuild3D(); draw2D(); }
};
document.getElementById('selSmall').onchange = e => {
  state.small = e.target.checked;
  if (state.sel) editBead(state.sel.row, state.sel.idx);
};

init3D();
renderPalette();
generate(14.5, 11);
animate();
