from service.database_service import orders_collection


# -------------------------
# GET OR CREATE CART
# -------------------------
def get_or_create_cart(user_id):

    cart = orders_collection.find_one({
        "user_id": user_id,
        "status": "cart"
    })

    if not cart:

        cart = {
            "user_id": user_id,
            "items": [],
            "total_price": 0,
            "status": "cart"
        }

        orders_collection.insert_one(cart)

        cart = orders_collection.find_one({
            "user_id": user_id,
            "status": "cart"
        })

    cart["_id"] = str(cart["_id"])

    return cart


# -------------------------
# CALCULATE TOTAL
# -------------------------
def calculate_total(items):

    total = 0

    for item in items:
        total += item["price"] * item["quantity"]

    return total


# -------------------------
# ADD ITEM TO CART
# -------------------------
def add_item(user_id, item):

    cart = get_or_create_cart(user_id)

    found = False

    for existing in cart["items"]:

        if existing["menu_id"] == item["menu_id"]:

            existing["quantity"] += 1
            found = True
            break

    if not found:

        item["quantity"] = 1
        cart["items"].append(item)

    cart["total_price"] = calculate_total(
        cart["items"]
    )

    orders_collection.update_one(
        {
            "user_id": user_id,
            "status": "cart"
        },
        {
            "$set": {
                "items": cart["items"],
                "total_price": cart["total_price"]
            }
        }
    )

    updated_cart = orders_collection.find_one({
        "user_id": user_id,
        "status": "cart"
    })

    updated_cart["_id"] = str(updated_cart["_id"])

    return updated_cart


# -------------------------
# REMOVE ITEM
# -------------------------
def remove_item(user_id, menu_id):

    cart = get_or_create_cart(user_id)

    updated_items = []

    for item in cart["items"]:

        if item["menu_id"] != menu_id:
            updated_items.append(item)

    total = calculate_total(updated_items)

    orders_collection.update_one(
        {
            "user_id": user_id,
            "status": "cart"
        },
        {
            "$set": {
                "items": updated_items,
                "total_price": total
            }
        }
    )

    updated_cart = orders_collection.find_one({
        "user_id": user_id,
        "status": "cart"
    })

    updated_cart["_id"] = str(updated_cart["_id"])

    return updated_cart