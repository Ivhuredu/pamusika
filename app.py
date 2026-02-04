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

def search_products(keyword):
    conn = get_db()
    cur = conn.cursor()

    cur.execute("""
        SELECT p.name, p.price, s.name, s.location, s.phone
        FROM products p
        JOIN sellers s ON p.seller_id = s.id
        WHERE LOWER(p.name) LIKE %s
    """, (f"%{keyword}%",))

    results = cur.fetchall()

    cur.close()
    conn.close()

    return results

# -------------------------
# WHATSAPP WEBHOOK
# -------------------------

@app.route("/webhook", methods=["POST"])
def bot():
    incoming = request.form.get("Body", "").strip().lower()

    resp = MessagingResponse()
    msg = resp.message()

    # MENU
    if incoming in ["menu", "hi", "hello", "start"]:
        msg.body(
            "🛒 PaMusika Marketplace\n\n"
            "1️⃣ Search product\n"
            "2️⃣ View sample products\n"
            "3️⃣ Help\n\n"
            "Type product name (eg: cement)"
        )
        return str(resp)

    # SAMPLE PRODUCTS
    if incoming == "2":
        msg.body(
            "📦 Available samples:\n\n"
            "• cement\n"
            "• sugar\n"
            "• rice\n"
            "• cooking oil\n\n"
            "Type product name."
        )
        return str(resp)

    # HELP
    if incoming == "3":
        msg.body(
            "ℹ Just type what you're looking for.\n\n"
            "Example: cement"
        )
        return str(resp)

    # SEARCH
    results = search_products(incoming)

    if not results:
        msg.body("❌ No results found. Type MENU.")
        return str(resp)

    reply = f"📦 Results for '{incoming}':\n\n"

    for i, row in enumerate(results, 1):
        product, price, seller, location, phone = row

        reply += (
            f"{i}. {seller}\n"
            f"   🛒 {product}\n"
            f"   💵 {price}\n"
            f"   📍 {location}\n"
            f"   📞 {phone}\n\n"
        )

    msg.body(reply)

    return str(resp)


if __name__ == "__main__":
    app.run()




