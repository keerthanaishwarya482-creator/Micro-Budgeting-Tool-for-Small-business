from flask import Flask, render_template, request, redirect, session
import psycopg2
from psycopg2.extras import RealDictCursor
import os
import smtplib
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart


app = Flask(__name__)

app.secret_key = os.getenv(
    "SECRET_KEY",
    "micro_budgeting_secret_key"
)


# =========================================================
# DATABASE CONNECTION
# =========================================================

def get_db_connection():

    database_url = os.getenv("DATABASE_URL")

    if not database_url:
        raise Exception(
            "DATABASE_URL environment variable is not set."
        )

    return psycopg2.connect(database_url)


# =========================================================
# EMAIL NOTIFICATION
# =========================================================

def send_registration_email(name, email):

    sender_email = os.getenv("EMAIL_ADDRESS")
    app_password = os.getenv("EMAIL_APP_PASSWORD")
    notify_email = os.getenv("NOTIFY_EMAIL")

    # If email settings are missing, skip email
    if not sender_email or not app_password or not notify_email:
        print("Email settings are missing.")
        return

    try:

        message = MIMEMultipart()

        message["From"] = sender_email
        message["To"] = notify_email
        message["Subject"] = "New Micro Budgeting App Registration"

        body = f"""
A new user has registered in your Micro Budgeting App.

Name: {name}
Email: {email}

The user has successfully created an account.
"""

        message.attach(
            MIMEText(body, "plain")
        )

        # Gmail SMTP
        with smtplib.SMTP(
            "smtp.gmail.com",
            587
        ) as server:

            server.starttls()

            server.login(
                sender_email,
                app_password
            )

            server.sendmail(
                sender_email,
                notify_email,
                message.as_string()
            )

        print("Registration email sent successfully.")

    except Exception as error:

        # Email failure should not stop registration
        print(
            "Email notification failed:",
            error
        )


# =========================================================
# CREATE DATABASE TABLES
# =========================================================

def initialize_database():

    db = get_db_connection()
    cursor = db.cursor()

    # USERS TABLE
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS users (
            user_id SERIAL PRIMARY KEY,
            name VARCHAR(100),
            email VARCHAR(100) UNIQUE,
            password VARCHAR(255)
        )
    """)

    # TRANSACTIONS TABLE
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS transactions (
            transaction_id SERIAL PRIMARY KEY,
            transaction_type VARCHAR(20),
            amount DECIMAL(10,2),
            category VARCHAR(50),
            transaction_date DATE,
            description VARCHAR(255),
            user_id INTEGER REFERENCES users(user_id)
        )
    """)

    # BUDGET TABLE
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS budget (
            budget_id SERIAL PRIMARY KEY,
            budget_amount DECIMAL(10,2)
        )
    """)

    db.commit()

    cursor.close()
    db.close()


# =========================================================
# LOGIN REQUIRED CHECK
# =========================================================

def login_required():

    if "user_id" not in session:
        return False

    return True


# =========================================================
# REGISTER
# =========================================================

@app.route("/register", methods=["GET", "POST"])
def register():

    if request.method == "POST":

        name = request.form["name"]
        email = request.form["email"]
        password = request.form["password"]

        db = get_db_connection()
        cursor = db.cursor()

        # Check existing user
        cursor.execute(
            """
            SELECT user_id
            FROM users
            WHERE email = %s
            """,
            (email,)
        )

        existing_user = cursor.fetchone()

        if existing_user:

            cursor.close()
            db.close()

            return "Email already registered. Please login."

        # Create new user
        cursor.execute(
            """
            INSERT INTO users
            (name, email, password)
            VALUES (%s, %s, %s)
            RETURNING user_id
            """,
            (
                name,
                email,
                password
            )
        )

        cursor.fetchone()

        db.commit()

        cursor.close()
        db.close()

        # Send notification email
        send_registration_email(
            name,
            email
        )

        return redirect("/login")

    return render_template("register.html")


# =========================================================
# LOGIN
# =========================================================

@app.route("/login", methods=["GET", "POST"])
def login():

    if request.method == "POST":

        email = request.form["email"]
        password = request.form["password"]

        db = get_db_connection()

        cursor = db.cursor(
            cursor_factory=RealDictCursor
        )

        cursor.execute(
            """
            SELECT *
            FROM users
            WHERE email = %s
            AND password = %s
            """,
            (
                email,
                password
            )
        )

        user = cursor.fetchone()

        cursor.close()
        db.close()

        if user:

            session["user_id"] = user["user_id"]

            session["user_name"] = user["name"]

            session["user_email"] = user["email"]

            return redirect("/")

        return "Invalid email or password."

    return render_template("login.html")


# =========================================================
# LOGOUT
# =========================================================

@app.route("/logout")
def logout():

    session.clear()

    return redirect("/login")


# =========================================================
# PROFILE
# =========================================================

@app.route("/profile")
def profile():

    if not login_required():
        return redirect("/login")

    return render_template(
        "profile.html",
        user_name=session["user_name"],
        user_email=session["user_email"]
    )


# =========================================================
# DASHBOARD
# =========================================================

@app.route("/")
def home():

    if not login_required():
        return redirect("/login")

    user_id = session["user_id"]

    db = get_db_connection()

    cursor = db.cursor()

    # TOTAL INCOME
    cursor.execute(
        """
        SELECT COALESCE(SUM(amount), 0)
        FROM transactions
        WHERE transaction_type = 'Income'
        AND user_id = %s
        """,
        (user_id,)
    )

    total_income = cursor.fetchone()[0]

    # TOTAL EXPENSE
    cursor.execute(
        """
        SELECT COALESCE(SUM(amount), 0)
        FROM transactions
        WHERE transaction_type = 'Expense'
        AND user_id = %s
        """,
        (user_id,)
    )

    total_expense = cursor.fetchone()[0]

    # TOTAL BUDGET
    cursor.execute(
        """
        SELECT COALESCE(MAX(budget_amount), 0)
        FROM budget
        """
    )

    budget = cursor.fetchone()[0]

    # CURRENT BALANCE
    balance = total_income - total_expense

    # REMAINING BUDGET
    remaining_budget = budget - total_expense

    # CHART PERCENTAGES
    total_money = total_income + total_expense

    if total_money > 0:

        income_percentage = (
            total_income / total_money
        ) * 100

        expense_percentage = (
            total_expense / total_money
        ) * 100

    else:

        income_percentage = 0
        expense_percentage = 0

    cursor.close()
    db.close()

    return render_template(
        "index.html",

        total_income=total_income,

        total_expense=total_expense,

        balance=balance,

        budget=budget,

        remaining_budget=remaining_budget,

        income_percentage=income_percentage,

        expense_percentage=expense_percentage,

        user_name=session["user_name"]
    )


# =========================================================
# ADD TRANSACTION
# =========================================================

@app.route("/add", methods=["GET", "POST"])
def add_transaction():

    if not login_required():
        return redirect("/login")

    if request.method == "POST":

        transaction_type = request.form["transaction_type"]

        amount = request.form["amount"]

        category = request.form["category"]

        transaction_date = request.form["transaction_date"]

        description = request.form["description"]

        user_id = session["user_id"]

        db = get_db_connection()

        cursor = db.cursor()

        cursor.execute(
            """
            INSERT INTO transactions
            (
                transaction_type,
                amount,
                category,
                transaction_date,
                description,
                user_id
            )
            VALUES
            (
                %s,
                %s,
                %s,
               
