// Inventory admin — add/edit tools & keys, view active checkouts.
// Staff only: /admin and every /api/admin/* route check that server-side, and
// signing in here as anyone else bounces back to the catalog (see session.js).

const $ = (s) => document.querySelector(s);
const esc = (s) => String(s ?? "").replace(/[&<>"]/g, (c) => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;" }[c]));

function toast(msg, kind = "") {
  const t = $("#toast");
  t.textContent = msg;
  t.className = "toast " + kind;
  setTimeout(() => (t.className = "toast hidden"), 2600);
}

function availClass(a, total) {
  if (a <= 0) return "out";
  if (a <= Math.max(1, Math.floor(total * 0.25))) return "low";
  return "in";
}

async function refresh() {
  const [cat, cos] = await Promise.all([api("/api/catalog"), api("/api/checkouts?active=1")]);
  renderItems(cat.items);
  renderKeys(cat.keys);
  renderConsumables(cat.consumables || []);
  renderCheckouts(cos.checkouts);
  const dl = $("#catOptions");
  dl.innerHTML = cat.categories.map((c) => `<option value="${esc(c)}">`).join("");
}

function renderItems(items) {
  $("#itemCount").textContent = `(${items.length})`;
  const tb = $("#itemTable tbody");
  tb.innerHTML = "";
  items.forEach((i) => {
    const tr = document.createElement("tr");
    tr.innerHTML = `
      <td>${esc(i.icon || "📦")}</td>
      <td>${esc(i.name)}</td>
      <td>${esc(i.category || "")}</td>
      <td>${esc(i.location || "")}</td>
      <td><span class="tinybadge ${availClass(i.available_qty, i.total_qty)}">${i.available_qty}/${i.total_qty}</span></td>
      <td>${i.checkout_days}</td>
      <td><button class="linkbtn">Edit</button></td>`;
    tr.querySelector("button").onclick = () => fillItemForm(i);
    tb.appendChild(tr);
  });
}

function renderKeys(keys) {
  $("#keyCount").textContent = `(${keys.length})`;
  const tb = $("#keyTable tbody");
  tb.innerHTML = "";
  keys.forEach((k) => {
    const tr = document.createElement("tr");
    tr.innerHTML = `
      <td>${esc(k.icon || "🗝️")}</td>
      <td>${esc(k.room)}</td>
      <td>${esc(k.description || "")}</td>
      <td><span class="tinybadge ${availClass(k.available_qty, k.total_qty)}">${k.available_qty}/${k.total_qty}</span></td>
      <td>${k.checkout_days}</td>
      <td><button class="linkbtn">Edit</button></td>`;
    tr.querySelector("button").onclick = () => fillKeyForm(k);
    tb.appendChild(tr);
  });
}

function renderConsumables(cons) {
  $("#consumableCount").textContent = `(${cons.length})`;
  const tb = $("#consumableTable tbody");
  tb.innerHTML = "";
  cons.forEach((x) => {
    const tr = document.createElement("tr");
    const low = x.stock_qty <= x.low_threshold;
    if (low) tr.className = "overdue";
    tr.innerHTML = `
      <td>${esc(x.icon || "🧤")}</td>
      <td>${esc(x.name)}</td>
      <td>${esc(x.category || "")}</td>
      <td>${esc(x.location || "")}</td>
      <td><span class="tinybadge ${low ? (x.stock_qty <= 0 ? "out" : "low") : "in"}">${x.stock_qty}</span></td>
      <td>${esc(x.unit || "")}</td>
      <td>${x.low_threshold}</td>
      <td><button class="linkbtn">Edit</button></td>`;
    tr.querySelector("button").onclick = () => fillConsumableForm(x);
    tb.appendChild(tr);
  });
}

function renderCheckouts(cos) {
  $("#coCount").textContent = `(${cos.length})`;
  const tb = $("#coTable tbody");
  tb.innerHTML = "";
  if (!cos.length) { tb.innerHTML = `<tr><td colspan="8" class="muted">Nothing is currently checked out.</td></tr>`; return; }
  cos.forEach((c) => {
    const tr = document.createElement("tr");
    if (c.overdue) tr.className = "overdue";
    const status = c.overdue ? `<span class="tinybadge out">Overdue</span>` : `<span class="tinybadge in">Out</span>`;
    tr.innerHTML = `
      <td>${c.kind === "key" ? "🗝️ " : "🧰 "}${esc(c.ref_name)}</td>
      <td>${esc(c.person_name)}</td>
      <td>${esc(c.cruzid)}</td>
      <td>${c.qty}</td>
      <td>${esc(c.checkout_time)}</td>
      <td>${esc(c.due_time)}</td>
      <td>${status}</td>
      <td><button class="linkbtn">Return</button></td>`;
    tr.querySelector("button").onclick = async (e) => {
      e.target.disabled = true;
      try {
        await api("/api/return", { method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify({ checkout_id: c.checkout_id }) });
        toast("Returned " + c.ref_name, "ok");
        refresh();
      } catch (err) { toast(err.message, "err"); e.target.disabled = false; }
    };
    tb.appendChild(tr);
  });
}

function fillItemForm(i) {
  const f = $("#itemForm");
  f.item_id.value = i.item_id;
  f.name.value = i.name;
  f.category.value = i.category || "";
  f.description.value = i.description || "";
  f.icon.value = i.icon || "";
  f.location.value = i.location || "";
  f.checkout_days.value = i.checkout_days;
  f.total_qty.value = i.total_qty;
  f.available_qty.value = i.available_qty;
  window.scrollTo({ top: 0, behavior: "smooth" });
}
function fillKeyForm(k) {
  const f = $("#keyForm");
  f.key_id.value = k.key_id;
  f.room.value = k.room;
  f.description.value = k.description || "";
  f.icon.value = k.icon || "";
  f.total_qty.value = k.total_qty;
  f.checkout_days.value = k.checkout_days;
  window.scrollTo({ top: 0, behavior: "smooth" });
}

function fillConsumableForm(x) {
  const f = $("#consumableForm");
  f.consumable_id.value = x.consumable_id;
  f.name.value = x.name;
  f.category.value = x.category || "";
  f.description.value = x.description || "";
  f.icon.value = x.icon || "";
  f.location.value = x.location || "";
  f.unit.value = x.unit || "";
  f.stock_qty.value = x.stock_qty;
  f.low_threshold.value = x.low_threshold;
  window.scrollTo({ top: 0, behavior: "smooth" });
}

function formToObj(form) {
  const o = {};
  new FormData(form).forEach((v, k) => (o[k] = v));
  return o;
}

function init() {
  $("#itemForm").onsubmit = async (e) => {
    e.preventDefault();
    try {
      await api("/api/admin/item", { method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify(formToObj(e.target)) });
      toast("Saved tool", "ok");
      e.target.reset(); e.target.item_id.value = "";
      refresh();
    } catch (err) { toast(err.message, "err"); }
  };
  $("#keyForm").onsubmit = async (e) => {
    e.preventDefault();
    try {
      await api("/api/admin/key", { method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify(formToObj(e.target)) });
      toast("Saved key", "ok");
      e.target.reset(); e.target.key_id.value = "";
      refresh();
    } catch (err) { toast(err.message, "err"); }
  };
  $("#consumableForm").onsubmit = async (e) => {
    e.preventDefault();
    try {
      await api("/api/admin/consumable", { method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify(formToObj(e.target)) });
      toast("Saved supply", "ok");
      e.target.reset(); e.target.consumable_id.value = "";
      refresh();
    } catch (err) { toast(err.message, "err"); }
  };
  $("#itemReset").onclick = () => { $("#itemForm").reset(); $("#itemForm").item_id.value = ""; };
  $("#keyReset").onclick = () => { $("#keyForm").reset(); $("#keyForm").key_id.value = ""; };
  $("#consumableReset").onclick = () => { $("#consumableForm").reset(); $("#consumableForm").consumable_id.value = ""; };

  MDSession.requireStaff = true;
  MDSession.on("signin", () => refresh().catch((e) => toast(e.message, "err")));
  MDSession.on("signout", () =>
    document.querySelectorAll("table tbody").forEach((b) => (b.innerHTML = ""))
  );
  if (MDSession.user) refresh().catch((e) => toast(e.message, "err"));
}
document.addEventListener("DOMContentLoaded", init);
