from enum import Enum
from uuid import uuid4
from .model_type import ModelType
import msgspec
import os
import json
from ..exceptions import DuckChatException

class Role(Enum):
    user = "user"
    assistant = "assistant"

class Message(msgspec.Struct):
    role: Role
    content: str
    
    def to_dict(self):
        return {
            "role": self.role.value,
            "content": self.content
        }

class History(msgspec.Struct):
    model: ModelType
    messages: list[Message]

    def add_input(self, message: str) -> None:
        self.messages.append(Message(Role.user, message))

    def add_answer(self, message: str) -> None:
        self.messages.append(Message(Role.assistant, message))
        
    def to_dict(self):
        return {
            "model": self.model.value,
            "messages": [message.to_dict() for message in self.messages]
        }
        


class SavedHistory:
    def __init__(self, model: ModelType, messages: list[Message] = None, history_id: str = None):
        self.id = history_id or str(uuid4())
        self.model = model
        self.messages = messages or []

    def add_input(self, message: str) -> None:
        self.messages.append(Message(Role.user, message))

    def add_answer(self, message: str) -> None:
        self.messages.append(Message(Role.assistant, message))

    def save(self) -> None:
        """Save the current conversation history to a file."""
        file_path = f"history_{self.id}.json"
        with open(file_path, 'w') as f:
            json.dump(self.to_dict(), f, indent=4)

    @staticmethod
    def load(history_id: str) -> 'SavedHistory':
        """Load a conversation history from a file."""
        file_path = f"history_{history_id}.json"
        if not os.path.exists(file_path):
            raise DuckChatException(f"No history found for ID {history_id}")
        
        with open(file_path, 'r') as f:
            history_data = json.load(f)
        
        return SavedHistory(
            model=ModelType(history_data['model']),
            messages=[Message(Role(msg['role']), msg['content']) for msg in history_data['messages']],
            history_id=history_data['id']
        )

    def to_dict(self):
        return {
            "id": self.id,
            "model": self.model.value,
            "messages": [message.to_dict() for message in self.messages]
        }