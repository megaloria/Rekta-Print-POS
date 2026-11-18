import qrcode
import os

# ✏️ Replace with your actual PC IP address
IP = "192.168.1.17"
PORT = "5000"

url = f"http://{IP}:{PORT}"

qr = qrcode.QRCode(
    version=1,
    error_correction=qrcode.constants.ERROR_CORRECT_H,
    box_size=10,
    border=4,
)

qr.add_data(url)
qr.make(fit=True)

img = qr.make_image(fill_color="black", back_color="white")
output = os.path.join(os.path.dirname(__file__), "printq_qr.png")
img.save(output)

print(f"✅ QR Code saved to: {output}")
print(f"   URL: {url}")
print(f"   Students scan this to open the upload page.")