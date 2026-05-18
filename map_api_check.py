import os
import sys
from urllib.parse import urlencode

import requests
from dotenv import load_dotenv


GEOCODE_URL = "https://maps.googleapis.com/maps/api/geocode/json"


def get_api_key():
    load_dotenv()

    candidates = [
        os.getenv("MAPS_API_KEY"),
        os.getenv("Maps_Demo_Key"),
        os.getenv("MAPS_DEMO_KEY"),
    ]

    for key in candidates:
        if key and key.strip():
            return key.strip()

    return None


def check_google_maps_api(api_key, address="Dhaka"):
    params = {
        "address": address,
        "key": api_key,
    }

    response = requests.get(GEOCODE_URL, params=params, timeout=20)

    print("HTTP Status:", response.status_code)
    print("Requested URL:", response.url)

    data = response.json()
    status = data.get("status")
    print("API Status:", status)

    if status == "OK":
        results = data.get("results", [])
        if results:
            first = results[0]
            print("Formatted Address:", first.get("formatted_address"))
            location = first.get("geometry", {}).get("location", {})
            print("Latitude:", location.get("lat"))
            print("Longitude:", location.get("lng"))
        print("Result: API is working.")
        return 0

    print("Result: API did not return OK.")
    if data.get("error_message"):
        print("Error Message:", data["error_message"])

    if status == "REQUEST_DENIED":
        print("Likely causes: API not enabled, key restriction issue, or billing problem.")
    elif status == "OVER_QUERY_LIMIT":
        print("Likely cause: quota exceeded.")
    elif status == "INVALID_REQUEST":
        print("Likely cause: bad request parameters.")
    elif status == "ZERO_RESULTS":
        print("No results found for the test address.")

    return 1


if __name__ == "__main__":
    api_key = get_api_key()
    if not api_key:
        print("No Google Maps API key found in .env.")
        print("Add one of these keys to .env: MAPS_API_KEY or Maps_Demo_Key")
        sys.exit(2)

    test_address = sys.argv[1] if len(sys.argv) > 1 else "Dhaka"
    raise SystemExit(check_google_maps_api(api_key, test_address))
