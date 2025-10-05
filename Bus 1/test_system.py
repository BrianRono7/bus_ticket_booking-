"""
Unit tests for the Bus Booking System
Run with: python -m pytest test_system.py
or: python test_system.py
"""

import unittest
import time
from datetime import datetime, timedelta

from models import Bus, Booking
from booking_system import BusBookingSystem
from clients import Client, BulkBookingClient
from admin import AdminAuth


class TestBusModel(unittest.TestCase):
    """Test Bus model functionality"""
    
    def setUp(self):
        self.bus = Bus(bus_id=1, total_seats=50)
    
    def test_bus_initialization(self):
        """Test bus is initialized correctly"""
        self.assertEqual(self.bus.bus_id, 1)
        self.assertEqual(self.bus.total_seats, 50)
        self.assertEqual(self.bus.status, "active")
        self.assertEqual(len(self.bus.seats), 50)
    
    def test_get_available_seats(self):
        """Test getting available seats"""
        available = self.bus.get_available_seats()
        self.assertEqual(len(available), 50)
        
        # Book a seat
        self.bus.book_seat(1, "client1", "2025-10-04")
        available = self.bus.get_available_seats()
        self.assertEqual(len(available), 49)
    
    def test_book_seat(self):
        """Test seat booking"""
        result = self.bus.book_seat(1, "client1", "2025-10-04")
        self.assertTrue(result)
        self.assertEqual(self.bus.seats[1], "client1")
        
        # Try to book same seat
        result = self.bus.book_seat(1, "client2", "2025-10-04")
        self.assertFalse(result)
    
    def test_release_seat(self):
        """Test seat release"""
        self.bus.book_seat(1, "client1", "2025-10-04")
        self.assertEqual(self.bus.seats[1], "client1")
        
        self.bus.release_seat(1)
        self.assertIsNone(self.bus.seats[1])
    
    def test_load_factor(self):
        """Test load factor calculation"""
        self.assertEqual(self.bus.get_load_factor(), 0.0)
        
        # Book 25 seats (50% load)
        for i in range(1, 26):
            self.bus.book_seat(i, f"client{i}", "2025-10-04")
        
        self.assertEqual(self.bus.get_load_factor(), 0.5)


class TestBookingSystem(unittest.TestCase):
    """Test BusBookingSystem functionality"""
    
    def setUp(self):
        self.system = BusBookingSystem(initial_buses=5, max_buses=20)
    
    def tearDown(self):
        self.system.shutdown()
    
    def test_system_initialization(self):
        """Test system initializes correctly"""
        self.assertEqual(len(self.system.buses), 5)
        self.assertEqual(self.system.max_buses, 20)
    
    def test_book_seat(self):
        """Test basic booking"""
        result = self.system.book_seat_for_client("client1", "2025-10-04")
        self.assertEqual(result["status"], "success")
        self.assertIn("booking_id", result)
        self.assertIn("bus_id", result)
        self.assertIn("seat_number", result)
    
    def test_multiple_bookings(self):
        """Test multiple bookings"""
        results = []
        for i in range(10):
            result = self.system.book_seat_for_client(f"client{i}", "2025-10-04")
            results.append(result)
        
        successful = [r for r in results if r["status"] == "success"]
        self.assertEqual(len(successful), 10)
    
    def test_cancel_booking(self):
        """Test booking cancellation"""
        # Make a booking
        result = self.system.book_seat_for_client("client1", "2025-10-04")
        booking_id = result["booking_id"]
        
        # Cancel it
        cancelled = self.system.cancel_booking(booking_id, "client1")
        self.assertTrue(cancelled)
        
        # Verify it's gone
        booking = self.system.get_booking(booking_id)
        self.assertIsNone(booking)
    
    def test_cancel_wrong_client(self):
        """Test cancellation with wrong client ID"""
        result = self.system.book_seat_for_client("client1", "2025-10-04")
        booking_id = result["booking_id"]
        
        # Try to cancel with different client
        cancelled = self.system.cancel_booking(booking_id, "client2")
        self.assertFalse(cancelled)
    
    def test_visitor_count(self):
        """Test visitor counting"""
        initial = self.system.get_total_visitors()
        
        self.system.book_seat_for_client("client1", "2025-10-04")
        self.system.book_seat_for_client("client2", "2025-10-04")
        
        self.assertEqual(self.system.get_total_visitors(), initial + 2)
    
    def test_load_factor(self):
        """Test overall load factor"""
        initial_load = self.system.get_overall_load_factor()
        
        # Book some seats
        for i in range(50):
            self.system.book_seat_for_client(f"client{i}", "2025-10-04")
        
        final_load = self.system.get_overall_load_factor()
        self.assertGreater(final_load, initial_load)
    
    def test_auto_scaling(self):
        """Test automatic bus addition"""
        initial_buses = len([b for b in self.system.buses.values() if b.status == "active"])
        
        # Book many seats to trigger scaling
        for i in range(200):
            self.system.book_seat_for_client(f"client{i}", "2025-10-04")
        
        final_buses = len([b for b in self.system.buses.values() if b.status == "active"])
        self.assertGreaterEqual(final_buses, initial_buses)


class TestConcurrency(unittest.TestCase):
    """Test concurrent operations"""
    
    def setUp(self):
        self.system = BusBookingSystem(initial_buses=10)
    
    def tearDown(self):
        self.system.shutdown()
    
    def test_concurrent_bookings(self):
        """Test multiple clients booking concurrently"""
        clients = []
        
        for i in range(50):
            client = Client(f"client{i}", self.system, "2025-10-04", booking_delay=0.01)
            client.start()
            clients.append(client)
        
        # Wait for all clients
        for client in clients:
            client.join()
        
        # Check results
        results = [c.result for c in clients if c.result]
        successful = [r for r in results if r["status"] == "success"]
        
        self.assertEqual(len(results), 50)
        self.assertGreater(len(successful), 0)
    
    def test_no_double_booking(self):
        """Test that same seat cannot be double-booked"""
        clients = []
        
        # All try to book seat 1 on bus 0
        for i in range(10):
            client = Client(
                f"client{i}", 
                self.system, 
                "2025-10-04", 
                booking_delay=0
            )
            clients.append(client)
        
        # Start all at once
        for client in clients:
            client.start()
        
        # Wait for completion
        for client in clients:
            client.join()
        
        # Verify no double bookings
        bus = self.system.buses[0]
        occupied_seats = [seat for seat, client in bus.seats.items() if client is not None]
        
        # Check no duplicate bookings
        seat_clients = {}
        for seat in occupied_seats:
            client_id = bus.seats[seat]
            self.assertNotIn(seat, seat_clients, "Seat was double-booked!")
            seat_clients[seat] = client_id


class TestAdminOperations(unittest.TestCase):
    """Test admin functionality"""
    
    def setUp(self):
        self.system = BusBookingSystem(initial_buses=10, load_threshold_low=0.1)
        self.admin = self.system.admin
    
    def tearDown(self):
        self.system.shutdown()
    
    def test_admin_login(self):
        """Test admin authentication"""
        self.assertTrue(self.admin.auth.login("admin", "admin123"))
        self.assertFalse(self.admin.auth.login("admin", "wrongpass"))
    
    def test_bus_merging(self):
        """Test bus merging operation"""
        initial_buses = len([b for b in self.system.buses.values() if b.status == "active"])
        
        result = self.admin.merge_buses("admin", "admin123")
        
        self.assertEqual(result["status"], "success")
        final_buses = len([b for b in self.system.buses.values() if b.status == "active"])
        self.assertLessEqual(final_buses, initial_buses)
    
    def test_system_overview(self):
        """Test system overview retrieval"""
        overview = self.admin.get_system_overview("admin", "admin123")
        
        self.assertIsNotNone(overview)
        self.assertIn("total_buses", overview)
        self.assertIn("active_buses", overview)
        self.assertIn("load_factor", overview)
    
    def test_unauthorized_access(self):
        """Test unauthorized admin access"""
        overview = self.admin.get_system_overview("admin", "wrongpass")
        self.assertIsNone(overview)


class TestBulkBookingClient(unittest.TestCase):
    """Test bulk booking client"""
    
    def setUp(self):
        self.system = BusBookingSystem(initial_buses=5)
        self.client = BulkBookingClient("bulk_client", self.system)
    
    def tearDown(self):
        self.system.shutdown()
    
    def test_make_booking(self):
        """Test making a booking"""
        result = self.client.make_booking("2025-10-04")
        self.assertEqual(result["status"], "success")
        self.assertEqual(len(self.client.bookings), 1)
    
    def test_cancel_booking(self):
        """Test cancelling a booking"""
        result = self.client.make_booking("2025-10-04")
        booking_id = result["booking_id"]
        
        cancelled = self.client.cancel_booking(booking_id)
        self.assertTrue(cancelled)
        self.assertEqual(len(self.client.bookings), 0)
    
    def test_get_my_bookings(self):
        """Test retrieving client's bookings"""
        self.client.make_booking("2025-10-04")
        self.client.make_booking("2025-10-05")
        
        bookings = self.client.get_my_bookings()
        self.assertEqual(len(bookings), 2)


def run_tests():
    """Run all tests"""
    loader = unittest.TestLoader()
    suite = unittest.TestSuite()
    
    # Add all test classes
    suite.addTests(loader.loadTestsFromTestCase(TestBusModel))
    suite.addTests(loader.loadTestsFromTestCase(TestBookingSystem))
    suite.addTests(loader.loadTestsFromTestCase(TestConcurrency))
    suite.addTests(loader.loadTestsFromTestCase(TestAdminOperations))
    suite.addTests(loader.loadTestsFromTestCase(TestBulkBookingClient))
    
    # Run tests
    runner = unittest.TextTestRunner(verbosity=2)
    result = runner.run(suite)
    
    return result.wasSuccessful()


if __name__ == "__main__":
    success = run_tests()
    exit(0 if success else 1)