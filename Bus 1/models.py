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
        # Change seats structure to be date-aware: {date: {seat: client_id}}
        self.seats_by_date: Dict[str, Dict[int, Optional[str]]] = {}
        self.locks: Dict[str, threading.Lock] = {}  # Lock per date
        self.reservation_time: Dict[tuple, float] = {}  # (seat, date) -> timestamp
        self.booking_confirmed: Dict[tuple, bool] = {}  # (seat, date) -> confirmed
        self.status = "active"
    
    def _ensure_date_exists(self, date: str):
        """Ensure date entry exists in seats_by_date"""
        if date not in self.seats_by_date:
            self.seats_by_date[date] = {i: None for i in range(1, self.total_seats + 1)}
        if date not in self.locks:
            self.locks[date] = threading.Lock()
    
    def get_available_seats(self, date: str) -> List[int]:
        """Get list of available seats for a specific date"""
        self._ensure_date_exists(date)
        # Check if seats_by_date[date] is actually a dictionary
        date_seats = self.seats_by_date[date]
        
        if isinstance(date_seats, dict):
            return [seat for seat, client in date_seats.items() if client is None]
        else:
            # If it's not a dictionary, return all seats as available
            return list(range(1, self.total_seats + 1))

    
    def get_load_factor_for_date(self, date: str) -> float:
        """Calculate load factor for a specific date"""
        self._ensure_date_exists(date)
        date_seats = self.seats_by_date[date]

        # Handle corrupted data
        if not isinstance(date_seats, dict):
            self.seats_by_date[date] = {i: None for i in range(1, self.total_seats + 1)}
            return 0.0

        booked_seats = sum(1 for client in date_seats.values() if client is not None)
        return booked_seats / self.total_seats if self.total_seats > 0 else 0
    
    def get_overall_load_factor(self) -> float:
        """Calculate overall load factor across all dates"""
        if not self.seats_by_date:
            return 0.0

        total_capacity = len(self.seats_by_date) * self.total_seats
        total_booked = 0

        for date_seats in self.seats_by_date.values():
            # Handle corrupted data
            if isinstance(date_seats, dict):
                total_booked += sum(1 for client in date_seats.values() if client is not None)

        return total_booked / total_capacity if total_capacity > 0 else 0

    def get_load_factor(self) -> float:
        """Alias for get_overall_load_factor() for backward compatibility"""
        return self.get_overall_load_factor()
    
    def book_seat(self, seat_number: int, client_id: str, date: str, confirmed: bool = True) -> bool:
        """Book a specific seat for a client on a given date"""
        self._ensure_date_exists(date)
        
        if 1 <= seat_number <= self.total_seats:
            with self.locks[date]:
                if self.seats_by_date[date][seat_number] is None:
                    self.seats_by_date[date][seat_number] = client_id
                    self.reservation_time[(seat_number, date)] = time.time()
                    self.booking_confirmed[(seat_number, date)] = confirmed
                    return True
        return False
    
    def release_seat(self, seat_number: int, date: str) -> bool:
        """Release a booked seat for a specific date"""
        if date in self.seats_by_date and 1 <= seat_number <= self.total_seats:
            with self.locks[date]:
                self.seats_by_date[date][seat_number] = None
                key = (seat_number, date)
                if key in self.reservation_time:
                    del self.reservation_time[key]
                if key in self.booking_confirmed:
                    del self.booking_confirmed[key]
                return True
        return False
    
    def is_seat_available(self, seat_number: int, date: str) -> bool:
        """Check if a seat is available for a specific date"""
        self._ensure_date_exists(date)
        return self.seats_by_date[date][seat_number] is None


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