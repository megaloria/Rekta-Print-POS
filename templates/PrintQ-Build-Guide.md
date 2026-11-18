# PrintQ – Full Build Guide
### VS Code + Python Flask + SQLite

---

## What You'll Build

```
printq/
├── app.py              ← Flask backend (the brain)
├── database.py         ← SQLite setup
├── printer.py          ← Windows print command
├── printq.db           ← Auto-created database
├── uploads/            ← Uploaded files saved here
├── templates/
│   ├── upload.html     ← Student upload page
│   └── dashboard.html  ← Your admin dashboard
└── requirements.txt    ← Python packages list
```

---

## STEP 1 — Install the Tools

### 1A. Install Python
1. Go to https://python.org/downloads
2. Download **Python 3.11** or newer
3. Run the installer
4. ✅ **CHECK "Add Python to PATH"** before clicking Install
5. Open Command Prompt and verify:
   ```
   python --version
   ```
   Should print: `Python 3.11.x`

### 1B. Install VS Code
1. Go to https://code.visualstudio.com
2. Download and install
3. Open VS Code
4. Install the **Python extension** (Ctrl+Shift+X → search "Python" → Install)

---

## STEP 2 — Create the Project Folder

Open VS Code, then open the Terminal (Ctrl+` or View → Terminal):

```bash
# Go to your Desktop
cd C:\Users\YourName\Desktop

# Create the project folder
mkdir printq
cd printq

# Create subfolders
mkdir uploads
mkdir templates
```

---

## STEP 3 — Install Python Packages

Still in the VS Code terminal:

```bash
pip install flask
```

That's it. Flask is all you need for the core system.

---

## STEP 4 — Create the Files

### 4A. `requirements.txt`
Create this file in `printq/`:
```
flask
```

### 4B. `database.py`
Create this file in `printq/`:

```python
import sqlite3

DB = "printq.db"

def init_db():
    conn = sqlite3.connect(DB)
    c = conn.cursor()
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
    conn.commit()
    conn.close()

def add_job(name, filename, color, paper, copies, notes):
    conn = sqlite3.connect(DB)
    c = conn.cursor()
    c.execute("""
        INSERT INTO jobs (name, filename, color, paper, copies, notes)
        VALUES (?, ?, ?, ?, ?, ?)
    """, (name, filename, color, paper, copies, notes))
    job_id = c.lastrowid
    conn.commit()
    conn.close()
    return job_id

def get_all_jobs():
    conn = sqlite3.connect(DB)
    conn.row_factory = sqlite3.Row
    c = conn.cursor()
    c.execute("SELECT * FROM jobs ORDER BY created_at DESC")
    jobs = [dict(row) for row in c.fetchall()]
    conn.close()
    return jobs

def update_status(job_id, status):
    conn = sqlite3.connect(DB)
    c = conn.cursor()
    c.execute("UPDATE jobs SET status = ? WHERE id = ?", (status, job_id))
    conn.commit()
    conn.close()

def get_job(job_id):
    conn = sqlite3.connect(DB)
    conn.row_factory = sqlite3.Row
    c = conn.cursor()
    c.execute("SELECT * FROM jobs WHERE id = ?", (job_id,))
    row = c.fetchone()
    conn.close()
    return dict(row) if row else None
```

### 4C. `printer.py`
Create this file in `printq/`:

```python
import os
import subprocess

def print_file(filepath, copies=1):
    """
    Sends a file to the default Windows printer.
    Works for PDF, DOCX, JPG, PNG.
    """
    if not os.path.exists(filepath):
        return False, "File not found"

    ext = filepath.lower().split(".")[-1]

    try:
        if ext == "pdf":
            # Uses Adobe Acrobat or built-in PDF reader
            # Option A: SumatraPDF (recommended - free, silent print)
            # Download SumatraPDF and put it in your project folder
            sumatra = r"C:\Program Files\SumatraPDF\SumatraPDF.exe"
            if os.path.exists(sumatra):
                cmd = [sumatra, "-print-to-default", "-print-settings",
                       f"{copies}x", filepath]
                subprocess.Popen(cmd)
            else:
                # Fallback: open with default app (shows dialog)
                os.startfile(filepath, "print")

        elif ext == "docx":
            # Uses Microsoft Word if installed
            import win32com.client
            word = win32com.client.Dispatch("Word.Application")
            doc = word.Documents.Open(os.path.abspath(filepath))
            doc.PrintOut(Copies=copies)
            doc.Close(False)
            word.Quit()

        elif ext in ["jpg", "jpeg", "png"]:
            os.startfile(filepath, "print")

        return True, "Print sent"

    except Exception as e:
        return False, str(e)
```

### 4D. `app.py`
Create this file in `printq/` — this is the main server:

```python
import os
from flask import (Flask, request, jsonify, render_template,
                   send_from_directory, redirect, url_for)
from database import init_db, add_job, get_all_jobs, update_status, get_job
from printer import print_file

app = Flask(__name__)

UPLOAD_FOLDER = "uploads"
ALLOWED_EXTENSIONS = {"pdf", "docx", "jpg", "jpeg", "png"}
MAX_FILE_MB = 20
app.config["MAX_CONTENT_LENGTH"] = MAX_FILE_MB * 1024 * 1024

# ── Helpers ──────────────────────────────────────────────────
def allowed_file(filename):
    return "." in filename and filename.rsplit(".", 1)[1].lower() in ALLOWED_EXTENSIONS

# ── Student Upload Page ───────────────────────────────────────
@app.route("/")
def upload_page():
    return render_template("upload.html")

@app.route("/upload", methods=["POST"])
def upload():
    name   = request.form.get("name", "").strip()
    color  = request.form.get("color", "B&W")
    paper  = request.form.get("paper", "Short")
    copies = int(request.form.get("copies", 1))
    notes  = request.form.get("notes", "")
    file   = request.files.get("file")

    if not name:
        return jsonify({"error": "Name is required"}), 400
    if not file or file.filename == "":
        return jsonify({"error": "No file selected"}), 400
    if not allowed_file(file.filename):
        return jsonify({"error": "File type not allowed"}), 400

    # Save file
    safe_name = f"{name.replace(' ','_')}_{file.filename}"
    save_path = os.path.join(UPLOAD_FOLDER, safe_name)
    file.save(save_path)

    # Add to database
    job_id = add_job(name, safe_name, color, paper, copies, notes)

    return jsonify({"queue_number": job_id, "message": "Upload successful"})

# ── Admin Dashboard ───────────────────────────────────────────
@app.route("/admin")
def admin():
    return render_template("dashboard.html")

@app.route("/api/jobs")
def api_jobs():
    return jsonify(get_all_jobs())

@app.route("/api/print/<int:job_id>", methods=["POST"])
def api_print(job_id):
    job = get_job(job_id)
    if not job:
        return jsonify({"error": "Job not found"}), 404

    filepath = os.path.join(UPLOAD_FOLDER, job["filename"])
    success, msg = print_file(filepath, job["copies"])

    if success:
        update_status(job_id, "done")
        return jsonify({"status": "printed"})
    else:
        return jsonify({"error": msg}), 500

@app.route("/api/cancel/<int:job_id>", methods=["POST"])
def api_cancel(job_id):
    update_status(job_id, "cancelled")
    return jsonify({"status": "cancelled"})

@app.route("/api/preview/<int:job_id>")
def api_preview(job_id):
    job = get_job(job_id)
    if not job:
        return jsonify({"error": "Not found"}), 404
    return send_from_directory(UPLOAD_FOLDER, job["filename"])

# ── Start ─────────────────────────────────────────────────────
if __name__ == "__main__":
    os.makedirs(UPLOAD_FOLDER, exist_ok=True)
    init_db()
    # host="0.0.0.0" makes it accessible from other devices on your Wi-Fi
    app.run(host="0.0.0.0", port=5000, debug=True)
```

---

## STEP 5 — Connect the HTML Files to Flask

### Upload page
Take your `upload.html` file and put it inside `templates/`.

Find this line in the JavaScript:
```javascript
/* --- REAL UPLOAD (uncomment when Flask is running) --- */
```
**Delete the fake progress bar simulation** and **uncomment** the real fetch block below it. It should look like:

```javascript
const formData = new FormData();
formData.append('name', name);
formData.append('color', document.querySelector('[name=color]:checked').value);
formData.append('paper', document.querySelector('[name=paper]:checked').value);
formData.append('copies', copies);
formData.append('notes', document.getElementById('notes').value);
formData.append('file', file);

const resp = await fetch('/upload', { method: 'POST', body: formData });
const data = await resp.json();
document.getElementById('queueNum').textContent = '#' + data.queue_number;
document.getElementById('successOverlay').classList.add('show');
submitBtn.disabled = false;
```

### Admin dashboard
Put `admin-dashboard.html` inside `templates/` and rename it to `dashboard.html`.

At the bottom, update the JavaScript to fetch real data from Flask. Replace the fake `queue` and `history` arrays with:

```javascript
// Load jobs from Flask on page load
async function loadJobs() {
    const resp = await fetch('/api/jobs');
    const jobs = await resp.json();
    queue = jobs.filter(j => j.status === 'waiting' || j.status === 'printing');
    history = jobs.filter(j => j.status === 'done' || j.status === 'cancelled');
    renderQueue();
    renderHistory();
}

// Call real API for print/cancel
async function printJob(id) {
    await fetch(`/api/print/${id}`, { method: 'POST' });
    loadJobs();
    showToast('Printed', 'Job sent to printer');
}

async function cancelJob(id) {
    await fetch(`/api/cancel/${id}`, { method: 'POST' });
    loadJobs();
    showToast('Cancelled', 'Job removed from queue', true);
}

// Auto-refresh every 5 seconds
setInterval(loadJobs, 5000);
loadJobs();
```

---

## STEP 6 — Run the Server

In VS Code terminal:

```bash
python app.py
```

You'll see:
```
* Running on http://0.0.0.0:5000
* Running on http://192.168.1.10:5000  ← This is your shop's URL
```

---

## STEP 7 — Connect Students

### Find Your PC's IP Address
Open Command Prompt and type:
```
ipconfig
```
Look for **IPv4 Address** under your Wi-Fi adapter.
Example: `192.168.1.10`

### Share These URLs:
| Who | URL |
|-----|-----|
| Students | `http://192.168.1.10:5000` |
| You (admin) | `http://192.168.1.10:5000/admin` |

### Make a QR Code (free):
Go to https://qr-code-generator.com and paste the student URL.
Print the QR code and tape it to your counter.

---

## STEP 8 — Auto-Start on Boot (Optional)

So you don't have to manually run `python app.py` every morning:

1. Create a file called `start_printq.bat` on your Desktop:
```bat
@echo off
cd C:\Users\YourName\Desktop\printq
python app.py
pause
```

2. Press `Win+R` → type `shell:startup` → paste a shortcut to the `.bat` file there.

Now it starts automatically when Windows boots.

---

## Final Folder Structure

```
printq/
├── app.py
├── database.py
├── printer.py
├── requirements.txt
├── printq.db          ← created automatically
├── uploads/           ← files saved here
└── templates/
    ├── upload.html    ← student page
    └── dashboard.html ← your admin page
```

---

## Quick Troubleshooting

| Problem | Fix |
|---------|-----|
| `python not found` | Reinstall Python, check "Add to PATH" |
| `flask not found` | Run `pip install flask` again |
| Students can't connect | Make sure they're on the same Wi-Fi |
| File won't print | Install SumatraPDF for PDFs |
| Port already in use | Change `port=5000` to `port=5001` in app.py |

---

## What to Add Next (After It Works)

- **Auto-pricing** — calculate cost based on pages × copies in `app.py`
- **GCash receipt upload** — add a second file field for payment proof  
- **File expiry** — delete files older than 24 hours with a scheduled task
- **Colored vs B&W printer** — route jobs to different printers in `printer.py`
- **Student queue number display** — a big TV screen showing who's next
