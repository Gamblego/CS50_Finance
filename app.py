import os

from cs50 import SQL
from flask import Flask, flash, redirect, render_template, request, session
from flask_session import Session
from tempfile import mkdtemp
from werkzeug.security import check_password_hash, generate_password_hash
from datetime import datetime

from helpers import apology, login_required, lookup, usd

# Configure application
app = Flask(__name__)

# Ensure templates are auto-reloaded
app.config["TEMPLATES_AUTO_RELOAD"] = True

# Custom filter
app.jinja_env.filters["usd"] = usd

# Configure session to use filesystem (instead of signed cookies)
app.config["SESSION_PERMANENT"] = False
app.config["SESSION_TYPE"] = "filesystem"
Session(app)

# Configure CS50 Library to use SQLite database
db = SQL("sqlite:///finance.db")

# Make sure API key is set
if not os.environ.get("API_KEY"):
    raise RuntimeError("API_KEY not set")


@app.after_request
def after_request(response):
    """Ensure responses aren't cached"""
    response.headers["Cache-Control"] = "no-cache, no-store, must-revalidate"
    response.headers["Expires"] = 0
    response.headers["Pragma"] = "no-cache"
    return response


@app.route("/")
@login_required
def index():

    user = session["user_id"]
    total = 0;
    owns = db.execute("SELECT symbol, SUM(shares) as shares FROM purchase WHERE user_id = ? GROUP BY symbol HAVING SUM(shares) > 0", user)
    balance = db.execute("SELECT cash FROM users WHERE id = ?", user)[0]["cash"]

    for own in owns:
        result = lookup(own["symbol"])
        own["name"] = result["name"]
        own["price"] = result["price"]
        own["value"] = own["shares"] * own["price"]
        total += own["value"]

    total += balance

    return render_template("index.html", owns = owns, balance = usd(balance), total = usd(total))


@app.route("/buy", methods=["GET", "POST"])
@login_required
def buy():
    """Buy shares of stock"""
    if request.method == "GET":
        return render_template("/buy.html")

    if request.method == "POST":

        result = lookup(request.form.get("symbol"))

    if not request.form.get("symbol"):
        return apology("Please enter symbol", 400)

    if not result:
        return apology("Symbol does not exist", 400)

    elif not request.form.get("shares"):
        return apology("enter share", 400)

    elif request.form.get("shares").isdigit() == False:
        return apology("invalid no of shares", 400)

    shares = int(request.form.get("shares"))

    if shares < 1:
        return apology("enter valid no of shares", 400)

    user = session["user_id"]
    balance = db.execute("SELECT cash FROM users WHERE id = ?", user)[0]["cash"]
    price = result["price"]
    total = price * shares

    if balance < total:
        return apology("insufficient balance", 400)

    db.execute("INSERT INTO purchase (user_id, symbol, shares, price, time) VALUES(?, ?, ?, ?, ?)", user, result["symbol"], shares, total, datetime.now())

    db.execute("UPDATE users SET cash = ? WHERE id = ?", balance - total, user)

    return redirect("/")



@app.route("/history")
@login_required
def history():
    user = session["user_id"]
    owns = db.execute("SELECT symbol, shares, price, time FROM purchase WHERE user_id = ?", user)
    for own in owns:
        result = lookup(own["symbol"])
        own["name"] = result["name"]

    return render_template("history.html", owns=owns)


@app.route("/login", methods=["GET", "POST"])
def login():
    """Log user in"""

    # Forget any user_id
    session.clear()

    # User reached route via POST (as by submitting a form via POST)
    if request.method == "POST":

        # Ensure username was submitted
        if not request.form.get("username"):
            return apology("must provide username", 400)

        # Ensure password was submitted
        elif not request.form.get("password"):
            return apology("must provide password", 400)

        # Query database for username
        rows = db.execute("SELECT * FROM users WHERE username = ?", request.form.get("username"))

        # Ensure username exists and password is correct
        if len(rows) != 1 or not check_password_hash(rows[0]["hash"], request.form.get("password")):
            return apology("invalid username and/or password", 400)

        # Remember which user has logged in
        session["user_id"] = rows[0]["id"]

        # Redirect user to home page
        return redirect("/")

    # User reached route via GET (as by clicking a link or via redirect)
    else:
        return render_template("login.html")


@app.route("/logout")
def logout():
    """Log user out"""

    # Forget any user_id
    session.clear()

    # Redirect user to login form
    return redirect("/")


@app.route("/quote", methods=["GET", "POST"])
@login_required
def quote():
    if request.method == "POST":
        result = lookup(request.form.get("symbol"))

        if not request.form.get("symbol"):
            return apology("must provide symbol", 400)

        if not lookup(request.form.get("symbol")):
            return apology("cannot find symbol", 400)

        return render_template("quoted.html", name=result["name"], price = usd(result["price"]), symbol = result["symbol"])

    elif request.method == "GET":
        return render_template("quote.html")


@app.route("/register", methods=["GET", "POST"])
def register():

    if request.method == "GET":
        return render_template("register.html")

    if request.method == "POST":

        if not request.form.get("username"):
            return apology("must provide username", 400)

        rows = db.execute("SELECT * FROM users WHERE username = ?", request.form.get("username"))

        if len(rows) == 1:
            return apology("username already exists",400)

        if not request.form.get("password"):
            return apology("must provide password", 400)

        if request.form.get("password") != request.form.get("confirmation"):
            return apology("password do not match", 400)


        db.execute("INSERT into users (username, hash) VALUES(?, ?)", request.form.get("username"), generate_password_hash(request.form.get("password")))

        return redirect("/")


@app.route("/sell", methods=["GET", "POST"])
@login_required
def sell():
    if request.method == "POST":

        if not request.form.get("symbol"):
            return apology("enter symbol", 400)

        user = session["user_id"]
        symbol = request.form.get("symbol")
        result = db.execute("SELECT symbol FROM purchase GROUP BY symbol HAVING user_id = ? AND SUM(shares) > 0", user)


        if not result:
            return apology("invalid symbol", 400)

        if not request.form.get("shares"):
            return apology("enter shares", 400)

        shares = int(request.form.get("shares"))
        owns = db.execute("SELECT SUM(shares) as shares FROM purchase GROUP BY symbol HAVING user_id = ? AND SUM(shares) > 0 AND symbol = ?", user, request.form.get("symbol"))[0]['shares']

        if shares > owns:
            return apology("not enough shares", 400)

        balance = db.execute("SELECT cash FROM users WHERE id = ?", user)[0]["cash"]
        look = lookup(symbol)
        price = look["price"]
        total = price * shares

        db.execute("INSERT INTO purchase (user_id, symbol, shares, price, time) VALUES (?, ?, ?, ?, ?)", user, symbol, -shares, total, datetime.now())
        db.execute("UPDATE users SET cash = ? WHERE id = ?", balance + total, user)

        return redirect("/")

    if request.method == "GET":
        user = session["user_id"]
        owns = db.execute("SELECT symbol FROM purchase GROUP BY user_id = ? HAVING SUM(shares) > 0", user)
        return render_template("sell.html", owns=owns)
