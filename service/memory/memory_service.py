from datetime import datetime

from service.data.database_service import conversation_collection, chat_session_collection


def _normalize_session_id(chat_session_id):
    return chat_session_id or "default"


def get_chat_sessions(user_id):

    sessions = chat_session_collection.find(
        {"user_id": user_id}
    ).sort("updated_at", -1)

    session_list = []
    for session in sessions:
        message_count = session.get("message_count", 0)
        if message_count <= 0:
            continue

        first_user_message = conversation_collection.find_one(
            {
                "user_id": user_id,
                "chat_session_id": session.get("chat_session_id"),
                "role": "user"
            },
            sort=[("timestamp", 1)]
        )

        display_title = session.get("title") or "New chat"
        if first_user_message and first_user_message.get("content"):
            display_title = first_user_message.get("content")[:48]

        session_list.append({
            "chat_session_id": session.get("chat_session_id"),
            "title": display_title,
            "message_count": message_count,
            "created_at": session.get("created_at").isoformat() if session.get("created_at") else None,
            "updated_at": session.get("updated_at").isoformat() if session.get("updated_at") else None,
        })

    return session_list


def ensure_chat_session(user_id, chat_session_id, first_message=None):

    chat_session_id = _normalize_session_id(chat_session_id)
    now = datetime.utcnow()

    existing = chat_session_collection.find_one({
        "user_id": user_id,
        "chat_session_id": chat_session_id
    })

    if existing:
        update_doc = {"updated_at": now}
        if existing.get("title") is None and first_message:
            update_doc["title"] = first_message[:48]
        chat_session_collection.update_one(
            {"_id": existing["_id"]},
            {"$set": update_doc}
        )
        return chat_session_id

    chat_session_collection.insert_one({
        "user_id": user_id,
        "chat_session_id": chat_session_id,
        "title": first_message[:48] if first_message else "New chat",
        "message_count": 0,
        "created_at": now,
        "updated_at": now
    })
    return chat_session_id


def get_conversation(user_id, chat_session_id=None):

    query = {"user_id": user_id}
    if chat_session_id:
        query["chat_session_id"] = chat_session_id

    messages = conversation_collection.find(
        query
    ).sort("timestamp", 1)

    conversation_history = []

    for message in messages:

        conversation_history.append({
            "role": message["role"],
            "content": message["content"]
        })

    return conversation_history


def add_message(user_id, role, content, chat_session_id=None):

    chat_session_id = _normalize_session_id(chat_session_id)
    existing = chat_session_collection.find_one({
        "user_id": user_id,
        "chat_session_id": chat_session_id
    })

    if not existing and role == "assistant":
        return

    if not existing and role == "user":
        ensure_chat_session(
            user_id,
            chat_session_id,
            first_message=content
        )
        existing = chat_session_collection.find_one({
            "user_id": user_id,
            "chat_session_id": chat_session_id
        })

    conversation_collection.insert_one({
        "user_id": user_id,
        "chat_session_id": chat_session_id,
        "role": role,
        "content": content,
        "timestamp": datetime.utcnow()
    })

    update_doc = {
        "$set": {"updated_at": datetime.utcnow()},
        "$inc": {"message_count": 1}
    }
    if role == "user" and content and not (existing or {}).get("title"):
        update_doc["$set"]["title"] = content[:48]

    chat_session_collection.update_one(
        {
            "user_id": user_id,
            "chat_session_id": chat_session_id
        },
        update_doc
    )
