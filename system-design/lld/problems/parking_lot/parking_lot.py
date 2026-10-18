"""Parking Lot - LLD. Patterns: Strategy (spot finding, pricing), Enum mapping, Lock for thread safety."""
from __future__ import annotations

import math
import threading
import uuid
from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from datetime import datetime, timedelta
from enum import Enum


class VehicleType(Enum):
    BIKE = "bike"
    CAR = "car"
    TRUCK = "truck"


class SpotType(Enum):
    MOTORCYCLE = "motorcycle"
    COMPACT = "compact"
    LARGE = "large"


SPOT_FOR_VEHICLE = {
    VehicleType.BIKE: SpotType.MOTORCYCLE,
    VehicleType.CAR: SpotType.COMPACT,
    VehicleType.TRUCK: SpotType.LARGE,
}


@dataclass(frozen=True)
class Vehicle:
    plate: str
    type: VehicleType


@dataclass
class ParkingSpot:
    id: str
    type: SpotType
    vehicle: Vehicle | None = None

    def is_free(self) -> bool:
        return self.vehicle is None


@dataclass
class ParkingFloor:
    number: int
    spots: list[ParkingSpot]

    def free_spots(self, spot_type: SpotType) -> list[ParkingSpot]:
        return [s for s in self.spots if s.type == spot_type and s.is_free()]


@dataclass
class Ticket:
    vehicle: Vehicle
    spot: ParkingSpot
    entry_time: datetime = field(default_factory=datetime.now)
    id: str = field(default_factory=lambda: uuid.uuid4().hex[:8])


# ---------- Strategies ----------
class SpotStrategy(ABC):
    @abstractmethod
    def find(self, floors: list[ParkingFloor], spot_type: SpotType) -> ParkingSpot | None: ...


class NearestFirstStrategy(SpotStrategy):
    def find(self, floors, spot_type):
        for floor in floors:  # floors sorted by number = nearest first
            free = floor.free_spots(spot_type)
            if free:
                return free[0]
        return None


class PricingStrategy(ABC):
    @abstractmethod
    def fee(self, ticket: Ticket, exit_time: datetime) -> float: ...


class HourlyPricing(PricingStrategy):
    RATES = {SpotType.MOTORCYCLE: 10, SpotType.COMPACT: 20, SpotType.LARGE: 50}

    def fee(self, ticket, exit_time):
        # Round partial hours UP; charge at least 1 hour (also covers clock skew giving <= 0).
        hours = max(1, math.ceil((exit_time - ticket.entry_time).total_seconds() / 3600))
        return hours * self.RATES[ticket.spot.type]


# ---------- Service ----------
class ParkingLot:
    def __init__(self, floors: list[ParkingFloor], strategy: SpotStrategy, pricing: PricingStrategy):
        self.floors = sorted(floors, key=lambda f: f.number)
        self.strategy = strategy
        self.pricing = pricing
        self.active: dict[str, Ticket] = {}
        self._lock = threading.Lock()

    def park(self, vehicle: Vehicle) -> Ticket:
        spot_type = SPOT_FOR_VEHICLE[vehicle.type]
        with self._lock:  # find + assign must be atomic
            spot = self.strategy.find(self.floors, spot_type)
            if spot is None:
                raise RuntimeError(f"No {spot_type.value} spot available")
            spot.vehicle = vehicle
            ticket = Ticket(vehicle, spot)
            self.active[ticket.id] = ticket
        return ticket

    def unpark(self, ticket_id: str, exit_time: datetime | None = None) -> float:
        with self._lock:
            ticket = self.active.pop(ticket_id, None)  # pop: a ticket can't be used twice
            if ticket is None:
                raise KeyError("invalid or already used ticket")
            ticket.spot.vehicle = None
        # Fee calculation is pure computation on the ticket: no need to hold the lock.
        return self.pricing.fee(ticket, exit_time or datetime.now())

    def free_count(self, spot_type: SpotType) -> int:
        with self._lock:
            return sum(len(f.free_spots(spot_type)) for f in self.floors)


def build_lot(num_floors: int = 2) -> ParkingLot:
    floors = []
    for n in range(1, num_floors + 1):
        spots = (
            [ParkingSpot(f"F{n}-M{i}", SpotType.MOTORCYCLE) for i in range(2)]
            + [ParkingSpot(f"F{n}-C{i}", SpotType.COMPACT) for i in range(2)]
            + [ParkingSpot(f"F{n}-L{i}", SpotType.LARGE) for i in range(1)]
        )
        floors.append(ParkingFloor(n, spots))
    return ParkingLot(floors, NearestFirstStrategy(), HourlyPricing())


if __name__ == "__main__":
    lot = build_lot()
    t1 = lot.park(Vehicle("KA01", VehicleType.CAR))
    t2 = lot.park(Vehicle("KA02", VehicleType.TRUCK))
    print(f"Car parked at {t1.spot.id}, truck at {t2.spot.id}")

    fee = lot.unpark(t1.id, exit_time=t1.entry_time + timedelta(hours=2, minutes=10))
    print(f"Car fee for 2h10m: {fee}")  # 3 hours * 20 = 60
    print(f"Free compact spots: {lot.free_count(SpotType.COMPACT)}")  # 4 (2 floors x 2)
    try:
        lot.unpark(t1.id)
    except KeyError as e:
        print("Reusing ticket:", e)

    # Concurrency check: 10 threads race for 4 compact spots
    lot = build_lot()
    results: list[str] = []

    def try_park(i: int):
        try:
            results.append(lot.park(Vehicle(f"C{i}", VehicleType.CAR)).spot.id)
        except RuntimeError:
            results.append("FULL")

    threads = [threading.Thread(target=try_park, args=(i,)) for i in range(10)]
    for t in threads:
        t.start()
    for t in threads:
        t.join()
    spots = [r for r in results if r != "FULL"]
    print(f"Parked {len(spots)} cars, unique spots: {len(set(spots)) == len(spots)}")
