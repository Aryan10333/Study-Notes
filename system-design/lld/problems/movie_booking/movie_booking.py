"""Movie Ticket Booking - LLD.
Focus: temporary seat holds with expiry, per-show locking, all-or-nothing multi-seat booking."""
from __future__ import annotations

import threading
import time
import uuid
from dataclasses import dataclass, field
from enum import Enum


class SeatStatus(Enum):
    AVAILABLE = "available"
    HELD = "held"        # temporarily reserved while the user pays
    BOOKED = "booked"


class BookingStatus(Enum):
    HELD = "held"
    CONFIRMED = "confirmed"
    EXPIRED = "expired"  # hold timed out or payment failed


@dataclass(frozen=True)
class Movie:
    title: str
    duration_min: int = 120


@dataclass(frozen=True)
class Seat:
    id: str


@dataclass
class Show:
    movie: Movie
    seats: list[Seat]
    id: str = field(default_factory=lambda: uuid.uuid4().hex[:6])
    status: dict[str, SeatStatus] = field(init=False)
    holds: dict[str, "Booking"] = field(default_factory=dict, repr=False)  # active HELD bookings of this show
    lock: threading.Lock = field(default_factory=threading.Lock, repr=False)

    def __post_init__(self):
        self.status = {s.id: SeatStatus.AVAILABLE for s in self.seats}

    def available_seats(self) -> list[str]:
        with self.lock:
            return [sid for sid, st in self.status.items() if st == SeatStatus.AVAILABLE]


@dataclass
class Booking:
    user: str
    show: Show
    seat_ids: list[str]
    expires_at: float
    status: BookingStatus = BookingStatus.HELD
    id: str = field(default_factory=lambda: uuid.uuid4().hex[:6])


class SeatUnavailable(Exception):
    pass


class BookingService:
    def __init__(self, hold_seconds: float = 300):
        self.hold_seconds = hold_seconds
        self.bookings: dict[str, Booking] = {}

    def hold(self, show: Show, seat_ids: list[str], user: str) -> Booking:
        """Atomically hold ALL requested seats, or none of them."""
        unknown = [s for s in seat_ids if s not in show.status]
        if unknown:
            raise ValueError(f"unknown seats {unknown}")
        with show.lock:  # one lock per show: bookings for different shows never block each other
            self._release_expired(show)
            taken = [s for s in seat_ids if show.status[s] != SeatStatus.AVAILABLE]
            if taken:  # check every seat BEFORE changing any (all-or-nothing)
                raise SeatUnavailable(f"{user}: seats {taken} unavailable")
            for s in seat_ids:
                show.status[s] = SeatStatus.HELD
            booking = Booking(user, show, list(seat_ids), time.monotonic() + self.hold_seconds)
            show.holds[booking.id] = booking
            self.bookings[booking.id] = booking
            return booking

    def confirm(self, booking_id: str, payment_ok: bool = True) -> Booking:
        """Called after the payment attempt. Turns a valid hold into a confirmed booking."""
        booking = self.bookings.get(booking_id)
        if booking is None:
            raise KeyError("unknown booking")
        show = booking.show
        with show.lock:
            if booking.status == BookingStatus.CONFIRMED:
                return booking  # idempotent: confirming twice is harmless
            if booking.status == BookingStatus.EXPIRED or time.monotonic() > booking.expires_at:
                self._expire(booking)
                raise SeatUnavailable("hold expired, please select seats again")
            if not payment_ok:
                self._expire(booking)
                raise RuntimeError("payment failed, seats released")
            for s in booking.seat_ids:
                show.status[s] = SeatStatus.BOOKED
            booking.status = BookingStatus.CONFIRMED
            show.holds.pop(booking.id, None)
            return booking

    # ---- helpers: caller must hold show.lock ----
    def _expire(self, booking: Booking) -> None:
        if booking.status == BookingStatus.HELD:
            for s in booking.seat_ids:
                booking.show.status[s] = SeatStatus.AVAILABLE
            booking.status = BookingStatus.EXPIRED
            booking.show.holds.pop(booking.id, None)

    def _release_expired(self, show: Show) -> None:
        """Lazy cleanup: free seats whose hold timed out. Only scans this show's active holds."""
        now = time.monotonic()
        for booking in list(show.holds.values()):
            if now > booking.expires_at:
                self._expire(booking)


if __name__ == "__main__":
    show = Show(Movie("Inception"), [Seat(f"A{i}") for i in range(1, 9)])
    svc = BookingService(hold_seconds=0.2)

    print("1) Two users want overlapping seats")
    a = svc.hold(show, ["A5", "A6"], "alice")
    try:
        svc.hold(show, ["A6", "A7"], "bob")
    except SeatUnavailable as e:
        print("   blocked:", e)
    print("   A7 still available (all-or-nothing):", "A7" in show.available_seats())
    print("   alice pays:", svc.confirm(a.id).status.name)

    print("2) A hold expires and the seat becomes bookable again")
    c = svc.hold(show, ["A1"], "carol")
    time.sleep(0.25)
    print("   dave holds A1:", svc.hold(show, ["A1"], "dave").status.name)
    try:
        svc.confirm(c.id)
    except SeatUnavailable as e:
        print("   carol tries to pay late:", e)

    print("3) Payment failure releases seats")
    e_ = svc.hold(show, ["A2"], "erin")
    try:
        svc.confirm(e_.id, payment_ok=False)
    except RuntimeError as err:
        print("  ", err, "| A2 available again:", "A2" in show.available_seats())

    print("4) 20 threads race for the same seat")
    show2 = Show(Movie("Dune"), [Seat("X1")])
    race_svc = BookingService(hold_seconds=60)  # long hold so it can't expire mid-race
    wins: list[str] = []

    def race(user: str):
        try:
            race_svc.hold(show2, ["X1"], user)
            wins.append(user)
        except SeatUnavailable:
            pass

    threads = [threading.Thread(target=race, args=(f"user{i}",)) for i in range(20)]
    for t in threads:
        t.start()
    for t in threads:
        t.join()
    print("   winners:", len(wins), "(expected 1)")
