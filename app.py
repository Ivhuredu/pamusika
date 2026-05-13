# pamusika_facebook_bot/app.py
import os
import logging
import requests
from flask import Flask, request
import psycopg2

app = Flask(__name__)

logging.basicConfig(level=logging.DEBUG)

user_states = {}
user_data = {}

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
# DATABASE HELPERS
# -------------------------
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

def update_product_price(product_id, new_price):
    conn = get_db()
    cur = conn.cursor()
    cur.execute("""
        UPDATE products SET price = %s WHERE id = %s
    """, (new_price, product_id))
    conn.commit()
    cur.close()
    conn.close()

def delete_product(product_id):
    conn = get_db()
    cur = conn.cursor()
    cur.execute("DELETE FROM products WHERE id = %s", (product_id,))
    conn.commit()
    cur.close()
    conn.close()

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

def search_products(text):
    text = text.strip().lower()
    logging.debug(f"Search input: {text}")
    if not text:
        return []
    parts = text.split()
    product = parts[0]
    location = parts[1] if len(parts) > 1 else None

    conn = get_db()
    cur = conn.cursor()
    if location:
        cur.execute("""
            SELECT p.id, p.name, p.price, p.category, s.name, s.location, s.phone
            FROM products p
            JOIN sellers s ON p.seller_id = s.id
            WHERE (LOWER(p.name) LIKE %s OR LOWER(p.category) LIKE %s)
              AND (s.location IS NULL OR LOWER(s.location) LIKE %s)
        """, (f"%{product}%", f"%{product}%", f"%{location}%"))
    else:
        cur.execute("""
            SELECT p.id, p.name, p.price, p.category, s.name, s.location, s.phone
            FROM products p
            JOIN sellers s ON p.seller_id = s.id
            WHERE LOWER(p.name) LIKE %s OR LOWER(p.category) LIKE %s
        """, (f"%{product}%", f"%{product}%"))

    products = cur.fetchall()
    results = []
    for row in products:
        product_id = row[0]
        cur.execute("SELECT image_url FROM product_photos WHERE product_id = %s", (product_id,))
        photos = [r[0] for r in cur.fetchall()]
        results.append((*row, photos))
    cur.close()
    conn.close()
    return results

# -------------------------
# FACEBOOK MESSENGER SUPPORT
# -------------------------
def send_message(recipient_id, text, media_url=None):
    payload = {
        "recipient": {"id": recipient_id},
        "message": {}
    }
    if media_url:
        payload["message"] = {
            "attachment": {
                "type": "image",
                "payload": {"url": media_url, "is_reusable": True}
            }
        }
    else:
        payload["message"]["text"] = text

    params = {"access_token": os.environ["FB_PAGE_ACCESS_TOKEN"]}
    headers = {"Content-Type": "application/json"}
    requests.post("https://graph.facebook.com/v18.0/me/messages", json=payload, params=params, headers=headers)

# -------------------------
# MAIN BOT LOGIC
# -------------------------
def handle_message(user, incoming):
    if incoming in ["menu", "hi", "hello", "start"]:
        send_message(user, "\U0001F6D2 PaMusika Marketplace\n\n\U0001F50D Type product name\n\U0001F4DD Type REGISTER to sell\n\nExample: cement")
        return

    if incoming == "register":
        user_states[user] = "name"
        user_data[user] = {}
        send_message(user, "\U0001F3EA Enter your business name:")
        return

    state = user_states.get(user)
    if state == "name":
        user_data[user]["name"] = incoming
        user_states[user] = "phone"
        send_message(user, "\U0001F4DE Enter your phone number:")
    elif state == "phone":
        user_data[user]["phone"] = incoming
        user_states[user] = "location"
        send_message(user, "\U0001F4CD Enter your location:")
    elif state == "location":
        user_data[user]["location"] = incoming
        seller_id = add_seller(user_data[user]["name"], user_data[user]["phone"], user_data[user]["location"])
        user_data[user]["seller_id"] = seller_id
        user_states[user] = "product"
        send_message(user, "\U0001F4E6 Enter product name:")
    elif state == "product":
        user_data[user]["product"] = incoming
        user_states[user] = "category"
        send_message(user, "\U0001F4C2 Enter category:")
    elif state == "category":
        user_data[user]["category"] = incoming
        user_states[user] = "price"
        send_message(user, "\U0001F4B5 Enter price:")
    elif state == "price":
        product_id = add_product(user_data[user]["product"], incoming, user_data[user]["seller_id"], user_data[user]["category"])
        user_data[user]["product_id"] = product_id
        user_states[user] = "photo_optional"
        send_message(user, "\U0001F4F7 Send product photo (optional), type DONE or SKIP")
    elif state == "photo_optional":
        if incoming == "skip" or incoming == "done":
            user_states[user] = "more"
            send_message(user, "✅ Product saved! Add another? (yes/no)")
        else:
            # Photo must be handled through attachments in Messenger payloads
            send_message(user, "Send image attachment or type DONE/SKIP")
    elif state == "more":
        if incoming == "yes":
            user_states[user] = "product"
            send_message(user, "\U0001F4E6 Enter next product name:")
        else:
            user_states.pop(user)
            user_data.pop(user)
            send_message(user, "\U0001F389 Registration complete!")
    elif incoming == "myproducts":
        phone = user_data.get(user, {}).get("phone", "")
        products = get_seller_products(phone)
        if not products:
            send_message(user, "❌ No products listed.")
            return
        reply = "\U0001F4E6 Your products:\n\n"
        for pid, name, price, category in products:
            reply += f"{pid}. {name} ({category}) - {price}\n"
        reply += "\nEdit: edit ID NEWPRICE\nDelete: delete ID"
        send_message(user, reply)
    elif incoming.startswith("edit"):
        parts = incoming.split()
        if len(parts) < 3:
            send_message(user, "edit PRODUCT_ID NEWPRICE")
        else:
            update_product_price(parts[1], parts[2])
            send_message(user, "✅ Price updated")
    elif incoming.startswith("delete"):
        parts = incoming.split()
        if len(parts) < 2:
            send_message(user, "delete PRODUCT_ID")
        else:
            delete_product(parts[1])
            send_message(user, "\U0001F5D1 Product deleted")
    else:
        results = search_products(incoming)
        if not results:
            send_message(user, "❌ No results found. Type MENU.")
            return
        for row in results:
            pid, name, price, category, seller, location, phone, photos = row
            if photos:
                send_message(user, photos[0])
            send_message(user, f"{seller}\n\U0001F6D2 {name} ({category})\n\U0001F4B5 {price}\n\U0001F4CD {location}\n\U0001F4DE {phone}")

# -------------------------
# FACEBOOK WEBHOOK ROUTE
# -------------------------
@app.route("/webhook", methods=["GET", "POST"])
def webhook():
    if request.method == "GET":
        if request.args.get("hub.verify_token") == os.environ["FB_VERIFY_TOKEN"]:
            return request.args.get("hub.challenge"), 200
        return "Unauthorized", 403

    data = request.get_json()
    for entry in data.get("entry", []):
        for msg in entry.get("messaging", []):
            sender = msg["sender"]["id"]
            if "message" in msg and "text" in msg["message"]:
                incoming = msg["message"]["text"].lower()
                handle_message(sender, incoming)
    return "ok", 200

@app.route("/privacy")
def privacy():
    return "<h1>Privacy Policy</h1><p>We do not collect or share your data. All interactions are initiated by users via WhatsApp.</p>"

@app.route("/terms")
def terms():
    return "<h1>Terms of Service</h1><p>Use of the bot is free and experimental. Use at your own discretion.</p>"

@app.route("/delete-my-data")
def delete_my_data():
    return """
    <h1>Data Deletion Instructions</h1>
    <p>If you want us to delete your data, please send a message via our chatbot saying <strong>"DELETE MY DATA"</strong>.
    We will remove your associated records.</p>
    """
if __name__ == "__main__":
    app.run(debug=True)

