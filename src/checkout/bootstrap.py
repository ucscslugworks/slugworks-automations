"""Prepare the backing Google Spreadsheet and seed dummy data.

Run once:  ./checkout bootstrap   (add --force to overwrite existing data)

Operates on the spreadsheet_id in common/checkout.json. Ensures the
Items / Keys / Consumables / Checkouts tabs exist (renaming a lone default
"Sheet1" into Items if present, creating any missing tabs), writes headers, and
fills in dummy makerspace inventory so someone can see the shape and edit it.
Existing tabs that already hold data are left alone unless --force is passed.
"""

import uuid

from src.checkout.store import (
    CHECKOUT_HEADERS,
    CONSUMABLE_HEADERS,
    ITEM_HEADERS,
    KEY_HEADERS,
    SheetStore,
)


def iid():
    return "itm-" + uuid.uuid4().hex[:8]


def kid():
    return "key-" + uuid.uuid4().hex[:8]


def cid():
    return "cns-" + uuid.uuid4().hex[:8]


# (name, category, description, icon, location, total_qty, checkout_days)
DUMMY_ITEMS = [
    ("Cordless Drill", "Power Tools", "18V brushless drill w/ 2 batteries", "🔩", "Tool Wall A", 6, 3),
    ("Impact Driver", "Power Tools", "1/4in hex impact driver", "🪛", "Tool Wall A", 4, 3),
    ("Jigsaw", "Power Tools", "Orbital jigsaw, variable speed", "🪚", "Tool Wall A", 3, 3),
    ("Random Orbital Sander", "Power Tools", "5in hook-and-loop sander", "🌀", "Tool Wall B", 3, 3),
    ("Heat Gun", "Power Tools", "Dual-temp heat gun", "🔥", "Tool Wall B", 2, 3),
    ("Soldering Iron Kit", "Electronics", "Temp-controlled iron + tips + stand", "🔌", "Electronics Bench", 8, 7),
    ("Digital Multimeter", "Electronics", "Auto-ranging DMM with leads", "🎚️", "Electronics Bench", 6, 7),
    ("Oscilloscope", "Electronics", "2-channel 100MHz benchtop scope", "📟", "Electronics Bench", 2, 7),
    ("Bench Power Supply", "Electronics", "0-30V 0-5A adjustable PSU", "⚡", "Electronics Bench", 3, 7),
    ("Digital Calipers", "Hand Tools", "6in stainless digital calipers", "📏", "Metrology Drawer", 10, 7),
    ("Socket Set", "Hand Tools", "Metric + SAE 40pc socket set", "🧰", "Tool Wall C", 4, 5),
    ("Claw Hammer", "Hand Tools", "16oz fiberglass claw hammer", "🔨", "Tool Wall C", 8, 5),
    ("Safety Glasses", "Safety Gear", "ANSI Z87 clear safety glasses", "🥽", "PPE Cabinet", 30, 30),
    ("Respirator", "Safety Gear", "Half-face respirator w/ P100", "😷", "PPE Cabinet", 12, 14),
    ("Cut-Resistant Gloves", "Safety Gear", "Level A4 cut gloves (pair)", "🧤", "PPE Cabinet", 20, 14),
    ("Glue Gun", "3D Printing & Craft", "Full-size hot glue gun", "🔫", "Craft Bench", 5, 7),
    ("Calibration Dial Indicator", "3D Printing & Craft", "0.01mm dial indicator", "🎯", "3D Print Area", 4, 7),
    ("Filament Dry Box", "3D Printing & Craft", "Heated filament dehumidifier", "📦", "3D Print Area", 3, 7),
]

# (name, category, description, icon, location, unit, stock_qty, low_threshold)
DUMMY_CONSUMABLES = [
    ("Nitrile Gloves (M)", "PPE & Supplies", "Disposable nitrile gloves, medium", "🧤", "PPE Cabinet", "pair", 240, 40),
    ("Nitrile Gloves (L)", "PPE & Supplies", "Disposable nitrile gloves, large", "🧤", "PPE Cabinet", "pair", 200, 40),
    ("Shop Towels", "PPE & Supplies", "Blue disposable shop towels", "🧻", "Cleanup Station", "roll", 30, 6),
    ("Foam Earplugs", "PPE & Supplies", "Disposable foam earplugs", "🎧", "PPE Cabinet", "pair", 150, 30),
    ("Dust Masks", "PPE & Supplies", "Disposable N95 dust masks", "😷", "PPE Cabinet", "each", 80, 20),
    ("Isopropyl Wipes", "Cleaning & Adhesives", "70% IPA cleaning wipes", "🧼", "Electronics Bench", "each", 300, 50),
    ("Sandpaper 120-grit", "Materials", "9x11 sandpaper sheets, 120 grit", "🟫", "Finishing Area", "sheet", 120, 25),
    ("Hot Glue Sticks", "Cleaning & Adhesives", "Full-size hot glue sticks", "🖍️", "Craft Bench", "each", 200, 40),
    ("Zip Ties (8in)", "Materials", "8 inch nylon zip ties", "🔗", "Hardware Bins", "each", 500, 100),
    ("Masking Tape", "Cleaning & Adhesives", "1in blue painter's/masking tape", "🩹", "Finishing Area", "roll", 24, 5),
    ("Solder (0.8mm)", "Electronics", "Leaded 60/40 rosin-core solder", "🪙", "Electronics Bench", "meter", 400, 75),
    ("Nitrile Gloves (S)", "PPE & Supplies", "Disposable nitrile gloves, small", "🧤", "PPE Cabinet", "pair", 30, 40),
]

# (room, description, icon, total_qty, checkout_days)
DUMMY_KEYS = [
    ("Laser Cutter Room", "Access key for the laser cutting room", "🗝️", 3, 1),
    ("Wood Shop", "Wood shop main door key", "🚪", 4, 1),
    ("Metal Shop", "Metal shop main door key", "🔧", 4, 1),
    ("Electronics Lab", "Electronics lab door key", "💡", 5, 1),
    ("Spray Booth", "Ventilated spray/paint booth key", "🎨", 2, 1),
    ("Materials Storage", "Bulk materials storage closet", "🏬", 3, 1),
]


def seed_values():
    items = [ITEM_HEADERS]
    for (name, cat, desc, icon, loc, qty, days) in DUMMY_ITEMS:
        items.append([iid(), name, cat, desc, icon, loc, qty, qty, days])

    keys = [KEY_HEADERS]
    for (room, desc, icon, qty, days) in DUMMY_KEYS:
        keys.append([kid(), room, desc, icon, qty, qty, days])

    consumables = [CONSUMABLE_HEADERS]
    for (name, cat, desc, icon, loc, unit, stock, low) in DUMMY_CONSUMABLES:
        consumables.append([cid(), name, cat, desc, icon, loc, unit, stock, low])

    checkouts = [CHECKOUT_HEADERS]
    return items, keys, consumables, checkouts


def _current_tabs(store, sid):
    meta = store.sheets.get(spreadsheetId=sid, fields="sheets.properties").execute()
    return {s["properties"]["title"]: s["properties"]["sheetId"] for s in meta["sheets"]}


def ensure_tabs(store, sid):
    """Make sure Items/Keys/Consumables/Checkouts tabs exist. Rename a lone
    default tab into Items rather than leaving an empty 'Sheet1' behind."""
    tabs = store.tabs
    wanted = [tabs["items"], tabs["keys"], tabs["consumables"], tabs["checkouts"]]
    existing = _current_tabs(store, sid)
    reqs = []

    if not any(w in existing for w in wanted) and len(existing) == 1:
        only_title, only_gid = next(iter(existing.items()))
        reqs.append({
            "updateSheetProperties": {
                "properties": {"sheetId": only_gid, "title": tabs["items"]},
                "fields": "title",
            }
        })
        existing = {tabs["items"]: only_gid}

    for title in wanted:
        if title not in existing:
            reqs.append({"addSheet": {"properties": {"title": title}}})
    if reqs:
        store.sheets.batchUpdate(spreadsheetId=sid, body={"requests": reqs}).execute()


def format_headers(store, sid):
    tabs = store.tabs
    gids = _current_tabs(store, sid)
    reqs = []
    for title in (tabs["items"], tabs["keys"], tabs["consumables"], tabs["checkouts"]):
        gid = gids.get(title)
        if gid is None:
            continue
        reqs.append({
            "repeatCell": {
                "range": {"sheetId": gid, "startRowIndex": 0, "endRowIndex": 1},
                "cell": {"userEnteredFormat": {"textFormat": {"bold": True}}},
                "fields": "userEnteredFormat.textFormat.bold",
            }
        })
        reqs.append({
            "updateSheetProperties": {
                "properties": {"sheetId": gid, "gridProperties": {"frozenRowCount": 1}},
                "fields": "gridProperties.frozenRowCount",
            }
        })
    if reqs:
        store.sheets.batchUpdate(spreadsheetId=sid, body={"requests": reqs}).execute()


def run(cfg, force=False):
    store = SheetStore(cfg, allow_auth=True)
    sid = store.spreadsheet_id
    if not sid:
        print("common/checkout.json has no spreadsheet_id. Set it first.")
        return 2

    ensure_tabs(store, sid)
    tabs = store.tabs
    items, keys, consumables, checkouts = seed_values()

    _, existing_items = store._read_tab(tabs["items"])
    _, existing_keys = store._read_tab(tabs["keys"])
    _, existing_cons = store._read_tab(tabs["consumables"])
    if (existing_items or existing_keys or existing_cons) and not force:
        print(
            "Items/Keys/Consumables already contain data — leaving them untouched.\n"
            "Pass --force to overwrite with fresh dummy data."
        )
        format_headers(store, sid)
        return 0

    for tab, values in (
        (tabs["items"], items),
        (tabs["keys"], keys),
        (tabs["consumables"], consumables),
        (tabs["checkouts"], checkouts),
    ):
        store.sheets.values().clear(spreadsheetId=sid, range=tab).execute()
        store.sheets.values().update(
            spreadsheetId=sid,
            range=f"{tab}!A1",
            valueInputOption="RAW",
            body={"values": values},
        ).execute()

    format_headers(store, sid)

    print("Seeded dummy data into the spreadsheet.")
    print(f"  spreadsheet_id: {sid}")
    print(f"  tabs:           {tabs['items']}, {tabs['keys']}, {tabs['consumables']}, {tabs['checkouts']}")
    print(f"  items:          {len(DUMMY_ITEMS)}")
    print(f"  room keys:      {len(DUMMY_KEYS)}")
    print(f"  consumables:    {len(DUMMY_CONSUMABLES)}")
    return 0
