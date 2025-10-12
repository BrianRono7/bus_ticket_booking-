import threading
import time
from threading import RLock
from datetime import datetime
from typing import Optional, Dict, List

from models import Bus, Booking
from logger import AsyncLogger
from admin import AdminOperations
from config import (
    DEFAULT_SEATS_PER_BUS, DEFAULT_ROUTE, INITIAL_BUS_COUNT, MAX_BUS_COUNT,
    LOAD_THRESHOLD_HIGH, LOAD_THRESHOLD_LOW, SEAT_RESERVATION_TIMEOUT,
    LOG_FILE, LOG_BATCH_SIZE, LOG_FLUSH_INTERVAL, ENABLE_DATABASE
)
from database import DatabaseManager


class BusBookingSystem:
    """Main bus booking system with thread-safe operations"""
    
    def __init__(self, initial_buses: int = INITIAL_BUS_COUNT,
                 max_buses: int = MAX_BUS_COUNT,
                 load_threshold_high: float = LOAD_THRESHOLD_HIGH,
                 load_threshold_low: float = LOAD_THRESHOLD_LOW,
                 seat_lock_timeout: float = SEAT_RESERVATION_TIMEOUT):
        self.buses: Dict[int, Bus] = {}
        self.initial_buses = initial_buses
        self.max_buses = max_buses
        self.load_threshold_high = load_threshold_high
        self.load_threshold_low = load_threshold_low
        self.seat_lock_timeout = seat_lock_timeout
        
        # Thread safety
        self.visitor_count = 0
        self.visitor_lock = threading.Lock()
        self.system_lock = RLock()
        
        # Booking management
        self.bookings_db: Dict[str, dict] = {}
        self.booking_counter = 0
        
        # Logger
        self.logger = AsyncLogger(
            log_file=LOG_FILE,
            batch_size=LOG_BATCH_SIZE,
            flush_interval=LOG_FLUSH_INTERVAL
        )
        if ENABLE_DATABASE:
            self.db = DatabaseManager()
            self._load_from_database()
        else:
            self.db = None
        
        # Admin operations
        self.admin = AdminOperations(self)
        
        # Initialize buses
        for i in range(initial_buses):
            self.buses[i] = Bus(i, total_seats=DEFAULT_SEATS_PER_BUS, route=DEFAULT_ROUTE)
            self.logger.log(f"Initialized bus {i}")

    def increment_visitor(self) -> int:
        """Thread-safe visitor counter increment"""
        with self.visitor_lock:
            self.visitor_count += 1
            return self.visitor_count

    def get_total_visitors(self) -> int:
        """Get total visitor count"""
        with self.visitor_lock:
            return self.visitor_count

    def get_overall_load_factor(self) -> float:
        """Calculate overall system load factor across ALL dates"""
        total_capacity = 0
        unique_bookings = set()

        with self.system_lock:
            for bus in self.buses.values():
                if bus.status == "active":
                    total_capacity += bus.total_seats
                    # Count unique (seat, date) combinations
                    for seat, date in bus.departure_dates.items():
                        if bus.seats[seat] is not None:
                            unique_bookings.add((bus.bus_id, seat, date))

        # For multi-date systems, you need to decide:
        # Option 1: Load factor per time slot (divide by number of dates)
        # Option 2: Average across all future dates
        # Currently showing instantaneous load
        return len(unique_bookings) / total_capacity if total_capacity > 0 else 0

    def add_buses_if_needed(self) -> int:
        """Add buses if load threshold is exceeded"""
        with self.system_lock:
            current_load = self.get_overall_load_factor()
            current_bus_count = len([b for b in self.buses.values() if b.status == "active"])

            if current_load >= self.load_threshold_high and current_bus_count < self.max_buses:
                buses_to_add = min(2, self.max_buses - current_bus_count)
                for i in range(buses_to_add):
                    new_bus_id = max(self.buses.keys()) + 1 if self.buses else current_bus_count
                    self.buses[new_bus_id] = Bus(new_bus_id, route="Nakuru-Nairobi")
                    self.logger.log(f"Added new bus {new_bus_id} (load: {current_load:.2%})")
                return buses_to_add
        return 0

    def release_expired_reservations(self) -> int:
        """Release seats held beyond timeout period"""
        current_time = time.time()
        released_seats = 0

        with self.system_lock:
            for bus in self.buses.values():
                if bus.status != "active":
                    continue

                expired_seats = []
                for seat, reservation_time in bus.reservation_time.items():
                    # CRITICAL FIX: Only release if actually expired
                    if current_time - reservation_time > self.seat_lock_timeout:
                        # Also check if seat is still "reserved" not "confirmed"
                        # For confirmed bookings, we should NOT auto-release
                        if seat in bus.departure_dates:  # This is a confirmed booking
                            continue  # Don't release confirmed bookings
                        expired_seats.append(seat)

                for seat in expired_seats:
                    if bus.release_seat(seat):
                        released_seats += 1
                        self.logger.log(
                            f"Released expired reservation: Bus {bus.bus_id}, Seat {seat}"
                        )

        return released_seats

    def book_seat_for_client(self, client_id: str, travel_date: str,
                            preferred_bus: Optional[int] = None,
                            preferred_seat: Optional[int] = None) -> dict:
        """Book a seat for a client"""
        self.increment_visitor()
        self.release_expired_reservations()
        self.add_buses_if_needed()

        with self.system_lock:
            # Try preferred bus/seat first
            if preferred_bus is not None and preferred_bus in self.buses:
                result = self._try_book_on_bus(
                    self.buses[preferred_bus], 
                    client_id, 
                    travel_date, 
                    preferred_seat
                )
                if result:
                    return result

            # Try any available bus
            for bus_id, bus in self.buses.items():
                if bus.status != "active":
                    continue

                result = self._try_book_on_bus(bus, client_id, travel_date)
                if result:
                    return result

        self.logger.log(f"Client {client_id} could not find available seat for {travel_date}")
        return {"status": "failure", "message": "No seats available for selected date"}

    def _try_book_on_bus(self, bus: Bus, client_id: str, travel_date: str,
                        preferred_seat: Optional[int] = None) -> Optional[dict]:
        """Try to book a seat on a specific bus"""
        if bus.status != "active":
            return None

        # Try preferred seat
        if preferred_seat is not None and preferred_seat in bus.seats:
            if bus.book_seat(preferred_seat, client_id, travel_date):
                return self._create_booking_response(
                    client_id, bus.bus_id, preferred_seat, travel_date
                )

        # Try any available seat
        for seat in bus.get_available_seats(travel_date):
            if bus.book_seat(seat, client_id, travel_date):
                return self._create_booking_response(
                    client_id, bus.bus_id, seat, travel_date
                )

        return None

    def _create_booking_response(self, client_id: str, bus_id: int,
                                seat: int, date: str) -> dict:
        """Create a booking and return response"""
        booking_id = self._create_booking(client_id, bus_id, seat, date)
        self.logger.log(
            f"Booking {booking_id}: Client {client_id} booked seat {seat} "
            f"on bus {bus_id} for {date}"
        )
        return {
            "status": "success",
            "booking_id": booking_id,
            "bus_id": bus_id,
            "seat_number": seat,
            "date": date,
            "route": "Nakuru-Nairobi"
        }

    def _create_booking(self, client_id: str, bus_id: int, seat: int, date: str) -> str:
        """Create a booking record"""
        with self.system_lock:
            self.booking_counter += 1
            booking_id = f"BK{self.booking_counter:06d}"
            booking_data = {
                "booking_id": booking_id,
                "client_id": client_id,
                "bus_id": bus_id,
                "seat": seat,
                "date": date,
                "booking_time": datetime.now().isoformat()
            }
            
            # Store in memory
            self.bookings_db[booking_id] = booking_data
            
            # Store in database if enabled
            if self.db:
                self.db.save_booking(booking_data)
                # Also save bus seat assignment
                self.db.save_bus_seat(bus_id, seat, client_id, date)
            
            return booking_id

    def cancel_booking(self, booking_id: str, client_id: str) -> bool:
        """Cancel a booking"""
        with self.system_lock:
            if booking_id not in self.bookings_db:
                return False

            booking = self.bookings_db[booking_id]
            if booking["client_id"] != client_id:
                return False

            bus_id = booking["bus_id"]
            seat = booking["seat"]
            date = booking["date"]

            if self.db:
                self.db.delete_booking(booking_id)
                self.db.delete_bus_seat(bus_id, seat, date)
            return True

    def get_booking(self, booking_id: str) -> Optional[dict]:
        """Get booking details"""
        with self.system_lock:
            return self.bookings_db.get(booking_id)

    def get_client_bookings(self, client_id: str) -> List[dict]:
        """Get all bookings for a client"""
        return self.db.get_client_bookings(client_id)
    def _load_from_database(self):
        """Load existing data from database on startup"""
        if not self.db:
            return
        
        # Load bookings
        db_bookings = self.db.get_all_bookings()
        for booking in db_bookings:
            self.bookings_db[booking['booking_id']] = {
                "client_id": booking['client_id'],
                "bus_id": booking['bus_id'],
                "seat": booking['seat'],
                "date": booking['date'],
                "booking_time": booking['booking_time']
            }
        
        # Update booking counter
        if self.bookings_db:
            max_id = max(int(bid[2:]) for bid in self.bookings_db.keys() if bid.startswith('BK'))
            self.booking_counter = max_id

    def get_bus_status(self, bus_id: int) -> dict:
        """Get status of a specific bus"""
        with self.system_lock:
            if bus_id in self.buses:
                bus = self.buses[bus_id]
                if bus.status == "merging":
                    return {"status": "merging", "alert": "Bus alteration in process"}
                return {
                    "status": bus.status,
                    "bus_id": bus_id,
                    "route": bus.route,
                    "total_seats": bus.total_seats,
                    "available_seats": len(bus.get_available_seats()),
                    "load_factor": bus.get_load_factor()
                }
        return {"status": "not_found"}

    def get_all_buses_status(self) -> List[dict]:
        """Get status of all buses"""
        with self.system_lock:
            return [
                self.get_bus_status(bus_id)
                for bus_id in self.buses.keys()
            ]

    def get_available_dates(self, bus_id: int) -> List[str]:
        """Get dates with available seats on a bus"""
        with self.system_lock:
            if bus_id not in self.buses:
                return []
            
            bus = self.buses[bus_id]
            return list(set(bus.departure_dates.values()))

    def shutdown(self):
        """Cleanup and shutdown system"""
        self.logger.log("System shutdown initiated")
        self.logger.shutdown()