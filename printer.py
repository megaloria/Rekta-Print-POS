import os
import subprocess


def _get_printer_settings():
    """
    Reads printer config from the database at print time so changes
    made in Settings take effect immediately without restarting the server.
    Falls back to safe defaults if the DB is unavailable.
    """
    try:
        from database import get_setting
        return {
            "bw":      get_setting("printer_bw",      "EPSON WF-C5890 Series (Black & White)"),
            "colored": get_setting("printer_colored",  "EPSON WF-C5890 Series (GENERAL)"),
            "sumatra": get_setting("sumatra_path",     r"C:\Users\ByteComputer\AppData\Local\SumatraPDF\SumatraPDF.exe"),
        }
    except Exception:
        return {
            "bw":      "EPSON WF-C5890 Series (Black & White)",
            "colored": "EPSON WF-C5890 Series (GENERAL)",
            "sumatra": r"C:\Users\ByteComputer\AppData\Local\SumatraPDF\SumatraPDF.exe",
        }


def get_available_printers():
    """
    Returns a list of printer names installed on Windows.
    Used by the Settings page to populate a dropdown.
    """
    try:
        result = subprocess.run(
            ["powershell", "Get-Printer | Select-Object -ExpandProperty Name"],
            capture_output=True, text=True, timeout=10
        )
        printers = [p.strip() for p in result.stdout.strip().splitlines() if p.strip()]
        return printers
    except Exception as e:
        return []


def print_file(filepath, copies=1, color="B&W", paper="Short"):
    if not os.path.exists(filepath):
        return False, "File not found: " + filepath

    cfg = _get_printer_settings()
    printer = cfg["colored"] if color == "Colored" else cfg["bw"]
    sumatra = cfg["sumatra"]

    ext = filepath.lower().split(".")[-1]
    filepath = os.path.abspath(filepath)

    try:
        if ext == "pdf":
            return print_pdf(filepath, copies, printer, color, paper, sumatra)
        elif ext == "docx":
            return print_docx(filepath, copies, printer)
        elif ext in ["jpg", "jpeg", "png"]:
            return print_image(filepath, copies, printer)
        else:
            return False, "Unsupported file type: " + ext
    except Exception as e:
        return False, str(e)


def _set_printer_paper(printer_name, paper):
    """
    Sets the default paper size on the Windows printer driver before printing.
    This ensures the printer driver uses the right tray/paper size.
    Paper sizes: Short=Letter(1), Long=Legal(5), A4=A4(9)
    """
    # Windows DMPAPER constants
    paper_code = {
        "Short": 1,   # DMPAPER_LETTER  8.5x11
        "Long":  5,   # DMPAPER_LEGAL   8.5x14
        "A4":    9,   # DMPAPER_A4      210x297mm
    }.get(paper, 1)

    ps = f"""
$printerName = "{printer_name}"
$printer = Get-WmiObject -Class Win32_Printer | Where-Object {{ $_.Name -eq $printerName }}
if ($printer) {{
    $printerConfig = Get-WmiObject -Class Win32_PrinterConfiguration | Where-Object {{ $_.Name -eq $printerName }}
    if ($printerConfig) {{
        $printerConfig.PaperSize = {paper_code}
        $printerConfig.Put() | Out-Null
    }}
}}
"""
    try:
        subprocess.run(
            ["powershell", "-Command", ps],
            capture_output=True, text=True, timeout=10
        )
        print(f"[PAPER SIZE SET] {printer_name} → {paper} (code {paper_code})")
    except Exception as e:
        print(f"[PAPER SIZE SET FAILED] {e}")


def print_pdf(filepath, copies, printer, color="B&W", paper="Short", sumatra=None):
    if sumatra is None:
        cfg = _get_printer_settings()
        sumatra = cfg["sumatra"]

    if not os.path.exists(sumatra):
        return False, "SumatraPDF not found at: " + sumatra

    # Set paper size on the printer driver first
    _set_printer_paper(printer, paper)

    # SumatraPDF paper size strings
    paper_size = {
        "Short": "letter",
        "Long":  "legal",
        "A4":    "A4"
    }.get(paper, "letter")

    settings_parts = [f"{copies}x", paper_size, "fit"]
    if color == "B&W":
        settings_parts += ["grayscale", "monochrome"]

    settings = ",".join(settings_parts)

    cmd = [
        sumatra,
        "-print-to", printer,
        "-print-settings", settings,
        filepath
    ]

    print("[PRINT CMD] " + " ".join(cmd))
    print(f"[PAPER] requested='{paper}' → sumatra='{paper_size}'")
    result = subprocess.run(cmd, capture_output=True, text=True, timeout=60)
    print("[RETURN CODE] " + str(result.returncode))
    if result.stdout: print("[STDOUT] " + result.stdout)
    if result.stderr: print("[STDERR] " + result.stderr)
    return True, f"PDF sent to {printer} ({paper_size}, {color})"


def print_docx(filepath, copies, printer):
    try:
        import win32com.client
        word = win32com.client.Dispatch("Word.Application")
        word.Visible = False
        doc = word.Documents.Open(filepath)
        doc.PrintOut(Copies=copies, Background=False)
        doc.Close(False)
        word.Quit()
        return True, "DOCX sent to " + printer
    except ImportError:
        result = subprocess.run(
            ["powershell", "-Command",
             "Start-Process -FilePath \"" + filepath + "\" -Verb Print -Wait"],
            capture_output=True, text=True
        )
        print("[DOCX STDOUT] " + result.stdout)
        print("[DOCX STDERR] " + result.stderr)
        return True, "DOCX sent via shell"


def print_image(filepath, copies, printer):
    for _ in range(copies):
        result = subprocess.run(
            ["powershell", "-Command",
             "Start-Process -FilePath \"" + filepath + "\" -Verb Print -Wait"],
            capture_output=True, text=True
        )
        print("[IMAGE STDOUT] " + result.stdout)
        print("[IMAGE STDERR] " + result.stderr)
    return True, "Image sent to " + printer
