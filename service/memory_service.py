from datetime import datetime

from service.database_service import conversation_collection


def get_conversation(user_id):

    messages = conversation_collection.find(
        {"user_id": user_id}
    ).sort("timestamp", 1)

    conversation_history = []

    for message in messages:

        conversation_history.append({
            "role": message["role"],
            "content": message["content"]
        })

    return conversation_history


def add_message(user_id, role, content):

    conversation_collection.insert_one({
        "user_id": user_id,
        "role": role,
        "content": content,
        "timestamp": datetime.utcnow()
    })