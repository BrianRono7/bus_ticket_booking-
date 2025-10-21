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
    LOG_FILE, LOG_BATCH_SIZE, LOG_FLUSH_INTERVAL, ENABLE_DATABASE, CANCELLATION_PENALTY, ALLOW_SAME_DAY_CANCELLATIONS
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
        self.unique_visitors = set()  # Track unique client IDs
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
        else:
            self.db = None
        
        # Admin operations
        self.admin = AdminOperations(self)
        
        # Initialize buses
        if ENABLE_DATABASE:
            db_buses = self.db.get_all_buses()
            if db_buses:
                for bus in db_buses:
                    self.buses[bus['bus_id']] = Bus(
                        bus['bus_id'], 
                        total_seats=bus['total_seats'], 
                        route=bus['route']
                    )
                self.logger.log(f"Loaded {len(db_buses)} buses from database")
            else:
                for i in range(initial_buses):
                    self.buses[i] = Bus(i, total_seats=DEFAULT_SEATS_PER_BUS, route=DEFAULT_ROUTE)
                    self.logger.log(f"Initialized bus {i}")

                    if ENABLE_DATABASE and self.db.get_bus_by_id(i) is None:
                        self.db.add_bus(i, DEFAULT_SEATS_PER_BUS, DEFAULT_ROUTE, 'active')
        
        if ENABLE_DATABASE:
            self._load_from_database()

    def increment_visitor(self, client_id: str = None) -> int:
        """Thread-safe visitor counter increment for unique visitors"""
        with self.visitor_lock:
            if client_id:
                self.unique_visitors.add(client_id)
                self.visitor_count = len(self.unique_visitors)
            else:
                # Fallback for when client_id is not provided
                self.visitor_count += 1
            return self.visitor_count

    def get_total_visitors(self) -> int:
        """Get total unique visitor count"""
        with self.visitor_lock:
            return self.visitor_count
    # ----------------------------------------------------------------------------#
    def get_load_factor_by_date(self, date: str) -> float:
        """Calculate system load factor for a specific date"""
        with self.system_lock:
            total_capacity = 0
            total_booked = 0
            
            for bus in self.buses.values():
                if bus.status == "active":
                    total_capacity += bus.total_seats
                    # Get booked seats for this specific date
                    if date in bus.seats_by_date:
                        booked_on_date = sum(1 for client in bus.seats_by_date[date].values() 
                                           if client is not None)
                        total_booked += booked_on_date
            
            return total_booked / total_capacity if total_capacity > 0 else 0
    
    def get_daily_load_factors(self, days: int = 7) -> Dict[str, float]:
        """Get load factors for the next N days"""
        from datetime import datetime, timedelta
        
        daily_loads = {}
        today = datetime.now().date()
        
        for i in range(days):
            date_str = (today + timedelta(days=i)).strftime('%Y-%m-%d')
            daily_loads[date_str] = self.get_load_factor_by_date(date_str)
        
        return daily_loads
    
    def get_bus_load_factor_by_date(self, bus_id: int, date: str) -> float:
        """Get load factor for a specific bus on a specific date"""
        with self.system_lock:
            if bus_id in self.buses:
                bus = self.buses[bus_id]
                return bus.get_load_factor_for_date(date)
        return 0.0
    
    def get_overall_load_factor(self) -> float:
        """Calculate overall system load factor across all buses and all dates (memory + DB safe)"""
        with self.system_lock:
            total_capacity = 0
            total_booked = 0

            # --- Step 1: Prefer in-memory data for active buses ---
            for bus in self.buses.values():
                if bus.status != "active":
                    continue

                total_capacity += bus.total_seats  # Each active bus adds once (not per date)

                # Count booked seats across all dates (memory)
                for date, seats in bus.seats_by_date.items():
                    if not isinstance(seats, dict):
                        continue
                    total_booked += sum(1 for client in seats.values() if client is not None)

            # --- Step 2: Cross-check with database if enabled ---
            if self.db:
                try:
                    db_bookings = self.db.get_all_bookings()
                    if db_bookings:
                        # Avoid double counting: only add DB-only records
                        in_memory_bookings = {
                            (b["bus_id"], b["seat"], b["date"]) 
                            for b in self.bookings_db.values()
                        }
                        db_only = [
                            b for b in db_bookings 
                            if (b["bus_id"], b["seat"], b["date"]) not in in_memory_bookings
                        ]
                        total_booked += len(db_only)
                except Exception as e:
                    self.logger.log(f"Warning: DB check in get_overall_load_factor failed: {e}")

            # --- Step 3: Return computed factor ---
            return total_booked / total_capacity if total_capacity > 0 else 0.0

    def book_seat_for_client(self, client_id: str, travel_date: str,
                         preferred_bus: int, preferred_seat: int) -> dict:
        """Atomically book a seat for a client on specific date"""
        self.increment_visitor()
        self.release_expired_reservations()
        self.add_buses_if_needed()

        if preferred_bus is None or preferred_seat is None:
            raise ValueError("Both preferred_bus and preferred_seat are required.")

        # Verify bus exists
        if preferred_bus not in self.buses:
            return {"status": "failure", "message": "Selected bus does not exist."}

        bus = self.buses[preferred_bus]
        if bus.status != "active":
            return {"status": "failure", "message": "Selected bus is not available."}

        try:
            # Perform the booking atomically
            with self.db.atomic_transaction() as conn:
                cursor = conn.cursor()

                # Check seat availability for this specific date
                cursor.execute('''
                    SELECT client_id 
                    FROM bus_seats 
                    WHERE bus_id = ? AND seat_number = ? AND departure_date = ?
                ''', (preferred_bus, preferred_seat, travel_date))
                existing = cursor.fetchone()

                if existing is not None:
                    return {
                        "status": "failure",
                        "message": f"Seat {preferred_seat} on bus {preferred_bus} for {travel_date} is already booked."
                    }

                # Book the seat
                cursor.execute('''
                    INSERT INTO bus_seats (bus_id, seat_number, client_id, departure_date)
                    VALUES (?, ?, ?, ?)
                ''', (preferred_bus, preferred_seat, client_id, travel_date))

                # Save booking record
                booking_id = f"BK-{preferred_bus}-{preferred_seat}-{travel_date}"
                booking_data = {
                    "booking_id": booking_id,
                    "client_id": client_id,
                    "bus_id": preferred_bus,
                    "seat": preferred_seat,
                    "date": travel_date,
                    "booking_time": self.get_current_time()
                }

                self.db.save_booking(booking_data, conn=conn)
            
            # Update in-memory bus object
            with self.system_lock:
                bus.book_seat(preferred_seat, client_id, travel_date)
                self.bookings_db[booking_id] = booking_data

            self.logger.log(f"Client {client_id} booked seat {preferred_seat} on bus {preferred_bus} for {travel_date}")
            return {
                "status": "success", 
                "booking_id": booking_id,
                "client_id": client_id,
                "bus_id": preferred_bus,
                "seat_number": preferred_seat,
                "date": travel_date,
                "route": "Nakuru-Nairobi",
                "message": "Seat booked successfully."
            }

        except Exception as e:
            self.logger.log(f"Booking failed for client {client_id}: {e}")
            return {"status": "failure", "message": f"Booking failed: {str(e)}"}

    def release_expired_reservations(self) -> int:
        """Release seats held beyond timeout period - date-aware"""
        current_time = time.time()
        released_seats = 0

        with self.system_lock:
            for bus in self.buses.values():
                if bus.status != "active":
                    continue

                expired_bookings = []
                for (seat, date), reservation_time in bus.reservation_time.items():
                    if current_time - reservation_time > self.seat_lock_timeout:
                        expired_bookings.append((seat, date))

                for seat, date in expired_bookings:
                    if bus.release_seat(seat, date):
                        released_seats += 1
                        # Also remove from database
                        if self.db:
                            self.db.delete_bus_seat(bus.bus_id, seat, date)
                        self.logger.log(
                            f"Released expired reservation: Bus {bus.bus_id}, Seat {seat}, Date {date}"
                        )

        return released_seats
    

    # def get_overall_load_factor(self) -> float:
    #     """Calculate overall system load factor across ALL dates"""
    #     total_capacity = 0
    #     unique_bookings = set()

    #     with self.system_lock:
    #         for bus in self.buses.values():
    #             if bus.status == "active":
    #                 total_capacity += bus.total_seats
    #                 # Count unique (seat, date) combinations
    #                 for seat, date in bus.departure_dates.items():
    #                     if bus.seats[seat] is not None:
    #                         unique_bookings.add((bus.bus_id, seat, date))

    #     # For multi-date systems, you need to decide:
    #     # Option 1: Load factor per time slot (divide by number of dates)
    #     # Option 2: Average across all future dates
    #     # Currently showing instantaneous load
    #     return len(unique_bookings) / total_capacity if total_capacity > 0 else 0

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

    # def release_expired_reservations(self) -> int:
    #     """Release seats held beyond timeout period"""
    #     current_time = time.time()
    #     released_seats = 0

    #     with self.system_lock:
    #         for bus in self.buses.values():
    #             if bus.status != "active":
    #                 continue

    #             expired_seats = []
    #             for seat, reservation_time in bus.reservation_time.items():
    #                 # CRITICAL FIX: Only release if actually expired
    #                 if current_time - reservation_time > self.seat_lock_timeout:
    #                     # Also check if seat is still "reserved" not "confirmed"
    #                     # For confirmed bookings, we should NOT auto-release
    #                     if seat in bus.departure_dates:  # This is a confirmed booking
    #                         continue  # Don't release confirmed bookings
    #                     expired_seats.append(seat)

    #             for seat in expired_seats:
    #                 if bus.release_seat(seat):
    #                     released_seats += 1
    #                     self.logger.log(
    #                         f"Released expired reservation: Bus {bus.bus_id}, Seat {seat}"
    #                     )

    #     return released_seats
    
    def get_current_time(self) -> str:
        """Return precise timestamp with microseconds"""
        now = datetime.utcnow().strftime("%Y-%m-%d %H:%M:%S.%f")
        time.sleep(0.001)  # small delay to avoid same-timestamp collision
        return now

    # def book_seat_for_client(self, client_id: str, travel_date: str,
    #                      preferred_bus: int, preferred_seat: int) -> dict:
    #     """Atomically book a seat for a client (bus and seat required)"""
    #     self.increment_visitor()
    #     self.release_expired_reservations()
    #     self.add_buses_if_needed()

    #     if preferred_bus is None or preferred_seat is None:
    #         raise ValueError("Both preferred_bus and preferred_seat are required.")

    #     # Verify bus exists
    #     if preferred_bus not in self.buses:
    #         return {"status": "failure", "message": "Selected bus does not exist."}

    #     bus = self.buses[preferred_bus]
    #     if bus.status != "active":
    #         return {"status": "failure", "message": "Selected bus is not available."}

    #     try:
    #         # Perform the booking atomically
    #         with self.db.atomic_transaction() as conn:
    #             cursor = conn.cursor()

    #             # Check seat availability or lock
    #             cursor.execute('''
    #                 SELECT client_id 
    #                 FROM bus_seats 
    #                 WHERE bus_id = ? AND seat_number = ? AND departure_date = ?
    #             ''', (preferred_bus, preferred_seat, travel_date))
    #             existing = cursor.fetchone()

    #             if existing is not None:
    #                 return {
    #                     "status": "failure",
    #                     "message": f"Seat {preferred_seat} on bus {preferred_bus} is already booked or locked."
    #                 }

    #             # Lock the seat before booking (prevent race conditions)
    #             cursor.execute('''
    #                 INSERT INTO bus_seats (bus_id, seat_number, client_id, departure_date)
    #                 VALUES (?, ?, ?, ?)
    #             ''', (preferred_bus, preferred_seat, client_id, travel_date))

    #             # Save booking record
    #             booking_id = f"BK-{preferred_bus}-{preferred_seat}-{travel_date}"
    #             booking_data = {
    #                 "booking_id": booking_id,
    #                 "client_id": client_id,
    #                 "bus_id": preferred_bus,
    #                 "seat": preferred_seat,
    #                 "date": travel_date,
    #                 "booking_time": self.get_current_time()
    #             }

    #             self.db.save_booking(booking_data, conn=conn)
    #         with self.system_lock:
    #             bus.seats[preferred_seat] = client_id
    #             bus.departure_dates[preferred_seat] = travel_date
    #             # Store in bookings_db for consistency
    #             self.bookings_db[booking_id] = booking_data

    #         self.logger.log(f"Client {client_id} successfully booked seat {preferred_seat} on bus {preferred_bus} ({travel_date})")
    #         return {"status": "success", 
    #         "booking_id": booking_id,
    #         "client_id": client_id,
    #         "bus_id": preferred_bus,
    #         "seat_number": preferred_seat,
    #         "date": travel_date,
    #         "route": "Nakuru-Nairobi",
    #         "message": "Seat booked successfully."}

    #     except Exception as e:
    #         self.logger.log(f"Booking failed for client {client_id}: {e}")
    #         return {"status": "failure", "message": f"Booking failed: {str(e)}"}


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

    def cancel_booking(self, booking_id: str, client_id: str) -> dict:
        """Cancel a booking with penalty support"""
        with self.system_lock:
            
            booking = self.db.get_booking_by_id(booking_id) if self.db else self.bookings_db.get(booking_id)
            if booking["client_id"] != client_id:
                return {"success": False, "message": "Unauthorized cancellation attempt"}

            bus_id = booking["bus_id"]
            seat = booking["seat"]
            date = booking["date"]

            # Check if same-day cancellation
            try:
                booking_date = datetime.strptime(date, '%Y-%m-%d').date()
                today = datetime.now().date()

                if booking_date == today and not ALLOW_SAME_DAY_CANCELLATIONS:
                    return {"success": False, "message": "Same-day cancellations not allowed"}
            except ValueError:
                pass  # If date parsing fails, allow cancellation

            # Calculate penalty
            penalty_amount = 0.0
            if CANCELLATION_PENALTY > 0:
                # Assuming a base fare (this could be stored in booking)
                base_fare = 1000.0  # Default fare in your currency
                penalty_amount = base_fare * CANCELLATION_PENALTY

            try:
                with self.db.atomic_transaction() as conn:
                    cursor = conn.cursor()
                    
                    # Delete from both tables atomically
                    cursor.execute('DELETE FROM bookings WHERE booking_id = ?', (booking_id,))
                    cursor.execute('''
                        DELETE FROM bus_seats 
                        WHERE bus_id = ? AND seat_number = ? AND departure_date = ?
                    ''', (bus_id, seat, date))
                
                # Update the in-memory Bus object
                if bus_id in self.buses:
                    bus = self.buses[bus_id]
                    bus.release_seat(seat, date)

                # Remove from in-memory storage
                if booking_id in self.bookings_db:
                    del self.bookings_db[booking_id]

            except Exception as e:
                self.logger.log(f"Cancellation failed: {e}")
                return {"success": False, "message": str(e)}

            self.logger.log(
                f"Cancelled booking {booking_id}: Bus {bus_id}, Seat {seat}, Date {date}, "
                f"Penalty: {penalty_amount:.2f}"
            )

            return {
                "success": True,
                "message": "Booking cancelled successfully",
                "penalty": penalty_amount,
                "refund_amount": base_fare - penalty_amount if CANCELLATION_PENALTY > 0 else 0.0
            }

    def get_booking(self, booking_id: str) -> Optional[dict]:
        """Get booking details"""
        with self.system_lock:
            return self.bookings_db.get(booking_id)

    def get_all_bookings(self) -> List[dict]:
        """Get all bookings in the system"""
        db_bookings = self.db.get_all_bookings()
        return db_bookings
    
    def get_all_buses(self) -> List[dict]:
        """Get all buses in the system"""
        db_buses = self.db.get_all_buses()
        return db_buses

    def _load_from_database(self):
        """Load existing data from database on startup"""
        if not self.db:
            self.logger.log("Database not enabled, skipping load")
            return

        try:
            # Load bookings
            db_bookings = self.db.get_all_bookings()
            self.logger.log(f"Loading {len(db_bookings)} bookings from database...")

            if not db_bookings:
                self.logger.log("No bookings found in database")
                return

            # Track unique visitors (client_ids)
            unique_visitors = set()

            loaded_count = 0
            for booking in db_bookings:
                booking_id = booking['booking_id']
                bus_id = booking['bus_id']
                seat = booking['seat']
                date = booking['date']
                client_id = booking['client_id']

                # Add to unique visitors set
                unique_visitors.add(client_id)

                # Store in bookings_db
                self.bookings_db[booking_id] = {
                    "client_id": client_id,
                    "bus_id": bus_id,
                    "seat": seat,
                    "date": date,
                    "booking_time": booking['booking_time']
                }
                
                # Update in-memory Bus objects
                if bus_id in self.buses:
                    bus = self.buses[bus_id]
                    bus.book_seat(seat, client_id, date)
                    bus.departure_dates[seat] = date
                    loaded_count += 1
                    self.logger.log(f"Loaded booking {booking_id}: Bus {bus_id}, Seat {seat}, Date {date}, Client {client_id}")
                else:
                    self.logger.log(f"WARNING: Booking {booking_id} references non-existent bus {bus_id}")
            
            self.logger.log(f"Successfully loaded {loaded_count} bookings into bus objects")
            
            # Update booking counter to avoid ID conflicts
            if self.bookings_db:
                # Extract numeric IDs from booking_id format "BK-{bus_id}-{seat}-{date}"
                # or "BK{counter:06d}" depending on your format
                try:
                    max_counter = 0
                    for bid in self.bookings_db.keys():
                        if bid.startswith('BK-'):
                            # Format: BK-{bus_id}-{seat}-{date}
                            # We need a different approach for this format
                            continue
                        elif bid.startswith('BK') and len(bid) > 2:
                            # Format: BK{counter:06d}
                            try:
                                counter = int(bid[2:])
                                max_counter = max(max_counter, counter)
                            except ValueError:
                                continue
                    
                    if max_counter > 0:
                        self.booking_counter = max_counter
                        self.logger.log(f"Set booking counter to {max_counter}")
                except Exception as e:
                    self.logger.log(f"Could not update booking counter: {e}")
            
            # Update visitor count with unique visitors from database
            with self.visitor_lock:
                self.visitor_count = len(unique_visitors)
            self.logger.log(f"Loaded {len(unique_visitors)} unique visitors from database")

            # Log final bus states
            for bus_id, bus in self.buses.items():
                occupied_seats = sum(1 for seat in bus.seats_by_date.values() if seat is not None)
                self.logger.log(f"Bus {bus_id}: {occupied_seats}/{bus.total_seats} seats occupied")

        except Exception as e:
            self.logger.log(f"ERROR loading from database: {e}")
            import traceback
            self.logger.log(traceback.format_exc())

    def get_bus_status(self, bus_id: int, date: Optional[str] = None) -> dict:
        """Get status of a specific bus (memory + DB safe)

        Args:
            bus_id: ID of the bus
            date: Optional specific date to check. If None, returns today's info
        """
        with self.system_lock:
            # --- 1️⃣ Prefer in-memory bus first ---
            # bus = self.buses.get(bus_id)
            # if bus:
            #     # Handle merging/transition state
            #     if bus.status == "merging":
            #         return {"status": "merging", "alert": "Bus alteration in process"}

            #     if date is None:
            #         date = datetime.now().strftime('%Y-%m-%d')

            #     # Try to retrieve in-memory seat info
            #     try:
            #         available = len(bus.get_available_seats(date))
            #         load_factor = bus.get_load_factor_for_date(date)
            #         overall = bus.get_overall_load_factor()
            #     except Exception:
            #         # fallback if seat data missing
            #         available = bus.total_seats
            #         load_factor = 0.0
            #         overall = 0.0

            #     return {
            #         "status": bus.status,
            #         "bus_id": bus_id,
            #         "route": bus.route,
            #         "total_seats": bus.total_seats,
            #         "available_seats": available,
            #         "load_factor": load_factor,
            #         "overall_load_factor": overall,
            #         "date": date
            #     }

            # --- 2️⃣ If not found in memory, fall back to DB ---
            if self.db:
                try:
                    db_bus = self.db.get_bus_by_id(bus_id)
                    if not db_bus:
                        return {"status": "not_found"}

                    if date is None:
                        date = datetime.now().strftime('%Y-%m-%d')

                    # Pull seat info from DB for that date
                    seats = self.db.get_bus_seats(bus_id, date)
                    if not seats:
                        available = db_bus["total_seats"]
                        booked = 0
                    else:
                        booked = sum(1 for c in seats.values() if c)
                        available = db_bus["total_seats"] - booked

                    load_factor = booked / db_bus["total_seats"] if db_bus["total_seats"] else 0.0

                    return {
                        "status": db_bus.get("status", "active"),
                        "bus_id": bus_id,
                        "route": db_bus.get("route", "unknown"),
                        "total_seats": db_bus["total_seats"],
                        "available_seats": available,
                        "load_factor": round(load_factor, 3),
                        "overall_load_factor": round(load_factor, 3),  # fallback approximation
                        "date": date
                    }

                except Exception as e:
                    self.logger.log(f"DB error in get_bus_status({bus_id}): {e}")
                    return {"status": "error", "error": str(e)}

            # --- 3️⃣ Not found anywhere ---
            return {"status": "not_found"}


    def get_all_buses_status(self, date: Optional[str] = None) -> List[dict]:
        """Get status of all buses"""
        
        if date is None:
            date = datetime.now().strftime('%Y-%m-%d')
        
        with self.system_lock:
            return [
                self.get_bus_status(bus_id, date)
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