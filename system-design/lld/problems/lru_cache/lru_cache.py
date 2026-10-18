"""LRU Cache - O(1) get/put using HashMap + Doubly Linked List. Thread-safe, optional TTL."""
from __future__ import annotations

import threading
import time
from collections import OrderedDict
from typing import Any


class Node:
    __slots__ = ("key", "value", "expires_at", "prev", "next")

    def __init__(self, key: Any = None, value: Any = None, expires_at: float | None = None):
        self.key, self.value, self.expires_at = key, value, expires_at
        self.prev: Node | None = None
        self.next: Node | None = None


class LRUCache:
    def __init__(self, capacity: int):
        if capacity <= 0:
            raise ValueError("capacity must be > 0")
        self.capacity = capacity
        self.map: dict[Any, Node] = {}
        self.head, self.tail = Node(), Node()  # dummies
        self.head.next, self.tail.prev = self.tail, self.head
        self._lock = threading.Lock()

    # --- linked-list helpers ---
    def _remove(self, node: Node) -> None:
        node.prev.next, node.next.prev = node.next, node.prev

    def _add_front(self, node: Node) -> None:
        node.prev, node.next = self.head, self.head.next
        self.head.next.prev = node
        self.head.next = node

    # --- public API ---
    def get(self, key: Any) -> Any | None:
        with self._lock:
            node = self.map.get(key)
            if node is None:
                return None
            if node.expires_at is not None and time.monotonic() > node.expires_at:
                self._remove(node)
                del self.map[key]
                return None
            self._remove(node)
            self._add_front(node)
            return node.value

    def put(self, key: Any, value: Any, ttl: float | None = None) -> None:
        expires = time.monotonic() + ttl if ttl is not None else None  # ttl=0 means 'expire now'
        with self._lock:
            if key in self.map:
                node = self.map[key]
                node.value, node.expires_at = value, expires
                self._remove(node)
                self._add_front(node)
                return
            if len(self.map) >= self.capacity:
                lru = self.tail.prev
                self._remove(lru)
                del self.map[lru.key]
            node = Node(key, value, expires)
            self.map[key] = node
            self._add_front(node)

    def keys_mru_to_lru(self) -> list[Any]:
        out, cur = [], self.head.next
        while cur is not self.tail:
            out.append(cur.key)
            cur = cur.next
        return out


class OrderedDictLRU:
    """The 10-line Pythonic version - good to mention in interviews."""

    def __init__(self, capacity: int):
        self.capacity, self.data = capacity, OrderedDict()

    def get(self, key):
        if key not in self.data:
            return None
        self.data.move_to_end(key, last=False)
        return self.data[key]

    def put(self, key, value):
        self.data[key] = value
        self.data.move_to_end(key, last=False)
        if len(self.data) > self.capacity:
            self.data.popitem(last=True)


if __name__ == "__main__":
    c = LRUCache(3)
    for k, v in [(1, "A"), (2, "B"), (3, "C")]:
        c.put(k, v)
    print("order:", c.keys_mru_to_lru())  # [3, 2, 1]
    c.get(1)
    print("after get(1):", c.keys_mru_to_lru())  # [1, 3, 2]
    c.put(4, "D")
    print("after put(4) evicts 2:", c.keys_mru_to_lru(), "get(2) ->", c.get(2))

    c.put("tmp", "x", ttl=0.1)
    time.sleep(0.15)
    print("expired key ->", c.get("tmp"))

    o = OrderedDictLRU(2)
    o.put("a", 1); o.put("b", 2); o.get("a"); o.put("c", 3)
    print("OrderedDict LRU keys:", list(o.data))  # ['c', 'a']
