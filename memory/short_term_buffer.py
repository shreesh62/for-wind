"""Short-term conversational memory buffer."""

from collections import deque
from dataclasses import dataclass, field
from typing import Deque, List, Tuple

ConversationTurn = Tuple[str, str]


@dataclass
class ShortTermMemory:
    """Maintains a rolling buffer of recent dialogue turns."""

    max_turns: int = 8
    history: Deque[ConversationTurn] = field(default_factory=deque)

    def add_turn(self, user_text: str, assistant_text: str) -> None:
        self.history.append((user_text, assistant_text))
        while len(self.history) > self.max_turns:
            self.history.popleft()

    def get_recent(self) -> List[ConversationTurn]:
        return list(self.history)

    def clear(self) -> None:
        self.history.clear()
