"""Splitwise - LLD. Pattern: Strategy (split types). Greedy debt simplification with heaps.
Amounts are in integer paise/cents to avoid float rounding errors."""
from __future__ import annotations

import heapq
from abc import ABC, abstractmethod
from collections import defaultdict
from dataclasses import dataclass


@dataclass(frozen=True)
class User:
    id: str
    name: str


@dataclass(frozen=True)
class Split:
    user: User
    amount: int


class SplitStrategy(ABC):
    @abstractmethod
    def compute(self, amount: int, users: list[User], values: list[int] | None) -> list[Split]: ...


class EqualSplit(SplitStrategy):
    def compute(self, amount, users, values=None):
        if not users:
            raise ValueError("need at least one participant")
        share, rem = divmod(amount, len(users))
        # first `rem` users pay 1 extra paisa so total matches exactly
        return [Split(u, share + (1 if i < rem else 0)) for i, u in enumerate(users)]


class ExactSplit(SplitStrategy):
    def compute(self, amount, users, values):
        if values is None or len(values) != len(users):
            raise ValueError("one exact amount per participant required")
        if sum(values) != amount:
            raise ValueError("exact amounts must sum to total")
        return [Split(u, v) for u, v in zip(users, values)]


class PercentSplit(SplitStrategy):
    def compute(self, amount, users, values):
        if values is None or len(values) != len(users):
            raise ValueError("one percentage per participant required")
        if sum(values) != 100:
            raise ValueError("percents must sum to 100")
        splits = [Split(u, amount * p // 100) for u, p in zip(users, values)]
        diff = amount - sum(s.amount for s in splits)  # rounding leftover -> first user
        splits[0] = Split(splits[0].user, splits[0].amount + diff)
        return splits


class ExpenseManager:
    def __init__(self):
        self.net: dict[User, int] = defaultdict(int)  # +ve = is owed, -ve = owes

    def add_expense(self, paid_by: User, amount: int, users: list[User],
                    strategy: SplitStrategy, values: list[int] | None = None) -> None:
        if amount <= 0:
            raise ValueError("amount must be positive")
        for split in strategy.compute(amount, users, values):
            self.net[split.user] -= split.amount
        self.net[paid_by] += amount

    def simplify(self) -> list[tuple[User, User, int]]:
        creditors = [(-amt, u.id, u) for u, amt in self.net.items() if amt > 0]  # max-heap
        debtors = [(amt, u.id, u) for u, amt in self.net.items() if amt < 0]     # most negative first
        heapq.heapify(creditors)
        heapq.heapify(debtors)
        txns = []
        while creditors and debtors:
            c_amt, cid, c = heapq.heappop(creditors)
            d_amt, did, d = heapq.heappop(debtors)
            settle = min(-c_amt, -d_amt)
            txns.append((d, c, settle))
            if -c_amt - settle:
                heapq.heappush(creditors, (c_amt + settle, cid, c))
            if -d_amt - settle:
                heapq.heappush(debtors, (d_amt + settle, did, d))
        return txns


if __name__ == "__main__":
    print("EqualSplit of 100.00 among 3:", [x.amount for x in EqualSplit().compute(10000, [User("x", "X"), User("y", "Y"), User("z", "Z")])])
    a, b, c, d = (User(x, x.upper()) for x in "abcd")
    m = ExpenseManager()
    m.add_expense(a, 120000, [a, b, c, d], EqualSplit())               # dinner 1200.00
    m.add_expense(b, 50000, [a, c], ExactSplit(), [20000, 30000])     # taxi 500.00
    m.add_expense(c, 30000, [b, d], PercentSplit(), [60, 40])         # movie 300.00

    assert sum(m.net.values()) == 0, "nets must always sum to zero"
    print("net balances (rupees):")
    for u, amt in m.net.items():
        print(f"  {u.name}: {amt / 100:+.2f}")
    print("simplified settlements:")
    for debtor, creditor, amt in m.simplify():
        print(f"  {debtor.name} pays {creditor.name} {amt / 100:.2f}")
