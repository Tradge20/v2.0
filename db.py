import pyodbc
import bcrypt
from flask import session


# Connection string
def get_connection():
    return pyodbc.connect(
        "DRIVER={ODBC Driver 17 for SQL Server};"
        r"SERVER=.\SQLEXPRESS;"
        "DATABASE=KeysCores;"
        "Trusted_Connection=yes;"
    )


def get_or_create_brand_id(cursor, brand_name):
    cursor.execute(
        """
        SELECT BrandID
        FROM Brands
        WHERE BrandName = ?
    """,
        (brand_name,),
    )

    row = cursor.fetchone()
    if row:
        return row.BrandID

    cursor.execute(
        """
        INSERT INTO Brands (BrandName)
        OUTPUT INSERTED.BrandID
        VALUES (?)
    """,
        (brand_name,),
    )

    return cursor.fetchone().BrandID


def add_key_inventory(cursor, brand, number, qty):
    brand_id = get_or_create_brand_id(cursor, brand)

    # Get current quantity
    cursor.execute(
        """
        SELECT Quantity FROM Keys
        WHERE BrandID = ? AND KeyNumber = ?
    """,
        (brand_id, number),
    )

    row = cursor.fetchone()

    current_qty = row[0] if row else 0
    new_qty = current_qty + qty

    if new_qty < 0:
        raise ValueError(f"Insufficient key inventory for {brand} {number}")

    if row:
        cursor.execute(
            """
            UPDATE Keys
            SET Quantity = ?
            WHERE BrandID = ? AND KeyNumber = ?
        """,
            (new_qty, brand_id, number),
        )
    else:
        if qty < 0:
            raise ValueError("Cannot remove non-existent key inventory")

        cursor.execute(
            """
            INSERT INTO Keys (BrandID, KeyNumber, Quantity)
            VALUES (?, ?, ?)
        """,
            (brand_id, number, qty),
        )


def add_core_inventory(cursor, brand, number, qty):
    brand_id = get_or_create_brand_id(cursor, brand)

    # Get current quantity
    cursor.execute(
        """
        SELECT Quantity FROM Cores
        WHERE BrandID = ? AND CoreNumber = ?
    """,
        (brand_id, number),
    )

    row = cursor.fetchone()

    current_qty = row[0] if row else 0
    new_qty = current_qty + qty

    if new_qty < 0:
        raise ValueError(f"Insufficient core inventory for {brand} {number}")

    if row:
        cursor.execute(
            """
            UPDATE Cores
            SET Quantity = ?
            WHERE BrandID = ? AND CoreNumber = ?
        """,
            (new_qty, brand_id, number),
        )
    else:
        if qty < 0:
            raise ValueError("Cannot remove non-existent core inventory")

        cursor.execute(
            """
            INSERT INTO Cores (BrandID, CoreNumber, Quantity)
            VALUES (?, ?, ?)
        """,
            (brand_id, number, qty),
        )


def search_keys(brand_name=None, key_number=None):
    conn = get_connection()
    cursor = conn.cursor()

    try:
        sql = """
        SELECT
            b.BrandName,
            k.KeyNumber,
            k.Quantity
        FROM Keys k
        JOIN Brands b ON k.BrandID = b.BrandID
        WHERE 1=1
        """
        params = []

        if brand_name:
            sql += " AND b.BrandName = ?"
            params.append(brand_name)

        if key_number:
            sql += " AND k.KeyNumber = ?"
            params.append(key_number)

        cursor.execute(sql, params)
        return cursor.fetchall()

    finally:
        cursor.close()
        conn.close()


def search_cores(brand_name=None, core_number=None):
    conn = get_connection()
    cursor = conn.cursor()

    try:
        sql = """
        SELECT
            b.BrandName,
            c.CoreNumber,
            c.Quantity
        FROM Cores c
        JOIN Brands b ON c.BrandID = b.BrandID
        WHERE 1=1
        """
        params = []

        if brand_name:
            sql += " AND b.BrandName = ?"
            params.append(brand_name)

        if core_number:
            sql += " AND c.CoreNumber = ?"
            params.append(core_number)

        cursor.execute(sql, params)
        return cursor.fetchall()

    finally:
        cursor.close()
        conn.close()


def search_matching_sets(brand_name=None):
    conn = get_connection()
    cursor = conn.cursor()

    try:
        sql = """
        SELECT
            b.BrandName,
            k.KeyNumber AS Number,
            k.Quantity AS KeyQty,
            c.Quantity AS CoreQty,
            CASE
                WHEN k.Quantity < c.Quantity THEN k.Quantity
                ELSE c.Quantity
            END AS SetsAvailable
        FROM Keys k
        JOIN Cores c
            ON k.BrandID = c.BrandID
            AND k.KeyNumber = c.CoreNumber
        JOIN Brands b
            ON k.BrandID = b.BrandID
        WHERE 1=1
        """

        params = []

        if brand_name:
            sql += " AND b.BrandName = ?"
            params.append(brand_name)

        cursor.execute(sql, params)
        return cursor.fetchall()

    finally:
        cursor.close()
        conn.close()


def process_inventory_batch(items, strict_mode=True):
    conn = get_connection()
    cursor = conn.cursor()

    results = []
    errors = []

    try:
        for index, item in enumerate(items):
            try:
                item_type = item["type"]
                brand = item["brand"]
                qty = int(item["quantity"])

                if qty == 0:
                    raise ValueError("Quantity cannot be zero")

                # Ensure we pass (cursor, brand_name) as defined
                brand_id = get_or_create_brand_id(cursor, brand)

                # ----------------------
                # HANDLE KEY
                # ----------------------
                if item_type == "key":
                    number = item["number"]
                    # add_key_inventory expects (cursor, brand, number, qty)
                    add_key_inventory(cursor, brand, number, qty)
                    insert_audit(cursor, "key", brand_id, number, qty, "batch")

                # ----------------------
                # HANDLE CORE
                # ----------------------
                elif item_type == "core":
                    number = item["number"]
                    # add_core_inventory expects (cursor, brand, number, qty)
                    add_core_inventory(cursor, brand, number, qty)
                    insert_audit(cursor, "core", brand_id, number, qty, "batch")

                # ----------------------
                # HANDLE SET
                # ----------------------
                elif item_type == "set":
                    key_number = item["key_number"]
                    core_number = item["core_number"]

                    # Apply both (cursor, brand, number, qty)
                    add_key_inventory(cursor, brand, key_number, qty)
                    add_core_inventory(cursor, brand, core_number, qty)

                    # Audit both
                    insert_audit(cursor, "key", brand_id, key_number, qty, "set")
                    insert_audit(cursor, "core", brand_id, core_number, qty, "set")

                else:
                    raise ValueError("Invalid item type")

                results.append(index)

            except ValueError as e:
                errors.append({"index": index, "error": str(e)})

                if strict_mode:
                    raise

        # Final transaction decision
        if errors and strict_mode:
            raise ValueError("One or more batch items failed")

        conn.commit()

    except ValueError:
        conn.rollback()
        raise

    finally:
        cursor.close()
        conn.close()

    return {"processed": len(results), "failed": len(errors), "errors": errors}


def insert_audit(cursor, item_type, brand_id, number, qty, action):
    user_id = session.get("user_id")
    cursor.execute(
        """
        INSERT INTO InventoryAudit
            (ItemType, BrandID, ItemNumber, QuantityChange, Action, UserID)
        VALUES (?, ?, ?, ?, ?, ?)
    """,
        (item_type, brand_id, number, qty, action, user_id),
    )


def create_user(username, password):
    conn = get_connection()
    cursor = conn.cursor()

    hashed = bcrypt.hashpw(password.encode("utf-8"), bcrypt.gensalt())

    cursor.execute(
        """
        INSERT INTO Users (Username, PasswordHash)
        VALUES (?, ?)
    """,
        (username, hashed.decode("utf-8")),
    )

    conn.commit()
    cursor.close()
    conn.close()


def authenticate_user(username, password):
    conn = get_connection()
    cursor = conn.cursor()

    cursor.execute(
        """
        SELECT UserID, Username, PasswordHash, Role
        FROM Users
        WHERE Username = ?
    """,
        (username,),
    )

    row = cursor.fetchone()

    cursor.close()
    conn.close()

    if not row:
        return None

    user_id, username, stored_hash, role = row

    if bcrypt.checkpw(password.encode("utf-8"), stored_hash.encode("utf-8")):
        return {
            "user_id": user_id,
            "username": username,
            "role": role,
        }

    return None
