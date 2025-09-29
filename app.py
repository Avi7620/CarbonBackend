from flask import Flask, request, jsonify, session
from flask_cors import CORS
import os
import psycopg2
from psycopg2.extras import RealDictCursor
import random, smtplib
from email.mime.text import MIMEText

app = Flask(__name__)

# --- Config ---
app.secret_key = os.environ.get("SECRET_KEY", "supersecret")  # Required for sessions
CORS(
    app,
    supports_credentials=True,
    origins=["https://ecocarbon.onrender.com", "http://localhost:5173"]
)

DATABASE_URL = os.environ.get("DATABASE_URL")
if not DATABASE_URL:
    raise ValueError("DATABASE_URL environment variable not set!")

ADMIN_EMAIL = "jadhavaj7620@gmail.com"


# --- Initialize Postgres Database ---
def init_db():
    conn = psycopg2.connect(DATABASE_URL)
    cursor = conn.cursor()
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS contacts (
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


# --- Contact Form API ---
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
        INSERT INTO contacts (name, email, company, phone, service, message)
        VALUES (%s, %s, %s, %s, %s, %s)
    """, (name, email, company, phone, service, message))
    conn.commit()
    cursor.close()
    conn.close()

    return jsonify({"message": "Form submitted successfully!"}), 201


@app.route("/api/contacts", methods=["GET"])
def get_contacts():
    if not session.get("is_admin"):
        return jsonify({"error": "Unauthorized"}), 403

    conn = psycopg2.connect(DATABASE_URL, cursor_factory=RealDictCursor)
    cursor = conn.cursor()
    cursor.execute("SELECT * FROM contacts ORDER BY created_at DESC")
    rows = cursor.fetchall()
    cursor.close()
    conn.close()
    return jsonify(rows)


# --- OTP Login API ---
@app.route("/api/send-otp", methods=["POST"])
def send_otp():
    data = request.get_json()
    email = data.get("email")

    if not email or email.lower() != ADMIN_EMAIL:
        return jsonify({"error": "Unauthorized access"}), 403

    otp = str(random.randint(100000, 999999))  # 6-digit OTP
    session["otp"] = otp
    session["email"] = email

    try:
        msg = MIMEText(f"Your Admin OTP is: {otp}")
        msg["Subject"] = "Admin Login OTP"
        msg["From"] = os.environ.get("EMAIL_USER")
        msg["To"] = email

        with smtplib.SMTP("smtp.gmail.com", 587) as server:
            server.starttls()
            server.login(os.environ["EMAIL_USER"], os.environ["EMAIL_PASS"])
            server.send_message(msg)

        return jsonify({"message": "OTP sent successfully"})
    except Exception as e:
        return jsonify({"error": str(e)}), 500


@app.route("/api/verify-otp", methods=["POST"])
def verify_otp():
    data = request.get_json()
    email = data.get("email")
    otp = data.get("otp")

    if email != session.get("email") or otp != session.get("otp"):
        return jsonify({"error": "Invalid OTP"}), 400

    session["is_admin"] = True
    return jsonify({"message": "Login successful"})


if __name__ == "__main__":
    app.run(host="0.0.0.0", port=int(os.environ.get("PORT", 5000)))
