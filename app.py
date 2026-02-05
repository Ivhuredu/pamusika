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
    parts = text.strip().split()
    if not parts:
        return []

    product = parts[0]
    location = parts[1] if len(parts) > 1 else None

    conn = get_db()
    cur = conn.cursor()

    if location:
        cur.execute("""
            SELECT p.id, p.name, p.price, p.category,
                   s.name, s.location, s.phone
            FROM products p
            JOIN sellers s ON p.seller_id = s.id
            WHERE (LOWER(p.name) LIKE %s OR LOWER(p.category) LIKE %s)
              AND LOWER(s.location) LIKE %s
        """, (f"%{product}%", f"%{product}%", f"%{location}%"))
    else:
        cur.execute("""
            SELECT p.id, p.name, p.price, p.category,
                   s.name, s.location, s.phone
            FROM products p
            JOIN sellers s ON p.seller_id = s.id
            WHERE LOWER(p.name) LIKE %s OR LOWER(p.category) LIKE %s
        """, (f"%{product}%", f"%{product}%"))

    products = cur.fetchall()

    results = []

    for row in products:
        product_id = row[0]

        cur.execute("""
            SELECT image_url FROM product_photos
            WHERE product_id = %s
        """, (product_id,))

        photos = [r[0] for r in cur.fetchall()]
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

def add_product(name, price, seller_id, category, image_url):
    conn = get_db()
    cur = conn.cursor()

    cur.execute("""
        INSERT INTO products (name, price, seller_id, category, image_url)
        VALUES (%s, %s, %s, %s, %s)
    """, (name, price, seller_id, category, image_url))

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
        user_data[user]["price"] = incoming
        user_states[user] = "photo"
        msg.body("📷 Please send a photo of the product.")
        return str(resp)

    if user_states.get(user) == "photo":

       image_url = request.form.get("MediaUrl0")

       if not image_url:
           msg.body("❗ Please send an image (not text).")
           return str(resp)

       add_product(
           user_data[user]["product"],
           user_data[user]["price"],
           user_data[user]["seller_id"],
           user_data[user]["category"],
           image_url
       )

       user_states[user] = "more"
       msg.body("✅ Product added with photo!\n\nAdd another product? (yes/no)")
       return str(resp)

    if user_states.get(user) == "price":
       user_data[user]["price"] = incoming

       product_id = add_product(
           user_data[user]["product"],
           user_data[user]["price"],
           user_data[user]["seller_id"],
           user_data[user]["category"]
       )

       user_data[user]["product_id"] = product_id
       user_states[user] = "photo_optional"

       msg.body(
           "📷 Send product photo (optional).\n"
           "You can send multiple photos.\n\n"
           "Type SKIP if no photo."
       )
       return str(resp)

    if user_states.get(user) == "photo_optional":

      image_url = request.form.get("MediaUrl0")

      # Seller skipped photos
      if incoming == "skip":
          user_states[user] = "more"
          msg.body("✅ Product saved without photo.\n\nAdd another product? (yes/no)")
          return str(resp)

      # Seller sent a photo
      if image_url:
          add_product_photo(user_data[user]["product_id"], image_url)

          msg.body("📸 Photo added! Send another or type DONE")
          return str(resp)

      # Seller finished adding photos
      if incoming == "done":
          user_states[user] = "more"
          msg.body("✅ Product saved!\n\nAdd another product? (yes/no)")
          return str(resp)

      msg.body("Send photo, DONE, or SKIP")
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

    if incoming == "myproducts":
       phone = request.form.get("From").split(":")[-1]

       products = get_seller_products(phone)

       if not products:
           msg.body("❌ You have no products listed.")
           return str(resp)

       reply = "📦 Your products:\n\n"

       for pid, name, price, category in products:
        reply += f"{pid}. {name} ({category}) - {price}\n"

       reply += "\n✏ To edit: edit PRODUCT_ID NEWPRICE\n🗑 To delete: delete PRODUCT_ID"

    if incoming.startswith("edit"):
        parts = incoming.split()

        if len(parts) < 3:
            msg.body("Usage: edit PRODUCT_ID NEWPRICE\nExample: edit 3 9usd")
            return str(resp)

        product_id = parts[1]
        new_price = parts[2]

        update_product_price(product_id, new_price)

        msg.body("✅ Price updated successfully!")
        return str(resp)

    if incoming.startswith("delete"):
        parts = incoming.split()

        if len(parts) < 2:
            msg.body("Usage: delete PRODUCT_ID\nExample: delete 3")
            return str(resp)

        product_id = parts[1]

        delete_product(product_id)

        msg.body("🗑 Product deleted successfully.")
        return str(resp)



        msg.body(reply)
        return str(resp)
 

        msg.body("Please reply YES or NO")
        return str(resp)

    # -----------------
    # MENU
    # -----------------

    if incoming in ["menu", "hi", "hello", "start"]:
        msg.body(
            "🛒 *PaMusika Marketplace*\n\n"
            "🔍 *Type product name to search*\n"
            "📝 Type *REGISTER* to sell\n\n"
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

    for row in results:
         product_id, name, price, category, seller, location, phone, photos = row

         if photos:
             for img in photos:
                 msg.media(img)

         msg.body(
             f"{seller}\n"
            f"🛒 {name} ({category})\n"
            f"💵 {price}\n"
            f"📍 {location}\n"
            f"📞 {phone}"
        )

        msg.body(reply)
        return str(resp)

if __name__ == "__main__":
    app.run()















