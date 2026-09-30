import os
import smtplib
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart

from flask import (
    Flask,
    render_template,
    request,
    redirect,
    url_for,
    session,
    flash
)

import psycopg2
from psycopg2.extras import RealDictCursor


app = Flask(__name__)
app.secret_key = os.getenv("SECRET_KEY", "micro-budgeting-secret-key")


# =========================================================
# DATABASE CONNECTION
# =========================================================

def get_db_connection():
    database_url = os.getenv("DATABASE_URL")

    if not database_url:
        raise Exception("DATABASE_URL is not configured.")

    return psycopg2.connect(database_url)


# =========================================================
# CREATE DATABASE TABLES
# =========================================================

def initialize_database():

    conn = get_db_connection()
    cursor = conn.cursor()

    cursor.execute("""
        CREATE TABLE IF NOT EXISTS users (
            user_id SERIAL PRIMARY KEY,
            name VARCHAR(100) NOT NULL,
            email VARCHAR(150) UNIQUE NOT NULL,
            password VARCHAR(255) NOT NULL
        )
    """)

    cursor.execute("""
        CREATE TABLE IF NOT EXISTS transactions (
            transaction_id SERIAL PRIMARY KEY,
            transaction_type VARCHAR(20) NOT NULL,
            amount NUMERIC(12,2) NOT NULL,
            category VARCHAR(100),
            transaction_date DATE NOT NULL,
            description TEXT,
            user_id INTEGER REFERENCES users(user_id)
        )
    """)

    cursor.execute("""
        CREATE TABLE IF NOT EXISTS budget (
            budget_id SERIAL PRIMARY KEY,
            user_id INTEGER REFERENCES users(user_id),
            budget_amount NUMERIC(12,2) NOT NULL DEFAULT 0
        )
    """)

    conn.commit()
    cursor.close()
    conn.close()


# =========================================================
# EMAIL NOTIFICATION
# =========================================================

def send_registration_email(name, email):

    sender_email = os.getenv("EMAIL_ADDRESS")
    app_password = os.getenv("EMAIL_APP_PASSWORD")
    notify_email = os.getenv("NOTIFY_EMAIL")

   
