import os
import psycopg2
import bcrypt
from flask import session


def get_connection():
    return psycopg2.connect(os.environ["DATABASE_URL"])


def get_or_create_brand_id(cursor, brand_name):
    cursor.execute(
        """
        SELECT brandid
        FROM Brands
        WHERE brandname = %s
    """,
        (brand_name,),
    )

    row = cursor.fetchone()
    if row:
        return row[0]

    cursor.execute(
        """
        INSERT INTO Brands (brandname)
        VALUES (%s)
        RETURNING brandid
    """,
        (brand_name,),
    )

    row = cursor.fetchone()
    return row[0]


def add_key_inventory(cursor, brand, number, qty):
    brand_id = get_or_create_brand_id(cursor, brand)

    # Get current quantity
    cursor.execute(
        """
        SELECT Quantity FROM Keys
        WHERE brandid = %s AND keynumber = %s
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
            SET Quantity = %s
            WHERE brandid = %s AND keynumber = %s
        """,
            (new_qty, brand_id, number),
        )
    else:
        if qty < 0:
            raise ValueError("Cannot remove non-existent key inventory")

        cursor.execute(
            """
            INSERT INTO Keys (brandid, keynumber, quantity)
            VALUES (%s, %s, %s)
        """,
            (brand_id, number, qty),
        )


def add_core_inventory(cursor, brand, number, qty):
    brand_id = get_or_create_brand_id(cursor, brand)

    # Get current quantity
    cursor.execute(
        """
        SELECT Quantity FROM Cores
        WHERE brandid = %s AND corenumber = %s
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
            SET Quantity = %s
            WHERE brandid = %s AND corenumber = %s
        """,
            (new_qty, brand_id, number),
        )
    else:
        if qty < 0:
            raise ValueError("Cannot remove non-existent core inventory")

        cursor.execute(
            """
            INSERT INTO Cores (brandid, corenumber, quantity)
            VALUES (%s, %s, %s)
        """,
            (brand_id, number, qty),
        )


def search_keys(brand_name=None, key_number=None):
    conn = get_connection()
    cursor = conn.cursor()

    try:
        sql = """
        SELECT
            b.brandname,
            k.keynumber,
            k.quantity
        FROM Keys k
        JOIN Brands b ON k.brandid = b.brandid
        WHERE 1=1
        """
        params = []

        if brand_name:
            sql += " AND b.brandname = %s"
            params.append(brand_name)

        if key_number:
            sql += " AND k.keynumber = %s"
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
            b.brandname,
            c.corenumber,
            c.quantity
        FROM Cores c
        JOIN Brands b ON c.brandid = b.brandid
        WHERE 1=1
        """
        params = []

        if brand_name:
            sql += " AND b.brandname = %s"
            params.append(brand_name)

        if core_number:
            sql += " AND c.corenumber = %s"
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
            b.brandname,
            k.keynumber AS number,
            k.quantity AS keyqty,
            c.quantity AS coreqty,
            CASE
                WHEN k.quantity < c.quantity THEN k.quantity
                ELSE c.quantity
            END AS SetsAvailable
        FROM Keys k
        JOIN Cores c
            ON k.brandid = c.brandid
            AND k.keynumber = c.corenumber
        JOIN Brands b
            ON k.brandid = b.brandid
        WHERE 1=1
        """

        params = []

        if brand_name:
            sql += " AND b.brandname = %s"
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
            (itemtype, brandid, itemnumber, quantitychange, action, userid)
        VALUES (%s, %s, %s, %s, %s, %s)
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
        VALUES (%s, %s)
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
        SELECT userid, username, passwordhash, role
        FROM Users
        WHERE username = %s
    """,
        (username,),
    )

    row = cursor.fetchone()

    cursor.close()
    conn.close()

    if not row:
        return None

    userid, username, stored_hash, role = row

    if bcrypt.checkpw(password.encode("utf-8"), stored_hash.encode("utf-8")):
        return {
            "userid": userid,
            "username": username,
            "role": role,
        }

    return None
