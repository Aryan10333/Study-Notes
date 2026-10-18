"""Vending Machine - LLD. Pattern: State."""
from __future__ import annotations

from abc import ABC
from dataclasses import dataclass


@dataclass(frozen=True)
class Product:
    name: str
    price: int


@dataclass
class Slot:
    product: Product
    quantity: int


class State(ABC):
    """Default: reject everything. Subclasses override only valid actions."""

    def insert_money(self, vm: VendingMachine, amount: int) -> None:
        print(f"  [{self.name}] cannot insert money now")

    def select(self, vm: VendingMachine, code: str) -> None:
        print(f"  [{self.name}] cannot select now")

    def cancel(self, vm: VendingMachine) -> None:
        print(f"  [{self.name}] nothing to cancel")

    @property
    def name(self) -> str:
        return type(self).__name__


class IdleState(State):
    def insert_money(self, vm, amount):
        vm.balance += amount
        print(f"  inserted {amount}, balance {vm.balance}")
        vm.set_state(HasMoneyState())


class HasMoneyState(State):
    def insert_money(self, vm, amount):
        vm.balance += amount
        print(f"  inserted {amount}, balance {vm.balance}")

    def select(self, vm, code):
        slot = vm.inventory.get(code)
        if slot is None or slot.quantity == 0:
            print(f"  {code} unavailable")
            return
        if vm.balance < slot.product.price:
            print(f"  need {slot.product.price - vm.balance} more")
            return
        vm.set_state(DispensingState())
        vm.state.dispense(vm, slot)

    def cancel(self, vm):
        print(f"  refunded {vm.balance}")
        vm.balance = 0
        vm.set_state(IdleState())


class DispensingState(State):
    def dispense(self, vm: VendingMachine, slot: Slot) -> None:
        slot.quantity -= 1
        change = vm.balance - slot.product.price
        vm.balance = 0
        print(f"  dispensed {slot.product.name}, change {change}")
        vm.set_state(IdleState())


class VendingMachine:
    def __init__(self, inventory: dict[str, Slot]):
        self.inventory = inventory
        self.balance = 0
        self.state: State = IdleState()

    def set_state(self, state: State) -> None:
        self.state = state

    # public API delegates to the current state
    def insert_money(self, amount: int) -> None:
        self.state.insert_money(self, amount)

    def select(self, code: str) -> None:
        self.state.select(self, code)

    def cancel(self) -> None:
        self.state.cancel(self)


if __name__ == "__main__":
    vm = VendingMachine({
        "A1": Slot(Product("Coke", 40), 2),
        "B1": Slot(Product("Chips", 20), 0),
    })
    print("select before paying:"); vm.select("A1")
    print("pay 20, select Coke:"); vm.insert_money(20); vm.select("A1")
    print("pay 30 more:"); vm.insert_money(30); vm.select("A1")
    print("out of stock + cancel:"); vm.insert_money(20); vm.select("B1"); vm.cancel()
