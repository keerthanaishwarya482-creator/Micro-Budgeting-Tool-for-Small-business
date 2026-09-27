from flask import Flask, render_template, request, redirect, session
import psycopg2
from psycopg2.extras import RealDictCursor
import os

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

        cursor.execute(
            """
            INSERT INTO users
            (name, email, password)
            VALUES (%s, %s, %s)
            """,
            (
                name,
                email,
                password
            )
        )

        db.commit()

        cursor.close()
        db.close()

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

        db.commit()

        cursor.close()
        db.close()

        return redirect("/transactions")

    return render_template("add.html")


# =========================================================
# TRANSACTIONS
# SEARCH + FILTER
# =========================================================

@app.route("/transactions")
def transactions():

    if not login_required():
        return redirect("/login")

    search = request.args.get(
        "search",
        ""
    ).strip()

    transaction_type = request.args.get(
        "type",
        ""
    ).strip()

    user_id = session["user_id"]

    db = get_db_connection()

    cursor = db.cursor(
        cursor_factory=RealDictCursor
    )

    query = """
        SELECT *
        FROM transactions
        WHERE user_id = %s
    """

    parameters = [user_id]

    # SEARCH
    if search:

        query += """
            AND
            (
                transaction_type ILIKE %s
                OR category ILIKE %s
                OR description ILIKE %s
            )
        """

        search_value = "%" + search + "%"

        parameters.append(search_value)
        parameters.append(search_value)
        parameters.append(search_value)

    # TYPE FILTER
    if transaction_type == "Income":

        query += """
            AND transaction_type = %s
        """

        parameters.append("Income")

    elif transaction_type == "Expense":

        query += """
            AND transaction_type = %s
        """

        parameters.append("Expense")

    # ORDER
    query += """
        ORDER BY transaction_id DESC
    """

    cursor.execute(
        query,
        tuple(parameters)
    )

    data = cursor.fetchall()

    cursor.close()
    db.close()

    return render_template(
        "transactions.html",

        transactions=data,

        search=search,

        transaction_type=transaction_type
    )


# =========================================================
# EDIT TRANSACTION
# =========================================================

@app.route(
    "/edit/<int:transaction_id>",
    methods=["GET", "POST"]
)
def edit_transaction(transaction_id):

    if not login_required():
        return redirect("/login")

    user_id = session["user_id"]

    db = get_db_connection()

    cursor = db.cursor(
        cursor_factory=RealDictCursor
    )

    # UPDATE
    if request.method == "POST":

        transaction_type = request.form[
            "transaction_type"
        ]

        amount = request.form["amount"]

        category = request.form["category"]

        transaction_date = request.form[
            "transaction_date"
        ]

        description = request.form["description"]

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

        db.commit()

        cursor.close()
        db.close()

        return redirect("/transactions")

    # GET TRANSACTION
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
    db.close()

    if transaction is None:

        return "Transaction not found."

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
def delete_transaction(transaction_id):

    if not login_required():
        return redirect("/login")

    user_id = session["user_id"]

    db = get_db_connection()

    cursor = db.cursor()

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

    db.commit()

    cursor.close()
    db.close()

    return redirect("/transactions")


# =========================================================
# BUDGET
# =========================================================

@app.route(
    "/budget",
    methods=["GET", "POST"]
)
def budget_page():

    if not login_required():
        return redirect("/login")

    db = get_db_connection()

    cursor = db.cursor(
        cursor_factory=RealDictCursor
    )

    if request.method == "POST":

        budget_amount = request.form[
            "budget_amount"
        ]

        cursor.execute(
            """
            SELECT budget_id
            FROM budget
            ORDER BY budget_id
            LIMIT 1
            """
        )

        existing = cursor.fetchone()

        if existing:

            cursor.execute(
                """
                UPDATE budget
                SET budget_amount = %s
                WHERE budget_id = %s
                """,
                (
                    budget_amount,
                    existing["budget_id"]
                )
            )

        else:

            cursor.execute(
                """
                INSERT INTO budget
                (budget_amount)
                VALUES
                (%s)
                """,
                (
                    budget_amount
                )
            )

        db.commit()

    cursor.execute(
        """
        SELECT
            COALESCE(
                MAX(budget_amount),
                0
            ) AS budget_amount
        FROM budget
        """
    )

    result = cursor.fetchone()

    budget = result["budget_amount"]

    cursor.close()
    db.close()

    return render_template(
        "budget.html",
        budget=budget
    )


# =========================================================
# CREATE TABLES
# =========================================================
#
# IMPORTANT:
# This is outside the __main__ block.
# Therefore Render + Gunicorn will also create
# the tables when the application starts.
#

initialize_database()


# =========================================================
# START FLASK LOCALLY
# =========================================================

if __name__ == "__main__":

    app.run(
        debug=True
    )
