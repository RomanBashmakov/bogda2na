/* d3Sc — редактор бисерной сферы (мозаичное/gourd плетение)
 * Данные: model = { R, rows:[{n, th, beads:[{c,s}]}] }  s: 0 крупный, 1 мелкий
 * Правки в 3D и 2D синхронны: единая модель, обе панели перерисовываются.
 */
'use strict';

// ---- Калибры бисера, мм (ширина вдоль нити × высота поперёк) ----
// подобраны так, чтобы паттерн из site.txt (16 Delica на экваторе)
// плотно садился на бусину ~14–15 мм
const BEAD = {
  0: { w: 2.8, h: 2.6 },   // крупный цилиндр (Delica)
  1: { w: 1.7, h: 1.9 },   // мелкий круглый (15/0)
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

const rowH = r => BEAD[r.beads[0].s].h;
const rowC = r => r.beads.reduce((a, b) => a + BEAD[b.s].w, 0);

// коллизионный радиус бисерины (грубая модель цилиндра сферой)
const colR = b => (BEAD[b.s].w + BEAD[b.s].h) / 4;


// ================= физическая укладка (релаксация) =================
// 1) стартовые позиции: ряды-кольца на бусине, мозаичный сдвиг на полшага
// 2) связи «нити»: каждая бисерина связана с двумя ближайшими бисеринами
//    соседнего ряда (пейот), целевая дистанция = касание (w_a+w_b)/2
// 3) итерации: пружины + жёсткое непроникновение + бусина-ограничитель
function buildLayout(rows, Rball) {
  const flat = [];   // {row, idx, bead, p:[x,y,z]}
  rows.forEach((row, ri) => {
    const n = row.beads.length;
    // θ: стек рядов по шагу укладки, экваторный ряд — на π/2
    let eq = 0, maxC = -1;
    rows.forEach((r, i) => { const C = rowC(r); if (C > maxC) { maxC = C; eq = i; } });
    const thArr = [];
    let a = 0;
    rows.forEach((r, i) => {
      const h = BEAD[r.beads[0].s].h;
      if (i === 0) a = h / 2 / (Rball + h / 2);
      else a += 0.87 * (BEAD[rows[i - 1].beads[0].s].h + h) / 2 / (Rball + h / 2);
      thArr.push(a);
    });
    const shift = Math.PI / 2 - thArr[eq];
    row.th = Math.min(Math.PI - 0.05, Math.max(0.05, thArr[ri] + shift));
    row.beads.forEach((b, j) => {
      const rc = Rball + BEAD[b.s].h / 2;
      const phi = (j + (ri % 2) * 0.5) / n * 2 * Math.PI;
      const p = [rc * Math.sin(row.th) * Math.cos(phi), rc * Math.cos(row.th),
                 rc * Math.sin(row.th) * Math.sin(phi)];
      b.p = p;
      flat.push({ row: ri, idx: j, bead: b, p });
    });
  });
  // индекс (row,idx) -> flat
  const at = (ri, j) => flat[rows.slice(0, ri).reduce((acc, r) => acc + r.beads.length, 0) + j];
  // связи нити: ребёнок (ряд i+1) -> 2 ближайших родителя (ряд i) по углу
  const links = [];
  const ang = f => Math.atan2(f.p[2], f.p[0]);
  for (let ri = 1; ri < rows.length; ri++) {
    const nCh = rows[ri].beads.length, nPar = rows[ri - 1].beads.length;
    const parAng = [];
    for (let j = 0; j < nPar; j++) parAng.push(ang(at(ri - 1, j)));
    for (let j = 0; j < nCh; j++) {
      const a = ang(at(ri, j));
      const sorted = parAng.map((pa, pj) => [Math.abs((((a - pa) % (2 * Math.PI)) + 3 * Math.PI) % (2 * Math.PI) - Math.PI), pj])
        .sort((x, y) => x[0] - y[0]);
      const t = (BEAD[rows[ri].beads[j].s].w + BEAD[rows[ri - 1].beads[sorted[0][1]].s].w) / 2;
      links.push([at(ri, j), at(ri - 1, sorted[0][1]), t]);
      const t2 = (BEAD[rows[ri].beads[j].s].w + BEAD[rows[ri - 1].beads[sorted[1][1]].s].w) / 2;
      links.push([at(ri, j), at(ri - 1, sorted[1][1]), t2]);
    }
  }
  // соседи по кольцу: бисерины ряда касаются торцами
  rows.forEach((row, ri) => {
    const n = row.beads.length;
    for (let j = 0; j < n; j++) {
      const a = at(ri, j), b = at(ri, (j + 1) % n);
      const t = (BEAD[row.beads[j].s].w + BEAD[row.beads[(j + 1) % n].s].w) / 2;
      links.push([a, b, t]);
    }
  });
  return { flat, links };
}

function relax(layout, rows, Rball, iters) {
  const { flat, links } = layout;
  const cell = 3.0; // ячейка сетки коллизий, мм
  const thread = new Set();
  for (const [a, b] of links) {
    thread.add(a.row + ':' + a.idx + '-' + b.row + ':' + b.idx);
    thread.add(b.row + ':' + b.idx + '-' + a.row + ':' + a.idx);
  }
  // капсульная модель бисерины: ось вдоль кольца, 2 сферы радиуса h/2
  for (const f of flat) {
    f.r = BEAD[f.bead.s].h / 2;
    const half = Math.max(0, BEAD[f.bead.s].w / 2 - f.r);
    const row = rows[f.row], n = row.beads.length;
    const prev = row.beads[(f.idx - 1 + n) % n].p, next = row.beads[(f.idx + 1) % n].p;
    let ux = next[0] - prev[0], uy = next[1] - prev[1], uz = next[2] - prev[2];
    const ul = Math.hypot(ux, uy, uz) || 1;
    ux /= ul; uy /= ul; uz /= ul;
    f.u = [ux, uy, uz];
    f.caps = [
      [f.p[0] + ux * half, f.p[1] + uy * half, f.p[2] + uz * half],
      [f.p[0] - ux * half, f.p[1] - uy * half, f.p[2] - uz * half],
    ];
  }
  const gkey = (x, y, z) => (Math.floor(x / cell) + 500) * 1e6 +
    (Math.floor(y / cell) + 500) * 1e3 + (Math.floor(z / cell) + 500);
  // зафиксировать масштаб: средний радиус оплётки не должен меняться
  let meanR0 = 0;
  for (const f of flat) meanR0 += Math.hypot(...f.p);
  meanR0 /= flat.length;
  const resolveCollisions = () => {
    // непроникновение капсул (по пространственной сетке)
    const grid = new Map();
    for (const f of flat) for (const c of f.caps) {
      const k = gkey(c[0], c[1], c[2]);
      if (!grid.has(k)) grid.set(k, []);
      grid.get(k).push([f, c]);
    }
    for (const f of flat) for (const cf of f.caps) {
      const cx = Math.floor(cf[0] / cell), cy = Math.floor(cf[1] / cell), cz = Math.floor(cf[2] / cell);
      for (let dx = -1; dx <= 1; dx++) for (let dy = -1; dy <= 1; dy++) for (let dz = -1; dz <= 1; dz++) {
        const bucket = grid.get(gkey((cx + dx + 0.5) * cell, (cy + dy + 0.5) * cell, (cz + dz + 0.5) * cell));
        if (!bucket) continue;
        for (const [g, cg] of bucket) {
          if (g === f) continue;
          if (g.row === f.row) {
            const n = rows[f.row].beads.length;
            const md = Math.min((f.idx - g.idx + n) % n, (g.idx - f.idx + n) % n);
            if (md <= 1) continue;
          }
          if (thread.has(f.row + ':' + f.idx + '-' + g.row + ':' + g.idx)) continue;
          const ex = cg[0] - cf[0], ey = cg[1] - cf[1], ez = cg[2] - cf[2];
          const d = Math.sqrt(ex * ex + ey * ey + ez * ez) || 1e-6;
          const t = f.r + g.r;
          if (d < t) {
            const push = (t - d) / d * 0.5;
            const mx = ex * push, my = ey * push, mz = ez * push;
            f.p[0] -= mx; f.p[1] -= my; f.p[2] -= mz;
            g.p[0] += mx; g.p[1] += my; g.p[2] += mz;
            cf[0] -= mx; cf[1] -= my; cf[2] -= mz;
            cg[0] += mx; cg[1] += my; cg[2] += mz;
          }
        }
      }
    }
  };
  for (let it = 0; it < iters; it++) {
    // пружины нити
    for (const [a, b, t] of links) {
      const dx = b.p[0] - a.p[0], dy = b.p[1] - a.p[1], dz = b.p[2] - a.p[2];
      const d = Math.sqrt(dx * dx + dy * dy + dz * dz) || 1e-6;
      const err = (d - t) / d * 0.15;
      const mx = dx * err, my = dy * err, mz = dz * err;
      a.p[0] += mx; a.p[1] += my; a.p[2] += mz;
      b.p[0] -= mx; b.p[1] -= my; b.p[2] -= mz;
    }
    // обновить капсулы
    for (const f of flat) {
      const half = Math.max(0, BEAD[f.bead.s].w / 2 - f.r);
      f.caps[0] = [f.p[0] + f.u[0] * half, f.p[1] + f.u[1] * half, f.p[2] + f.u[2] * half];
      f.caps[1] = [f.p[0] - f.u[0] * half, f.p[1] - f.u[1] * half, f.p[2] - f.u[2] * half];
    }
    // непроникновение капсул — два прохода
    resolveCollisions();
    resolveCollisions();
    // бусина как упор: только не даём провалиться внутрь (мягко)
    for (const f of flat) {
      const h = BEAD[f.bead.s].h;
      const d = Math.sqrt(f.p[0] ** 2 + f.p[1] ** 2 + f.p[2] ** 2) || 1;
      const rMin = Rball + h / 2;
      if (d < rMin) {
        const k = 1 + (rMin / d - 1) * 0.2;
        f.p[0] *= k; f.p[1] *= k; f.p[2] *= k;
      }
    }
    // форма: нормализация среднего радиуса (анти-сплющивание)
    let meanR = 0;
    for (const f of flat) meanR += Math.hypot(...f.p);
    meanR = meanR / flat.length || 1;
    const k = meanR0 / meanR;
    for (const f of flat) { f.p[0] *= k; f.p[1] *= k; f.p[2] *= k; }
  }
  // финальная чистка: только непроникновение, без пружин
  for (let k = 0; k < 300; k++) {
    for (const f of flat) {
      const half = Math.max(0, BEAD[f.bead.s].w / 2 - f.r);
      f.caps[0] = [f.p[0] + f.u[0] * half, f.p[1] + f.u[1] * half, f.p[2] + f.u[2] * half];
      f.caps[1] = [f.p[0] - f.u[0] * half, f.p[1] - f.u[1] * half, f.p[2] - f.u[2] * half];
    }
    resolveCollisions();
    resolveCollisions();
    let meanR = 0;
    for (const f of flat) meanR += Math.hypot(...f.p);
    meanR = meanR / flat.length || 1;
    const k = meanR0 / meanR;
    for (const f of flat) { f.p[0] *= k; f.p[1] *= k; f.p[2] *= k; }
  }
  // записать позиции в модель
  for (const f of flat) rows[f.row].beads[f.idx].p = f.p;
}

// вписанная бусина: максимальный шар, помещающийся под оплёткой
function innerBall(rows) {
  let R = 1e9;
  rows.forEach(r => r.beads.forEach(b => {
    R = Math.min(R, Math.hypot(...b.p) - BEAD[b.s].h / 2);
  }));
  return Math.max(1, R);
}

// пересчёт укладки на текущих позициях (после ручной смены размера бисерины)
function reRelax(iters) {
  const m = state.model;
  if (!m) return;
  const layout = buildLayout(m.rows, m.R);
  relax(layout, m.rows, m.R, iters || 120);
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
  const R = ballMm / 2;
  relax(buildLayout(rows, R), rows, R, 500);
  state.model = { R: innerBall(rows), middle, rows };
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
  let R = 20;
  if (state.model) {
    R = 1;
    state.model.rows.forEach(r => r.beads.forEach(b => { R = Math.max(R, Math.hypot(...b.p)); }));
  }
  const d = R * 3.2;
  const cx = Math.cos(rot.x);
  camera.position.set(d * cx * Math.sin(rot.y), d * Math.sin(rot.x), d * cx * Math.cos(rot.y));
  camera.lookAt(0, 0, 0);
}

function beadPos(m, ri, j) {
  const row = m.rows[ri];
  const p = row.beads[j].p;
  // ось цилиндра — вдоль нити кольца (по соседям)
  const n = row.beads.length;
  const prev = row.beads[(j - 1 + n) % n].p, next = row.beads[(j + 1) % n].p;
  const dir = [next[0] - prev[0], next[1] - prev[1], next[2] - prev[2]];
  const dl = Math.hypot(...dir) || 1;
  const east = new THREE.Vector3(dir[0] / dl, dir[1] / dl, dir[2] / dl);
  return { east, v: new THREE.Vector3(p[0], p[1], p[2]) };
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
      const { east, v } = beadPos(m, it.ri, it.j);
      dummy.position.copy(v);
      // ось цилиндра (Y) вдоль нити кольца
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
  if (sizeChanged) { reRelax(150); rebuild3D(); } else repaintBead(ri, j);
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
  // 2D — «плетёный» вид: бисерины ряда вплотную (порядок как в 3D-кольце)
  const pxmm = Math.min((W - 70) / (16 * BEAD[0].w), 20 / BEAD[0].w);
  const rh = BEAD[0].h * pxmm * 1.4;
  c2d.width = W; c2d.height = m.rows.length * rh + 30;
  ctx.clearRect(0, 0, c2d.width, c2d.height);
  d2 = { pxmm, rh, rows: [] };
  m.rows.forEach((row, ri) => {
    const y = 15 + ri * rh + rh / 2;
    const rowW = rowC(row) * pxmm;
    const x0 = (W - rowW) / 2;
    // позиции по кольцу: cumulative касание, старт с бисерины 0
    const xs = [x0];
    for (let j = 1; j < row.beads.length; j++) {
      const gap = (BEAD[row.beads[j - 1].s].w + BEAD[row.beads[j].s].w) / 2 * pxmm;
      xs.push(xs[j - 1] + gap);
    }
    d2.rows.push({ y, x0, xs, n: row.beads.length, rowW });
    row.beads.forEach((b, j) => {
      const x = xs[j];
      const r = BEAD[b.s].w * pxmm * 0.48;
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
  let small = 0, maxR = 0;
  m.rows.forEach(r => r.beads.forEach(b => {
    if (b.s) small++;
    maxR = Math.max(maxR, Math.hypot(...b.p));
  }));
  document.getElementById('stat').textContent =
    `рядов: ${m.rows.length}, бисерин: ${beadCount(m)} (15/0 — ${small}), ` +
    `итог ⌀ ${(2 * maxR).toFixed(1)} мм (бусина ⌀ ${(2 * m.R).toFixed(1)}, средних рядов Delica: ${m.middle})`;
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
          th: r.th || 0, beads: r.beads.map(a => ({ c: a[0], s: a[1], p: [0, 0, 0] })),
        })),
      };
      // восстановить физическую укладку
      relax(buildLayout(state.model.rows, d.R), state.model.rows, d.R, 500);
      state.model.R = innerBall(state.model.rows);
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
