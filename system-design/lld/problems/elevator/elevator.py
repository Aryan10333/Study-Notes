"""Elevator System - LLD. Patterns: Strategy (dispatch). Algorithm: LOOK with two heaps. Simulated in steps.

Simplification (state it in an interview): every request becomes a "stop" floor. The hall-call
direction (UP/DOWN button) is used by the dispatcher to choose an elevator, but the elevator stops at
every stop floor it passes in its current direction. A fuller version keeps hall calls tagged with
their direction and serves an opposite-direction call only on the return sweep.
"""
from __future__ import annotations

import heapq
from abc import ABC, abstractmethod
from enum import Enum


class Direction(Enum):
    UP = 1
    DOWN = -1
    IDLE = 0


class Elevator:
    def __init__(self, eid: int, floor: int = 0):
        self.id, self.floor = eid, floor
        self.direction = Direction.IDLE
        self.up_stops: list[int] = []     # min-heap
        self.down_stops: list[int] = []   # max-heap (store negatives)

    def add_stop(self, floor: int) -> None:
        if floor == self.floor:
            print(f"    E{self.id} already at {floor}: doors open")
            return
        # Floors above go in the up heap (served on the way up, lowest first);
        # floors below go in the down heap (served on the way down, highest first).
        if floor > self.floor and floor not in self.up_stops:
            heapq.heappush(self.up_stops, floor)
        elif floor < self.floor and -floor not in self.down_stops:
            heapq.heappush(self.down_stops, -floor)
        if self.direction == Direction.IDLE and floor != self.floor:
            self.direction = Direction.UP if floor > self.floor else Direction.DOWN

    def has_work(self) -> bool:
        return bool(self.up_stops or self.down_stops)

    def step(self) -> None:
        """Move one floor; open doors if this floor is a stop."""
        if self.direction == Direction.UP and not self.up_stops:
            self.direction = Direction.DOWN if self.down_stops else Direction.IDLE
        elif self.direction == Direction.DOWN and not self.down_stops:
            self.direction = Direction.UP if self.up_stops else Direction.IDLE
        if self.direction == Direction.IDLE:
            return
        self.floor += self.direction.value
        if self.direction == Direction.UP and self.up_stops and self.up_stops[0] == self.floor:
            heapq.heappop(self.up_stops)
            print(f"    E{self.id} doors open at {self.floor}")
        elif self.direction == Direction.DOWN and self.down_stops and -self.down_stops[0] == self.floor:
            heapq.heappop(self.down_stops)
            print(f"    E{self.id} doors open at {self.floor}")
        if not self.has_work():
            self.direction = Direction.IDLE   # nothing left to serve

    def __repr__(self):
        return f"E{self.id}@{self.floor}({self.direction.name})"


class DispatchStrategy(ABC):
    @abstractmethod
    def choose(self, elevators: list[Elevator], floor: int, direction: Direction) -> Elevator: ...


class NearestElevatorStrategy(DispatchStrategy):
    def choose(self, elevators, floor, direction):
        def cost(e: Elevator) -> int:
            distance = abs(e.floor - floor)
            if e.direction == Direction.IDLE:
                return distance
            moving_toward = (e.direction == Direction.UP and e.floor <= floor) or (
                e.direction == Direction.DOWN and e.floor >= floor
            )
            same_dir = e.direction == direction
            return distance if (moving_toward and same_dir) else distance + 100  # penalty
        return min(elevators, key=cost)


class ElevatorSystem:
    def __init__(self, n_elevators: int, dispatcher: DispatchStrategy):
        self.elevators = [Elevator(i) for i in range(n_elevators)]
        self.dispatcher = dispatcher

    def request(self, floor: int, direction: Direction) -> Elevator:  # external (hall) button
        e = self.dispatcher.choose(self.elevators, floor, direction)
        e.add_stop(floor)
        print(f"  hall call floor {floor} {direction.name} -> E{e.id}")
        return e

    def press(self, eid: int, floor: int) -> None:  # internal (cabin) button
        self.elevators[eid].add_stop(floor)

    def step(self) -> None:
        for e in self.elevators:
            e.step()


if __name__ == "__main__":
    system = ElevatorSystem(2, NearestElevatorStrategy())
    system.elevators[1].floor = 8
    system.request(3, Direction.UP)     # E0 is nearer
    system.request(7, Direction.DOWN)   # E1 is nearer
    system.press(0, 6)
    system.press(1, 1)
    for t in range(10):
        system.step()
        print(f"t={t + 1}: {system.elevators}")
        if not any(e.has_work() for e in system.elevators):
            break
