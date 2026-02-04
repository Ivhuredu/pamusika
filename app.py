from flask import Flask, request
from twilio.twiml.messaging_response import MessagingResponse
from db import get_db

app = Flask(__name__)

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


@app.route("/whatsapp", methods=["POST"])
def whatsapp_bot():
    incoming = request.form.get("Body", "").strip().lower()

    resp = MessagingResponse()
    msg = resp.message()

    if not incoming:
        msg.body("Type a product name to search.")
        return str(resp)

    results = search_products(incoming)

    if not results:
        msg.body("❌ No suppliers found. Try another product.")
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
    app.run(debug=True)
