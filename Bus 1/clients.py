import threading
import time
import queue
from typing import Optional


class Client(threading.Thread):
    """Simulated client for threading approach"""
    
    def __init__(self, client_id: str, booking_system, travel_date: str, 
                 booking_delay: float = 0.1, preferred_bus: Optional[int] = None,
                 preferred_seat: Optional[int] = None):
        super().__init__()
        self.client_id = client_id
        self.booking_system = booking_system
        self.travel_date = travel_date
        self.booking_delay = booking_delay
        self.preferred_bus = preferred_bus
        self.preferred_seat = preferred_seat
        self.result = None

    def run(self):
        """Execute booking request"""
        time.sleep(self.booking_delay)
        self.result = self.booking_system.book_seat_for_client(
            self.client_id, 
            self.travel_date,
            self.preferred_bus,
            self.preferred_seat
        )


class BulkBookingClient:
    """Client for making multiple bookings"""
    
    def __init__(self, client_id: str, booking_system):
        self.client_id = client_id
        self.booking_system = booking_system
        self.bookings = []

    def make_booking(self, travel_date: str, preferred_bus: Optional[int] = None,
                    preferred_seat: Optional[int] = None) -> dict:
        """Make a single booking"""
        result = self.booking_system.book_seat_for_client(
            self.client_id,
            travel_date,
            preferred_bus,
            preferred_seat
        )
        if result["status"] == "success":
            self.bookings.append(result["booking_id"])
        return result

    def cancel_booking(self, booking_id: str) -> bool:
        """Cancel a booking"""
        success = self.booking_system.cancel_booking(booking_id, self.client_id)
        if success and booking_id in self.bookings:
            self.bookings.remove(booking_id)
        return success

    def get_my_bookings(self) -> list:
        """Get all bookings for this client"""
        return self.booking_system.get_client_bookings(self.client_id)

    def cancel_all_bookings(self) -> int:
        """Cancel all bookings for this client"""
        cancelled = 0
        for booking_id in self.bookings.copy():
            if self.cancel_booking(booking_id):
                cancelled += 1
        return cancelled


def client_booking_process(client_id: str, booking_system, travel_date: str, 
                          result_queue: queue.Queue, preferred_bus: Optional[int] = None,
                          preferred_seat: Optional[int] = None):
    """For multiprocessing approach"""
    result = booking_system.book_seat_for_client(
        client_id, 
        travel_date,
        preferred_bus,
        preferred_seat
    )
    result_queue.put(result)


class LoadGenerator:
    """Generates realistic booking load for testing"""
    
    def __init__(self, booking_system):
        self.booking_system = booking_system
        self.active_clients = []

    def generate_steady_load(self, num_clients: int, dates: list, 
                           delay_between_clients: float = 0.1) -> list:
        """Generate steady booking load"""
        clients = []
        
        for i in range(num_clients):
            date = dates[i % len(dates)]
            client = Client(
                f"load_client_{i}",
                self.booking_system,
                date,
                booking_delay=delay_between_clients
            )
            client.start()
            clients.append(client)
        
        return clients

    def generate_burst_load(self, num_clients: int, dates: list) -> list:
        """Generate burst of concurrent bookings"""
        clients = []
        
        for i in range(num_clients):
            date = dates[i % len(dates)]
            client = Client(
                f"burst_client_{i}",
                self.booking_system,
                date,
                booking_delay=0.01  # Minimal delay for burst
            )
            client.start()
            clients.append(client)
        
        return clients

    def generate_mixed_load(self, num_steady: int, num_burst: int, dates: list) -> tuple:
        """Generate mixed load pattern"""
        steady_clients = self.generate_steady_load(num_steady, dates)
        time.sleep(0.5)  # Wait before burst
        burst_clients = self.generate_burst_load(num_burst, dates)
        
        return steady_clients, burst_clients

    def wait_for_clients(self, clients: list) -> list:
        """Wait for all clients to complete and return results"""
        for client in clients:
            client.join()
        
        return [c.result for c in clients if c.result is not None]


class ClientSimulator:
    """Advanced client simulation with realistic patterns"""
    
    def __init__(self, booking_system):
        self.booking_system = booking_system

    def simulate_normal_day(self, num_clients: int, dates: list) -> dict:
        """Simulate normal booking day with varied timing"""
        import random
        
        clients = []
        results = {"morning": [], "afternoon": [], "evening": []}
        
        # Morning rush (40% of clients)
        morning_clients = int(num_clients * 0.4)
        for i in range(morning_clients):
            date = random.choice(dates)
            delay = random.uniform(0, 0.2)
            client = Client(f"morning_{i}", self.booking_system, date, delay)
            client.start()
            clients.append(("morning", client))
        
        time.sleep(1)  # Simulate time gap
        
        # Afternoon steady (30% of clients)
        afternoon_clients = int(num_clients * 0.3)
        for i in range(afternoon_clients):
            date = random.choice(dates)
            delay = random.uniform(0.1, 0.5)
            client = Client(f"afternoon_{i}", self.booking_system, date, delay)
            client.start()
            clients.append(("afternoon", client))
        
        time.sleep(1)  # Simulate time gap
        
        # Evening rush (30% of clients)
        evening_clients = num_clients - morning_clients - afternoon_clients
        for i in range(evening_clients):
            date = random.choice(dates)
            delay = random.uniform(0, 0.15)
            client = Client(f"evening_{i}", self.booking_system, date, delay)
            client.start()
            clients.append(("evening", client))
        
        # Collect results
        for period, client in clients:
            client.join()
            if client.result:
                results[period].append(client.result)
        
        return results

    def simulate_cancellations(self, booking_ids: list, cancel_rate: float = 0.1) -> int:
        """Simulate random cancellations"""
        import random
        
        num_cancellations = int(len(booking_ids) * cancel_rate)
        cancelled = 0
        
        for _ in range(num_cancellations):
            if not booking_ids:
                break
            booking_id = random.choice(booking_ids)
            # Extract client_id from booking
            booking = self.booking_system.get_booking(booking_id)
            if booking:
                if self.booking_system.cancel_booking(booking_id, booking["client_id"]):
                    cancelled += 1
                    booking_ids.remove(booking_id)
        
        return cancelled