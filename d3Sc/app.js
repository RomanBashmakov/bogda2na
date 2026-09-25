/* d3Sc — редактор бисерной сферы (мозаичное/gourd плетение)
 * Данные: model = { R, rows:[{n, th, beads:[{c,s}]}] }  s: 0 крупный, 1 мелкий
 * Правки в 3D и 2D синхронны: единая модель, обе панели перерисовываются.
 */
'use strict';

// ---- Калибры бисера, мм (ширина вдоль нити × высота поперёк) ----
// Delica — основной размер «пояска», 15/0 — венцы у полюсов; число бисерин
// в рядах выводится из целевой сферы (см. patternRows)
const BEAD = {
  0: { w: 2.8, h: 2.6 },   // крупный цилиндр (Delica)
  1: { w: 1.7, h: 1.9 },   // мелкий круглый (15/0)
};

// Паттерн: полюсные венцы — фиксированные, по site.txt (у полюса кольцо
// из 4 Delica, выше 4×15/0, 8 Delica, 8×15/0, 16×15/0, 8 Delica,
// 16×15/0 ×2 — и зеркально сверху). Средняя часть — сферический профиль:
// число Delica убывает от экватора к полюсам пропорционально cos широты.
// Широты считаются в единицах самой схемы (шаг утопленного ряда к длине
// экваториального кольца), поэтому схема НЕ зависит от размера бусины —
// поле «Бусина, мм» можно менять после генерации без пересборки.
// middle — число средних рядов Delica.
function patternRows(middle) {
  const D = 0, S = 1;
  const crownLo = [
    [D, 4], [S, 4], [D, 8], [S, 8], [S, 16], [D, 8], [S, 16], [S, 16],
  ];
  const crownHi = [
    [S, 16], [S, 16], [D, 8], [S, 16], [S, 8], [D, 8], [S, 4], [D, 4],
  ];
  const N = 16;  // экваториальное число Delica (как в site.txt)
  const dth = 0.6 * BEAD[D].h * 2 * Math.PI / (N * BEAD[D].w); // шаг по широте
  const per = Math.floor(middle / 2), odd = middle % 2;
  const half = [];                     // от экватора к венцу
  for (let k = 0; k < per + odd; k++) {
    // минимум — кольцо длиной с S16-венец (16×1.7 мм ≈ 10 Delica):
    // тоньше нельзя, стык с венцом не должен разрежаться
    half.push(Math.max(10, Math.round(N * Math.cos((k + (odd ? 0 : 0.5)) * dth))));
  }
  const mid = (odd ? half.slice(1).reverse() : [...half].reverse()).concat(half);
  const seq = [...crownLo, ...mid.map(n => [D, n]), ...crownHi];
  return seq.map(([sz, n]) => ({ sizes: Array(n).fill(sz) }));
}

const rowH = r => BEAD[r.beads[0].s].h;
const rowC = r => r.beads.reduce((a, b) => a + BEAD[b.s].w, 0);

// коллизионный радиус бисерины (грубая модель цилиндра сферой)
const colR = b => (BEAD[b.s].w + BEAD[b.s].h) / 4;


// ================= физическая укладка (PBD: проекции позиций) =================
// Приоритеты ограничений: целевая сфера — сильно, непроникновение — жёстко,
// нить — слабо. Связь нити асимметричная: сжатие (бисерины наезжают)
// разводится жёстко, растяжение подтягивается слабо — где паттерну тесно,
// там остаётся зазор, который распределяет сам решатель
// («напрягающиеся» и «расслабляющиеся» места). Средний радиус НЕ
// нормализуется: форма итогового изделия — сфера заданного размера.
//
// 1) стартовые позиции: ряды-кольца на сфере R + h/2, мозаичный сдвиг на полшага
// 2) итерации: связи нити → ориентация капсул по соседям → коллизии → сфера
// 3) финальная чистка: коллизии + сфера, без пружин
// естественный радиус плетения: сфера, на которую площадь плетения
// ложится с утопленным шагом рядов (footprint бисерины ≈ w × 0.6h).
// Меньше неё бусину не сделать — не влезет; от неё считается
// коэффициент раздувания k = R/RvNat
function naturalR(rows) {
  let area = 0;
  rows.forEach(r => r.beads.forEach(b => { area += BEAD[b.s].w * BEAD[b.s].h; }));
  return Math.sqrt(area * 0.6 / (4 * Math.PI)) - BEAD[0].h / 2;
}

function buildLayout(rows, Rball) {
  const flat = [];
  const totalRows = rows.length;
  
  // 1. Определяем общую высоту сферы.
  // Rball — это радиус внутренней бусины. Бисерины лежат на сфере радиусом Rball + половина высоты бисерины.
  // Для простоты возьмем средний радиус, или можно считать для каждого ряда отдельно.
  const R_center = Rball + BEAD[0].h / 2; 
  
  // 2. Равномерный шаг по высоте (Y).
  // Если рядов N, то промежутков между ними N-1. 
  // Распределяем от -R_center до +R_center.
  const dY = totalRows > 1 ? (2 * R_center) / (totalRows - 1) : 0;
  
  rows.forEach((row, ri) => {
    // 3. Жестко задаем Y для текущего ряда
    let Y = -R_center + ri * dY;
    // Защита от микроскопических ошибок округления
    Y = Math.max(-R_center, Math.min(R_center, Y)); 
    
    // 4. Вычисляем радиус окружности на этой высоте (Теорема Пифагора)
    const r_ring = Math.sqrt(Math.max(0, R_center * R_center - Y * Y));
    
    // Сохраняем theta (угол) для совместимости с другими функциями (например, updateCam)
    row.th = Math.acos(Y / R_center); 
    
    const n = row.beads.length;
    row.beads.forEach((b, j) => {
      // 5. Распределяем n бисерин равномерно по окружности радиуса r_ring
      // Добавляем сдвиг на полшага для четных/нечетных рядов (мозаика)
      const phi = (j + (ri % 2) * 0.5) / n * 2 * Math.PI;
      
      const p = [
        r_ring * Math.cos(phi),
        Y,
        r_ring * Math.sin(phi)
      ];
      
      b.p = p; // Присваиваем координаты напрямую, без физики!
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

// ориентация капсулы бисерины — вдоль нити кольца (по текущим соседям);
// вызывается каждую итерацию: капсулы следуют за фактической укладкой
function updateCaps(flat, rows) {
  for (const f of flat) {
    const row = rows[f.row], n = row.beads.length;
    const prev = row.beads[(f.idx - 1 + n) % n].p, next = row.beads[(f.idx + 1) % n].p;
    let ux = next[0] - prev[0], uy = next[1] - prev[1], uz = next[2] - prev[2];
    const ul = Math.hypot(ux, uy, uz) || 1;
    ux /= ul; uy /= ul; uz /= ul;
    f.u = [ux, uy, uz];
    const half = Math.max(0, BEAD[f.bead.s].w / 2 - f.r);
    f.caps = [
      [f.p[0] + ux * half, f.p[1] + uy * half, f.p[2] + uz * half],
      [f.p[0] - ux * half, f.p[1] - uy * half, f.p[2] - uz * half],
    ];
  }
}

// пошаговый решатель: step() — одна итерация, finish() — финальная чистка
function makeSolver(layout, rows, Rball) {
  const { flat, links } = layout;
  const W_RING = 0.20;    // подтяжка растянутых связей внутри кольца
  const W_PEYOTE = 0.10;  // подтяжка растянутых межрядных (пейот) связей
  const W_PUSH = 0.20;    // развод сжатых внутрикольцевых связей (слабее коллизий)
  const COL_PUSH = 0.50;  // выталкивание в коллизиях — сильнейшая коррекция
  const SPH = 0.45;       // мягкое округление виртуальной сферой
  for (const f of flat) f.r = BEAD[f.bead.s].h / 2;
  updateCaps(flat, rows);
  const cell = 3.0; // ячейка сетки коллизий, мм
  const gkey = (x, y, z) => (Math.floor(x / cell) + 500) * 1e6 +
    (Math.floor(y / cell) + 500) * 1e3 + (Math.floor(z / cell) + 500);
  // непроникновение капсул (по пространственной сетке)
  const resolveCollisions = () => {
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
          // коллизии действуют на ВСЕ пары, включая пары одной нити
          // (кольцо/пейот): без жёсткого пола расстояния сжатые кольца
          // сминаются внахлёст («утопленные» бисерины). Допуск
          // утапливания — как в реальном плетении: торцы соседей по
          // кольцу 0.25 мм, межрядные пары 0.9 мм (мозаичные ряды
          // утапливаются на ~0.6 высоты бисерины)
          const ex = cg[0] - cf[0], ey = cg[1] - cf[1], ez = cg[2] - cf[2];
          const d = Math.sqrt(ex * ex + ey * ey + ez * ez) || 1e-6;
          const t = f.r + g.r - (f.row === g.row ? 0.25 : 0.9);
          if (d < t) {
            const push = (t - d) / d * COL_PUSH;
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
  // виртуальная сфера обжатия: радиус = max(введённый старт, оценка
  // минимума по площади плетения; footprint бисерины на сфере ≈ w × 0.6h
  // из-за утопленного шага рядов). Схема от бусины не зависит — размер
  // можно менять после генерации (поле «Бусина, мм», без перегенерации)
  const RvNat = naturalR(rows);
  const Rv = Math.max(Rball, RvNat);
  // равномерное «раздувание» при бусине больше естественного размера
  // плетения: длины связей РЕШАТЕЛЯ растут пропорционально сфере
  // (k = Rv/RvNat). Без этого замкнутые кольца держат свой радиус,
  // сбиваются к полюсам в кучу, а экватор рвётся щелями. С масштабом
  // укладка раздувается равномерно: бисерины разъезжаются по всему
  // свободному месту, в том числе у полюсов. Истинные длины связей
  // (layout.links) не трогаем — карта натяжения и зазор в статусе
  // честно показывают, насколько плетение свободно на этой бусине
  const kin = RvNat > 0 ? Rv / RvNat : 1;
  const inflate = kin > 1.0001;
  const slinks = inflate ? links.map(l => [l[0], l[1], l[2] * kin]) : links;
  // сфера-оболочка: центры на Rv + h/2 (мелкий бисер сидит глубже);
  // и не провалиться внутрь, и не улететь наружу
  const toSphere = () => {
    for (const f of flat) {
      const r0 = Rv + BEAD[f.bead.s].h / 2;
      const d = Math.hypot(f.p[0], f.p[1], f.p[2]) || 1e-6;
      const k = 1 + (r0 / d - 1) * SPH;
      f.p[0] *= k; f.p[1] *= k; f.p[2] *= k;
    }
  };
  const step = () => {
    // связи нити: кольцо — двустороннее (сжатие жёстко, растяжение слабо),
    // пейот — только подтяжка с люфтом 0.1 мм (нить слегка растяжима:
    // в тесных местах ход отдаётся коллизиям, чтобы не давить бисерины).
    // slinks — связи с длинами, растянутыми k-кратно сфере (см. выше).
    // Пейот остаётся только подтяжкой: у мозаичных пар естественная
    // дистанция — утопленное вложение (~0.6h), а не касание, поэтому
    // «расталкивание» до t·k ломало бы укладку. Распределение рядов
    // по меридиану при раздувании держат кольцевые связи (радиус
    // кольца жёстко привязан к широте на сфере) + правильный старт
    for (const [a, b, t] of slinks) {
      const dx = b.p[0] - a.p[0], dy = b.p[1] - a.p[1], dz = b.p[2] - a.p[2];
      const d = Math.sqrt(dx * dx + dy * dy + dz * dz) || 1e-6;
      if (a.row !== b.row && d < t + 0.1) continue;
      const w = d < t ? W_PUSH : (a.row === b.row ? W_RING : W_PEYOTE);
      const err = (d - t) / d * w;
      const mx = dx * err, my = dy * err, mz = dz * err;
      a.p[0] += mx; a.p[1] += my; a.p[2] += mz;
      b.p[0] -= mx; b.p[1] -= my; b.p[2] -= mz;
    }
    updateCaps(flat, rows);
    resolveCollisions();
    resolveCollisions();
    toSphere();
  };
  const finish = () => {
    // порядок: сначала сфера, коллизии — последними: финальное слово
    // за непроникновением (приоритетнее точного радиуса)
    for (let k = 0; k < 80; k++) {
      toSphere();
      updateCaps(flat, rows);
      resolveCollisions();
      resolveCollisions();
    }
  };
  return { step, finish, Rv: () => Rv };
}

// равномерное раздувание для бусины больше естественного размера:
// сначала укладка на естественной сфере (отточенное равновесие k=1),
// затем позиции ×k — это ТОЧНОЕ решение раздутой задачи: все длины
// растут ×k, бисерины расходятся по всей сфере, включая полюса, а не
// сбиваются к полюсам кучей с рваным экватором. Дальше решателю
// остаётся только шлифовка. Возвращает true, если раздували
function naturalInflate(layout, rows, Rball, iters) {
  const RvNat = naturalR(rows);
  if (Rball <= RvNat * 1.0001) return false;
  const s0 = makeSolver(layout, rows, RvNat);
  for (let i = 0; i < iters; i++) s0.step();
  s0.finish();
  const k = Rball / RvNat;
  for (const f of layout.flat) {
    f.p[0] *= k; f.p[1] *= k; f.p[2] *= k;
  }
  updateCaps(layout.flat, rows);
  return true;
}

// пакетная укладка (правки размера бисерин, загрузка JSON, смена бусины);
// возвращает фактический радиус виртуальной сферы
function relax(layout, rows, Rball, iters) {
  naturalInflate(layout, rows, Rball, iters);
  const s = makeSolver(layout, rows, Rball);
  for (let i = 0; i < iters; i++) s.step();
  s.finish();
  return s.Rv();
}

// вписанная бусина: максимальный шар, помещающийся под оплёткой
function innerBall(rows) {
  let R = 1e9;
  rows.forEach(r => r.beads.forEach(b => {
    R = Math.min(R, Math.hypot(...b.p) - BEAD[b.s].h / 2);
  }));
  return Math.max(1, R);
}

// натяжение: для каждой бисерины — максимальный зазор её связей нити (мм)
function computeTension() {
  state.tens = null;
  const m = state.model;
  if (!m || !state.layout) return;
  const t = m.rows.map(r => r.beads.map(() => 0));
  for (const [a, b, tgt] of state.layout.links) {
    const err = Math.hypot(b.p[0] - a.p[0], b.p[1] - a.p[1], b.p[2] - a.p[2]) - tgt;
    if (err > t[a.row][a.idx]) t[a.row][a.idx] = err;
    if (err > t[b.row][b.idx]) t[b.row][b.idx] = err;
  }
  state.tens = t;
}

// цвет натяжения: красный — нить натянута (касание), зелёный — расслаблена
function tensColor(ri, j) {
  const gapMax = 0.1 * state.model.R; // 10% радиуса бусины = «полностью расслаблено»
  const x = state.tens ? Math.max(0, Math.min(1, state.tens[ri][j] / gapMax)) : 0;
  return `hsl(${Math.round(120 * x)}, 72%, 48%)`;
}

// пересчёт укладки (после ручной смены размера бисерины) — мгновенно, пакетом
function reRelax(iters) {
  const m = state.model;
  if (!m) return;
  relaxAnim = null; // прервать анимацию генерации, если идёт
  state.layout = buildLayout(m.rows, m.R);
  m.Rres = relax(state.layout, m.rows, m.R, iters || 300);
  computeTension();
}



const DEF_COLORS = [
  { c: '#c22a1e', b: 1 },
  { c: '#20486e', b: 2 },
  { c: '#e9dfc9', b: 3 },
  { c: '#d8a013', b: 4 },
];

let relaxAnim = null; // идущая анимация укладки (текущая frame-функция)

const state = {
  palette: DEF_COLORS.map(x => ({ ...x })),
  activeColor: 0,
  small: false,           // что ставится кликом
  sel: null,              // {row, idx}
  model: null,
  layout: null,           // {flat, links} последней укладки
  tens: null,             // натяжение: [row][idx] -> зазор связи, мм
  showTension: false,     // подсветка натяжения
  showThread: false,      // показ связей нити (3D и 2D)
};

function beadCount(m) { return m.rows.reduce((a, r) => a + r.beads.length, 0); }

// ================= генерация модели =================
function generate(ballMm, middle) {
  ballMm = Math.max(5, ballMm || 14.5);
  middle = Math.max(1, Math.min(40, middle || 11));
  const R = ballMm / 2;
  const rows = patternRows(middle).map(r => ({
    th: 0,
    beads: r.sizes.map(s => ({ c: 0, s })),
  }));
  state.model = { R, middle, rows, Rres: null };
  state.sel = null;
  state.layout = buildLayout(rows, R);
  state.tens = null;
  // при старте больше естественного размера — сразу естественная
  // укладка и равномерное раздувание (анимация лишь шлифует)
  naturalInflate(state.layout, rows, R, 400);
  rebuild3D();
  updateCam();
  draw2D();
  updateStat();
  animateRelax(600);
}

// анимация укладки при генерации: оплётка садится на сферу на глазах
// (кадр = 12 итераций решателя); правки и загрузка JSON — пакетно, без анимации
function animateRelax(totalIters) {
  relaxAnim = null;
  const solver = makeSolver(state.layout, state.model.rows, state.model.R);
  let done = 0;
  const frame = () => {
    if (relaxAnim !== frame) return; // отменена (новая генерация или правка)
    for (let k = 0; k < 12 && done < totalIters; k++, done++) solver.step();
    refreshBeadMatrices();
    if (done < totalIters) requestAnimationFrame(frame);
    else {
      solver.finish();
      relaxAnim = null;
      state.model.Rres = solver.Rv();
      computeTension();
      refreshBeadMatrices();
      updateCam(); draw2D(); updateStat();
    }
  };
  relaxAnim = frame;
  requestAnimationFrame(frame);
}
// ================= 3D =================
let renderer, scene, camera, meshes, beadList, selMarker, ballMesh, threadLines = null, rot = { x: 0.4, y: 0 }, drag = null;

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
  if (ballMesh) ballMesh.scale.setScalar(innerBall(m.rows));
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
      im.setColorAt(k, state.showTension && state.tens
        ? col.setStyle(tensColor(it.ri, it.j))
        : col.set(state.palette[it.b.c].c));
      beadList.push({ ri: it.ri, j: it.j, mesh: im, inst: k, v });
    });
    if (im.instanceColor) im.instanceColor.needsUpdate = true;
    scene.add(im); meshes.push(im);
  }
  rebuildThreadLines();
}

// связи нити между бисеринами (галочка «нить»): по одному отрезку на
// связь; позиции обновляются на каждом кадре укладки вместе с бисеринами
function rebuildThreadLines() {
  if (threadLines) {
    scene.remove(threadLines);
    threadLines.geometry.dispose();
    threadLines.material.dispose();
    threadLines = null;
  }
  const lk = state.layout;
  if (!state.showThread || !lk || !lk.links.length) return;
  const g = new THREE.BufferGeometry();
  g.setAttribute('position', new THREE.BufferAttribute(new Float32Array(lk.links.length * 6), 3));
  threadLines = new THREE.LineSegments(g,
    new THREE.LineBasicMaterial({ color: 0x181818, transparent: true, opacity: 0.6 }));
  updateThreadLines();
  scene.add(threadLines);
}

function updateThreadLines() {
  if (!threadLines || !state.layout) return;
  const attr = threadLines.geometry.attributes.position;
  state.layout.links.forEach(([a, b], i) => {
    attr.setXYZ(i * 2, a.p[0], a.p[1], a.p[2]);
    attr.setXYZ(i * 2 + 1, b.p[0], b.p[1], b.p[2]);
  });
  attr.needsUpdate = true;
}

// обновить матрицы инстансов из текущих позиций модели (без пересборки)
function refreshBeadMatrices() {
  const m = state.model;
  if (!m || !meshes) return;
  const dummy = new THREE.Object3D(), up = new THREE.Vector3(0, 1, 0);
  for (const rec of beadList) {
    const b = m.rows[rec.ri].beads[rec.j];
    const { east, v } = beadPos(m, rec.ri, rec.j);
    rec.v = v;
    dummy.position.copy(v);
    dummy.quaternion.setFromUnitVectors(up, east);
    dummy.scale.set(BEAD[b.s].h / 2, BEAD[b.s].w / 2, BEAD[b.s].h / 2);
    dummy.updateMatrix();
    rec.mesh.setMatrixAt(rec.inst, dummy.matrix);
  }
  meshes.forEach(im => { im.instanceMatrix.needsUpdate = true; });
  updateThreadLines();
  if (ballMesh) ballMesh.scale.setScalar(innerBall(m.rows));
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
  // масштаб — по самому длинному ряду (число бисерин теперь плавает)
  const maxC = m.rows.reduce((a, r) => Math.max(a, rowC(r)), 0) || BEAD[0].w;
  const pxmm = Math.min((W - 70) / maxC, 20 / BEAD[0].w);
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
  });
  // связи нити — под бисеринами (галочка «нить»): видно, какая с какой
  if (state.showThread && state.layout) {
    ctx.strokeStyle = 'rgba(25,25,25,0.45)';
    ctx.lineWidth = 1;
    ctx.beginPath();
    for (const [a, b] of state.layout.links) {
      const ra = d2.rows[a.row], rb = d2.rows[b.row];
      if (!ra || !rb) continue;
      ctx.moveTo(ra.xs[a.idx], ra.y);
      ctx.lineTo(rb.xs[b.idx], rb.y);
    }
    ctx.stroke();
  }
  m.rows.forEach((row, ri) => {
    const y = d2.rows[ri].y;
    row.beads.forEach((b, j) => {
      const x = d2.rows[ri].xs[j];
      const r = BEAD[b.s].w * pxmm * 0.48;
      ctx.beginPath(); ctx.arc(x, y, r, 0, Math.PI * 2);
      ctx.fillStyle = state.showTension && state.tens ? tensColor(ri, j) : state.palette[b.c].c;
      ctx.fill();
      ctx.lineWidth = 1;
      ctx.strokeStyle = b.s ? '#888' : '#000';
      if (b.s) ctx.setLineDash([2, 2]);
      ctx.stroke(); ctx.setLineDash([]);
      if (state.sel && state.sel.row === ri && state.sel.idx === j) {
        ctx.beginPath(); ctx.arc(x, y, r + 2.5, 0, Math.PI * 2);
        ctx.strokeStyle = '#00c000'; ctx.lineWidth = 2.5; ctx.stroke();
      }
      if (r >= 5) {
        ctx.fillStyle = state.showTension && state.tens ? '#fff' : '#000';
        ctx.font = `${Math.max(7, Math.floor(r))}px sans-serif`;
        ctx.textAlign = 'center'; ctx.textBaseline = 'middle';
        ctx.fillText(state.palette[b.c].b, x, y);
      }
    });
    ctx.fillStyle = '#aaa'; ctx.font = '9px sans-serif'; ctx.textAlign = 'right';
    ctx.fillText(ri + 1, d2.rows[ri].x0 - 6, y);
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
  let small = 0, maxY = -1e9, minY = 1e9, maxXY = 0;
  m.rows.forEach(r => r.beads.forEach(b => {
    if (b.s) small++;
    maxY = Math.max(maxY, b.p[1]); minY = Math.min(minY, b.p[1]);
    maxXY = Math.max(maxXY, Math.hypot(b.p[0], b.p[2]));
  }));
  let gap = '';
  if (state.tens) {
    let g = 0;
    state.tens.forEach(r => r.forEach(v => { if (v > g) g = v; }));
    gap = `, макс. зазор нити ${g.toFixed(2)} мм`;
  }
  document.getElementById('stat').textContent =
    `рядов: ${m.rows.length}, бисерин: ${beadCount(m)} (15/0 — ${small}), ` +
    `модель ⌀ ${(2 * maxXY).toFixed(1)} × ${(maxY - minY).toFixed(1)} мм, ` +
    `вписанная бусина ⌀ ${(2 * innerBall(m.rows)).toFixed(1)}${gap}`;
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
      // восстановить физическую укладку — мгновенно, пакетом
      relaxAnim = null;
      state.layout = buildLayout(state.model.rows, d.R);
      state.model.Rres = relax(state.layout, state.model.rows, d.R, 500);
      computeTension();
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
document.getElementById('tension').onchange = e => {
  state.showTension = e.target.checked;
  if (state.model) { rebuild3D(); draw2D(); }
};
document.getElementById('threadShow').onchange = e => {
  state.showThread = e.target.checked;
  if (state.model) { rebuild3D(); draw2D(); }
};
// смена размера бусины — без перегенерации: схема и раскраска те же,
// укладка пересчитывается под новую сферу обжатия
document.getElementById('ballMm').onchange = e => {
  const m = state.model;
  if (!m) return;
  m.R = Math.max(5, parseFloat(e.target.value) || 14.5) / 2;
  reRelax(300);
  rebuild3D(); updateCam(); draw2D(); updateStat();
};

init3D();
renderPalette();
generate(14.5, 11);
animate();
