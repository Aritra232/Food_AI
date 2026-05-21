from datetime import datetime
from uuid import uuid4

from service.data.database_service import conversation_collection, chat_sessions_collection


def _serialize_datetime(value):
    if isinstance(value, datetime):
        return value.isoformat()
    return value


def _build_session_preview(content):
    text = str(content or "").strip()
    if len(text) <= 80:
        return text
    return f"{text[:77]}..."


def _create_chat_session(user_id, title=None):
    session_id = uuid4().hex
    now = datetime.utcnow()
    session_doc = {
        "session_id": session_id,
        "user_id": user_id,
        "title": title or "New chat",
        "preview": "",
        "message_count": 0,
        "is_active": True,
        "created_at": now,
        "updated_at": now
    }

    chat_sessions_collection.update_many(
        {"user_id": user_id},
        {"$set": {"is_active": False}}
    )
    chat_sessions_collection.insert_one(session_doc)
    return session_doc


def get_or_create_chat_session(user_id, session_id=None):

    if session_id:
        session = chat_sessions_collection.find_one({"user_id": user_id, "session_id": session_id})
        if session:
            chat_sessions_collection.update_many(
                {"user_id": user_id},
                {"$set": {"is_active": False}}
            )
            chat_sessions_collection.update_one(
                {"user_id": user_id, "session_id": session_id},
                {"$set": {"is_active": True, "updated_at": datetime.utcnow()}}
            )
            session["_id"] = str(session["_id"])
            return session

    active_session = chat_sessions_collection.find_one(
        {"user_id": user_id, "is_active": True},
        sort=[("updated_at", -1)]
    )
    if active_session:
        active_session["_id"] = str(active_session["_id"])
        return active_session

    newest_session = chat_sessions_collection.find_one(
        {"user_id": user_id},
        sort=[("updated_at", -1)]
    )
    if newest_session:
        chat_sessions_collection.update_many(
            {"user_id": user_id},
            {"$set": {"is_active": False}}
        )
        chat_sessions_collection.update_one(
            {"_id": newest_session["_id"]},
            {"$set": {"is_active": True, "updated_at": datetime.utcnow()}}
        )
        newest_session["_id"] = str(newest_session["_id"])
        return newest_session

    return _create_chat_session(user_id)


def create_new_chat_session(user_id, title=None):

    return _create_chat_session(user_id, title=title)


def list_chat_sessions(user_id):

    sessions = []
    for session in chat_sessions_collection.find({"user_id": user_id}).sort("updated_at", -1):
        session["_id"] = str(session["_id"])
        session["created_at"] = _serialize_datetime(session.get("created_at"))
        session["updated_at"] = _serialize_datetime(session.get("updated_at"))
        sessions.append(session)

    return sessions


def get_conversation(user_id, session_id=None):

    session = get_or_create_chat_session(user_id, session_id=session_id)
    active_session_id = session.get("session_id")

    messages = conversation_collection.find(
        {"user_id": user_id, "session_id": active_session_id}
    ).sort("timestamp", 1)

    conversation_history = []

    for message in messages:

        conversation_history.append({
            "role": message["role"],
            "content": message["content"],
            "timestamp": _serialize_datetime(message.get("timestamp"))
        })

    return conversation_history


def add_message(user_id, role, content, session_id=None):

    session = get_or_create_chat_session(user_id, session_id=session_id)
    active_session_id = session.get("session_id")
    now = datetime.utcnow()

    conversation_collection.insert_one({
        "user_id": user_id,
        "session_id": active_session_id,
        "role": role,
        "content": content,
        "timestamp": now
    })

    updates = {
        "updated_at": now,
        "preview": _build_session_preview(content)
    }

    if role == "user" and session.get("title") in {None, "", "New chat"}:
        updates["title"] = _build_session_preview(content) or "New chat"

    chat_sessions_collection.update_one(
        {"user_id": user_id, "session_id": active_session_id},
        {
            "$inc": {"message_count": 1},
            "$set": updates
        }
    )
