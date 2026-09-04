// app.js — логика страницы: вкладки, запуск генераторов, загрузки, схемы.
"use strict";

const $ = (sel, root = document) => root.querySelector(sel);

async function api(url, body) {
  const opt = body === undefined ? {} : {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(body),
  };
  const res = await fetch(url, opt);
  return res.json();
}

function esc(s) {
  return String(s).replace(/[&<>"']/g, (c) => ({
    "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;",
  }[c]));
}

function escAttr(s) { return esc(s); }

function viewUrl(gen, name) {
  // name может быть путём с подпапкой — кодируем каждый сегмент
  return "/view/" + gen + "/" + name.split("/").map(encodeURIComponent).join("/");
}

function fmtSize(n) {
  if (n >= 1024 * 1024) return (n / 1024 / 1024).toFixed(1) + " МБ";
  if (n >= 1024) return Math.round(n / 1024) + " КБ";
  return n + " Б";
}

function fmtDate(ts) {
  return new Date(ts * 1000).toLocaleString("ru-RU");
}

// --- вкладки ---

document.querySelectorAll(".tab").forEach((btn) => {
  btn.addEventListener("click", () => {
    document.querySelectorAll(".tab").forEach((b) => b.classList.remove("active"));
    document.querySelectorAll(".panel").forEach((p) => p.classList.remove("active"));
    btn.classList.add("active");
    $("#" + btn.dataset.tab).classList.add("active");
  });
});

// --- состояние: пресеты, загрузки, схемы ---

async function refreshState() {
  const st = await api("/api/state");
  $('select[name="preset"]').innerHTML =
    '<option value="">— по умолчанию —</option>' +
    st.presets.map((p) => `<option>${esc(p)}</option>`).join("");
  $('select[name="image"]').innerHTML =
    '<option value="">— выберите загруженную —</option>' +
    st.uploads.map((u) => `<option>${esc(u.name)}</option>`).join("");
  renderUploads(st.uploads);
  renderSchemes(st.schemes);
}

function renderUploads(list) {
  const box = $("#uploads-list");
  if (!list.length) {
    box.innerHTML = '<p class="meta">Загруженных картинок нет.</p>';
    return;
  }
  box.innerHTML = list.map((u) =>
    `<div class="up">
       <span class="upname">${esc(u.name)}</span>
       <span class="meta">${fmtSize(u.size)} · ${fmtDate(u.mtime)}</span>
       <button class="del up-del" title="Удалить загрузку" data-name="${escAttr(u.name)}">✕</button>
     </div>`).join("");
}

function renderSchemes(list) {
  const tb = $("#schemes-table tbody");
  window.__schemes = list;
  $(".empty").classList.toggle("hidden", list.length > 0);
  list.sort((a, b) => b.mtime - a.mtime);
  tb.innerHTML = "";
  for (const s of list) {
    const tr = document.createElement("tr");
    const singleCell = s.single.length
      ? `<span class="lnk toggle-singles" data-gen="${escAttr(s.gen)}" data-name="${escAttr(s.name)}">${s.single.length} цв. ▾</span>`
      : "—";
    tr.innerHTML = `
      <td><a href="${viewUrl(s.gen, s.name)}" target="_blank" rel="noopener">${esc(s.name)}</a></td>
      <td>${esc(s.gen_label)}</td>
      <td>${singleCell}</td>
      <td>${fmtDate(s.mtime)}</td>
      <td>${fmtSize(s.size)}</td>
      <td><button class="del scheme-del" data-gen="${escAttr(s.gen)}" data-name="${escAttr(s.name)}">Удалить</button></td>`;
    tb.appendChild(tr);
  }
}

// --- запуск генераторов ---

function formParams(form) {
  const p = {};
  new FormData(form).forEach((v, k) => { p[k] = v; });
  form.querySelectorAll('input[type="checkbox"]').forEach((c) => {
    p[c.name] = c.checked;
  });
  return p;
}

async function runGen(gen, form) {
  const btn = form.querySelector(".run");
  const box = $("#run-result");
  btn.disabled = true;
  box.classList.remove("hidden", "ok", "err");
  box.textContent = "Работаю…";
  try {
    const r = await api("/api/run/" + gen, formParams(form));
    if (r.ok) {
      box.classList.add("ok");
      const links = (r.created || []).map((f) =>
        `<a href="${viewUrl(f.gen, f.name)}" target="_blank" rel="noopener">${esc(f.name)}</a>`);
      box.innerHTML = "<strong>Готово.</strong> Создано/обновлено: " +
        (links.join(" · ") || "—") +
        (r.stdout ? `<pre>${esc(r.stdout.trim())}</pre>` : "");
    } else {
      box.classList.add("err");
      const tail = (r.stderr || r.error || "").trim().split("\n");
      box.innerHTML = "<strong>Ошибка.</strong>" +
        `<pre>${esc(tail.slice(-30).join("\n"))}</pre>`;
    }
  } catch (e) {
    box.classList.add("err");
    box.textContent = "Сервер недоступен: " + e;
  } finally {
    btn.disabled = false;
    refreshState();
  }
}

["glitch", "belt", "img"].forEach((gen) => {
  $("#form-" + gen).addEventListener("submit", (ev) => {
    ev.preventDefault();
    runGen(gen, ev.target);
  });
});

// --- загрузка картинок ---

$("#img-upload-btn").addEventListener("click", async () => {
  const inp = $("#img-file");
  if (!inp.files.length) {
    alert("Сначала выберите файл картинки.");
    return;
  }
  const fd = new FormData();
  fd.append("file", inp.files[0]);
  const res = await fetch("/api/upload", { method: "POST", body: fd });
  const r = await res.json();
  if (r.ok) {
    inp.value = "";
    await refreshState();
    $('select[name="image"]').value = r.name;
  } else {
    alert(r.error || "Не удалось загрузить.");
  }
});

// --- удаления (делегирование) ---

document.addEventListener("click", async (ev) => {
  const up = ev.target.closest(".up-del");
  if (up) {
    if (!confirm(`Удалить загрузку «${up.dataset.name}»?`)) return;
    await api("/api/uploads/delete", { name: up.dataset.name });
    refreshState();
    return;
  }
  const del = ev.target.closest(".scheme-del");
  if (del) {
    if (!confirm(`Удалить «${del.dataset.name}» вместе с папкой одноцветных схем?`)) return;
    await api("/api/schemes/delete", { gen: del.dataset.gen, name: del.dataset.name });
    refreshState();
    return;
  }
  const tog = ev.target.closest(".toggle-singles");
  if (tog) {
    const row = tog.closest("tr");
    const next = row.nextElementSibling;
    if (next && next.classList.contains("single-row")) {
      next.remove();
      return;
    }
    const st = window.__schemes.find((s) =>
      s.name === tog.dataset.name && s.gen === tog.dataset.gen);
    if (!st) return;
    const tr = document.createElement("tr");
    tr.className = "single-row";
    tr.innerHTML = `<td colspan="6"><div class="singles">` +
      st.single.map((n) =>
        `<a href="${viewUrl(st.gen, st.folder + "/" + n)}" target="_blank" rel="noopener">${esc(n)}</a>`
      ).join("") + "</div></td>";
    row.after(tr);
  }
});

refreshState();
