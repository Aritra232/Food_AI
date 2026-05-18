from service.database_service import db

state_collection = db["conversation_state"]


def get_state(user_id):

    state = state_collection.find_one(
        {"user_id": user_id}
    )

    if not state:

        state_collection.insert_one({
            "user_id": user_id,
            "state": "idle"
        })

        return "idle"

    return state["state"]


def set_state(user_id, new_state):

    state_collection.update_one(
        {"user_id": user_id},
        {"$set": {"state": new_state}},
        upsert=True
    )