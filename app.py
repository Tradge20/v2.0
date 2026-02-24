import json
from functools import wraps
import bcrypt
from flask import (
    Flask,
    render_template,
    request,
    redirect,
    flash,
    url_for,
    session,
)
from db import (
    # create_user,
    get_connection,
    process_inventory_batch,
    search_keys,
    search_cores,
    search_matching_sets,
    authenticate_user,
)

app = Flask(__name__)
app.secret_key = "super_secret_key"


def login_required(f):
    @wraps(f)
    def decorated_function(*args, **kwargs):
        if "user_id" not in session:
            return redirect(url_for("login"))
        return f(*args, **kwargs)

    return decorated_function


def admin_required(f):
    @wraps(f)
    def decorated_function(*args, **kwargs):
        if session.get("role") != "admin":
            # Non-admins should stay logged in but cannot access admin pages
            return redirect(url_for("inventory_form"))
        return f(*args, **kwargs)

    return decorated_function


@app.route("/")
def home():
    if "user_id" in session:
        # Send users to the right place based on their role
        if session.get("role") == "admin":
            return redirect(url_for("dashboard"))
        else:
            return redirect(url_for("inventory_form"))
    return redirect(url_for("login"))


@app.route("/search")
def search():
    brand = request.args.get("brand")
    number = request.args.get("number")
    item_type = request.args.get("type")

    if item_type == "key":
        results = search_keys(brand, number)
    elif item_type == "core":
        results = search_cores(brand, number)
    else:
        results = search_matching_sets(brand)

    return render_template("results.html", results=results, item_type=item_type)


@app.route("/inventory/batch", methods=["POST"])
@login_required
def batch_inventory():
    items = json.loads(request.form["items"])

    try:
        # choose strict or partial
        result = process_inventory_batch(items, strict_mode=False)

        if result["failed"] > 0:
            flash(
                f"{result['processed']} succeeded, {result['failed']} failed", "error"
            )
        else:
            flash(
                f"Inventory updated successfully ({result['processed']} items)",
                "success",
            )

    except ValueError as e:
        flash(f"Batch failed: {str(e)}", "error")

    return redirect(url_for("inventory_form"))


@app.route("/inventory")
@login_required
def inventory_form():
    return render_template("inventory.html")


@app.route("/audit")
@login_required
@admin_required
def view_audit():
    conn = get_connection()
    cursor = conn.cursor()

    cursor.execute(
        """
        SELECT 
            itemtype,
            itemnumber,
            quantitychange,
            action,
            createdat
        FROM inventoryaudit
        ORDER BY createdat DESC
        LIMIT 100
    """
    )

    rows = cursor.fetchall()

    cursor.close()
    conn.close()

    return render_template("audit.html", rows=rows)


@app.route("/dashboard")
@login_required
@admin_required
def dashboard():
    conn = get_connection()
    cursor = conn.cursor()

    cursor.execute(
        """
        SELECT SUM(quantity) FROM keys
    """
    )
    total_keys = cursor.fetchone()[0] or 0

    cursor.execute(
        """
        SELECT SUM(quantity) FROM cores
    """
    )
    total_cores = cursor.fetchone()[0] or 0

    cursor.close()
    conn.close()

    return render_template(
        "dashboard.html", total_keys=total_keys, total_cores=total_cores
    )


@app.route("/login", methods=["GET", "POST"])
def login():
    if request.method == "POST":
        username = request.form["username"]
        password = request.form["password"]

        user = authenticate_user(username, password)

        if user:
            session["user_id"] = user["userid"]
            session["username"] = user["username"]
            session["role"] = user["role"]
            flash("Logged in successfully", "success")
            # After login, send admins to dashboard, everyone else to inventory
            if user["role"] == "admin":
                return redirect(url_for("dashboard"))
            else:
                return redirect(url_for("inventory_form"))
        else:
            flash("Invalid credentials", "error")

    return render_template("login.html")


@app.route("/logout")
def logout():
    session.clear()
    flash("Logged out", "success")
    return redirect(url_for("login"))


@app.route("/register", methods=["GET", "POST"])
def register():
    if request.method == "POST":
        username = request.form["username"]
        password = request.form["password"]
        role = request.form.get("role", "user")

        if not username or not password:
            flash("Username and password required")
            return redirect(url_for("register"))

        hashed_pw = bcrypt.hashpw(password.encode("utf-8"), bcrypt.gensalt())

        conn = get_connection()
        cursor = conn.cursor()

        try:
            cursor.execute(
                """
                INSERT INTO Users (username, passwordhash, role)
                VALUES (%s, %s, %s)
            """,
                (username, hashed_pw.decode("utf-8"), role),
            )
            conn.commit()
        except ValueError as e:
            flash(f"Username already exists: {str(e)}")
            return redirect(url_for("register"))

        return redirect(url_for("login"))

    return render_template("register.html")


if __name__ == "__main__":
    app.run(debug=True)
