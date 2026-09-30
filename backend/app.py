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

app.secret_key = os.getenv(
    "SECRET_KEY",
    "micro-budgeting-secret-key"
)


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

    if not sender_email or not app_password or not notify_email:

        print("Email settings are missing.")

        return

    try:

        message = MIMEMultipart()

        message["From"] = sender_email
        message["To"] = notify_email
        message["Subject"] = "New Micro Budgeting App Registration"

        body = f"""
New user registered in Micro Budgeting App.

Name: {name}
Email: {email}

The user has successfully created an account.
"""

        message.attach(
            MIMEText(body, "plain")
        )

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

        print(
            "Registration email sent successfully."
        )

    except Exception as error:

        print(
            "Email notification failed:",
            error
        )


# =========================================================
# REGISTER
# =========================================================

@app.route(
    "/register",
    methods=["GET", "POST"]
)
def register():

    if request.method == "POST":

        name = request.form.get(
            "name",
            ""
        ).strip()

        email = request.form.get(
            "email",
            ""
        ).strip()

        password = request.form.get(
            "password",
            ""
        )

        if not name or not email or not password:

            flash(
                "Please fill all fields.",
                "error"
            )

            return redirect(
                url_for("register")
            )

        conn = get_db_connection()

        cursor = conn.cursor()

        try:

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

                flash(
                    "Email already registered.",
                    "error"
                )

                cursor.close()
                conn.close()

                return redirect(
                    url_for("register")
                )

            cursor.execute(
                """
                INSERT INTO users
                (
                    name,
                    email,
                    password
                )
                VALUES
                (
                    %s,
                    %s,
                    %s
                )
                RETURNING user_id
                """,
                (
                    name,
                    email,
                    password
                )
            )

            user_id = cursor.fetchone()[0]

            cursor.execute(
                """
                INSERT INTO budget
                (
                    user_id,
                    budget_amount
                )
                VALUES
                (
                    %s,
                    %s
                )
                """,
                (
                    user_id,
                    0
                )
            )

            conn.commit()

            cursor.close()
            conn.close()

            # Send email after successful registration
            send_registration_email(
                name,
                email
            )

            flash(
                "Registration successful. Please login.",
                "success"
            )

            return redirect(
                url_for("login")
            )

        except Exception as error:

            conn.rollback()

            cursor.close()
            conn.close()

            print(
                "Registration error:",
                error
            )

            flash(
                "Registration failed. Please try again.",
                "error"
            )

            return redirect(
                url_for("register")
            )

    return render_template(
        "register.html"
    )


# =========================================================
# LOGIN
# =========================================================

@app.route(
    "/login",
    methods=["GET", "POST"]
)
def login():

    if request.method == "POST":

        email = request.form.get(
            "email",
            ""
        ).strip()

        password = request.form.get(
            "password",
            ""
        )

        conn = get_db_connection()

        cursor = conn.cursor(
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
        conn.close()

        if user:

            session["user_id"] = user["user_id"]

            session["user_name"] = user["name"]

            session["user_email"] = user["email"]

            return redirect(
                url_for("dashboard")
            )

        flash(
            "Invalid email or password.",
            "error"
        )

        return redirect(
            url_for("login")
        )

    return render_template(
        "login.html"
    )


# =========================================================
# LOGOUT
# =========================================================

@app.route("/logout")
def logout():

    session.clear()

    return redirect(
        url_for("login")
    )


# =========================================================
# PROFILE
# =========================================================

@app.route("/profile")
def profile():

    if "user_id" not in session:

        return redirect(
            url_for("login")
        )

    conn = get_db_connection()

    cursor = conn.cursor(
        cursor_factory=RealDictCursor
    )

    cursor.execute(
        """
        SELECT
            user_id,
            name,
            email
        FROM users
        WHERE user_id = %s
        """,
        (
            session["user_id"],
        )
    )

    user = cursor.fetchone()

    cursor.close()
    conn.close()

    return render_template(
        "profile.html",
        user=user
    )


# =========================================================
# DASHBOARD
# =========================================================

@app.route("/")
def dashboard():

    if "user_id" not in session:

        return redirect(
            url_for("login")
        )

    user_id = session["user_id"]

    conn = get_db_connection()

    cursor = conn.cursor(
        cursor_factory=RealDictCursor
    )

    # Income

    cursor.execute(
        """
        SELECT
            COALESCE(SUM(amount), 0) AS total
        FROM transactions
        WHERE user_id = %s
        AND transaction_type = 'Income'
        """,
        (
            user_id,
        )
    )

    income_result = cursor.fetchone()

    total_income = float(
        income_result["total"] or 0
    )

    # Expense

    cursor.execute(
        """
        SELECT
            COALESCE(SUM(amount), 0) AS total
        FROM transactions
        WHERE user_id = %s
        AND transaction_type = 'Expense'
        """,
        (
            user_id,
        )
    )

    expense_result = cursor.fetchone()

    total_expense = float(
        expense_result["total"] or 0
    )

    # Balance

    balance = (
        total_income -
        total_expense
    )

    # Budget

    cursor.execute(
        """
        SELECT budget_amount
        FROM budget
        WHERE user_id = %s
        """,
        (
            user_id,
        )
    )

    budget_result = cursor.fetchone()

    budget_amount = float(
        budget_result["budget_amount"]
        if budget_result
        else 0
    )

    remaining_budget = (
        budget_amount -
        total_expense
    )

    # Recent transactions

    cursor.execute(
        """
        SELECT
            transaction_id,
            transaction_type,
            amount,
            category,
            transaction_date,
            description
        FROM transactions
        WHERE user_id = %s
        ORDER BY transaction_id DESC
        LIMIT 5
        """,
        (
            user_id,
        )
    )

    recent_transactions = cursor.fetchall()

    cursor.close()
    conn.close()

    return render_template(
        "index.html",
        total_income=total_income,
        total_expense=total_expense,
        balance=balance,
        budget_amount=budget_amount,
        remaining_budget=remaining_budget,
        recent_transactions=recent_transactions
    )


# =========================================================
# ADD TRANSACTION
# =========================================================

@app.route(
    "/add",
    methods=["GET", "POST"]
)
def add_transaction():

    if "user_id" not in session:

        return redirect(
            url_for("login")
        )

    if request.method == "POST":

        transaction_type = request.form.get(
            "transaction_type"
        )

        amount = request.form.get(
            "amount"
        )

        category = request.form.get(
            "category",
            ""
        )

        transaction_date = request.form.get(
            "transaction_date"
        )

        description = request.form.get(
            "description",
            ""
        )

        user_id = session["user_id"]

        conn = get_db_connection()

        cursor = conn.cursor()

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
                %s,
                %s,
                %s
            )
            """,
            (
                transaction_type,
                amount,
                category,
                transaction_date,
                description,
                user_id
            )
        )

        conn.commit()

        cursor.close()
        conn.close()

        return redirect(
            url_for("transactions")
        )

    return render_template(
        "add.html"
    )


# =========================================================
# VIEW / SEARCH TRANSACTIONS
# =========================================================

@app.route("/transactions")
def transactions():

    if "user_id" not in session:

        return redirect(
            url_for("login")
        )

    user_id = session["user_id"]

    search = request.args.get(
        "search",
        ""
    ).strip()

    transaction_type = request.args.get(
        "type",
        ""
    ).strip()

    conn = get_db_connection()

    cursor = conn.cursor(
        cursor_factory=RealDictCursor
    )

    query = """
        SELECT
            transaction_id,
            transaction_type,
            amount,
            category,
            transaction_date,
            description
        FROM transactions
        WHERE user_id = %s
    """

    parameters = [
        user_id
    ]

    if search:

        query += """
            AND
            (
                category ILIKE %s
                OR description ILIKE %s
            )
        """

        search_value = (
            "%" +
            search +
            "%"
        )

        parameters.extend(
            [
                search_value,
                search_value
            ]
        )

    if transaction_type:

        query += """
            AND transaction_type = %s
        """

        parameters.append(
            transaction_type
        )

    query += """
        ORDER BY transaction_id DESC
    """

    cursor.execute(
        query,
        parameters
    )

    transaction_list = cursor.fetchall()

    cursor.close()
    conn.close()

    return render_template(
        "transactions.html",
        transactions=transaction_list,
        search=search,
        selected_type=transaction_type
    )


# =========================================================
# EDIT TRANSACTION
# =========================================================

@app.route(
    "/edit/<int:transaction_id>",
    methods=["GET", "POST"]
)
def edit_transaction(
    transaction_id
):

    if "user_id" not in session:

        return redirect(
            url_for("login")
        )

    user_id = session["user_id"]

    conn = get_db_connection()

    cursor = conn.cursor(
        cursor_factory=RealDictCursor
    )

    if request.method == "POST":

        transaction_type = request.form.get(
            "transaction_type"
        )

        amount = request.form.get(
            "amount"
        )

        category = request.form.get(
            "category",
            ""
        )

        transaction_date = request.form.get(
            "transaction_date"
        )

        description = request.form.get(
            "description",
            ""
        )

        cursor.execute(
            """
            UPDATE transactions
            SET
                transaction_type = %s,
                amount = %s,
                category = %s,
                transaction_date = %s,
                description = %s
            WHERE transaction_id = %s
            AND user_id = %s
            """,
            (
                transaction_type,
                amount,
                category,
                transaction_date,
                description,
                transaction_id,
                user_id
            )
        )

        conn.commit()

        cursor.close()
        conn.close()

        return redirect(
            url_for("transactions")
        )

    cursor.execute(
        """
        SELECT *
        FROM transactions
        WHERE transaction_id = %s
        AND user_id = %s
        """,
        (
            transaction_id,
            user_id
        )
    )

    transaction = cursor.fetchone()

    cursor.close()
    conn.close()

    if not transaction:

        return "Transaction not found", 404

    return render_template(
        "edit.html",
        transaction=transaction
    )


# =========================================================
# DELETE TRANSACTION
# =========================================================

@app.route(
    "/delete/<int:transaction_id>"
)
def delete_transaction(
    transaction_id
):

    if "user_id" not in session:

        return redirect(
            url_for("login")
        )

    user_id = session["user_id"]

    conn = get_db_connection()

    cursor = conn.cursor()

    cursor.execute(
        """
        DELETE FROM transactions
        WHERE transaction_id = %s
        AND user_id = %s
        """,
        (
            transaction_id,
            user_id
        )
    )

    conn.commit()

    cursor.close()
    conn.close()

    return redirect(
        url_for("transactions")
    )


# =========================================================
# BUDGET
# =========================================================

@app.route(
    "/budget",
    methods=["GET", "POST"]
)
def budget():

    if "user_id" not in session:

        return redirect(
            url_for("login")
        )

    user_id = session["user_id"]

    conn = get_db_connection()

    cursor = conn.cursor(
        cursor_factory=RealDictCursor
    )

    if request.method == "POST":

        budget_amount = request.form.get(
            "budget_amount"
        )

        cursor.execute(
            """
            SELECT budget_id
            FROM budget
            WHERE user_id = %s
            """,
            (
                user_id,
            )
        )

        existing_budget = cursor.fetchone()

        if existing_budget:

            cursor.execute(
                """
                UPDATE budget
                SET budget_amount = %s
                WHERE user_id = %s
                """,
                (
                    budget_amount,
                    user_id
                )
            )

        else:

            cursor.execute(
                """
                INSERT INTO budget
                (
                    user_id,
                    budget_amount
                )
                VALUES
                (
                    %s,
                    %s
                )
                """,
                (
                    user_id,
                    budget_amount
                )
            )

        conn.commit()

    cursor.execute(
        """
        SELECT budget_amount
        FROM budget
        WHERE user_id = %s
        """,
        (
            user_id,
        )
    )

    budget_result = cursor.fetchone()

    budget_amount = float(
        budget_result["budget_amount"]
        if budget_result
        else 0
    )

    cursor.execute(
        """
        SELECT
            COALESCE(SUM(amount), 0) AS total
        FROM transactions
        WHERE user_id = %s
        AND transaction_type = 'Expense'
        """,
        (
            user_id,
        )
    )

    expense_result = cursor.fetchone()

    total_expense = float(
        expense_result["total"] or 0
    )

    remaining_budget = (
        budget_amount -
        total_expense
    )

    cursor.close()
    conn.close()

    return render_template(
        "budget.html",
        budget_amount=budget_amount,
        total_expense=total_expense,
        remaining_budget=remaining_budget
    )


# =========================================================
# INITIALIZE DATABASE
# IMPORTANT: This runs when Render starts Gunicorn
# =========================================================

initialize_database()


# =========================================================
# RUN APPLICATION
# =========================================================

if __name__ == "__main__":

    app.run(
        debug=True
    )
