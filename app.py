from flask import Flask, request, jsonify, session
from flask_cors import CORS
from flask_mail import Mail, Message
import os
import psycopg2
from psycopg2.extras import RealDictCursor
import time
import secrets

# --- Flask App Setup ---
app = Flask(__name__)
app.secret_key = os.environ.get("SECRET_KEY", "your-secret-key")
CORS(app, origins=["https://ecocarbon.onrender.com", "http://localhost:5173"], supports_credentials=True)

# --- Mail Setup ---
app.config["MAIL_SERVER"] = "smtp.gmail.com"
app.config["MAIL_PORT"] = 587
app.config["MAIL_USE_TLS"] = True
app.config["MAIL_USERNAME"] = os.environ.get("MAIL_USERNAME", "jadhavavi7620@gmail.com")
app.config["MAIL_PASSWORD"] = os.environ.get("MAIL_PASSWORD", "pfwhfzhxcucbcoiy")

mail = Mail(app)
otp_storage = {}  # { email: {otp: 123456, expires: timestamp} }

# --- Database Setup ---
DATABASE_URL = os.environ.get("DATABASE_URL")
if not DATABASE_URL:
    raise ValueError("DATABASE_URL environment variable not set!")

def init_db():
    conn = psycopg2.connect(DATABASE_URL)
    cursor = conn.cursor()
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS submissions (
            id SERIAL PRIMARY KEY,
            name TEXT NOT NULL,
            email TEXT NOT NULL,
            company TEXT,
            phone TEXT,
            service TEXT,
            message TEXT NOT NULL,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
    """)
    conn.commit()
    cursor.close()
    conn.close()

init_db()

# --- OTP Functions ---
def send_otp_email(email):
    otp = secrets.randbelow(900000) + 100000
    otp_storage[email] = {"otp": otp, "expires": time.time() + 300}

    msg = Message(
        "Your Admin OTP",
        sender=app.config["MAIL_USERNAME"],
        recipients=[email]
    )
    msg.body = f"Your OTP is {otp}. It will expire in 5 minutes."
    mail.send(msg)
    return otp

def verify_otp(email, otp):
    record = otp_storage.get(email)
    if not record:
        return False, "OTP not requested"
    if time.time() > record["expires"]:
        return False, "OTP expired"
    if str(record["otp"]) == str(otp):
        return True, "OTP verified"
    return False, "Invalid OTP"

# ======================
# API 1: Save Contact Form
# ======================
@app.route("/api/contact", methods=["POST"])
def save_contact():
    data = request.get_json()
    name = data.get("name")
    email = data.get("email")
    company = data.get("company", "")
    phone = data.get("phone", "")
    service = data.get("service", "")
    message = data.get("message")

    if not name or not email or not message:
        return jsonify({"error": "Missing required fields"}), 400

    conn = psycopg2.connect(DATABASE_URL)
    cursor = conn.cursor()
    cursor.execute("""
        INSERT INTO submissions (name, email, company, phone, service, message)
        VALUES (%s, %s, %s, %s, %s, %s)
    """, (name, email, company, phone, service, message))
    conn.commit()
    cursor.close()
    conn.close()

    return jsonify({"message": "Form submitted successfully!"}), 201

# ======================
# API 2: Get Submissions (Admin Only)
# ======================
@app.route("/api/submissions", methods=["GET"])
def get_submissions():
    if not session.get("admin"):
        return jsonify({"error": "Unauthorized"}), 403

    conn = psycopg2.connect(DATABASE_URL, cursor_factory=RealDictCursor)
    cursor = conn.cursor()
    cursor.execute("SELECT * FROM submissions ORDER BY created_at DESC")
    rows = cursor.fetchall()
    cursor.close()
    conn.close()
    return jsonify(rows)

# ======================
# API 3: Send OTP (Admin Login)
# ======================
@app.route("/api/send-otp", methods=["POST"])
def send_otp():
    data = request.get_json()
    email = data.get("email")

    if email != "jadhavaj7620@gmail.com":
        return jsonify({"error": "Unauthorized"}), 403

    try:
        send_otp_email(email)
        return jsonify({"message": "OTP sent to email"}), 200
    except Exception as e:
        return jsonify({"error": str(e)}), 500

# ======================
# API 4: Verify OTP
# ======================
@app.route("/api/verify-otp", methods=["POST"])
def verify_otp_route():
    data = request.get_json()
    email = data.get("email")
    otp = data.get("otp")

    if not email or not otp:
        return jsonify({"error": "Email and OTP required"}), 400

    success, msg = verify_otp(email, otp)
    if success:
        session["admin"] = True
        return jsonify({"message": "Login successful"}), 200
    return jsonify({"error": msg}), 400

# ======================
# API 5: Admin Dashboard
# ======================
@app.route("/api/admin-dashboard", methods=["GET"])
def admin_dashboard():
    if not session.get("admin"):
        return jsonify({"error": "Unauthorized"}), 403
    return jsonify({"message": "Welcome to Admin Dashboard"}), 200

# ======================
# Run Server
# ======================
if __name__ == "__main__":
    app.run(host="0.0.0.0", port=int(os.environ.get("PORT", 5000)))