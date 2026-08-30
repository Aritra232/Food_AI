from datetime import datetime

from bson import ObjectId

from service.data.database_service import ai_conversation_collection, ai_message_collection
from service.data.mongo_utils import serialize_mongo


def _object_id(value):
    try:
        return ObjectId(value)
    except Exception:
        return None


def create_conversation(user_id, title=None):
    now = datetime.utcnow()
    document = {
        "user_id": user_id,
        "title": title or "New chat",
        "is_pinned": False,
        "status": "active",
        "created_at": now,
        "updated_at": now,
    }
    result = ai_conversation_collection.insert_one(document)
    document["_id"] = result.inserted_id
    return serialize_mongo(document)


def get_or_create_conversation(user_id, conversation_id=None, first_message=None):
    object_id = _object_id(conversation_id)
    if object_id:
        existing = ai_conversation_collection.find_one({"_id": object_id, "user_id": user_id})
        if existing:
            ai_conversation_collection.update_one(
                {"_id": object_id},
                {"$set": {"updated_at": datetime.utcnow()}},
            )
            return serialize_mongo(existing)
    return create_conversation(user_id, title=(first_message or "New chat")[:60])


def list_conversations(user_id, limit=30):
    cursor = ai_conversation_collection.find({"user_id": user_id}).sort(
        [("is_pinned", -1), ("updated_at", -1)]
    ).limit(int(limit or 30))
    return [serialize_mongo(doc) for doc in cursor]


def get_messages(conversation_id, user_id=None, limit=100):
    object_id = _object_id(conversation_id)
    if not object_id:
        return []
    query = {"conversation_id": object_id}
    if user_id:
        query["user_id"] = user_id
    cursor = ai_message_collection.find(query).sort("created_at", 1).limit(int(limit or 100))
    return [serialize_mongo(doc) for doc in cursor]


def add_message(user_id, conversation_id, role, message, intent=None, structured_data=None):
    object_id = _object_id(conversation_id)
    if not object_id:
        conversation = get_or_create_conversation(user_id, first_message=message if role == "user" else None)
        object_id = ObjectId(conversation["_id"])

    now = datetime.utcnow()
    document = {
        "conversation_id": object_id,
        "user_id": user_id,
        "role": role,
        "message": message,
        "intent": intent,
        "structured_data": structured_data or {},
        "created_at": now,
    }
    result = ai_message_collection.insert_one(document)
    ai_conversation_collection.update_one(
        {"_id": object_id},
        {"$set": {"updated_at": now}},
    )
    document["_id"] = result.inserted_id
    return serialize_mongo(document)
