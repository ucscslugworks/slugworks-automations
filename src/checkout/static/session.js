// Who is at the station. Loaded before app.js / admin.js on every page.
//
// One person signs in, does what they came for, and walks away; the next
// person must sign in again. The page enforces that by watching for real
// interaction and putting the sign-in screen back after the idle window --
// but the server enforces it too (see session.py), so a page left open with
// its timer sabotaged still cannot check anything out.

const MDSession = {
  user: null,                            // {cruzid, name, is_staff, via} or null
  timeout: window.MD_TIMEOUT || 30,      // idle seconds, from the server config
  swipeEnabled: false,                   // is the Canvas roster cache built?
  requireStaff: false,                   // set by admin.js: bounce non-staff
  _handlers: { signin: [], signout: [] },
  on(event, fn) { this._handlers[event].push(fn); },
  _fire(event, arg) { this._handlers[event].forEach((fn) => fn(arg)); },
};
window.MDSession = MDSession;

// Shared by app.js and admin.js. A 401 means the idle window closed under us,
// so put the sign-in screen back instead of showing a confusing error.
async function api(url, opts) {
  const res = await fetch(url, opts);
  let data = {};
  try { data = await res.json(); } catch {}
  if (res.status === 401 && data.need_login) forgetUser(data.error);
  if (!res.ok) throw new Error(data.error || `Request failed (${res.status})`);
  return data;
}
window.api = api;

const S = (sel) => document.querySelector(sel);

// ---- activity ----
// Only deliberate interaction counts. Adding to the cart never touches the
// server, so without this the timer would expire mid-shop.
let lastActivity = Date.now();
let lastBeat = 0;
let beatPending = false;

function noteActivity() {
  lastActivity = Date.now();
  beatPending = true;
}

function idleSeconds() { return (Date.now() - lastActivity) / 1000; }

// ---- rendering who is signed in ----
function paintUser() {
  const u = MDSession.user;
  S("#whoami").classList.toggle("hidden", !u);
  S("#adminLink").classList.toggle("hidden", !(u && u.is_staff));
  document.querySelectorAll(".staff-only").forEach((n) =>
    n.classList.toggle("hidden", !(u && u.is_staff))
  );
  if (u) {
    S("#whoamiName").textContent = u.name;
    S("#whoamiId").textContent = u.cruzid;
  }
}

function paintTimer() {
  const left = Math.max(0, Math.ceil(MDSession.timeout - idleSeconds()));
  const pill = S("#whoamiTimer");
  pill.textContent = left + "s";
  pill.classList.toggle("warn", left <= 10);
}

// ---- the sign-in screen ----
function showSignin(message) {
  const box = S("#signin");
  box.classList.remove("hidden");
  S("#signinNameField").classList.toggle("hidden", MDSession.swipeEnabled);
  S("#signinInput").value = "";
  S("#signinName").value = "";
  const msg = S("#signinMsg");
  msg.className = "signin-msg" + (message ? " err" : "");
  msg.textContent = message || "";
  S("#signinInput").focus();
}

function hideSignin() {
  S("#signin").classList.add("hidden");
  S("#signinMsg").textContent = "";
}

function setUser(user) {
  MDSession.user = user;
  paintUser();
  if (user) {
    // /admin is staff-only; signing in there as anyone else goes back to the
    // catalog rather than leaving a page whose every request will 403.
    if (MDSession.requireStaff && !user.is_staff) { location.href = "/"; return; }
    noteActivity();
    paintTimer();
    hideSignin();
    MDSession._fire("signin", user);
  }
}

/** Drop the local session and ask for a card again. */
function forgetUser(message) {
  if (!MDSession.user) return;
  MDSession.user = null;
  paintUser();
  MDSession._fire("signout");
  showSignin(message);
}

async function signIn() {
  const value = S("#signinInput").value.trim();
  const name = S("#signinName").value.trim();
  const msg = S("#signinMsg");
  if (!value) { S("#signinInput").focus(); return; }
  msg.className = "signin-msg info";
  msg.textContent = "Checking…";
  try {
    const d = await api("/api/login", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ swipe: value, name }),
    });
    setUser(d.user);
  } catch (e) {
    msg.className = "signin-msg err";
    msg.textContent = e.message;
    S("#signinInput").select();
  }
}

async function signOut() {
  try { await fetch("/api/logout", { method: "POST" }); } catch {}
  forgetUser("Signed out. Swipe to start a new session.");
}

// ---- keeping the two clocks together ----
async function heartbeat() {
  beatPending = false;
  lastBeat = Date.now();
  try { await api("/api/keepalive", { method: "POST" }); } catch {}
}

function tick() {
  if (!MDSession.user) return;
  if (idleSeconds() >= MDSession.timeout) {
    signOut();
    return;
  }
  paintTimer();
  // Tell the server someone is still here, but only when they actually did
  // something, and no more often than a third of the window.
  if (beatPending && (Date.now() - lastBeat) / 1000 > MDSession.timeout / 3) heartbeat();
}

/** Ask the server who it thinks is signed in (on load, and after a sleep). */
async function syncSession() {
  try {
    const d = await api("/api/session");
    MDSession.timeout = d.timeout_seconds || MDSession.timeout;
    MDSession.swipeEnabled = !!d.swipe_enabled;
    if (d.signed_in) {
      lastActivity = Date.now() - (MDSession.timeout - d.remaining) * 1000;
      setUser(d.user);
    } else {
      MDSession.user = null;
      paintUser();
      showSignin();
    }
  } catch {
    showSignin("Can't reach the checkout server.");
  }
}

function initSession() {
  ["pointerdown", "keydown", "input", "wheel", "touchstart", "mousemove"].forEach((ev) =>
    document.addEventListener(ev, noteActivity, { passive: true })
  );

  S("#signinBtn").onclick = signIn;
  S("#signOutBtn").onclick = signOut;
  // Card readers are keyboards: they type the number and press Enter.
  ["#signinInput", "#signinName"].forEach((sel) =>
    S(sel).addEventListener("keydown", (e) => {
      if (e.key === "Enter") { e.preventDefault(); signIn(); }
    })
  );
  // Keep the caret in the card box so a swipe lands there wherever they click.
  document.addEventListener("keydown", (e) => {
    if (S("#signin").classList.contains("hidden")) return;
    if (e.target === S("#signinInput") || e.target === S("#signinName")) return;
    S("#signinInput").focus();
  });
  // A laptop lid closed for a minute must not look like an active session.
  document.addEventListener("visibilitychange", () => {
    if (!document.hidden) syncSession();
  });

  // The gate is up in the markup, so put the caret in the card box right away
  // and let syncSession() take it down if someone is in fact still signed in.
  S("#signinInput").focus();
  setInterval(tick, 1000);
  syncSession();
}

document.addEventListener("DOMContentLoaded", initSession);
