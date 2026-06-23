"""Token-budgeted context packing for SQL-generation prompts (Vanna-style).

Three channels of retrieval evidence are packed into the prompt under separate
per-channel token budgets plus a hard total budget:

* **schema/DDL** — the selected tables' columns/types/comments;
* **examples** — few-shot question→SQL pairs (``data_training``);
* **docs** — terminology / business glossary;
* **samples** — representative rows per table.

Channels are packed in priority order (schema first by default — it is the most
load-bearing evidence). Within a channel, items are added greedily until either
the channel budget or the remaining total budget is exhausted; an item that
does not fit is dropped whole (no partial items) and the channel is flagged
``truncated``. This keeps large schemas from overflowing the model context
window while preserving the most relevant evidence.
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Callable, Optional


def default_token_counter(text: str) -> int:
    """Rough token estimate (~4 chars/token), never zero for non-empty text."""
    if not text:
        return 0
    return max(1, len(text) // 4)


@dataclass
class PackedChannel:
    name: str
    items: list
    tokens: int
    truncated: bool


@dataclass
class BuildContext:
    channels: list  # list[PackedChannel], in priority order
    total_tokens: int = 0

    def text(self, separator: str = "\n\n") -> str:
        return separator.join(item for channel in self.channels for item in channel.items)


class ContextPacker:
    def __init__(
        self,
        channel_budgets: dict,
        total_budget: int,
        *,
        priority: Optional[list] = None,
        token_counter: Optional[Callable] = None,
    ):
        self.channel_budgets = dict(channel_budgets)
        self.total_budget = total_budget
        self.priority = list(priority) if priority else list(self.channel_budgets.keys())
        self._count = token_counter or default_token_counter

    def pack(self, channels: dict) -> BuildContext:
        packed: list = []
        total_used = 0

        for name in self.priority:
            budget = self.channel_budgets.get(name, 0)
            packed_items: list = []
            used = 0
            truncated = False

            for item in channels.get(name, []):
                item_tokens = self._count(item)
                channel_remaining = budget - used
                total_remaining = self.total_budget - total_used
                if item_tokens <= channel_remaining and item_tokens <= total_remaining:
                    packed_items.append(item)
                    used += item_tokens
                    total_used += item_tokens
                else:
                    truncated = True
                    break

            packed.append(PackedChannel(name=name, items=packed_items, tokens=used, truncated=truncated))

        return BuildContext(channels=packed, total_tokens=total_used)
