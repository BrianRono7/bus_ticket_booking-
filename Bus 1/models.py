import threading
import time
from typing import Optional, Dict, List
from config import DEFAULT_SEATS_PER_BUS, DEFAULT_ROUTE


class Bus:
    """Represents a bus with seat management capabilities"""
    
    def __init__(self, bus_id: int, total_seats: int = DEFAULT_SEATS_PER_BUS, route: str = DEFAULT_ROUTE):
        self.bus_id = bus_id
        self.total_seats = total_seats
        self.route = route
        self.seats: Dict[int, Optional[str]] = {i: None for i in range(1, total_seats + 1)}
        self.locks: Dict[int, threading.Lock] = {i: threading.Lock() for i in range(1, total_seats + 1)}
        self.reservation_time: Dict[int, float] = {}
        self.booking_confirmed: Dict[int, bool] = {} 
        self.status = "active"  # active, merging, merged
        self.departure_dates: Dict[int, str] = {}

    def get_available_seats(self, date: Optional[str] = None) -> List[int]:
        """Get list of available seats, optionally filtered by date"""
        if date is None:
            return [seat for seat, client in self.seats.items() if client is None]
        return [
            seat for seat in range(1, self.total_seats + 1)
            if self.seats[seat] is None or self.departure_dates.get(seat) != date
        ]

    def get_load_factor(self) -> float:
        """Calculate the percentage of booked seats"""
        booked_seats = sum(1 for client in self.seats.values() if client is not None)
        return booked_seats / self.total_seats if self.total_seats > 0 else 0

    def book_seat(self, seat_number: int, client_id: str, date: str, confirmed: bool = True) -> bool:
        """Book a specific seat for a client on a given date"""
        if seat_number in self.seats:
            with self.locks[seat_number]:
                if self.seats[seat_number] is None or self.departure_dates.get(seat_number) != date:
                    self.seats[seat_number] = client_id
                    self.reservation_time[seat_number] = time.time()
                    self.departure_dates[seat_number] = date
                    self.booking_confirmed[seat_number] = confirmed
                    
                    # Notify booking system to update database
                    # You'll need to pass booking_system reference or use callback
                    return True
        return False

    def release_seat(self, seat_number: int) -> bool:
        """Release a booked seat"""
        if seat_number in self.seats:
            with self.locks[seat_number]:
                self.seats[seat_number] = None
                if seat_number in self.reservation_time:
                    del self.reservation_time[seat_number]
                if seat_number in self.departure_dates:
                    del self.departure_dates[seat_number]
                return True
        return False


class Booking:
    """Represents a booking record"""
    
    def __init__(self, booking_id: str, client_id: str, bus_id: int, 
                 seat: int, date: str, booking_time: str):
        self.booking_id = booking_id
        self.client_id = client_id
        self.bus_id = bus_id
        self.seat = seat
        self.date = date
        self.booking_time = booking_time

    def to_dict(self) -> dict:
        """Convert booking to dictionary"""
        return {
            "booking_id": self.booking_id,
            "client_id": self.client_id,
            "bus_id": self.bus_id,
            "seat": self.seat,
            "date": self.date,
            "booking_time": self.booking_time
        }

    @classmethod
    def from_dict(cls, data: dict) -> 'Booking':
        """Create booking from dictionary"""
        return cls(
            data["booking_id"],
            data["client_id"],
            data["bus_id"],
            data["seat"],
            data["date"],
            data["booking_time"]
        )