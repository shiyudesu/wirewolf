"""Agent 记忆管理."""

from __future__ import annotations

from collections import deque
from typing import Optional

from app.models.log import ThoughtRecord, Message


class ConversationBuffer:
    """内存级对话缓冲区，管理私有思考和公共消息."""

    def __init__(self, max_private: int = 100, max_public: int = 200) -> None:
        self.private_memory: deque[ThoughtRecord] = deque(maxlen=max_private)
        self.public_memory: deque[Message] = deque(maxlen=max_public)

    def add_thought(self, record: ThoughtRecord) -> None:
        self.private_memory.append(record)

    def add_message(self, message: Message) -> None:
        self.public_memory.append(message)

    def get_recent_thoughts(self, n: int = 10) -> list[ThoughtRecord]:
        return list(self.private_memory)[-n:]

    def get_recent_messages(self, n: int = 20) -> list[Message]:
        return list(self.public_memory)[-n:]

    def get_thoughts_by_round(self, round_num: int) -> list[ThoughtRecord]:
        return [t for t in self.private_memory if t.round_num == round_num]

    def get_messages_by_round(self, round_num: int) -> list[Message]:
        return [m for m in self.public_memory if m.round_num == round_num]

    def summarize_public(self, max_chars: int = 2000) -> str:
        """将公共消息压缩为文本摘要."""
        lines = []
        for msg in self.public_memory:
            prefix = "[系统]" if msg.msg_type == "system" else f"[{msg.speaker_id}号]"
            lines.append(f"{prefix} {msg.content}")
        text = "\n".join(lines)
        if len(text) > max_chars:
            text = "...\n" + text[-max_chars:]
        return text

    def clear(self) -> None:
        self.private_memory.clear()
        self.public_memory.clear()
