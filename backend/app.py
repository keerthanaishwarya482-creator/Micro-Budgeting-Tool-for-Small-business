import os
import smtplib
from email.mime.text import MIMEText

from flask import Flask, render_template, request, redirect, url_for, session, flash
import psycopg2
from psycopg2.extras import RealDictCursor

app = Flask(__name__)
app.secret_key = os.getenv("SECRET_KEY", "micro-budget-secret")


# DATABASE
def get_db():
    return psycopg2.connect(os.getenv("DATABASE_URL"))


def create_tables():
    conn = get_db()
    cur = conn.cursor()

    cur.execute(
        "CREATE TABLE IF NOT EXISTS users ("
        "user_id SERIAL PRIMARY KEY, "
        "name VARCHAR(100) NOT NULL, "
        "email VARCHAR(150) UNIQUE NOT NULL, "
        "password VARCHAR(255) NOT NULL)"
    )

    cur.execute(
        "CREATE TABLE IF NOT EXISTS transactions ("
        "transaction_id SERIAL PRIMARY KEY, "
        "transaction_type VARCHAR(20) NOT NULL, "
        "amount NUMERIC(12,2) NOT NULL, "
        "category VARCHAR(100), "
        "transaction_date DATE NOT NULL, "
        "description TEXT, "
        "user_id INTEGER REFERENCES users(user_id))"
    )

    cur.execute(
        "CREATE TABLE IF NOT EXISTS budget ("
        "budget_id SERIAL PRIMARY KEY, "
        "user_id INTEGER UNIQUE REFERENCES users(user_id), "
        "budget_amount NUMERIC(12,2) DEFAULT 0)"
    )

    conn.commit()
    cur.close()
    conn.close()


# EMAIL
def send_registration_email(name, email):
    sender = os.getenv("EMAIL_ADDRESS")
    password = os.getenv("EMAIL_APP_PASSWORD")
    receiver = os.getenv("NOTIFY_EMAIL")

    if not sender or not password or not receiver:
        print("Email settings are missing.")
        return

    try:
        body = "New Micro Budgeting App Registration\n\n"
        body += "Name: " + name + "\n"
        body += "Email: " + email + "\n"
        body += "\nA new user has registered successfully."

        message = MIMEText(body)
        message["Subject"] = "New Micro Budgeting App Registration"
        message["From"] = sender
        message["To"] = receiver

        server = smtplib.SMTP("smtp.gmail.com", 587)
        server.starttls()
        server.login(sender, password)
        server.send_message(message)
        server.quit()

        print("Registration email sent.")

    except Exception as e:
        print("Email error:", e)


# LOGIN CHECK
def logged_in():
    return "user_id" in session


# REGISTER
@app.route("/register", methods=["GET", "POST"])
def register():

    if request.method == "POST":

        name = request.form.get("name", "").strip()
        email = request.form.get("email", "").strip()
        password = request.form.get("password", "")

        if not name or not email or not password:
            flash("Please fill all fields.")
            return redirect(url_for("register"))

        conn = get_db()
        cur = conn.cursor()

        cur.execute(
            "SELECT user_id FROM users WHERE email=%s",
            (email,)
        )

        if cur.fetchone():
            cur.close()
            conn.close()
            flash("Email already registered.")
            return redirect(url_for("register"))

        cur.execute(
            "INSERT INTO users (name, email, password) "
            "VALUES (%s, %s, %s) RETURNING user_id",
            (name, email, password)
        )

        user_id = cur.fetchone()[0]

        cur.execute(
            "INSERT INTO budget (user_id, budget_amount) VALUES (%s, %s)",
            (user_id, 0)
        )

        conn.commit()
        cur.close()
        conn.close()

        send_registration_email(name, email)

        flash("Registration successful. Please login.")
        return redirect(url_for("login"))

    return render_template("register.html")


# LOGIN
@app.route("/login", methods=["GET", "POST"])
def login():

    if request.method == "POST":

        email = request.form.get("email", "").strip()
        password = request.form.get("password", "")

        conn = get_db()
        cur = conn.cursor(cursor_factory=RealDictCursor)

        cur.execute(
            "SELECT * FROM users WHERE email=%s AND password=%s",
            (email, password)
        )

        user = cur.fetchone()

        cur.close()
        conn.close()

        if user:
            session["user_id"] = user["user_id"]
            session["user_name"] = user["name"]
            session["user_email"] = user["email"]

            return redirect(url_for("dashboard"))

        flash("Invalid email or password.")
        return redirect(url_for("login"))

    return render_template("login.html")


# LOGOUT
@app.route("/logout")
def logout():
    session.clear()
    return redirect(url_for("login"))


# DASHBOARD
@app.route("/")
def dashboard():

    if not logged_in():
        return redirect(url_for("login"))

    user_id = session["user_id"]

    conn = get_db()
    cur = conn.cursor(cursor_factory=RealDictCursor)

    cur.execute(
        "SELECT COALESCE(SUM(amount),0) AS total "
        "FROM transactions "
        "WHERE user_id=%s AND transaction_type='Income'",
        (user_id,)
    )
    income = float(cur.fetchone()["total"])

    cur.execute(
        "SELECT COALESCE(SUM(amount),0) AS total "
        "FROM transactions "
        "WHERE user_id=%s AND transaction_type='Expense'",
        (user_id,)
    )
    expense = float(cur.fetchone()["total"])

    cur.execute(
        "SELECT budget_amount FROM budget WHERE user_id=%s",
        (user_id,)
    )

    budget_row = cur.fetchone()
    budget_amount = float(budget_row["budget_amount"]) if budget_row else 0

    cur.execute(
        "SELECT * FROM transactions "
        "WHERE user_id=%s "
        "ORDER BY transaction_id DESC LIMIT 5",
        (user_id,)
    )

    recent = cur.fetchall()

    cur.close()
    conn.close()

    return render_template(
        "index.html",
        total_income=income,
        total_expense=expense,
        balance=income - expense,
        budget_amount=budget_amount,
        remaining_budget=budget_amount - expense,
        recent_transactions=recent
    )


# ADD TRANSACTION
@app.route("/add", methods=["GET", "POST"])
def add_transaction():

    if not logged_in():
        return redirect(url_for("login"))

    if request.method == "POST":

        conn = get_db()
        cur = conn.cursor()

        cur.execute(
            "INSERT INTO transactions "
            "(transaction_type, amount, category, transaction_date, "
            "description, user_id) "
            "VALUES (%s,%s,%s,%s,%s,%s)",
            (
                request.form["transaction_type"],
                request.form["amount"],
                request.form["category"],
                request.form["transaction_date"],
                request.form["description"],
                session["user_id"]
            )
        )

        conn.commit()
        cur.close()
        conn.close()

        return redirect(url_for("transactions"))

    return render_template("add.html")


# TRANSACTIONS
@app.route("/transactions")
def transactions():

    if not logged_in():
        return redirect(url_for("login"))

    search = request.args.get("search", "")
    type_filter = request.args.get("type", "")

    conn = get_db()
    cur = conn.cursor(cursor_factory=RealDictCursor)

    query = "SELECT * FROM transactions WHERE user_id=%s"
    values = [session["user_id"]]

    if search:
        query += " AND (category ILIKE %s OR description ILIKE %s)"
        values += ["%" + search + "%", "%" + search + "%"]

    if type_filter:
        query += " AND transaction_type=%s"
        values.append(type_filter)

    query += " ORDER BY transaction_id DESC"

    cur.execute(query, values)
    rows = cur.fetchall()

    cur.close()
    conn.close()

    return render_template(
        "transactions.html",
        transactions=rows,
        search=search,
        selected_type=type_filter
    )


# EDIT TRANSACTION
@app.route("/edit/<int:id>", methods=["GET", "POST"])
def edit_transaction(id):

    if not logged_in():
        return redirect(url_for("login"))

    conn = get_db()
    cur = conn.cursor(cursor_factory=RealDictCursor)

    if request.method == "POST":

        cur.execute(
            "UPDATE transactions SET "
            "transaction_type=%s, "
            "amount=%s, "
            "category=%s, "
            "transaction_date=%s, "
            "description=%s "
            "WHERE transaction_id=%s AND user_id=%s",
            (
                request.form["transaction_type"],
                request.form["amount"],
                request.form["category"],
                request.form["transaction_date"],
                request.form["description"],
                id,
                session["user_id"]
            )
        )

        conn.commit()
        cur.close()
        conn.close()

        return redirect(url_for("transactions"))

    cur.execute(
        "SELECT * FROM transactions "
        "WHERE transaction_id=%s AND user_id=%s",
        (id, session["user_id"])
    )

    transaction = cur.fetchone()

    cur.close()
    conn.close()

    if not transaction:
        return "Transaction not found", 404

    return render_template(
        "edit.html",
        transaction=transaction
    )


# DELETE TRANSACTION
@app.route("/delete/<int:id>")
def delete_transaction(id):

    if not logged_in():
        return redirect(url_for("login"))

    conn = get_db()
    cur = conn.cursor()

    cur.execute(
        "DELETE FROM transactions "
        "WHERE transaction_id=%s AND user_id=%s",
        (id, session["user_id"])
    )

    conn.commit()
    cur.close()
    conn.close()

    return redirect(url_for("transactions"))


# BUDGET
@app.route("/budget", methods=["GET", "POST"])
def budget():

    if not logged_in():
        return redirect(url_for("login"))

    conn = get_db()
    cur = conn.cursor(cursor_factory=RealDictCursor)

    if request.method == "POST":

        amount = request.form["budget_amount"]

        cur.execute(
            "SELECT budget_id FROM budget WHERE user_id=%s",
            (session["user_id"],)
        )

        row = cur.fetchone()

        if row:
            cur.execute(
                "UPDATE budget SET budget_amount=%s "
                "WHERE user_id=%s",
                (amount, session["user_id"])
            )
        else:
            cur.execute(
                "INSERT INTO budget (user_id, budget_amount) "
                "VALUES (%s,%s)",
                (session["user_id"], amount)
            )

        conn.commit()

    cur.execute(
        "SELECT budget_amount FROM budget WHERE user_id=%s",
        (session["user_id"],)
    )

    row = cur.fetchone()
    budget_amount = float(row["budget_amount"]) if row else 0

    cur.execute(
        "SELECT COALESCE(SUM(amount),0) AS total "
        "FROM transactions "
        "WHERE user_id=%s AND transaction_type='Expense'",
        (session["user_id"],)
    )

    expense = float(cur.fetchone()["total"])

    cur.close()
    conn.close()

    return render_template(
        "budget.html",
        budget_amount=budget_amount,
        total_expense=expense,
        remaining_budget=budget_amount - expense
    )


# PROFILE
@app.route("/profile")
def profile():

    if not logged_in():
        return redirect(url_for("login"))

    conn = get_db()
    cur = conn.cursor(cursor_factory=RealDictCursor)

    cur.execute(
        "SELECT user_id, name, email "
        "FROM users WHERE user_id=%s",
        (session["user_id"],)
    )

    user = cur.fetchone()

    cur.close()
    conn.close()

    return render_template(
        "profile.html",
        user=user
    )


# CREATE TABLES WHEN RENDER STARTS
create_tables()


if __name__ == "__main__":
    app.run(debug=True)
