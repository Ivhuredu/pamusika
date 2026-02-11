user_states = {}
user_data = {}
import logging
from flask import Flask, request
from twilio.twiml.messaging_response import MessagingResponse
import psycopg2
import os

app = Flask(__name__)

# Setup logging
logging.basicConfig(level=logging.DEBUG)  # Or INFO for less detail

# -------------------------
# DATABASE CONNECTION
# -------------------------

def get_db():
    return psycopg2.connect(
        host=os.environ["DB_HOST"],
        database=os.environ["DB_NAME"],
        user=os.environ["DB_USER"],
        password=os.environ["DB_PASSWORD"],
        port=os.environ.get("DB_PORT", 5432)
    )

# -------------------------
# SEARCH FUNCTION
# -------------------------
def search_products(text):
    text = text.strip().lower()
    logging.debug(f"Search input: {text}")
    if not text:
        return []

    parts = text.split()

    product = parts[0]
    location = parts[1] if len(parts) > 1 else None

    logging.debug(f"Parsed product: {product}, location: {location}")
    conn = get_db()
    cur = conn.cursor()

    if location:
        cur.execute("""
            SELECT p.id, p.name, p.price, p.category,
                   s.name, s.location, s.phone
            FROM products p
            JOIN sellers s ON p.seller_id = s.id
            WHERE (
                LOWER(p.name) LIKE %s
                OR LOWER(p.category) LIKE %s
            )
            AND (
                s.location IS NULL
                OR LOWER(s.location) LIKE %s
            )
        """, (f"%{product}%", f"%{product}%", f"%{location}%"))
    else:
        cur.execute("""
            SELECT p.id, p.name, p.price, p.category,
                   s.name, s.location, s.phone
            FROM products p
            JOIN sellers s ON p.seller_id = s.id
            WHERE LOWER(p.name) LIKE %s
               OR LOWER(p.category) LIKE %s
        """, (f"%{product}%", f"%{product}%"))

    products = cur.fetchall()
    logging.debug(f"DB returned {len(products)} products")

    results = []

    for row in products:
        logging.debug(f"Product row: {row}")
        product_id = row[0]

        cur.execute("""
            SELECT image_url
            FROM product_photos
            WHERE product_id = %s
        """, (product_id,))

        photos = [r[0] for r in cur.fetchall()]
        logging.debug(f"Found {len(photos)} photos for product {product_id}")
        results.append((*row, photos))

    cur.close()
    conn.close()

    return results



def add_seller(name, phone, location):
    conn = get_db()
    cur = conn.cursor()

    cur.execute("""
        INSERT INTO sellers (name, phone, location)
        VALUES (%s, %s, %s)
        RETURNING id
    """, (name, phone, location))

    seller_id = cur.fetchone()[0]

    conn.commit()
    cur.close()
    conn.close()

    return seller_id

def add_product(name, price, seller_id, category):
    conn = get_db()
    cur = conn.cursor()

    cur.execute("""
        INSERT INTO products (name, price, seller_id, category)
        VALUES (%s, %s, %s, %s)
        RETURNING id
    """, (name, price, seller_id, category))

    product_id = cur.fetchone()[0]

    conn.commit()
    cur.close()
    conn.close()

    return product_id

def get_seller_products(phone):
    conn = get_db()
    cur = conn.cursor()

    cur.execute("""
        SELECT p.id, p.name, p.price, p.category
        FROM products p
        JOIN sellers s ON p.seller_id = s.id
        WHERE s.phone = %s
    """, (phone,))

    results = cur.fetchall()

    cur.close()
    conn.close()

    return results


def update_product_price(product_id, new_price):
    conn = get_db()
    cur = conn.cursor()

    cur.execute("""
        UPDATE products
        SET price = %s
        WHERE id = %s
    """, (new_price, product_id))

    conn.commit()
    cur.close()
    conn.close()

def delete_product(product_id):
    conn = get_db()
    cur = conn.cursor()

    cur.execute("""
        DELETE FROM products
        WHERE id = %s
    """, (product_id,))

    conn.commit()
    cur.close()
    conn.close()

def add_product_photo(product_id, image_url):
    conn = get_db()
    cur = conn.cursor()

    cur.execute("""
        INSERT INTO product_photos (product_id, image_url)
        VALUES (%s, %s)
    """, (product_id, image_url))

    conn.commit()
    cur.close()
    conn.close()

    logging.debug("Executed product search query")


# -------------------------
# WHATSAPP WEBHOOK
# -------------------------
@app.route("/webhook", methods=["POST"])
def bot():
    user = request.form.get("From")
    incoming = request.form.get("Body", "").strip().lower()
    logging.info(f"User: {user} | Incoming: {incoming}")
    resp = MessagingResponse()
    msg = resp.message()

    # -----------------
    # REGISTRATION FLOW
    # -----------------

    if incoming == "register":
        user_states[user] = "name"
        user_data[user] = {}
        msg.body("🏪 Enter your business name:")
        return str(resp)

    if user_states.get(user) == "name":
        user_data[user]["name"] = incoming
        user_states[user] = "phone"
        msg.body("📞 Enter your phone number:")
        return str(resp)

    if user_states.get(user) == "phone":
        user_data[user]["phone"] = incoming
        user_states[user] = "location"
        msg.body("📍 Enter your location:")
        return str(resp)

    if user_states.get(user) == "location":
        user_data[user]["location"] = incoming

        seller_id = add_seller(
            user_data[user]["name"],
            user_data[user]["phone"],
            user_data[user]["location"]
        )

        user_data[user]["seller_id"] = seller_id
        user_states[user] = "product"

        msg.body("📦 Enter product name:")
        return str(resp)

    if user_states.get(user) == "product":
        user_data[user]["product"] = incoming
        user_states[user] = "category"
        msg.body("📂 Enter category:")
        return str(resp)

    if user_states.get(user) == "category":
        user_data[user]["category"] = incoming
        user_states[user] = "price"
        msg.body("💵 Enter price:")
        return str(resp)

    # SAVE PRODUCT (NO PHOTO YET)
    if user_states.get(user) == "price":
        product_id = add_product(
            user_data[user]["product"],
            incoming,
            user_data[user]["seller_id"],
            user_data[user]["category"]
        )

        user_data[user]["product_id"] = product_id
        user_states[user] = "photo_optional"

        msg.body(
            "📷 Send product photo (optional).\n"
            "Send multiple photos or type DONE.\n"
            "Type SKIP if none."
        )
        return str(resp)

    # PHOTO HANDLING
    if user_states.get(user) == "photo_optional":

        image_url = request.form.get("MediaUrl0")

        if incoming == "skip":
            user_states[user] = "more"
            msg.body("✅ Product saved!\nAdd another product? (yes/no)")
            return str(resp)

        if image_url:
            add_product_photo(user_data[user]["product_id"], image_url)
            msg.body("📸 Photo added! Send another or type DONE")
            return str(resp)

        if incoming == "done":
            user_states[user] = "more"
            msg.body("✅ Product saved!\nAdd another product? (yes/no)")
            return str(resp)

        msg.body("Send photo, DONE or SKIP")
        return str(resp)

    # ADD MORE PRODUCTS
    if user_states.get(user) == "more":

        if incoming == "yes":
            user_states[user] = "product"
            msg.body("📦 Enter next product name:")
            return str(resp)

        if incoming == "no":
            user_states.pop(user)
            user_data.pop(user)
            msg.body("🎉 Registration complete!")
            return str(resp)

    # -----------------
    # SELLER MANAGEMENT
    # -----------------

    if incoming == "myproducts":
        phone = request.form.get("From").split(":")[-1]
        products = get_seller_products(phone)

        if not products:
            msg.body("❌ No products listed.")
            return str(resp)

        reply = "📦 Your products:\n\n"

        for pid, name, price, category in products:
            reply += f"{pid}. {name} ({category}) - {price}\n"

        reply += "\nEdit: edit ID NEWPRICE\nDelete: delete ID"

        msg.body(reply)
        return str(resp)

    if incoming.startswith("edit"):
        parts = incoming.split()
        if len(parts) < 3:
            msg.body("edit PRODUCT_ID NEWPRICE")
            return str(resp)

        update_product_price(parts[1], parts[2])
        msg.body("✅ Price updated")
        return str(resp)

    if incoming.startswith("delete"):
        parts = incoming.split()
        if len(parts) < 2:
            msg.body("delete PRODUCT_ID")
            return str(resp)

        delete_product(parts[1])
        msg.body("🗑 Product deleted")
        return str(resp)

    # -----------------
    # MENU
    # -----------------

    if incoming in ["menu", "hi", "hello", "start"]:
        msg.body(
            "🛒 PaMusika Marketplace\n\n"
            "🔍 Type product name\n"
            "📝 Type REGISTER to sell\n\n"
            "Example: cement"
        )
        return str(resp)
    # -----------------
    # SEARCH
    # -----------------

    results = search_products(incoming)

    if not results:
        msg.body("❌ No results found. Type MENU.")
        return str(resp)

   for row in results:
        product_id, name, price, category, seller, location, phone, photos = row

        # Create a new message for each product
        product_msg = resp.message()

        # Add photo first (if any)
        if photos:
            product_msg.media(photos[0])  # Only send 1 photo to avoid blocking

        # Add text last
        product_msg.body(
            f"{seller}\n"
            f"🛒 {name} ({category})\n"
            f"💵 {price}\n"
            f"📍 {location}\n"
            f"📞 {phone}"
        )


    logging.debug("Finished sending results, returning response")
    return str(resp)

   

if __name__ == "__main__":
    app.run()



























