import sqlite3
from datetime import datetime, date

DB = "printq.db"


def get_conn():
    conn = sqlite3.connect(DB)
    conn.row_factory = sqlite3.Row
    return conn


def _run_migrations(c):
    """
    Safe migrations — adds missing columns to existing tables.
    Uses 'ALTER TABLE ADD COLUMN IF NOT EXISTS' via try/except since
    SQLite doesn't support IF NOT EXISTS on columns directly.
    """
    migrations = [
        # sales table
        ("ALTER TABLE sales ADD COLUMN created_at DATETIME DEFAULT CURRENT_TIMESTAMP",),
        ("ALTER TABLE sales ADD COLUMN payment_method TEXT DEFAULT 'Cash'",),
        # services table
        ("ALTER TABLE services ADD COLUMN is_promo INTEGER DEFAULT 0",),
        ("ALTER TABLE services ADD COLUMN category TEXT DEFAULT 'Other'",),
        # inventory table
        ("ALTER TABLE inventory ADD COLUMN unit_cost REAL DEFAULT 0",),
        ("ALTER TABLE inventory ADD COLUMN selling_price REAL DEFAULT 0",),
        ("ALTER TABLE inventory ADD COLUMN is_supply_item INTEGER DEFAULT 0",),
        ("ALTER TABLE inventory ADD COLUMN pieces_per_unit REAL DEFAULT 1",),
        ("ALTER TABLE inventory ADD COLUMN piece_label TEXT DEFAULT ''",),
        # orders table
        ("ALTER TABLE orders ADD COLUMN created_at DATETIME DEFAULT CURRENT_TIMESTAMP",),
        # app_settings table (create if missing)
        ("""CREATE TABLE IF NOT EXISTS app_settings (
            key   TEXT PRIMARY KEY,
            value TEXT NOT NULL
        )""",),
        # reject_types table
        ("ALTER TABLE reject_types ADD COLUMN default_qty REAL DEFAULT 1",),
        ("ALTER TABLE reject_types ADD COLUMN active INTEGER DEFAULT 1",),
        # rejects table
        ("ALTER TABLE rejects ADD COLUMN created_at DATETIME DEFAULT CURRENT_TIMESTAMP",),
        # sale_items table
        ("ALTER TABLE sale_items ADD COLUMN inventory_item_id INTEGER",),
    ]
    for (sql,) in migrations:
        try:
            c.execute(sql)
        except Exception:
            pass  # Column already exists or table doesn't exist yet — safe to skip


def init_db():
    conn = get_conn()
    c = conn.cursor()

    # ── Run migrations first (safe for existing databases) ────
    _run_migrations(c)
    conn.commit()

    # ── Student Print Orders (one queue number per upload) ────
    c.execute("""
        CREATE TABLE IF NOT EXISTS orders (
            id          INTEGER PRIMARY KEY AUTOINCREMENT,
            name        TEXT NOT NULL,
            notes       TEXT,
            status      TEXT DEFAULT 'waiting',
            created_at  DATETIME DEFAULT CURRENT_TIMESTAMP
        )
    """)

    # ── Files within an order (each can have its own settings) ─
    c.execute("""
        CREATE TABLE IF NOT EXISTS order_files (
            id          INTEGER PRIMARY KEY AUTOINCREMENT,
            order_id    INTEGER NOT NULL,
            filename    TEXT NOT NULL,
            color       TEXT NOT NULL,
            paper       TEXT NOT NULL,
            copies      INTEGER NOT NULL,
            status      TEXT DEFAULT 'waiting',
            FOREIGN KEY (order_id) REFERENCES orders (id)
        )
    """)

    # ── Legacy table kept for backward compatibility (unused going forward) ─
    c.execute("""
        CREATE TABLE IF NOT EXISTS jobs (
            id          INTEGER PRIMARY KEY AUTOINCREMENT,
            name        TEXT NOT NULL,
            filename    TEXT NOT NULL,
            color       TEXT NOT NULL,
            paper       TEXT NOT NULL,
            copies      INTEGER NOT NULL,
            notes       TEXT,
            status      TEXT DEFAULT 'waiting',
            created_at  DATETIME DEFAULT CURRENT_TIMESTAMP
        )
    """)

    # ── Services & Pricing (editable price list) ──────────────
    c.execute("""
        CREATE TABLE IF NOT EXISTS services (
            id          INTEGER PRIMARY KEY AUTOINCREMENT,
            name        TEXT NOT NULL UNIQUE,
            unit        TEXT NOT NULL,
            price       REAL NOT NULL,
            active      INTEGER DEFAULT 1,
            is_promo    INTEGER DEFAULT 0,
            category    TEXT DEFAULT 'Other'
        )
    """)

    # ── App Settings (key-value store for config) ──────────────
    c.execute("""
        CREATE TABLE IF NOT EXISTS app_settings (
            key         TEXT PRIMARY KEY,
            value       TEXT NOT NULL
        )
    """)

    # ── POS Sales (one row per transaction) ───────────────────
    c.execute("""
        CREATE TABLE IF NOT EXISTS sales (
            id              INTEGER PRIMARY KEY AUTOINCREMENT,
            subtotal        REAL NOT NULL,
            discount        REAL DEFAULT 0,
            total           REAL NOT NULL,
            cash_received   REAL NOT NULL,
            change_given    REAL NOT NULL,
            payment_method  TEXT DEFAULT 'Cash',
            created_at      DATETIME DEFAULT CURRENT_TIMESTAMP
        )
    """)

    # ── POS Sale Items (line items per transaction) ───────────
    c.execute("""
        CREATE TABLE IF NOT EXISTS sale_items (
            id          INTEGER PRIMARY KEY AUTOINCREMENT,
            sale_id     INTEGER NOT NULL,
            service_name TEXT NOT NULL,
            unit_price  REAL NOT NULL,
            quantity    REAL NOT NULL,
            line_total  REAL NOT NULL,
            inventory_item_id INTEGER,
            FOREIGN KEY (sale_id) REFERENCES sales (id),
            FOREIGN KEY (inventory_item_id) REFERENCES inventory (id)
        )
    """)

    # ── Inventory Items ────────────────────────────────────────
    c.execute("""
        CREATE TABLE IF NOT EXISTS inventory (
            id              INTEGER PRIMARY KEY AUTOINCREMENT,
            name            TEXT NOT NULL UNIQUE,
            unit            TEXT NOT NULL,
            beginning_stock REAL DEFAULT 0,
            stock_in        REAL DEFAULT 0,
            stock_out       REAL DEFAULT 0,
            low_stock_alert REAL DEFAULT 5,
            unit_cost       REAL DEFAULT 0,
            selling_price   REAL DEFAULT 0,
            is_supply_item  INTEGER DEFAULT 0,
            pieces_per_unit REAL DEFAULT 1,
            piece_label     TEXT DEFAULT '',
            updated_at      DATETIME DEFAULT CURRENT_TIMESTAMP
        )
    """)

    # ── Inventory Movement Log ─────────────────────────────────
    c.execute("""
        CREATE TABLE IF NOT EXISTS inventory_log (
            id          INTEGER PRIMARY KEY AUTOINCREMENT,
            item_id     INTEGER NOT NULL,
            type        TEXT NOT NULL,
            quantity    REAL NOT NULL,
            note        TEXT,
            created_at  DATETIME DEFAULT CURRENT_TIMESTAMP,
            FOREIGN KEY (item_id) REFERENCES inventory (id)
        )
    """)

    # ── Expenses ────────────────────────────────────────────────
    c.execute("""
        CREATE TABLE IF NOT EXISTS expenses (
            id          INTEGER PRIMARY KEY AUTOINCREMENT,
            category    TEXT NOT NULL,
            description TEXT,
            amount      REAL NOT NULL,
            expense_date DATE DEFAULT (date('now')),
            created_at  DATETIME DEFAULT CURRENT_TIMESTAMP
        )
    """)

    # ── Reject / Wastage Types (catalog) ──────────────────────
    c.execute("""
        CREATE TABLE IF NOT EXISTS reject_types (
            id              INTEGER PRIMARY KEY AUTOINCREMENT,
            name            TEXT NOT NULL UNIQUE,
            category        TEXT NOT NULL,    -- 'Printing Error' or 'Supply Wastage'
            inventory_item_id INTEGER,         -- linked inventory item to auto-deduct, nullable
            default_qty     REAL DEFAULT 1,    -- default quantity wasted per occurrence
            active          INTEGER DEFAULT 1,
            FOREIGN KEY (inventory_item_id) REFERENCES inventory (id)
        )
    """)

    # ── Reject / Wastage Log (actual occurrences) ─────────────
    c.execute("""
        CREATE TABLE IF NOT EXISTS rejects (
            id              INTEGER PRIMARY KEY AUTOINCREMENT,
            reject_type_id  INTEGER NOT NULL,
            quantity        REAL NOT NULL,
            estimated_cost  REAL NOT NULL DEFAULT 0,
            note            TEXT,
            created_at      DATETIME DEFAULT CURRENT_TIMESTAMP,
            FOREIGN KEY (reject_type_id) REFERENCES reject_types (id)
        )
    """)

    conn.commit()

    # ── Seed default services if empty ─────────────────────────
    c.execute("SELECT COUNT(*) FROM services")
    if c.fetchone()[0] == 0:
        # name, unit, price, is_promo, category
        defaults = [
            ("Piso Print B&W (Thesis/Research)",    "page",     1.0,  1, "Piso Print"),
            ("Piso Print Colored (Thesis/Research)", "page",     2.0,  1, "Piso Print"),
            ("Black & White Printing",               "page",     3.0,  0, "Printing"),
            ("Colored Printing",                     "page",     5.0,  0, "Printing"),
            ("Photo Printing",                       "page",     15.0, 0, "Printing"),
            ("Photocopy",                            "page",     2.0,  0, "Photocopy"),
            ("Scanning",                             "document", 10.0, 0, "Scanning"),
            ("Laminating",                           "sheet",    15.0, 0, "Laminating"),
            ("ID Picture",                           "package",  30.0, 0, "Other"),
            ("Typing Services",                      "page",     20.0, 0, "Other"),
            ("Binding",                              "package",  40.0, 0, "Other"),
        ]
        c.executemany(
            "INSERT INTO services (name, unit, price, is_promo, category) VALUES (?, ?, ?, ?, ?)",
            defaults
        )
        conn.commit()

    # ── Seed default inventory if empty ─────────────────────────
    c.execute("SELECT COUNT(*) FROM inventory")
    if c.fetchone()[0] == 0:
        # name, unit, beginning_stock, low_stock_alert, unit_cost, selling_price, is_supply_item, pieces_per_unit, piece_label
        items = [
            ("Bond Paper",       "ream",   0, 5,  220.0, 0,    0, 500, "sheet"),
            ("Photo Paper",      "pack",   0, 3,  180.0, 0,    0, 20,  "sheet"),
            ("Laminating Film",  "pack",   0, 3,  150.0, 0,    0, 100, "sheet"),
            ("Ink",              "bottle", 0, 2,  450.0, 0,    0, 60,  "ml"),
            ("Ballpen",          "pc",     0, 10, 8.0,   12.0, 1, 1,   "pc"),
            ("Folder",           "pc",     0, 10, 5.0,   10.0, 1, 1,   "pc"),
            ("Envelope",         "pc",     0, 10, 3.0,   8.0,  1, 1,   "pc"),
        ]
        c.executemany(
            """INSERT INTO inventory
               (name, unit, beginning_stock, low_stock_alert, unit_cost, selling_price, is_supply_item, pieces_per_unit, piece_label)
               VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)""",
            items
        )
        conn.commit()

    # ── Seed default app settings if empty ───────────────────────
    defaults = {
        "printer_bw":      "EPSON WF-C5890 Series (Black & White)",
        "printer_colored": "EPSON WF-C5890 Series (GENERAL)",
        "sumatra_path":    r"C:\Users\ByteComputer\AppData\Local\SumatraPDF\SumatraPDF.exe",
        "shop_name":       "RektaPrint",
    }
    for key, value in defaults.items():
        c.execute("INSERT OR IGNORE INTO app_settings (key, value) VALUES (?, ?)", (key, value))
    conn.commit()

    # ── Seed default reject types if empty ──────────────────────
    c.execute("SELECT COUNT(*) FROM reject_types")
    if c.fetchone()[0] == 0:
        # Look up inventory IDs to link wastage types to stock items
        c.execute("SELECT id, name FROM inventory")
        inv_map = {row["name"]: row["id"] for row in c.fetchall()}

        reject_defaults = [
            # name, category, linked inventory item name (or None), default qty (in piece_label units)
            ("Wrong Print",              "Printing Error",  "Bond Paper", 1),
            ("Paper Jam Damage",         "Printing Error",  "Bond Paper", 1),
            ("Ink Smudge",               "Printing Error",  "Bond Paper", 1),
            ("Misalignment",             "Printing Error",  "Bond Paper", 1),
            ("Customer Changed File",    "Printing Error",  "Bond Paper", 1),
            ("Power Interruption",       "Printing Error",  "Bond Paper", 1),
            ("Damaged Bond Paper",       "Supply Wastage",  "Bond Paper", 1),
            ("Damaged Photo Paper",      "Supply Wastage",  "Photo Paper", 1),
            ("Ruined Laminating Film",   "Supply Wastage",  "Laminating Film", 1),
            ("Ink Cleaning / Head Cleaning Consumption", "Supply Wastage", "Ink", 2),
        ]

        for name, category, inv_name, qty in reject_defaults:
            inv_id = inv_map.get(inv_name)
            c.execute("""
                INSERT INTO reject_types (name, category, inventory_item_id, default_qty)
                VALUES (?, ?, ?, ?)
            """, (name, category, inv_id, qty))
        conn.commit()

    conn.close()


# ════════════════════════════════════════════════════════════
# ORDERS / ORDER FILES (student print queue, multi-file aware)
# ════════════════════════════════════════════════════════════

def create_order(name, files, notes=""):
    """
    files: list of dicts like
        [{"filename": "...", "color": "B&W", "paper": "Short", "copies": 1}, ...]
    Returns the new order_id (this is the student's queue number).
    created_at stored in Philippine Standard Time (UTC+8).
    """
    from datetime import datetime, timezone, timedelta
    PST = timezone(timedelta(hours=8))
    now_pst = datetime.now(PST).strftime("%Y-%m-%d %H:%M:%S")

    conn = get_conn()
    c = conn.cursor()

    c.execute("""
        INSERT INTO orders (name, notes, created_at)
        VALUES (?, ?, ?)
    """, (name, notes, now_pst))
    order_id = c.lastrowid

    for f in files:
        c.execute("""
            INSERT INTO order_files (order_id, filename, color, paper, copies)
            VALUES (?, ?, ?, ?, ?)
        """, (order_id, f["filename"], f["color"], f["paper"], f["copies"]))

    conn.commit()
    conn.close()
    return order_id


def get_all_orders():
    """
    Returns orders with their files nested under "files", plus a computed
    "status" for the order as a whole:
      - waiting  : any file is still waiting/printing
      - failed   : at least one file failed (and none still waiting)
      - done     : all files are done
      - cancelled: all files are cancelled (or mix of cancelled/done)
    """
    conn = get_conn()
    c = conn.cursor()
    c.execute("SELECT * FROM orders ORDER BY created_at DESC")
    orders = [dict(row) for row in c.fetchall()]

    for order in orders:
        c.execute("SELECT * FROM order_files WHERE order_id = ? ORDER BY id", (order["id"],))
        files = [dict(row) for row in c.fetchall()]
        order["files"] = files

        statuses = {f["status"] for f in files}

        if not statuses:
            order["status"] = "waiting"
        elif "waiting" in statuses or "printing" in statuses:
            order["status"] = "waiting"
        elif "failed" in statuses:
            order["status"] = "failed"
        elif statuses <= {"done", "cancelled"}:
            if statuses == {"cancelled"}:
                order["status"] = "cancelled"
            else:
                order["status"] = "done"
        else:
            order["status"] = "done"

    conn.close()
    return orders


def get_order(order_id):
    conn = get_conn()
    c = conn.cursor()
    c.execute("SELECT * FROM orders WHERE id = ?", (order_id,))
    row = c.fetchone()
    if not row:
        conn.close()
        return None

    order = dict(row)
    c.execute("SELECT * FROM order_files WHERE order_id = ? ORDER BY id", (order_id,))
    order["files"] = [dict(r) for r in c.fetchall()]
    conn.close()
    return order


def get_order_file(file_id):
    conn = get_conn()
    c = conn.cursor()
    c.execute("SELECT * FROM order_files WHERE id = ?", (file_id,))
    row = c.fetchone()
    conn.close()
    return dict(row) if row else None


def update_file_status(file_id, status):
    conn = get_conn()
    c = conn.cursor()
    c.execute("UPDATE order_files SET status = ? WHERE id = ?", (status, file_id))
    conn.commit()
    conn.close()


def update_order_status_if_complete(order_id):
    """Optional helper: not required since get_all_orders computes status live."""
    pass


# ════════════════════════════════════════════════════════════
# SERVICES (price list)
# ════════════════════════════════════════════════════════════

def get_all_services():
    conn = get_conn()
    c = conn.cursor()
    c.execute("SELECT * FROM services WHERE active = 1 ORDER BY id")
    services = [dict(row) for row in c.fetchall()]
    conn.close()
    return services


def update_service_price(service_id, price):
    conn = get_conn()
    c = conn.cursor()
    c.execute("UPDATE services SET price = ? WHERE id = ?", (price, service_id))
    conn.commit()
    conn.close()


def add_service(name, unit, price, is_promo=0, category="Other"):
    conn = get_conn()
    c = conn.cursor()
    c.execute(
        "INSERT INTO services (name, unit, price, is_promo, category) VALUES (?, ?, ?, ?, ?)",
        (name, unit, price, is_promo, category)
    )
    conn.commit()
    conn.close()


def delete_service(service_id):
    conn = get_conn()
    c = conn.cursor()
    c.execute("DELETE FROM services WHERE id = ?", (service_id,))
    conn.commit()
    conn.close()


# ════════════════════════════════════════════════════════════
# POS SALES
# ════════════════════════════════════════════════════════════

def create_sale(items, discount, cash_received, payment_method="Cash"):
    """
    items: list of dicts like
        {"service_name": "Black & White Printing", "unit_price": 3.0, "quantity": 5}
        or for supply items, include "inventory_item_id": 5
    created_at is stored in Philippine Standard Time (UTC+8).
    """
    from datetime import datetime, timezone, timedelta
    PST = timezone(timedelta(hours=8))
    now_pst = datetime.now(PST).strftime("%Y-%m-%d %H:%M:%S")

    subtotal = sum(i["unit_price"] * i["quantity"] for i in items)
    total = max(subtotal - discount, 0)
    change = cash_received - total

    conn = get_conn()
    c = conn.cursor()
    c.execute("""
        INSERT INTO sales (subtotal, discount, total, cash_received, change_given, payment_method, created_at)
        VALUES (?, ?, ?, ?, ?, ?, ?)
    """, (subtotal, discount, total, cash_received, change, payment_method, now_pst))
    sale_id = c.lastrowid

    for item in items:
        line_total = item["unit_price"] * item["quantity"]
        inv_id = item.get("inventory_item_id")

        c.execute("""
            INSERT INTO sale_items (sale_id, service_name, unit_price, quantity, line_total, inventory_item_id)
            VALUES (?, ?, ?, ?, ?, ?)
        """, (sale_id, item["service_name"], item["unit_price"], item["quantity"], line_total, inv_id))

        # Deduct stock if this line item is a supply item tied to inventory
        if inv_id:
            c.execute("""
                UPDATE inventory SET stock_out = stock_out + ?, updated_at = CURRENT_TIMESTAMP
                WHERE id = ?
            """, (item["quantity"], inv_id))
            c.execute("""
                INSERT INTO inventory_log (item_id, type, quantity, note)
                VALUES (?, 'out', ?, ?)
            """, (inv_id, item["quantity"], f"POS sale #{sale_id}"))

    conn.commit()
    conn.close()
    return {
        "sale_id": sale_id,
        "subtotal": subtotal,
        "discount": discount,
        "total": total,
        "cash_received": cash_received,
        "change": change
    }


def get_sales_between(start_date, end_date):
    conn = get_conn()
    c = conn.cursor()
    c.execute("""
        SELECT * FROM sales
        WHERE date(created_at) BETWEEN ? AND ?
        ORDER BY created_at DESC
    """, (start_date, end_date))
    sales = [dict(row) for row in c.fetchall()]
    conn.close()
    return sales


def get_today_sales_total():
    conn = get_conn()
    c = conn.cursor()
    # Use Philippine time (UTC+8) for date comparison
    c.execute("""
        SELECT COALESCE(SUM(total), 0) as total
        FROM sales
        WHERE date(created_at) = date('now', '+8 hours')
    """)
    result = c.fetchone()["total"]
    conn.close()
    return result


def get_month_sales_total():
    conn = get_conn()
    c = conn.cursor()
    # Use Philippine time (UTC+8) for month comparison
    c.execute("""
        SELECT COALESCE(SUM(total), 0) as total
        FROM sales
        WHERE strftime('%Y-%m', created_at) = strftime('%Y-%m', 'now', '+8 hours')
    """)
    result = c.fetchone()["total"]
    conn.close()
    return result


def get_recent_transactions(limit=10):
    conn = get_conn()
    c = conn.cursor()
    c.execute("""
        SELECT s.*, GROUP_CONCAT(si.service_name || ' x' || si.quantity, ', ') as items_summary
        FROM sales s
        LEFT JOIN sale_items si ON s.id = si.sale_id
        GROUP BY s.id
        ORDER BY s.created_at DESC
        LIMIT ?
    """, (limit,))
    rows = [dict(row) for row in c.fetchall()]
    conn.close()
    return rows


def get_sale_with_items(sale_id):
    conn = get_conn()
    c = conn.cursor()
    c.execute("SELECT * FROM sales WHERE id = ?", (sale_id,))
    sale = c.fetchone()
    if not sale:
        conn.close()
        return None
    sale = dict(sale)
    c.execute("SELECT * FROM sale_items WHERE sale_id = ?", (sale_id,))
    sale["lines"] = [dict(row) for row in c.fetchall()]
    conn.close()
    return sale


# ════════════════════════════════════════════════════════════
# INVENTORY
# ════════════════════════════════════════════════════════════

def get_all_inventory():
    conn = get_conn()
    c = conn.cursor()
    c.execute("SELECT * FROM inventory ORDER BY name")
    items = []
    for row in c.fetchall():
        item = dict(row)
        item["remaining_stock"] = (
            item["beginning_stock"] + item["stock_in"] - item["stock_out"]
        )
        item["low_stock"] = item["remaining_stock"] <= item["low_stock_alert"]
        items.append(item)
    conn.close()
    return items


def get_low_stock_items():
    items = get_all_inventory()
    return [i for i in items if i["low_stock"]]


def add_stock(item_id, quantity, note=""):
    conn = get_conn()
    c = conn.cursor()
    c.execute("UPDATE inventory SET stock_in = stock_in + ?, updated_at = CURRENT_TIMESTAMP WHERE id = ?",
              (quantity, item_id))
    c.execute("INSERT INTO inventory_log (item_id, type, quantity, note) VALUES (?, 'in', ?, ?)",
              (item_id, quantity, note))
    conn.commit()
    conn.close()


def remove_stock(item_id, quantity, note=""):
    conn = get_conn()
    c = conn.cursor()
    c.execute("UPDATE inventory SET stock_out = stock_out + ?, updated_at = CURRENT_TIMESTAMP WHERE id = ?",
              (quantity, item_id))
    c.execute("INSERT INTO inventory_log (item_id, type, quantity, note) VALUES (?, 'out', ?, ?)",
              (item_id, quantity, note))
    conn.commit()
    conn.close()


def delete_inventory_item(item_id):
    """
    Deletes an inventory item and its movement log.
    If any reject_types reference this item, unlink them (set inventory_item_id to NULL)
    rather than blocking the delete or leaving a dangling foreign key.
    """
    conn = get_conn()
    c = conn.cursor()

    c.execute("UPDATE reject_types SET inventory_item_id = NULL WHERE inventory_item_id = ?", (item_id,))
    c.execute("DELETE FROM inventory_log WHERE item_id = ?", (item_id,))
    c.execute("DELETE FROM inventory WHERE id = ?", (item_id,))

    conn.commit()
    conn.close()
    return True


def add_inventory_item(name, unit, beginning_stock=0, low_stock_alert=5, unit_cost=0, selling_price=0, is_supply_item=0):
    conn = get_conn()
    c = conn.cursor()
    c.execute("""
        INSERT INTO inventory (name, unit, beginning_stock, low_stock_alert, unit_cost, selling_price, is_supply_item)
        VALUES (?, ?, ?, ?, ?, ?, ?)
    """, (name, unit, beginning_stock, low_stock_alert, unit_cost, selling_price, is_supply_item))
    conn.commit()
    conn.close()


def get_supply_items():
    """Returns inventory items marked as sellable school supplies, with remaining stock computed."""
    conn = get_conn()
    c = conn.cursor()
    c.execute("SELECT * FROM inventory WHERE is_supply_item = 1 ORDER BY name")
    items = []
    for row in c.fetchall():
        item = dict(row)
        item["remaining_stock"] = item["beginning_stock"] + item["stock_in"] - item["stock_out"]
        items.append(item)
    conn.close()
    return items


def update_selling_price(item_id, selling_price):
    conn = get_conn()
    c = conn.cursor()
    c.execute("UPDATE inventory SET selling_price = ? WHERE id = ?", (selling_price, item_id))
    conn.commit()
    conn.close()


def set_is_supply_item(item_id, is_supply_item):
    conn = get_conn()
    c = conn.cursor()
    c.execute("UPDATE inventory SET is_supply_item = ? WHERE id = ?", (1 if is_supply_item else 0, item_id))
    conn.commit()
    conn.close()


# ════════════════════════════════════════════════════════════
# EXPENSES
# ════════════════════════════════════════════════════════════

def add_expense(category, description, amount, expense_date=None):
    conn = get_conn()
    c = conn.cursor()
    if expense_date:
        c.execute("""
            INSERT INTO expenses (category, description, amount, expense_date)
            VALUES (?, ?, ?, ?)
        """, (category, description, amount, expense_date))
    else:
        c.execute("""
            INSERT INTO expenses (category, description, amount)
            VALUES (?, ?, ?)
        """, (category, description, amount))
    conn.commit()
    conn.close()


def get_today_expenses_total():
    conn = get_conn()
    c = conn.cursor()
    c.execute("""
        SELECT COALESCE(SUM(amount), 0) as total
        FROM expenses
        WHERE expense_date = date('now')
    """)
    result = c.fetchone()["total"]
    conn.close()
    return result


def get_month_expenses_total():
    conn = get_conn()
    c = conn.cursor()
    c.execute("""
        SELECT COALESCE(SUM(amount), 0) as total
        FROM expenses
        WHERE strftime('%Y-%m', expense_date) = strftime('%Y-%m', 'now', '+8 hours')
    """)
    result = c.fetchone()["total"]
    conn.close()
    return result


def get_all_expenses(limit=50):
    conn = get_conn()
    c = conn.cursor()
    c.execute("SELECT * FROM expenses ORDER BY expense_date DESC, created_at DESC LIMIT ?", (limit,))
    expenses = [dict(row) for row in c.fetchall()]
    conn.close()
    return expenses


# ════════════════════════════════════════════════════════════
# REJECTS / WASTAGE
# ════════════════════════════════════════════════════════════

def get_all_reject_types():
    conn = get_conn()
    c = conn.cursor()
    c.execute("""
        SELECT rt.*, i.name as inventory_name, i.unit as inventory_unit, i.unit_cost,
               i.pieces_per_unit, i.piece_label
        FROM reject_types rt
        LEFT JOIN inventory i ON rt.inventory_item_id = i.id
        WHERE rt.active = 1
        ORDER BY rt.category, rt.name
    """)
    types = [dict(row) for row in c.fetchall()]
    conn.close()
    return types


def log_reject(reject_type_id, quantity, note=""):
    """
    quantity is entered in PIECE units (e.g. sheets for paper, ml for ink) —
    matching reject_types.inventory_item's piece_label, NOT the package unit (ream/bottle).

    Cost is computed as: (unit_cost / pieces_per_unit) * quantity
      e.g. Bond Paper: ₱220/ream ÷ 500 sheets/ream = ₱0.44/sheet
           1 sheet wasted = ₱0.44

    Stock deduction is in PACKAGE units (fractional):
      e.g. 1 sheet wasted = 1/500 = 0.002 ream deducted from stock_out
    """
    conn = get_conn()
    c = conn.cursor()

    c.execute("""
        SELECT rt.*, i.unit_cost, i.id as inv_id, i.pieces_per_unit, i.piece_label, i.unit as package_unit
        FROM reject_types rt
        LEFT JOIN inventory i ON rt.inventory_item_id = i.id
        WHERE rt.id = ?
    """, (reject_type_id,))
    rt = c.fetchone()

    if not rt:
        conn.close()
        return None

    unit_cost = rt["unit_cost"] or 0
    pieces_per_unit = rt["pieces_per_unit"] or 1

    cost_per_piece = unit_cost / pieces_per_unit if pieces_per_unit else 0
    estimated_cost = cost_per_piece * quantity

    # Fractional package quantity to deduct from stock (e.g. 1 sheet / 500 sheets-per-ream)
    package_qty_to_deduct = quantity / pieces_per_unit if pieces_per_unit else 0

    from datetime import datetime, timezone, timedelta
    PST = timezone(timedelta(hours=8))
    now_pst = datetime.now(PST).strftime("%Y-%m-%d %H:%M:%S")

    c.execute("""
        INSERT INTO rejects (reject_type_id, quantity, estimated_cost, note, created_at)
        VALUES (?, ?, ?, ?, ?)
    """, (reject_type_id, quantity, estimated_cost, note, now_pst))

    # Auto-deduct from inventory if linked (in package units, fractional)
    if rt["inv_id"]:
        c.execute("""
            UPDATE inventory SET stock_out = stock_out + ?, updated_at = CURRENT_TIMESTAMP
            WHERE id = ?
        """, (package_qty_to_deduct, rt["inv_id"]))
        c.execute("""
            INSERT INTO inventory_log (item_id, type, quantity, note)
            VALUES (?, 'out', ?, ?)
        """, (
            rt["inv_id"],
            package_qty_to_deduct,
            f"Reject/Wastage: {rt['name']} ({quantity} {rt['piece_label'] or 'pc'})"
        ))

    conn.commit()
    reject_id = c.lastrowid
    conn.close()
    return {"reject_id": reject_id, "estimated_cost": estimated_cost}


def get_all_rejects(limit=100):
    conn = get_conn()
    c = conn.cursor()
    c.execute("""
        SELECT r.*, rt.name as reject_name, rt.category
        FROM rejects r
        JOIN reject_types rt ON r.reject_type_id = rt.id
        ORDER BY r.created_at DESC
        LIMIT ?
    """, (limit,))
    rows = [dict(row) for row in c.fetchall()]
    conn.close()
    return rows


def get_today_reject_cost():
    conn = get_conn()
    c = conn.cursor()
    c.execute("""
        SELECT COALESCE(SUM(estimated_cost), 0) as total
        FROM rejects
        WHERE date(created_at) = date('now', '+8 hours')
    """)
    result = c.fetchone()["total"]
    conn.close()
    return result


def get_month_reject_cost():
    conn = get_conn()
    c = conn.cursor()
    c.execute("""
        SELECT COALESCE(SUM(estimated_cost), 0) as total
        FROM rejects
        WHERE strftime('%Y-%m', created_at) = strftime('%Y-%m', 'now', '+8 hours')
    """)
    result = c.fetchone()["total"]
    conn.close()
    return result


def add_reject_type(name, category, inventory_item_id=None, default_qty=1):
    conn = get_conn()
    c = conn.cursor()
    c.execute("""
        INSERT INTO reject_types (name, category, inventory_item_id, default_qty)
        VALUES (?, ?, ?, ?)
    """, (name, category, inventory_item_id, default_qty))
    conn.commit()
    conn.close()


def update_inventory_unit_cost(item_id, unit_cost):
    conn = get_conn()
    c = conn.cursor()
    c.execute("UPDATE inventory SET unit_cost = ? WHERE id = ?", (unit_cost, item_id))
    conn.commit()
    conn.close()


def update_inventory_packaging(item_id, pieces_per_unit, piece_label):
    """
    e.g. Bond Paper: pieces_per_unit=500, piece_label='sheet'
         Ink: pieces_per_unit=60, piece_label='ml'
    Used to compute cost-per-piece for wastage/reject estimates.
    """
    conn = get_conn()
    c = conn.cursor()
    c.execute(
        "UPDATE inventory SET pieces_per_unit = ?, piece_label = ? WHERE id = ?",
        (pieces_per_unit, piece_label, item_id)
    )
    conn.commit()
    conn.close()


# ════════════════════════════════════════════════════════════
# APP SETTINGS
# ════════════════════════════════════════════════════════════

def get_setting(key, default=""):
    conn = get_conn()
    c = conn.cursor()
    c.execute("SELECT value FROM app_settings WHERE key = ?", (key,))
    row = c.fetchone()
    conn.close()
    return row["value"] if row else default


def set_setting(key, value):
    conn = get_conn()
    c = conn.cursor()
    c.execute("INSERT OR REPLACE INTO app_settings (key, value) VALUES (?, ?)", (key, value))
    conn.commit()
    conn.close()


def get_all_settings():
    conn = get_conn()
    c = conn.cursor()
    c.execute("SELECT key, value FROM app_settings ORDER BY key")
    settings = {row["key"]: row["value"] for row in c.fetchall()}
    conn.close()
    return settings


# ════════════════════════════════════════════════════════════
# DASHBOARD SUMMARY
# ════════════════════════════════════════════════════════════

def get_dashboard_summary():
    today_sales = get_today_sales_total()
    month_sales = get_month_sales_total()
    month_expenses = get_month_expenses_total()
    month_reject_cost = get_month_reject_cost()
    net_profit = month_sales - month_expenses - month_reject_cost
    low_stock = get_low_stock_items()
    recent = get_recent_transactions(10)

    return {
        "today_sales": today_sales,
        "month_sales": month_sales,
        "month_expenses": month_expenses,
        "month_reject_cost": month_reject_cost,
        "net_profit": net_profit,
        "low_stock_items": low_stock,
        "recent_transactions": recent
    }
