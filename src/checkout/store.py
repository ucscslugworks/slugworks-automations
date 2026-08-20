"""Google Sheets data store for the makerspace checkout system.

Auth reuses src.checkoff.sheets.get_service (the repo's shared OAuth client and
token-refresh flow); this module adds the checkout business logic plus a
thread-safe, cached, retrying wrapper around the Sheets API.

The backing spreadsheet has four tabs (created by bootstrap.py):

  Items        one row per tool/equipment type in the catalog
  Keys         one row per room key
  Consumables  single-use supplies (gloves, towels…) — taken, never returned
  Checkouts    log of every checkout/take; items & keys flip to "returned"

Quantities live on the catalog rows (available_qty / stock_qty) so the catalog
shows availability without scanning the whole log.
"""

import datetime
import socket
import ssl
import threading
import time
import uuid

from googleapiclient.errors import HttpError

from src.checkoff import sheets as gsheets

# Transient network/connection errors worth retrying with a fresh connection.
# The big one is ssl.SSLError "RECORD_LAYER_FAILURE", which httplib2 throws when
# the same (non-thread-safe) connection is used from two threads at once — e.g.
# the admin page fetching /api/catalog and /api/checkouts together.
TRANSIENT_ERRORS = (
    ssl.SSLError,
    socket.timeout,
    ConnectionError,
    BrokenPipeError,
    OSError,
)

# Sheets API HTTP statuses worth retrying: rate limit + transient server errors.
RETRYABLE_STATUS = {429, 500, 502, 503, 504}

# How long a tab read is reused before re-fetching. Google's read quota is
# 60 reads/min/user and each page load touches several tabs — caching a few
# seconds keeps bursts (and multiple viewers) well under quota. Writes bust the
# cache immediately, so app-driven changes always show at once; only direct
# edits to the sheet take up to this long to appear.
READ_CACHE_TTL = 6.0

# Column order for each tab. Written by bootstrap.py and relied on here.
ITEM_HEADERS = [
    "item_id",
    "name",
    "category",
    "description",
    "icon",
    "location",
    "total_qty",
    "available_qty",
    "checkout_days",
]
KEY_HEADERS = [
    "key_id",
    "room",
    "description",
    "icon",
    "total_qty",
    "available_qty",
    "checkout_days",
]
CONSUMABLE_HEADERS = [
    "consumable_id",
    "name",
    "category",
    "description",
    "icon",
    "location",
    "unit",           # "pair", "roll", "sheet", "each"…
    "stock_qty",
    "low_threshold",  # flag for reorder when stock_qty <= this
]
CHECKOUT_HEADERS = [
    "checkout_id",
    "kind",          # "item", "key", or "consumable"
    "ref_id",        # item_id / key_id / consumable_id
    "ref_name",      # denormalized for easy display
    "person_name",
    "cruzid",
    "qty",
    "checkout_time",
    "due_time",
    "return_time",
    "status",        # "out" / "returned" (items & keys) or "taken" (consumables)
]

TIME_FMT = "%Y-%m-%d %H:%M:%S"


def to_int(value, default=0):
    """Best-effort int from a spreadsheet cell. Blank or non-numeric text
    (someone typed 'a few' in a qty column) falls back to `default` instead of
    raising — the sheet is hand-editable, so it must never 500 on us."""
    if value is None:
        return default
    s = str(value).strip()
    if not s:
        return default
    try:
        return int(s)
    except ValueError:
        try:
            return int(float(s))
        except ValueError:
            return default


def _now():
    return datetime.datetime.now()


def fmt_time(dt):
    return dt.strftime(TIME_FMT)


def parse_time(s):
    if not s:
        return None
    try:
        return datetime.datetime.strptime(s, TIME_FMT)
    except ValueError:
        return None


class SheetStore:
    def __init__(self, cfg, allow_auth=False):
        """`cfg` is a src.checkout.config.Config. `allow_auth=True` permits the
        interactive copy-paste OAuth flow (for CLI/bootstrap); the web server
        passes False so a dead token fails fast instead of hanging."""
        self.cfg = cfg
        self.allow_auth = allow_auth
        self.spreadsheet_id = cfg.spreadsheet_id
        self.tabs = cfg.tabs
        self.default_days = cfg.default_checkout_days
        self._svc = None
        # googleapiclient/httplib2 are NOT thread-safe: one connection must not
        # be shared across concurrent requests. Serialize all API calls.
        self._lock = threading.Lock()
        # short-lived read cache: tab -> (monotonic_time, raw_values)
        self._cache = {}
        self._cache_lock = threading.Lock()

    # ---- auth / low-level ------------------------------------------------

    @property
    def sheets(self):
        if self._svc is None:
            # Reuse the repo's shared auth (token refresh, paste flow, etc.).
            service = gsheets.get_service(self.cfg, allow_auth=self.allow_auth)
            self._svc = service.spreadsheets()
        return self._svc

    def _call(self, build_and_execute, tries=4):
        """Run a Sheets API call under a lock (so concurrent web requests never
        share the non-thread-safe HTTP connection) and retry transient failures.

        `build_and_execute` takes the spreadsheets() service and must build AND
        .execute() the request, so a retry uses a brand-new request/connection.
        """
        last = None
        for attempt in range(tries):
            try:
                with self._lock:
                    return build_and_execute(self.sheets)
            except HttpError as e:
                last = e
                status = getattr(e.resp, "status", None)
                if status is None or int(status) not in RETRYABLE_STATUS:
                    raise
                if attempt < tries - 1:
                    time.sleep(0.8 * (2 ** attempt))
            except TRANSIENT_ERRORS as e:
                last = e
                with self._lock:
                    self._svc = None  # drop the bad connection; rebuild next try
                if attempt < tries - 1:
                    time.sleep(0.4 * (attempt + 1))
        raise last

    def _invalidate_cache(self):
        with self._cache_lock:
            self._cache.clear()

    def _tab_values(self, tab):
        """Raw sheet values for a tab, served from a short-lived cache to stay
        under the read quota. Callers build their own dicts, so the cached list
        is never mutated by them."""
        now = time.monotonic()
        with self._cache_lock:
            hit = self._cache.get(tab)
            if hit and now - hit[0] < READ_CACHE_TTL:
                return hit[1]
        resp = self._call(
            lambda s: s.values()
            .get(spreadsheetId=self.spreadsheet_id, range=tab)
            .execute()
        )
        values = resp.get("values", [])
        with self._cache_lock:
            self._cache[tab] = (time.monotonic(), values)
        return values

    def _read_tab(self, tab):
        """Return (headers, list-of-dict-rows) for a whole tab. Fresh dicts are
        built each call so callers may safely mutate them."""
        values = self._tab_values(tab)
        if not values:
            return [], []
        headers = values[0]
        rows = []
        for raw in values[1:]:
            padded = list(raw) + [""] * (len(headers) - len(raw))
            rows.append(dict(zip(headers, padded)))
        return headers, rows

    def _row_number_for(self, tab, headers, id_field, id_value):
        """Find the 1-based spreadsheet row for a record (header is row 1).
        Uses the cached tab values (id is always column A) — no extra read."""
        values = self._tab_values(tab)
        for idx, row in enumerate(values):
            if idx == 0:
                continue  # header
            if (row[0] if row else "") == id_value:
                return idx + 1
        return None

    def _update_row(self, tab, headers, row_number, record):
        row = [record.get(h, "") for h in headers]
        rng = f"{tab}!A{row_number}"
        self._call(
            lambda s: s.values().update(
                spreadsheetId=self.spreadsheet_id,
                range=rng,
                valueInputOption="RAW",
                body={"values": [row]},
            ).execute()
        )
        self._invalidate_cache()

    def _append_row(self, tab, headers, record):
        row = [record.get(h, "") for h in headers]
        self._call(
            lambda s: s.values().append(
                spreadsheetId=self.spreadsheet_id,
                range=f"{tab}!A1",
                valueInputOption="RAW",
                insertDataOption="INSERT_ROWS",
                body={"values": [row]},
            ).execute()
        )
        self._invalidate_cache()

    # ---- catalog reads ---------------------------------------------------

    def get_items(self):
        _, rows = self._read_tab(self.tabs["items"])
        rows = [r for r in rows if r.get("item_id")]
        for r in rows:
            r["total_qty"] = to_int(r.get("total_qty"))
            r["available_qty"] = to_int(r.get("available_qty"))
            r["checkout_days"] = to_int(r.get("checkout_days"), self.default_days)
        return rows

    def get_keys(self):
        _, rows = self._read_tab(self.tabs["keys"])
        rows = [r for r in rows if r.get("key_id")]
        for r in rows:
            r["total_qty"] = to_int(r.get("total_qty"))
            r["available_qty"] = to_int(r.get("available_qty"))
            r["checkout_days"] = to_int(r.get("checkout_days"), self.default_days)
        return rows

    def get_consumables(self):
        _, rows = self._read_tab(self.tabs["consumables"])
        rows = [r for r in rows if r.get("consumable_id")]
        for r in rows:
            r["stock_qty"] = to_int(r.get("stock_qty"))
            r["low_threshold"] = to_int(r.get("low_threshold"))
            r["low"] = r["stock_qty"] <= r["low_threshold"]
        return rows

    def get_categories(self):
        cats = {r["category"] for r in self.get_items() if r.get("category")}
        cats |= {r["category"] for r in self.get_consumables() if r.get("category")}
        return sorted(cats)

    def get_checkouts(self, active_only=False, cruzid=None):
        _, rows = self._read_tab(self.tabs["checkouts"])
        now = _now()
        out = []
        for r in rows:
            if not r.get("checkout_id"):
                continue
            r["qty"] = to_int(r.get("qty"))
            due = parse_time(r.get("due_time"))
            r["overdue"] = bool(
                r.get("status") == "out" and due is not None and now > due
            )
            if active_only and r.get("status") != "out":
                continue
            if cruzid and r.get("cruzid", "").lower() != cruzid.lower():
                continue
            out.append(r)
        return out

    # ---- checkout / return ----------------------------------------------

    def _catalog_meta(self, kind):
        if kind == "item":
            return self.tabs["items"], ITEM_HEADERS, "item_id", "name"
        elif kind == "key":
            return self.tabs["keys"], KEY_HEADERS, "key_id", "room"
        raise ValueError(f"unknown kind {kind!r}")

    def checkout(self, kind, ref_id, qty, person_name, cruzid):
        """Check out `qty` of an item or key. Returns the new checkout record.

        Read-modify-write against the Sheet; decrements available_qty and
        appends a Checkouts row with a due date.
        """
        qty = int(qty)
        if qty < 1:
            raise ValueError("Quantity must be at least 1.")
        tab, headers, id_field, name_field = self._catalog_meta(kind)
        _, rows = self._read_tab(tab)
        record = next((r for r in rows if r.get(id_field) == ref_id), None)
        if record is None:
            raise LookupError(f"No {kind} with id {ref_id}.")

        available = to_int(record.get("available_qty"))
        if qty > available:
            raise ValueError(
                f"Only {available} of '{record.get(name_field)}' available."
            )

        days = to_int(record.get("checkout_days"), self.default_days)
        record["available_qty"] = available - qty
        row_number = self._row_number_for(tab, headers, id_field, ref_id)
        self._update_row(tab, headers, row_number, record)

        now = _now()
        checkout = {
            "checkout_id": uuid.uuid4().hex[:12],
            "kind": kind,
            "ref_id": ref_id,
            "ref_name": record.get(name_field, ""),
            "person_name": person_name,
            "cruzid": cruzid,
            "qty": qty,
            "checkout_time": fmt_time(now),
            "due_time": fmt_time(now + datetime.timedelta(days=days)),
            "return_time": "",
            "status": "out",
        }
        self._append_row(self.tabs["checkouts"], CHECKOUT_HEADERS, checkout)
        return checkout

    def take_consumable(self, ref_id, qty, person_name, cruzid):
        """Take `qty` of a single-use item. Permanently decrements stock_qty and
        logs a "taken" row (no due date, no return)."""
        qty = int(qty)
        if qty < 1:
            raise ValueError("Quantity must be at least 1.")
        tab, headers = self.tabs["consumables"], CONSUMABLE_HEADERS
        _, rows = self._read_tab(tab)
        record = next((r for r in rows if r.get("consumable_id") == ref_id), None)
        if record is None:
            raise LookupError(f"No consumable with id {ref_id}.")

        stock = to_int(record.get("stock_qty"))
        if qty > stock:
            raise ValueError(f"Only {stock} of '{record.get('name')}' in stock.")

        record["stock_qty"] = stock - qty
        row_number = self._row_number_for(tab, headers, "consumable_id", ref_id)
        self._update_row(tab, headers, row_number, record)

        now = _now()
        taken = {
            "checkout_id": uuid.uuid4().hex[:12],
            "kind": "consumable",
            "ref_id": ref_id,
            "ref_name": record.get("name", ""),
            "person_name": person_name,
            "cruzid": cruzid,
            "qty": qty,
            "checkout_time": fmt_time(now),
            "due_time": "",
            "return_time": "",
            "status": "taken",
        }
        self._append_row(self.tabs["checkouts"], CHECKOUT_HEADERS, taken)
        return taken

    def return_checkout(self, checkout_id, owner_cruzid=None):
        """Mark a checkout returned and restore available_qty.

        `owner_cruzid` limits the return to that person's own checkouts, which
        is how the web app keeps one student from returning another's tools.
        """
        _, rows = self._read_tab(self.tabs["checkouts"])
        record = next((r for r in rows if r.get("checkout_id") == checkout_id), None)
        if record is None:
            raise LookupError(f"No checkout {checkout_id}.")
        if owner_cruzid and record.get("cruzid", "").lower() != owner_cruzid.lower():
            raise ValueError("That checkout is not yours. Ask staff to return it.")
        if record.get("kind") == "consumable":
            raise ValueError("Single-use consumables cannot be returned.")
        if record.get("status") == "returned":
            raise ValueError("This checkout was already returned.")

        record["qty"] = to_int(record.get("qty"))
        record["return_time"] = fmt_time(_now())
        record["status"] = "returned"
        row_number = self._row_number_for(
            self.tabs["checkouts"], CHECKOUT_HEADERS, "checkout_id", checkout_id
        )
        self._update_row(
            self.tabs["checkouts"], CHECKOUT_HEADERS, row_number, record
        )

        # restore availability on the catalog row
        kind = record.get("kind")
        tab, headers, id_field, _ = self._catalog_meta(kind)
        _, crows = self._read_tab(tab)
        cat = next((r for r in crows if r.get(id_field) == record.get("ref_id")), None)
        if cat is not None:
            cat["available_qty"] = to_int(cat.get("available_qty")) + record["qty"]
            cat["total_qty"] = to_int(cat.get("total_qty"))
            cnum = self._row_number_for(tab, headers, id_field, record.get("ref_id"))
            self._update_row(tab, headers, cnum, cat)
        return record

    # ---- admin writes ----------------------------------------------------

    def upsert_item(self, record):
        """Create or update an item. Generates an id if absent."""
        tab, headers = self.tabs["items"], ITEM_HEADERS
        if not record.get("item_id"):
            record["item_id"] = "itm-" + uuid.uuid4().hex[:8]
            record.setdefault("available_qty", record.get("total_qty", 0))
            self._append_row(tab, headers, record)
        else:
            num = self._row_number_for(tab, headers, "item_id", record["item_id"])
            if num is None:
                self._append_row(tab, headers, record)
            else:
                self._update_row(tab, headers, num, record)
        return record

    def upsert_key(self, record):
        tab, headers = self.tabs["keys"], KEY_HEADERS
        if not record.get("key_id"):
            record["key_id"] = "key-" + uuid.uuid4().hex[:8]
            record.setdefault("available_qty", record.get("total_qty", 0))
            self._append_row(tab, headers, record)
        else:
            num = self._row_number_for(tab, headers, "key_id", record["key_id"])
            if num is None:
                self._append_row(tab, headers, record)
            else:
                self._update_row(tab, headers, num, record)
        return record

    def upsert_consumable(self, record):
        tab, headers = self.tabs["consumables"], CONSUMABLE_HEADERS
        if not record.get("consumable_id"):
            record["consumable_id"] = "cns-" + uuid.uuid4().hex[:8]
            self._append_row(tab, headers, record)
        else:
            num = self._row_number_for(
                tab, headers, "consumable_id", record["consumable_id"]
            )
            if num is None:
                self._append_row(tab, headers, record)
            else:
                self._update_row(tab, headers, num, record)
        return record
