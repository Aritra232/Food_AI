from service.data.database_service import session_collection


def save_session(user_id, data):

    existing = session_collection.find_one({
        "user_id": user_id
    })

    if existing:

        session_collection.update_one(
            {
                "user_id": user_id
            },
            {
                "$set": data
            }
        )

    else:

        data["user_id"] = user_id

        session_collection.insert_one(data)


def get_session(user_id):

    session = session_collection.find_one({
        "user_id": user_id
    })

    if not session:
        return {}

    session["_id"] = str(session["_id"])

    return session


def clear_session(user_id):

    session_collection.delete_one({
        "user_id": user_id
    })
