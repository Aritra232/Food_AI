import math
from service.database_service import restaurant_collection


# -------------------------
# DISTANCE FUNCTION
# -------------------------
def calculate_distance(lat1, lon1, lat2, lon2):

    R = 6371  # Earth radius in KM

    dlat = math.radians(lat2 - lat1)
    dlon = math.radians(lon2 - lon1)

    a = (
        math.sin(dlat / 2) ** 2 +
        math.cos(math.radians(lat1)) *
        math.cos(math.radians(lat2)) *
        math.sin(dlon / 2) ** 2
    )

    c = 2 * math.asin(math.sqrt(a))

    return R * c


# -------------------------
# NEARBY RESTAURANTS
# -------------------------
def get_nearby_restaurants(user_lat, user_lng, max_distance_km=10):

    restaurants = list(restaurant_collection.find())

    nearby = []

    for r in restaurants:

        if "lat" not in r or "lng" not in r:
            continue

        try:
            distance = calculate_distance(
                float(user_lat),
                float(user_lng),
                float(r["lat"]),
                float(r["lng"])
            )
        except:
            continue

        if distance <= max_distance_km:

            nearby.append({
                **r,
                "distance": distance
            })

    nearby.sort(key=lambda x: x["distance"])

    return nearby