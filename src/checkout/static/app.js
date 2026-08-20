// Makerspace Depot — catalog, cart, checkout, returns.
// Who you are comes from the session started in session.js; nothing here asks
// for a name or CruzID again. The cart lives in localStorage so a reload does
// not lose it, and is emptied at sign-out so the next person starts clean.

const state = {
  items: [],
  keys: [],
  consumables: [],
  categories: [],
  activeCat: "",
  view: "catalog",
  search: "",
  cart: loadCart(), // {ref_id: {kind, ref_id, name, icon, qty, available, days}}
};

function loadCart() {
  try { return JSON.parse(localStorage.getItem("md_cart") || "{}"); }
  catch { return {}; }
}
function saveCart() { localStorage.setItem("md_cart", JSON.stringify(state.cart)); }
function clearCart() {
  state.cart = {};
  localStorage.removeItem("md_cart");
  localStorage.removeItem("md_cart_owner");
}

const $ = (sel) => document.querySelector(sel);
const el = (tag, cls, html) => {
  const n = document.createElement(tag);
  if (cls) n.className = cls;
  if (html != null) n.innerHTML = html;
  return n;
};
const esc = (s) => String(s ?? "").replace(/[&<>"]/g, (c) => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;" }[c]));

function toast(msg, kind = "") {
  const t = $("#toast");
  t.textContent = msg;
  t.className = "toast " + kind;
  setTimeout(() => (t.className = "toast hidden"), 2600);
}

// ---- load catalog ----
async function loadCatalog() {
  try {
    const d = await api("/api/catalog");
    state.items = d.items;
    state.keys = d.keys;
    state.consumables = d.consumables || [];
    state.categories = d.categories;
    renderCats();
    render();
  } catch (e) {
    $("#itemGrid").innerHTML = `<div class="notice">⚠️ ${esc(e.message)}</div>`;
  }
}

function renderCats() {
  const ul = $("#catList");
  ul.innerHTML = "";
  const mk = (label, cat) => {
    const li = el("li", cat === state.activeCat ? "active" : "", esc(label));
    li.dataset.cat = cat;
    li.onclick = () => { state.activeCat = cat; renderCats(); render(); };
    ul.appendChild(li);
  };
  mk("All", "");
  state.categories.forEach((c) => mk(c, c));
}

function availBadge(a, total) {
  if (a <= 0) return `<span class="badge out">Checked out</span>`;
  if (a <= Math.max(1, Math.floor(total * 0.25))) return `<span class="badge low">${a} left</span>`;
  return `<span class="badge in">${a} available</span>`;
}

function matchesSearch(x, fields) {
  if (!state.search) return true;
  const q = state.search.toLowerCase();
  return fields.some((f) => String(x[f] || "").toLowerCase().includes(q));
}

function render() {
  // toggle views
  ["catalog", "consumables", "keys", "checkouts"].forEach((v) => {
    $("#view-" + v).classList.toggle("hidden", state.view !== v);
  });
  const usesCats = state.view === "catalog" || state.view === "consumables";
  $("#sidebar").style.display = usesCats ? "" : "none";
  document.querySelectorAll(".tab").forEach((t) =>
    t.classList.toggle("active", t.dataset.view === state.view)
  );

  if (state.view === "catalog") renderItems();
  else if (state.view === "consumables") renderConsumables();
  else if (state.view === "keys") renderKeys();
  updateCartCount();
}

function consumableBadge(x) {
  if (x.stock_qty <= 0) return `<span class="badge out">Out of stock</span>`;
  if (x.low) return `<span class="badge low">Low: ${x.stock_qty} ${esc(x.unit || "")}</span>`;
  return `<span class="badge in">${x.stock_qty} ${esc(x.unit || "")} in stock</span>`;
}

function card(x, kind) {
  const id = kind === "item" ? x.item_id : kind === "key" ? x.key_id : x.consumable_id;
  const name = kind === "key" ? x.room : x.name;
  const stock = kind === "consumable" ? x.stock_qty : x.available_qty;
  const inCart = state.cart[id]?.qty || 0;
  const maxAdd = stock - inCart;
  const defaultIcon = kind === "item" ? "📦" : kind === "key" ? "🗝️" : "🧤";

  const catLine = kind === "key" ? "Room Key"
    : kind === "consumable" ? `${esc(x.category || "Supplies")} · single-use`
    : esc(x.category || "");
  const meta = kind === "consumable"
    ? `${consumableBadge(x)}<span class="days-tag">per ${esc(x.unit || "each")}</span>`
    : `${availBadge(x.available_qty, x.total_qty)}<span class="days-tag">${x.checkout_days}-day</span>`;
  const btnLabel = kind === "consumable" ? "Take 🧤" : "Add to cart 🛒";
  const fullLabel = kind === "consumable" ? "In cart" : "In cart";

  const c = el("div", "card");
  c.innerHTML = `
    <div class="thumb">${esc(x.icon || defaultIcon)}</div>
    <div class="cat">${catLine}</div>
    <div class="name">${esc(name)}</div>
    <div class="desc">${esc(x.description || "")}</div>
    <div class="loc">${x.location ? "📍 " + esc(x.location) : ""}</div>
    <div class="meta">${meta}</div>
    <div class="addwrap">
      <input class="qtysel" type="number" min="1" value="1" max="${Math.max(1, maxAdd)}" ${maxAdd <= 0 ? "disabled" : ""}/>
      <button class="addbtn" ${maxAdd <= 0 ? "disabled" : ""}>${maxAdd <= 0 ? (stock <= 0 ? "Unavailable" : fullLabel) : btnLabel}</button>
    </div>`;
  const qtyInput = c.querySelector(".qtysel");
  c.querySelector(".addbtn").onclick = () => {
    const q = Math.max(1, Math.min(parseInt(qtyInput.value) || 1, maxAdd));
    addToCart({
      kind, ref_id: id, name, icon: x.icon, qty: q, available: stock,
      days: kind === "consumable" ? null : x.checkout_days,
      unit: x.unit || null,
    });
  };
  return c;
}

function renderItems() {
  const grid = $("#itemGrid");
  grid.innerHTML = "";
  const list = state.items.filter(
    (i) => (!state.activeCat || i.category === state.activeCat) &&
      matchesSearch(i, ["name", "description", "category", "location"])
  );
  if (!list.length) { grid.innerHTML = `<div class="notice">No tools match your search.</div>`; return; }
  list.forEach((i) => grid.appendChild(card(i, "item")));
}

function renderConsumables() {
  const grid = $("#consumableGrid");
  grid.innerHTML = "";
  const list = state.consumables.filter(
    (x) => (!state.activeCat || x.category === state.activeCat) &&
      matchesSearch(x, ["name", "description", "category", "location"])
  );
  if (!list.length) { grid.innerHTML = `<div class="notice">No supplies match your filter.</div>`; return; }
  list.forEach((x) => grid.appendChild(card(x, "consumable")));
}

function renderKeys() {
  const grid = $("#keyGrid");
  grid.innerHTML = "";
  const list = state.keys.filter((k) => matchesSearch(k, ["room", "description"]));
  if (!list.length) { grid.innerHTML = `<div class="notice">No room keys match your search.</div>`; return; }
  list.forEach((k) => grid.appendChild(card(k, "key")));
}

// ---- cart ----
function addToCart(entry) {
  const cur = state.cart[entry.ref_id];
  const qty = Math.min((cur?.qty || 0) + entry.qty, entry.available);
  state.cart[entry.ref_id] = { ...entry, qty };
  saveCart();
  toast(`Added ${entry.qty} × ${entry.name}`, "ok");
  render();
  renderCart();
}
function removeFromCart(id) { delete state.cart[id]; saveCart(); render(); renderCart(); }
function cartLines() { return Object.values(state.cart); }
function updateCartCount() {
  const n = cartLines().reduce((s, l) => s + l.qty, 0);
  $("#cartCount").textContent = n;
}

function renderCart() {
  const body = $("#cartBody");
  const lines = cartLines();
  body.innerHTML = "";
  if (!lines.length) { body.innerHTML = `<div class="cart-empty">Your cart is empty.<br/>Add tools or keys to check them out.</div>`; }
  lines.forEach((l) => {
    const row = el("div", "cart-item");
    row.innerHTML = `
      <div class="ci-icon">${esc(l.icon || "📦")}</div>
      <div class="ci-main">
        <div class="n">${esc(l.name)}</div>
        <div class="d">${
          l.kind === "consumable"
            ? `Supply · single-use${l.unit ? " · per " + esc(l.unit) : ""}`
            : (l.kind === "key" ? "Room key" : "Tool") + ` · ${l.days}-day · ${l.available} avail`
        }</div>
      </div>
      <input class="ci-qty" type="number" min="1" max="${l.available}" value="${l.qty}"/>
      <button class="rm" title="remove">🗑️</button>`;
    row.querySelector(".ci-qty").onchange = (e) => {
      let q = Math.max(1, Math.min(parseInt(e.target.value) || 1, l.available));
      state.cart[l.ref_id].qty = q; e.target.value = q; saveCart(); updateCartCount();
    };
    row.querySelector(".rm").onclick = () => removeFromCart(l.ref_id);
    body.appendChild(row);
  });
  updateCartCount();
  validateCheckout();
}

function openCart() { $("#cartScrim").classList.remove("hidden"); $("#cartDrawer").classList.remove("hidden"); renderCart(); }
function closeCart() { $("#cartScrim").classList.add("hidden"); $("#cartDrawer").classList.add("hidden"); }

function validateCheckout() {
  const ready = cartLines().length > 0 && $("#ack").checked && !!MDSession.user;
  $("#doCheckout").disabled = !ready;
}

async function doCheckout() {
  const msg = $("#cartMsg");
  msg.className = "cart-msg";
  // No name or CruzID here on purpose: the server takes them from the session.
  const payload = {
    acknowledged: $("#ack").checked,
    lines: cartLines().map((l) => ({ kind: l.kind, ref_id: l.ref_id, qty: l.qty })),
  };
  $("#doCheckout").disabled = true;
  try {
    const d = await api("/api/checkout", { method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify(payload) });
    const failed = d.results.filter((r) => !r.ok);
    const ok = d.results.filter((r) => r.ok);
    if (ok.length) {
      // clear the successfully checked-out lines
      ok.forEach((r) => delete state.cart[r.ref_id]);
      saveCart();
    }
    if (failed.length) {
      msg.className = "cart-msg err";
      msg.textContent = `${ok.length} checked out. Issues: ` + failed.map((f) => f.error).join("; ");
    } else {
      msg.className = "cart-msg ok";
      msg.textContent = `✅ Checked out ${ok.length} line(s). Due dates set. You're responsible for their return.`;
      $("#ack").checked = false;
    }
    await loadCatalog();
    renderCart();
    toast("Checkout complete", "ok");
  } catch (e) {
    msg.className = "cart-msg err";
    msg.textContent = e.message;
  }
  validateCheckout();
}

// ---- my checkouts ----
async function loadCheckouts() {
  const list = $("#checkoutList");
  // Non-staff always get their own; the server ignores the parameter for them.
  const staff = MDSession.user && MDSession.user.is_staff;
  const cruzid = staff ? $("#lookupCruzid").value.trim() : "";
  const activeOnly = $("#activeOnly").checked;
  const params = new URLSearchParams();
  if (cruzid) params.set("cruzid", cruzid);
  if (activeOnly) params.set("active", "1");
  list.innerHTML = `<div class="muted">Loading…</div>`;
  try {
    const d = await api("/api/checkouts?" + params.toString());
    if (!d.checkouts.length) { list.innerHTML = `<div class="notice">No checkouts found${cruzid ? " for " + esc(cruzid) : ""}.</div>`; return; }
    list.innerHTML = "";
    d.checkouts
      .sort((a, b) => (a.status === "out" ? -1 : 1) - (b.status === "out" ? -1 : 1))
      .forEach((c) => list.appendChild(checkoutRow(c)));
  } catch (e) { list.innerHTML = `<div class="notice">⚠️ ${esc(e.message)}</div>`; }
}

function checkoutRow(c) {
  const taken = c.status === "taken";
  const cls = (c.status === "returned" || taken) ? "returned" : c.overdue ? "overdue" : "";
  const row = el("div", "co-row " + cls);
  const pill = taken
    ? `<span class="pill returned">Taken (single-use)</span>`
    : c.status === "returned"
    ? `<span class="pill returned">Returned</span>`
    : c.overdue ? `<span class="pill overdue">⚠ Overdue</span>` : `<span class="pill out">Checked out</span>`;
  const icon = c.kind === "key" ? "🗝️" : c.kind === "consumable" ? "🧤" : "🧰";
  const timing = taken
    ? `taken ${esc(c.checkout_time)}`
    : `out ${esc(c.checkout_time)} · due ${esc(c.due_time)}${c.return_time ? " · returned " + esc(c.return_time) : ""}`;
  row.innerHTML = `
    <div class="co-icon">${icon}</div>
    <div class="co-main">
      <div class="t">${esc(c.ref_name)} ${c.qty > 1 ? "×" + c.qty : ""} ${pill}</div>
      <div class="s">${esc(c.person_name)} (${esc(c.cruzid)}) · ${timing}</div>
    </div>`;
  if (c.status === "out") {
    const btn = el("button", "returnbtn", "Return");
    btn.onclick = async () => {
      btn.disabled = true; btn.textContent = "…";
      try {
        await api("/api/return", { method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify({ checkout_id: c.checkout_id }) });
        toast("Returned " + c.ref_name, "ok");
        await loadCatalog(); loadCheckouts();
      } catch (e) { toast(e.message, "err"); btn.disabled = false; btn.textContent = "Return"; }
    };
    row.appendChild(btn);
  }
  return row;
}

// ---- session ----
// The cart belongs to the person who is signed in, so it goes away with them.
function onSignIn(user) {
  // A cart that outlived its session (a crash, a killed browser) belongs to
  // whoever filled it, not to whoever swipes in next.
  if (localStorage.getItem("md_cart_owner") !== user.cruzid) clearCart();
  localStorage.setItem("md_cart_owner", user.cruzid);
  $("#cartWho").textContent = `${user.name} (${user.cruzid})`;
  $("#myCheckoutsWho").textContent = user.is_staff ? "you (staff)" : "you";
  loadCatalog();
  if (state.view === "checkouts") loadCheckouts();
  validateCheckout();
}

function onSignOut() {
  clearCart();
  closeCart();
  $("#ack").checked = false;
  $("#cartMsg").textContent = "";
  $("#checkoutList").innerHTML = "";
  state.view = "catalog";
  render();
  renderCart();
}

// ---- wire up ----
function init() {
  document.querySelectorAll(".tab").forEach((t) => {
    t.onclick = () => { state.view = t.dataset.view; render(); if (state.view === "checkouts") loadCheckouts(); };
  });
  $("#openCart").onclick = openCart;
  $("#closeCart").onclick = closeCart;
  $("#cartScrim").onclick = closeCart;
  $("#doCheckout").onclick = doCheckout;
  ["input", "change"].forEach((ev) => $("#ack").addEventListener(ev, validateCheckout));
  $("#search").addEventListener("input", (e) => { state.search = e.target.value; if (state.view !== "checkouts") render(); });
  $("#lookupBtn").onclick = loadCheckouts;
  $("#activeOnly").onchange = loadCheckouts;
  $("#lookupCruzid").addEventListener("keydown", (e) => { if (e.key === "Enter") loadCheckouts(); });

  // Left over from when the cart asked for a name; nothing reads them now.
  localStorage.removeItem("md_name");
  localStorage.removeItem("md_cruzid");

  // Nothing loads until someone has swiped in; the API would refuse anyway.
  MDSession.on("signin", onSignIn);
  MDSession.on("signout", onSignOut);
  if (MDSession.user) onSignIn(MDSession.user);
}
document.addEventListener("DOMContentLoaded", init);
