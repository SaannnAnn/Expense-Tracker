const $ = (sel) => document.querySelector(sel);
const money = new Intl.NumberFormat("en-IN", { style: "currency", currency: "INR" });
const fmt = (s) => money.format(Number(s));
const todayISO = () => {
  const d = new Date();
  return new Date(d.getTime() - d.getTimezoneOffset() * 60000).toISOString().slice(0, 10);
};

const form = $("#expense-form");
const filters = $("#filters");
let editingId = null;

async function api(path, options = {}) {
  const res = await fetch(path, {
    headers: { "Content-Type": "application/json" },
    ...options,
  });
  if (res.status === 204) return null;
  const data = await res.json().catch(() => ({}));
  if (!res.ok) throw Object.assign(new Error(data.error || "Something went wrong."), { fields: data.fields || {} });
  return data;
}

/* ---------- form ---------- */
function clearErrors() {
  document.querySelectorAll(".err[data-for]").forEach((e) => (e.textContent = ""));
  form.querySelectorAll(".invalid").forEach((e) => e.classList.remove("invalid"));
  $("#form-msg").textContent = "";
}

function showErrors(err) {
  for (const [field, msg] of Object.entries(err.fields || {})) {
    const slot = document.querySelector(`.err[data-for="${field}"]`);
    if (slot) slot.textContent = msg;
    if (form.elements[field]) form.elements[field].classList.add("invalid");
  }
  $("#form-msg").textContent = err.message;
}

function resetForm() {
  editingId = null;
  form.reset();
  form.elements.date.max = todayISO(); // no future dates
  form.elements.date.min = "2000-01-01"; // matches the server's lower limit
  form.elements.date.value = todayISO();
  $("#form-title").textContent = "Add expense";
  $("#save-btn").textContent = "Add expense";
  $("#cancel-btn").hidden = true;
  clearErrors();
}

function startEdit(exp) {
  editingId = exp.id;
  for (const k of ["title", "amount", "category", "date", "note"]) form.elements[k].value = exp[k];
  $("#form-title").textContent = "Edit expense";
  $("#save-btn").textContent = "Save changes";
  $("#cancel-btn").hidden = false;
  clearErrors();
  form.scrollIntoView({ behavior: "smooth", block: "center" });
  form.elements.title.focus();
}

form.addEventListener("submit", async (e) => {
  e.preventDefault();
  clearErrors();
  const body = Object.fromEntries(new FormData(form));
  const saveBtn = $("#save-btn");
  saveBtn.disabled = true; // prevents duplicate rows from a double click
  try {
    if (editingId) await api(`/api/expenses/${editingId}`, { method: "PUT", body: JSON.stringify(body) });
    else await api("/api/expenses", { method: "POST", body: JSON.stringify(body) });
    resetForm();
    await refresh();
  } catch (err) {
    showErrors(err);
  } finally {
    saveBtn.disabled = false;
  }
});
$("#cancel-btn").addEventListener("click", resetForm);

/* ---------- list ---------- */
function currentQuery() {
  const p = new URLSearchParams();
  for (const [k, v] of new FormData(filters)) if (String(v).trim()) p.set(k, String(v).trim());
  return p.toString();
}

function cell(text, cls) {
  const td = document.createElement("td");
  if (cls) td.className = cls;
  td.textContent = text; // textContent, never innerHTML: user text is untrusted
  return td;
}

async function loadList() {
  const msg = $("#list-msg");
  msg.textContent = "";
  let items;
  try {
    items = await api("/api/expenses?" + currentQuery());
  } catch (err) {
    msg.textContent = Object.values(err.fields)[0] || err.message;
    items = [];
  }
  const tbody = $("#rows");
  tbody.replaceChildren();
  for (const exp of items) {
    const tr = document.createElement("tr");
    tr.append(cell(exp.date), cell(exp.title, "title"), cell(exp.category), cell(fmt(exp.amount), "num"), cell(exp.note, "note"));
    const act = document.createElement("td");
    const box = document.createElement("div");
    box.className = "act";
    const edit = Object.assign(document.createElement("button"), { textContent: "Edit", className: "small secondary", type: "button" });
    const del = Object.assign(document.createElement("button"), { textContent: "Delete", className: "small danger", type: "button" });
    edit.onclick = () => startEdit(exp);
    del.onclick = async () => {
      if (!confirm(`Delete "${exp.title}"?`)) return;
      try { await api(`/api/expenses/${exp.id}`, { method: "DELETE" }); } catch (e) { msg.textContent = e.message; }
      if (editingId === exp.id) resetForm();
      refresh();
    };
    box.append(edit, del);
    act.append(box);
    tr.append(act);
    tbody.append(tr);
  }
  const filtered = currentQuery() !== "";
  const empty = $("#empty");
  empty.hidden = items.length > 0;
  empty.textContent = filtered ? "No expenses match these filters." : "No expenses yet. Add your first one above.";
  const sum = items.reduce((s, e) => s + Math.round(Number(e.amount) * 100), 0) / 100;
  $("#list-total").textContent = items.length ? `${items.length} shown, ${fmt(sum)} total` : "";
}

/* ---------- summary ---------- */
const now = new Date();
const curY = now.getFullYear();
const curM = now.getMonth() + 1;
const MONTHS = [...Array(12)].map((_, i) => new Date(2000, i, 1).toLocaleString("en-IN", { month: "long" }));
let sumY = curY;
let sumM = curM; // 0 means the whole year
const monthSel = $("#sum-month");
const yearSel = $("#sum-year");

function renderPeriodControls(years) {
  yearSel.replaceChildren(...years.map((y) => new Option(y, y)));
  yearSel.value = sumY;
  monthSel.replaceChildren(
    new Option("Whole year", 0),
    ...MONTHS.map((name, i) => {
      const o = new Option(name, i + 1);
      o.disabled = sumY === curY && i + 1 > curM; // no future months
      return o;
    })
  );
  monthSel.value = sumM;
  const atEnd = sumM === 0 ? sumY >= curY : sumY > curY || (sumY === curY && sumM >= curM);
  $("#next-period").disabled = atEnd;
  $("#this-month").disabled = sumY === curY && sumM === curM;
}

async function loadSummary() {
  const qs = sumM ? `month=${sumY}-${String(sumM).padStart(2, "0")}` : `year=${sumY}`;
  const [s, years] = await Promise.all([api("/api/summary?" + qs), api("/api/years")]);
  renderPeriodControls([...new Set([...years.filter((y) => y <= curY), sumY])].sort((a, b) => b - a));
  $("#summary-title").textContent = sumM ? `${MONTHS[sumM - 1]} ${sumY}` : String(sumY);
  $("#summary-total").textContent = fmt(s.total);
  const box = $("#summary-breakdown");
  box.replaceChildren();
  if (!s.by_category.length) {
    const p = document.createElement("p");
    p.className = "empty";
    p.textContent = sumM ? "Nothing spent in this month." : "Nothing spent in this year.";
    box.append(p);
    return;
  }
  for (const c of s.by_category) {
    const row = document.createElement("div");
    row.className = "bar-row";
    const name = document.createElement("span");
    name.textContent = c.category;
    const bar = document.createElement("div");
    bar.className = "bar";
    const fill = document.createElement("span");
    fill.style.width = c.percent + "%";
    bar.append(fill);
    const amt = document.createElement("span");
    amt.className = "amt";
    amt.textContent = `${fmt(c.total)} (${c.percent}%)`;
    row.append(name, bar, amt);
    box.append(row);
  }
}

function shiftPeriod(step) {
  if (sumM === 0) sumY += step;
  else {
    sumM += step;
    if (sumM < 1) { sumM = 12; sumY--; }
    if (sumM > 12) { sumM = 1; sumY++; }
  }
  loadSummary();
}
$("#prev-period").addEventListener("click", () => shiftPeriod(-1));
$("#next-period").addEventListener("click", () => shiftPeriod(1));
$("#this-month").addEventListener("click", () => { sumY = curY; sumM = curM; loadSummary(); });
monthSel.addEventListener("change", () => { sumM = Number(monthSel.value); loadSummary(); });
yearSel.addEventListener("change", () => {
  sumY = Number(yearSel.value);
  if (sumY === curY && sumM > curM) sumM = curM;
  loadSummary();
});

const refresh = () => Promise.all([loadList(), loadSummary()]);

/* ---------- filters ---------- */
let timer;
filters.addEventListener("input", () => { clearTimeout(timer); timer = setTimeout(loadList, 250); });
$("#clear-filters").addEventListener("click", () => { filters.reset(); loadList(); });

/* ---------- init ---------- */
(async function init() {
  const cats = await api("/api/categories");
  form.elements.category.append(new Option("Select a category", "")); // placeholder: user must choose
  for (const sel of [form.elements.category, filters.elements.category])
    for (const c of cats) sel.append(new Option(c, c));
  resetForm();
  refresh();
})();
