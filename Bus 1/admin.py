import hashlib
from typing import Dict, Optional
from config import DEFAULT_ADMIN_USERNAME, DEFAULT_ADMIN_PASSWORD, DEFAULT_ROUTE, DEFAULT_SEATS_PER_BUS
from models import Bus 


class AdminAuth:
    """Handles admin authentication"""
    
    def __init__(self):
        self.credentials: Dict[str, str] = {
            DEFAULT_ADMIN_USERNAME: hashlib.sha256(DEFAULT_ADMIN_PASSWORD.encode()).hexdigest()
        }

    def login(self, username: str, password: str) -> bool:
        """Authenticate admin user"""
        password_hash = hashlib.sha256(password.encode()).hexdigest()
        return username in self.credentials and self.credentials[username] == password_hash

    def add_admin(self, username: str, password: str) -> bool:
        """Add a new admin user"""
        if username in self.credentials:
            return False
        self.credentials[username] = hashlib.sha256(password.encode()).hexdigest()
        return True

    def change_password(self, username: str, old_password: str, new_password: str) -> bool:
        """Change admin password"""
        if self.login(username, old_password):
            self.credentials[username] = hashlib.sha256(new_password.encode()).hexdigest()
            return True
        return False


class AdminOperations:
    """Handles admin-level operations on the booking system"""
    
    def __init__(self, booking_system):
        self.booking_system = booking_system
        self.auth = AdminAuth()

    def merge_buses(self, username: str, password: str) -> dict:
        """Merge underutilized buses"""
        if not self.auth.login(username, password):
            return {"status": "unauthorized"}
        
        with self.booking_system.system_lock:
            # Find buses to merge
            active_buses = [b for b in self.booking_system.buses.values() 
                        if b.status == "active"]
            
            # Only merge if system load is low
            if self.booking_system.get_overall_load_factor() >= self.booking_system.load_threshold_low:
                return {"status": "failure", "message": "Load factor too high to merge"}
            
            # Sort by load factor (merge emptiest first)
            buses_by_load = sorted(active_buses, key=lambda b: b.get_load_factor())
            
            # Keep half, merge half
            buses_to_keep = buses_by_load[len(buses_by_load)//2:]
            buses_to_merge = buses_by_load[:len(buses_by_load)//2]
            
            merged_count = 0
            
            for source_bus in buses_to_merge:
                # Transfer all bookings from source bus (date-aware)
                for date_str, date_seats in list(source_bus.seats_by_date.items()):
                    if not isinstance(date_seats, dict):
                        continue

                    for seat_num, client_id in list(date_seats.items()):
                        if client_id is None:
                            continue

                        # Try to preserve the same seat number if possible
                        transferred = False
                        for target_bus in buses_to_keep:
                            if target_bus.status == "active":
                                # Try to book the SAME seat number first
                                if target_bus.is_seat_available(seat_num, date_str):
                                    if target_bus.book_seat(seat_num, client_id, date_str):
                                        # Update booking record
                                        self._update_booking_after_merge(
                                            client_id, source_bus.bus_id, seat_num,
                                            target_bus.bus_id, seat_num, date_str
                                        )
                                        transferred = True
                                        break
                                # If same seat not available, try any seat
                                else:
                                    available = target_bus.get_available_seats(date_str)
                                    if available:
                                        new_seat = available[0]
                                        if target_bus.book_seat(new_seat, client_id, date_str):
                                            # Update booking record
                                            self._update_booking_after_merge(
                                                client_id, source_bus.bus_id, seat_num,
                                                target_bus.bus_id, new_seat, date_str
                                            )
                                            transferred = True
                                            break

                        if transferred:
                            # Clear old seat
                            source_bus.release_seat(seat_num, date_str)
                        else:
                            self.booking_system.logger.log(
                                f"Warning: Could not transfer booking for {client_id} "
                                f"from Bus {source_bus.bus_id} Seat {seat_num} Date {date_str}"
                            )

                # Now mark bus as merged (should be empty)
                source_bus.status = "merged"
                # Clear all seat data
                source_bus.seats_by_date.clear()
                source_bus.locks.clear()
                source_bus.reservation_time.clear()
                source_bus.booking_confirmed.clear()

                merged_count += 1
            
            return {
                "status": "success",
                "merged_buses": [b.bus_id for b in buses_to_merge],
                "new_bus_count": len(buses_to_keep)
            }

    def _transfer_bookings(self, source_bus, target_bus):
        """Transfer bookings to any available seats in target bus"""
        transferred = 0
        
        # Get all booked seats from source bus
        booked_seats = []
        for seat, client in source_bus.seats.items():
            if client is not None:
                booked_seats.append((seat, client))
        
        # Try to transfer each booking to any available seat
        for old_seat, client in booked_seats:
            # Find first available seat in target bus
            seat_transferred = False
            for new_seat in range(1, target_bus.total_seats + 1):
                if target_bus.seats[new_seat] is None:
                    # Transfer the booking
                    target_bus.seats[new_seat] = client
                    if old_seat in source_bus.departure_dates:
                        target_bus.departure_dates[new_seat] = source_bus.departure_dates[old_seat]
                    # Update booking record
                    self._update_booking_after_merge(client, source_bus.bus_id, 
                                                    old_seat, target_bus.bus_id, new_seat)
                    transferred += 1
                    seat_transferred = True
                    break
            
            if not seat_transferred:
                # No available seats in target bus
                print(f"Warning: Could not transfer booking for {client} - no available seats")
        
        return transferred
                    
    def _update_booking_after_merge(self, client_id, old_bus_id, old_seat,
                                new_bus_id, new_seat, date):
        """Update booking records after bus merge"""
        for booking_id, booking in self.booking_system.bookings_db.items():
            if (booking['client_id'] == client_id and
                booking['bus_id'] == old_bus_id and
                booking['seat'] == old_seat and
                booking['date'] == date):
                
                # Update the booking data
                booking['bus_id'] = new_bus_id
                booking['seat'] = new_seat
                
                # Ensure booking_id is in the dict (it should be, but make sure)
                if 'booking_id' not in booking:
                    booking['booking_id'] = booking_id

                # Update database
                if self.booking_system.db:
                    self.booking_system.db.save_booking(booking)
                    self.booking_system.db.delete_bus_seat(old_bus_id, old_seat, date)
                    self.booking_system.db.save_bus_seat(new_bus_id, new_seat, client_id, date)

                self.booking_system.logger.log(
                    f"Updated booking {booking_id}: Bus {old_bus_id} Seat {old_seat} "
                    f"→ Bus {new_bus_id} Seat {new_seat} (Date: {date})"
                )
                break
    def get_system_overview(self, username: str, password: str) -> Optional[dict]:
        """Get comprehensive system overview (admin only)"""
        if not self.auth.login(username, password):
            return None

        # Get all buses from database
        all_buses = self.booking_system.get_all_buses()
        active_buses = [b for b in all_buses if b['status'] == 'active']
        merged_buses = [b for b in all_buses if b['status'] == 'merged']

        total_seats = sum(bus['total_seats'] for bus in active_buses)

        # Count booked seats across all dates and buses
        booked_seats = 0
        for bus in active_buses:
            bus_dates = self.booking_system.db.get_all_dates_for_bus(bus['bus_id'])
            for date in bus_dates:
                bus_seats = self.booking_system.db.get_bus_seats(bus['bus_id'], date)
                booked_seats += sum(1 for client_id in bus_seats.values() if client_id is not None)

        # Get all bookings
        all_bookings = self.booking_system.get_all_bookings()

        return {
            "total_buses": len(all_buses),
            "active_buses": len(active_buses),
            "merged_buses": len(merged_buses),
            "total_seats": total_seats,
            "booked_seats": booked_seats,
            "load_factor": booked_seats / total_seats if total_seats > 0 else 0,
            "total_visitors": len(set(booking['client_id'] for booking in all_bookings)),
            "total_bookings": len(all_bookings)
        }

    def force_release_seat(self, username: str, password: str, 
                          bus_id: int, seat_number: int) -> bool:
        """Force release a seat (admin emergency function)"""
        if not self.auth.login(username, password):
            return False

        with self.booking_system.system_lock:
            if bus_id in self.booking_system.buses:
                bus = self.booking_system.buses[bus_id]
                if bus.release_seat(seat_number):
                    self.booking_system.logger.log(
                        f"Admin {username}: Force released seat {seat_number} on bus {bus_id}"
                    )
                    return True
        return False