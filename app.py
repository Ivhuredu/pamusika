user_states = {}
user_data = {}

from flask import Flask, request
from twilio.twiml.messaging_response import MessagingResponse
import psycopg2
import os

app = Flask(__name__)

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
    parts = text.split()

    product = parts[0]
    location = None

    if len(parts) > 1:
        location = parts[1]

    conn = get_db()
    cur = conn.cursor()

    if location:
        cur.execute("""
            SELECT p.name, p.price, p.category, s.name, s.location, s.phone
            FROM products p
            JOIN sellers s ON p.seller_id = s.id
            WHERE LOWER(p.name) LIKE %s
               OR LOWER(p.category) LIKE %s
              AND LOWER(s.location) LIKE %s
        """, (f"%{product}%", f"%{product}%", f"%{location}%"))
    else:
        cur.execute("""
            SELECT p.name, p.price, p.category, s.name, s.location, s.phone
            FROM products p
            JOIN sellers s ON p.seller_id = s.id
            WHERE LOWER(p.name) LIKE %s
               OR LOWER(p.category) LIKE %s
        """, (f"%{product}%", f"%{product}%"))

    results = cur.fetchall()

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
    """, (name, price, seller_id, category))

    conn.commit()
    cur.close()
    conn.close()


# -------------------------
# WHATSAPP WEBHOOK
# -------------------------
@app.route("/webhook", methods=["POST"])
def bot():
    user = request.form.get("From")
    incoming = request.form.get("Body", "").strip().lower()

    resp = MessagingResponse()
    msg = resp.message()

    # -----------------
    # START REGISTRATION
    # -----------------

    if incoming == "register":
        user_states[user] = "name"
        user_data[user] = {}
        msg.body("🏪 Enter your business name:")
        return str(resp)

    # BUSINESS NAME
    if user_states.get(user) == "name":
        user_data[user]["name"] = incoming
        user_states[user] = "phone"
        msg.body("📞 Enter your phone number:")
        return str(resp)

    # PHONE
    if user_states.get(user) == "phone":
        user_data[user]["phone"] = incoming
        user_states[user] = "location"
        msg.body("📍 Enter your location (city/town):")
        return str(resp)

    # LOCATION → CREATE SELLER ONCE
    if user_states.get(user) == "location":
        user_data[user]["location"] = incoming

        seller_id = add_seller(
            user_data[user]["name"],
            user_data[user]["phone"],
            user_data[user]["location"]
        )

        user_data[user]["seller_id"] = seller_id
        user_states[user] = "product"

        msg.body("📦 Enter your first product name:")
        return str(resp)

    # PRODUCT NAME
    if user_states.get(user) == "product":
        user_data[user]["product"] = incoming
        user_states[user] = "category"
        msg.body("📂 Enter product category (food, building, electronics etc):")
        return str(resp)

    # CATEGORY
    if user_states.get(user) == "category":
        user_data[user]["category"] = incoming
        user_states[user] = "price"
        msg.body("💵 Enter price:")
        return str(resp)

    # PRICE → SAVE PRODUCT
    if user_states.get(user) == "price":
      add_product(
          user_data[user]["product"],
             incoming,
             user_data[user]["seller_id"],
             user_data[user]["category"]
      )

      user_states[user] = "more"
      msg.body("✅ Product added!\n\nAdd another product? (yes/no)")
      return str(resp)


    # ADD MORE?
    if user_states.get(user) == "more":

        if incoming == "yes":
            user_states[user] = "product"
            msg.body("📦 Enter next product name:")
            return str(resp)

        if incoming == "no":
            user_states.pop(user)
            user_data.pop(user)

            msg.body("🎉 Registration complete! All products listed.")
            return str(resp)

        msg.body("Please reply YES or NO")
        return str(resp)

    # -----------------
    # MENU
    # -----------------

    if incoming in ["menu", "hi", "hello", "start"]:
        msg.body(
            "🛒 PaMusika Marketplace\n\n"
            "🔍 Type product name to search\n"
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

    reply = f"📦 Results for '{incoming}':\n\n"

    for i, row in enumerate(results, 1):
        product, price, category, seller, location, phone = row

        reply += (
             f"{i}. {seller}\n"
             f"   🛒 {product} ({category})\n"
             f"   💵 {price}\n"
             f"   📍 {location}\n"
             f"   📞 {phone}\n\n"
        )

        

    msg.body(reply)
    return str(resp)

if __name__ == "__main__":
    app.run()





