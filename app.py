import os
import sys
import threading
import time

# Ensure the project folder is always on the path so database.py and printer.py
# are found regardless of where Python is launched from
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from flask import Flask, request, jsonify, render_template, send_from_directory, session, redirect, url_for
from functools import wraps
from database import (
    init_db, create_order, get_all_orders, get_order, get_order_file, update_file_status,
    get_all_services, update_service_price, add_service, delete_service,
    create_sale, get_sale_with_items, get_dashboard_summary,
    get_all_inventory, add_stock, remove_stock, add_inventory_item, delete_inventory_item,
    add_expense, get_all_expenses,
    get_all_reject_types, log_reject, get_all_rejects,
    update_inventory_unit_cost, update_inventory_packaging,
    get_supply_items, update_selling_price, set_is_supply_item,
    get_setting, set_setting, get_all_settings
)
from printer import get_available_printers
from printer import print_file

BASE_DIR = os.path.dirname(os.path.abspath(__file__))

app = Flask(__name__, template_folder=os.path.join(BASE_DIR, "templates"))

app.secret_key = "printq_secret_2026"

ADMIN_USERNAME = "admin"
ADMIN_PASSWORD = "printq123"

UPLOAD_FOLDER = os.path.join(BASE_DIR, "uploads")
ALLOWED_EXTENSIONS = {"pdf", "docx", "jpg", "jpeg", "png"}
app.config["MAX_CONTENT_LENGTH"] = 20 * 1024 * 1024

from datetime import timedelta
app.config["PERMANENT_SESSION_LIFETIME"] = timedelta(hours=12)
app.config["SESSION_PERMANENT"] = True

os.makedirs(UPLOAD_FOLDER, exist_ok=True)

print(f"[STARTUP] BASE_DIR: {BASE_DIR}")
print(f"[STARTUP] UPLOAD_FOLDER: {UPLOAD_FOLDER}")


def allowed_file(filename):
    return "." in filename and filename.rsplit(".", 1)[1].lower() in ALLOWED_EXTENSIONS


def login_required(f):
    @wraps(f)
    def decorated(*args, **kwargs):
        if not session.get("logged_in"):
            return jsonify({"error": "Unauthorized"}), 401
        return f(*args, **kwargs)
    return decorated


def page_login_required(f):
    @wraps(f)
    def decorated(*args, **kwargs):
        if not session.get("logged_in"):
            return redirect(url_for("login"))
        return f(*args, **kwargs)
    return decorated


# ════════════════════════════════════════════════════════════
# STUDENT UPLOAD (existing)
# ════════════════════════════════════════════════════════════

@app.route("/")
def upload_page():
    return render_template("upload.html")


@app.route("/upload", methods=["POST"])
def upload():
    """
    Expects multipart/form-data:
      - name: student name
      - notes: optional order-level note
      - file_count: number of files
      - for each i in range(file_count):
          file_{i}: the file blob
          color_{i}: "B&W" | "Colored"
          paper_{i}: "Short" | "Long" | "A4"
          copies_{i}: integer
    """
    name = request.form.get("name", "").strip()
    notes = request.form.get("notes", "")

    if not name:
        return jsonify({"error": "Name is required"}), 400

    try:
        file_count = int(request.form.get("file_count", 0))
    except ValueError:
        file_count = 0

    if file_count <= 0:
        return jsonify({"error": "No files selected"}), 400

    files_to_save = []
    saved_paths = []

    for i in range(file_count):
        file = request.files.get(f"file_{i}")
        color = request.form.get(f"color_{i}", "B&W")
        paper = request.form.get(f"paper_{i}", "Short")
        try:
            copies = int(request.form.get(f"copies_{i}", 1))
        except ValueError:
            copies = 1

        if not file or file.filename == "":
            continue
        if not allowed_file(file.filename):
            return jsonify({"error": f"File type not allowed: {file.filename}"}), 400

        safe_name = f"{name.replace(' ', '_')}_{i}_{file.filename}"
        save_path = os.path.join(UPLOAD_FOLDER, safe_name)

        try:
            file.save(save_path)
            saved_paths.append(save_path)
        except Exception as e:
            # Roll back any files already saved in this batch
            for p in saved_paths:
                if os.path.exists(p):
                    os.remove(p)
            return jsonify({"error": str(e)}), 500

        files_to_save.append({
            "filename": safe_name,
            "color": color,
            "paper": paper,
            "copies": copies
        })

    if not files_to_save:
        return jsonify({"error": "No valid files in upload"}), 400

    order_id = create_order(name, files_to_save, notes)
    return jsonify({
        "queue_number": order_id,
        "file_count": len(files_to_save),
        "message": "Upload successful"
    })


# ════════════════════════════════════════════════════════════
# AUTH
# ════════════════════════════════════════════════════════════

@app.route("/login", methods=["GET", "POST"])
def login():
    error = None
    if request.method == "POST":
        username = request.form.get("username")
        password = request.form.get("password")
        if username == ADMIN_USERNAME and password == ADMIN_PASSWORD:
            session.permanent = True
            session["logged_in"] = True
            return redirect(url_for("admin"))
        else:
            error = "Wrong username or password."
    return render_template("login.html", error=error)


@app.route("/logout")
def logout():
    session.clear()
    return redirect(url_for("login"))


# ════════════════════════════════════════════════════════════
# PRINT QUEUE (admin dashboard for student uploads)
# ════════════════════════════════════════════════════════════

@app.route("/admin")
@page_login_required
def admin():
    return render_template("queue.html")


@app.route("/api/orders")
def api_orders():
    return jsonify(get_all_orders())


@app.route("/api/print-file/<int:file_id>", methods=["POST"])
@login_required
def api_print_file(file_id):
    order_file = get_order_file(file_id)
    if not order_file:
        return jsonify({"error": "File not found"}), 404

    filepath = os.path.join(UPLOAD_FOLDER, order_file["filename"])
    success, msg = print_file(filepath, order_file["copies"], order_file["color"], order_file["paper"])

    if success:
        update_file_status(file_id, "done")
        return jsonify({"status": "printed", "message": msg})
    else:
        return jsonify({"error": msg}), 500


@app.route("/api/reprint-file/<int:file_id>", methods=["POST"])
@login_required
def api_reprint_file(file_id):
    order_file = get_order_file(file_id)
    if not order_file:
        return jsonify({"error": "File not found"}), 404

    filepath = os.path.join(UPLOAD_FOLDER, order_file["filename"])

    if not os.path.exists(filepath):
        return jsonify({"error": "File no longer on disk. Student must re-upload."}), 410

    success, msg = print_file(filepath, order_file["copies"], order_file["color"], order_file["paper"])

    if success:
        update_file_status(file_id, "done")
        return jsonify({"status": "reprinted", "message": msg})
    else:
        return jsonify({"error": msg}), 500


@app.route("/api/fail-file/<int:file_id>", methods=["POST"])
@login_required
def api_fail_file(file_id):
    order_file = get_order_file(file_id)
    if not order_file:
        return jsonify({"error": "File not found"}), 404
    update_file_status(file_id, "failed")
    return jsonify({"status": "failed"})


@app.route("/api/check-file/<int:file_id>")
@login_required
def api_check_file(file_id):
    order_file = get_order_file(file_id)
    if not order_file:
        return jsonify({"exists": False})
    filepath = os.path.join(UPLOAD_FOLDER, order_file["filename"])
    return jsonify({"exists": os.path.exists(filepath)})


@app.route("/api/cancel-file/<int:file_id>", methods=["POST"])
@login_required
def api_cancel_file(file_id):
    update_file_status(file_id, "cancelled")
    return jsonify({"status": "cancelled"})


@app.route("/api/preview-file/<int:file_id>")
@login_required
def api_preview_file(file_id):
    order_file = get_order_file(file_id)
    if not order_file:
        return jsonify({"error": "Not found"}), 404
    return send_from_directory(UPLOAD_FOLDER, order_file["filename"])


# ════════════════════════════════════════════════════════════
# POS (walk-in customers)
# ════════════════════════════════════════════════════════════

@app.route("/pos")
@page_login_required
def pos():
    return render_template("pos.html")


@app.route("/api/services")
def api_services():
    return jsonify(get_all_services())


@app.route("/api/services/<int:service_id>/price", methods=["POST"])
@login_required
def api_update_service_price(service_id):
    data = request.get_json()
    price = data.get("price")
    if price is None or price < 0:
        return jsonify({"error": "Invalid price"}), 400
    update_service_price(service_id, price)
    return jsonify({"status": "updated"})


@app.route("/api/services/add", methods=["POST"])
@login_required
def api_add_service():
    data = request.get_json()
    name = data.get("name", "").strip()
    unit = data.get("unit", "page")
    price = data.get("price")
    is_promo = 1 if data.get("is_promo") else 0

    if not name:
        return jsonify({"error": "Service name is required"}), 400
    if price is None or price < 0:
        return jsonify({"error": "Invalid price"}), 400

    category = data.get("category", "Other").strip() or "Other"
    try:
        add_service(name, unit, float(price), is_promo, category)
    except Exception as e:
        return jsonify({"error": "A service with that name may already exist"}), 400

    return jsonify({"status": "added"})


@app.route("/api/services/<int:service_id>/delete", methods=["POST"])
@login_required
def api_delete_service(service_id):
    delete_service(service_id)
    return jsonify({"status": "deleted"})


@app.route("/api/supplies")
def api_supplies():
    return jsonify(get_supply_items())


@app.route("/api/inventory/<int:item_id>/selling-price", methods=["POST"])
@login_required
def api_update_selling_price(item_id):
    data = request.get_json()
    selling_price = data.get("selling_price")
    if selling_price is None or selling_price < 0:
        return jsonify({"error": "Invalid price"}), 400
    update_selling_price(item_id, selling_price)
    return jsonify({"status": "updated"})


@app.route("/api/inventory/<int:item_id>/mark-supply", methods=["POST"])
@login_required
def api_mark_supply(item_id):
    data = request.get_json()
    is_supply = data.get("is_supply_item", True)
    set_is_supply_item(item_id, is_supply)
    return jsonify({"status": "updated"})


@app.route("/api/pos/sale", methods=["POST"])
@login_required
def api_pos_sale():
    try:
        data = request.get_json()
        items = data.get("items", [])
        discount = float(data.get("discount", 0))
        cash_received = float(data.get("cash_received", 0))

        if not items:
            return jsonify({"error": "Cart is empty"}), 400

        # Validate stock availability for supply items
        supply_items = {i["id"]: i for i in get_supply_items()}
        for item in items:
            inv_id = item.get("inventory_item_id")
            if inv_id and inv_id in supply_items:
                available = supply_items[inv_id]["remaining_stock"]
                if item["quantity"] > available:
                    return jsonify({
                        "error": f"Not enough stock for {item['service_name']} (only {available} left)"
                    }), 400

        subtotal = sum(i["unit_price"] * i["quantity"] for i in items)
        total = max(subtotal - discount, 0)

        if cash_received < total:
            return jsonify({"error": "Insufficient cash received"}), 400

        result = create_sale(items, discount, cash_received)
        return jsonify(result)

    except Exception as e:
        import traceback
        traceback.print_exc()
        return jsonify({"error": str(e)}), 500


# ════════════════════════════════════════════════════════════
# DASHBOARD
# ════════════════════════════════════════════════════════════

@app.route("/dashboard")
@page_login_required
def dashboard():
    return render_template("dashboard.html")


@app.route("/api/dashboard")
def api_dashboard():
    try:
        return jsonify(get_dashboard_summary())
    except Exception as e:
        import traceback
        traceback.print_exc()
        return jsonify({"error": str(e)}), 500


# ════════════════════════════════════════════════════════════
# INVENTORY
# ════════════════════════════════════════════════════════════

@app.route("/inventory")
@page_login_required
def inventory_page():
    return render_template("inventory.html")


@app.route("/api/inventory")
@login_required
def api_inventory():
    return jsonify(get_all_inventory())


@app.route("/api/inventory/<int:item_id>/stock-in", methods=["POST"])
@login_required
def api_stock_in(item_id):
    data = request.get_json()
    quantity = float(data.get("quantity", 0))
    note = data.get("note", "")
    if quantity <= 0:
        return jsonify({"error": "Quantity must be greater than 0"}), 400
    add_stock(item_id, quantity, note)
    return jsonify({"status": "updated"})


@app.route("/api/inventory/<int:item_id>/stock-out", methods=["POST"])
@login_required
def api_stock_out(item_id):
    data = request.get_json()
    quantity = float(data.get("quantity", 0))
    note = data.get("note", "")
    if quantity <= 0:
        return jsonify({"error": "Quantity must be greater than 0"}), 400
    remove_stock(item_id, quantity, note)
    return jsonify({"status": "updated"})


@app.route("/api/inventory/add-item", methods=["POST"])
@login_required
def api_add_inventory_item():
    data = request.get_json()
    name = data.get("name", "").strip()
    unit = data.get("unit", "pc")
    beginning_stock = float(data.get("beginning_stock", 0))
    low_stock_alert = float(data.get("low_stock_alert", 5))
    unit_cost = float(data.get("unit_cost", 0))
    selling_price = float(data.get("selling_price", 0))
    is_supply_item = 1 if data.get("is_supply_item") else 0

    if not name:
        return jsonify({"error": "Name is required"}), 400

    add_inventory_item(name, unit, beginning_stock, low_stock_alert, unit_cost, selling_price, is_supply_item)
    return jsonify({"status": "added"})


@app.route("/api/inventory/<int:item_id>/delete", methods=["POST"])
@login_required
def api_delete_inventory_item(item_id):
    delete_inventory_item(item_id)
    return jsonify({"status": "deleted"})


# ════════════════════════════════════════════════════════════
# EXPENSES
# ════════════════════════════════════════════════════════════

@app.route("/expenses")
@page_login_required
def expenses_page():
    return render_template("expenses.html")


@app.route("/api/expenses")
@login_required
def api_expenses():
    return jsonify(get_all_expenses())


@app.route("/api/expenses/add", methods=["POST"])
@login_required
def api_add_expense():
    data = request.get_json()
    category = data.get("category", "Other")
    description = data.get("description", "")
    amount = float(data.get("amount", 0))
    expense_date = data.get("expense_date")

    if amount <= 0:
        return jsonify({"error": "Amount must be greater than 0"}), 400

    add_expense(category, description, amount, expense_date)
    return jsonify({"status": "added"})


# ════════════════════════════════════════════════════════════
# REJECTS / WASTAGE
# ════════════════════════════════════════════════════════════

@app.route("/wastage")
@page_login_required
def wastage_page():
    return render_template("wastage.html")


@app.route("/api/reject-types")
@login_required
def api_reject_types():
    return jsonify(get_all_reject_types())


@app.route("/api/rejects")
@login_required
def api_rejects():
    return jsonify(get_all_rejects())


@app.route("/api/rejects/log", methods=["POST"])
@login_required
def api_log_reject():
    data = request.get_json()
    reject_type_id = data.get("reject_type_id")
    quantity = float(data.get("quantity", 1))
    note = data.get("note", "")

    if not reject_type_id or quantity <= 0:
        return jsonify({"error": "Invalid reject type or quantity"}), 400

    result = log_reject(reject_type_id, quantity, note)
    if result is None:
        return jsonify({"error": "Reject type not found"}), 404

    return jsonify(result)


@app.route("/api/inventory/<int:item_id>/unit-cost", methods=["POST"])
@login_required
def api_update_unit_cost(item_id):
    data = request.get_json()
    unit_cost = float(data.get("unit_cost", 0))
    if unit_cost < 0:
        return jsonify({"error": "Invalid cost"}), 400
    update_inventory_unit_cost(item_id, unit_cost)
    return jsonify({"status": "updated"})


@app.route("/api/inventory/<int:item_id>/packaging", methods=["POST"])
@login_required
def api_update_packaging(item_id):
    data = request.get_json()
    pieces_per_unit = float(data.get("pieces_per_unit", 1))
    piece_label = data.get("piece_label", "pc").strip()
    if pieces_per_unit <= 0:
        return jsonify({"error": "Pieces per unit must be greater than 0"}), 400
    update_inventory_packaging(item_id, pieces_per_unit, piece_label)
    return jsonify({"status": "updated"})


# ════════════════════════════════════════════════════════════
# RECEIPT
# ════════════════════════════════════════════════════════════

@app.route("/receipt/<int:sale_id>")
@login_required
def receipt_page(sale_id):
    sale = get_sale_with_items(sale_id)
    if not sale:
        return "Receipt not found", 404
    shop_name = get_setting("shop_name", "RektaPrint")
    return render_template("receipt.html", sale=sale, shop_name=shop_name)


# ════════════════════════════════════════════════════════════
# SETTINGS (prices, printers, config)
# ════════════════════════════════════════════════════════════

@app.route("/settings")
@page_login_required
def settings_page():
    return render_template("settings.html")


@app.route("/api/settings")
def api_get_settings():
    return jsonify(get_all_settings())


@app.route("/api/settings/update", methods=["POST"])
@login_required
def api_update_setting():
    data = request.get_json()
    key   = data.get("key", "").strip()
    value = data.get("value", "").strip()

    allowed_keys = {"printer_bw", "printer_colored", "sumatra_path", "shop_name"}
    if key not in allowed_keys:
        return jsonify({"error": "Unknown setting key"}), 400
    if not value:
        return jsonify({"error": "Value cannot be empty"}), 400

    set_setting(key, value)
    return jsonify({"status": "updated"})


@app.route("/api/printers")
def api_printers():
    printers = get_available_printers()
    return jsonify(printers)


@app.route("/api/test-print", methods=["POST"])
@login_required
def api_test_print():
    """
    Debug route — sends a test print and returns exactly what happened.
    POST body: { "filepath": "C:\\path\\to\\file.pdf" }  (optional)
    """
    import subprocess
    from database import get_setting

    printer_bw      = get_setting("printer_bw")
    printer_colored = get_setting("printer_colored")
    sumatra_path    = get_setting("sumatra_path")

    data     = request.get_json() or {}
    filepath = data.get("filepath", "").strip()

    result = {
        "printer_bw":      printer_bw,
        "printer_colored": printer_colored,
        "sumatra_path":    sumatra_path,
        "sumatra_exists":  os.path.exists(sumatra_path),
        "file_exists":     os.path.exists(filepath) if filepath else "no filepath given",
    }

    if filepath and os.path.exists(filepath) and os.path.exists(sumatra_path):
        cmd = [
            sumatra_path,
            "-print-to", printer_bw,
            "-print-settings", "1x,letter,grayscale",
            filepath
        ]
        result["command"] = " ".join(cmd)
        try:
            proc = subprocess.run(cmd, capture_output=True, text=True, timeout=30)
            result["returncode"] = proc.returncode
            result["stdout"]     = proc.stdout
            result["stderr"]     = proc.stderr
        except Exception as e:
            result["exception"] = str(e)

    return jsonify(result)


# ════════════════════════════════════════════════════════════
# AUTO CLEANUP (delete print queue files older than 24 hours)
# ════════════════════════════════════════════════════════════

def auto_cleanup():
    while True:
        time.sleep(3600)
        now = time.time()
        for filename in os.listdir(UPLOAD_FOLDER):
            filepath = os.path.join(UPLOAD_FOLDER, filename)
            try:
                if os.path.getmtime(filepath) < now - 86400:
                    os.remove(filepath)
                    print(f"Auto-deleted: {filename}")
            except Exception as e:
                print(f"Cleanup error: {e}")


cleanup_thread = threading.Thread(target=auto_cleanup, daemon=True)
cleanup_thread.start()


if __name__ == "__main__":
    print("Starting RektaPrint server...")
    init_db()
    app.run(host="0.0.0.0", port=5000, debug=False, use_reloader=False)
