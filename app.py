from flask import Flask, request, jsonify, session
from flask_cors import CORS
import os
import psycopg2
from psycopg2.extras import RealDictCursor
import smtplib
import random
import string
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart
from datetime import datetime, timedelta

app = Flask(__name__)
app.secret_key = os.environ.get("SECRET_KEY", "your-secret-key-here")
CORS(app, origins=["https://ecocarbon.onrender.com", "http://localhost:5173"], supports_credentials=True)

# Admin email configuration
ADMIN_EMAIL = "jadhavaj7620@gmail.com"

# Email configuration
SMTP_SERVER = os.environ.get("SMTP_SERVER", "smtp.gmail.com")
SMTP_PORT = int(os.environ.get("SMTP_PORT", 587))
EMAIL_ADDRESS = os.environ.get("EMAIL_ADDRESS", "your-email@gmail.com")
EMAIL_PASSWORD = os.environ.get("EMAIL_PASSWORD", "your-app-password")

DATABASE_URL = os.environ.get("DATABASE_URL")

if not DATABASE_URL:
    raise ValueError("DATABASE_URL environment variable not set!")

# Schema name for this service
SCHEMA_NAME = "ecocarbon_schema"

# --- Initialize Postgres Database with Schema ---
def init_db():
    conn = psycopg2.connect(DATABASE_URL)
    cursor = conn.cursor()
    
    # Create schema if not exists
    cursor.execute(f"CREATE SCHEMA IF NOT EXISTS {SCHEMA_NAME}")
    
    # Create tables in the specific schema
    cursor.execute(f"""
        CREATE TABLE IF NOT EXISTS {SCHEMA_NAME}.contacts (
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
    
    # Create table for OTP storage in the schema
    cursor.execute(f"""
        CREATE TABLE IF NOT EXISTS {SCHEMA_NAME}.admin_otps (
            id SERIAL PRIMARY KEY,
            email TEXT NOT NULL,
            otp TEXT NOT NULL,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            expires_at TIMESTAMP NOT NULL,
            used BOOLEAN DEFAULT FALSE
        )
    """)
    conn.commit()
    cursor.close()
    conn.close()

init_db()

def get_connection():
    """Get database connection with schema set"""
    conn = psycopg2.connect(DATABASE_URL)
    cursor = conn.cursor()
    # Set the search path to our schema
    cursor.execute(f"SET search_path TO {SCHEMA_NAME}")
    conn.commit()
    cursor.close()
    return conn

def generate_otp(length=6):
    """Generate a random OTP"""
    return ''.join(random.choices(string.digits, k=length))

def send_otp_email(email, otp):
    """Send OTP to email"""
    try:
        msg = MIMEMultipart()
        msg['From'] = EMAIL_ADDRESS
        msg['To'] = email
        msg['Subject'] = "Admin Login OTP"
        
        body = f"""
        <html>
            <body>
                <h2>Admin Login OTP</h2>
                <p>Your OTP for admin login is: <strong>{otp}</strong></p>
                <p>This OTP will expire in 10 minutes.</p>
                <p>If you didn't request this OTP, please ignore this email.</p>
            </body>
        </html>
        """
        
        msg.attach(MIMEText(body, 'html'))
        
        server = smtplib.SMTP(SMTP_SERVER, SMTP_PORT)
        server.starttls()
        server.login(EMAIL_ADDRESS, EMAIL_PASSWORD)
        text = msg.as_string()
        server.sendmail(EMAIL_ADDRESS, email, text)
        server.quit()
        return True
    except Exception as e:
        print(f"Error sending email: {e}")
        return False

# --- OTP Endpoints ---
@app.route("/api/send-otp", methods=["POST"])
def send_otp():
    data = request.get_json()
    email = data.get("email", "").strip().lower()
    
    # Only allow admin email
    if email != ADMIN_EMAIL:
        return jsonify({"error": "Unauthorized access"}), 403
    
    # Generate OTP
    otp = generate_otp()
    expires_at = datetime.now() + timedelta(minutes=10)
    
    # Store OTP in database
    conn = get_connection()
    cursor = conn.cursor()
    
    # Clean up expired OTPs
    cursor.execute("DELETE FROM admin_otps WHERE expires_at < NOW() OR used = TRUE")
    
    # Insert new OTP
    cursor.execute("""
        INSERT INTO admin_otps (email, otp, expires_at)
        VALUES (%s, %s, %s)
    """, (email, otp, expires_at))
    
    conn.commit()
    cursor.close()
    conn.close()
    
    # Send OTP via email
    if send_otp_email(email, otp):
        return jsonify({"message": "OTP sent successfully"}), 200
    else:
        return jsonify({"error": "Failed to send OTP"}), 500

@app.route("/api/verify-otp", methods=["POST"])
def verify_otp():
    data = request.get_json()
    email = data.get("email", "").strip().lower()
    otp = data.get("otp", "").strip()
    
    # Only allow admin email
    if email != ADMIN_EMAIL:
        return jsonify({"error": "Unauthorized access"}), 403
    
    conn = get_connection()
    cursor = conn.cursor(cursor_factory=RealDictCursor)
    
    # Find valid OTP
    cursor.execute("""
        SELECT * FROM admin_otps 
        WHERE email = %s AND otp = %s AND expires_at > NOW() AND used = FALSE
        ORDER BY created_at DESC LIMIT 1
    """, (email, otp))
    
    otp_record = cursor.fetchone()
    
    if otp_record:
        # Mark OTP as used
        cursor.execute("UPDATE admin_otps SET used = TRUE WHERE id = %s", (otp_record['id'],))
        conn.commit()
        
        # Set session
        session['admin_logged_in'] = True
        session['admin_email'] = email
        
        cursor.close()
        conn.close()
        return jsonify({"message": "Login successful"}), 200
    else:
        cursor.close()
        conn.close()
        return jsonify({"error": "Invalid or expired OTP"}), 401

@app.route("/api/admin/logout", methods=["POST"])
def admin_logout():
    session.clear()
    return jsonify({"message": "Logged out successfully"}), 200

@app.route("/api/admin/check-auth", methods=["GET"])
def check_admin_auth():
    if session.get('admin_logged_in') and session.get('admin_email') == ADMIN_EMAIL:
        return jsonify({"authenticated": True}), 200
    return jsonify({"authenticated": False}), 401

# --- Protected Routes ---
@app.route("/api/contacts", methods=["GET"])
def get_contacts():
    # Check admin authentication
    if not session.get('admin_logged_in') or session.get('admin_email') != ADMIN_EMAIL:
        return jsonify({"error": "Unauthorized"}), 401
    
    conn = get_connection()
    cursor = conn.cursor(cursor_factory=RealDictCursor)
    cursor.execute("SELECT * FROM contacts ORDER BY created_at DESC")
    rows = cursor.fetchall()
    cursor.close()
    conn.close()
    return jsonify(rows)

# --- API Route to Save Form Data ---
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

    conn = get_connection()
    cursor = conn.cursor()
    cursor.execute("""
        INSERT INTO contacts (name, email, company, phone, service, message)
        VALUES (%s, %s, %s, %s, %s, %s)
    """, (name, email, company, phone, service, message))
    conn.commit()
    cursor.close()
    conn.close()

    return jsonify({"message": "Form submitted successfully!"}), 201

# Health check endpoint
@app.route("/api/health", methods=["GET"])
def health_check():
    return jsonify({"status": "healthy", "message": "EcoCarbon API is running"})

if __name__ == "__main__":
    app.run(host="0.0.0.0", port=int(os.environ.get("PORT", 5000)))