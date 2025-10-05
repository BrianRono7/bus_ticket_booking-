import unittest
import time
from datetime import datetime, timedelta
from booking_system import BusBookingSystem
from clients import Client

class TestComprehensiveSystem(unittest.TestCase):
    """Comprehensive system tests"""
    
    def test_load_factor_accuracy(self):
        """Test that load factor is calculated correctly"""
        system = BusBookingSystem(initial_buses=2, max_buses=10)
        
        # Book exactly 50 seats (50% of 100 total)
        for i in range(50):
            system.book_seat_for_client(f"client_{i}", "2025-10-04")
        
        load_factor = system.get_overall_load_factor()
        self.assertAlmostEqual(load_factor, 0.5, places=2, 
                              msg=f"Expected 50% load, got {load_factor*100:.1f}%")
        
        system.shutdown()
    
    def test_concurrent_same_seat(self):
        """Test that same seat cannot be double-booked"""
        system = BusBookingSystem(initial_buses=1)
        
        results = []
        clients = []
        
        # 10 clients try to book seat 1 simultaneously
        for i in range(10):
            client = Client(f"client_{i}", system, "2025-10-04", booking_delay=0)
            clients.append(client)
        
        for client in clients:
            client.start()
        
        for client in clients:
            client.join()
            if client.result:
                results.append(client.result)
        
        # Count successful bookings for seat 1 on bus 0
        bus = system.buses[0]
        seat_1_bookings = [r for r in results if r.get('bus_id') == 0 and r.get('seat_number') == 1]
        
        self.assertLessEqual(len(seat_1_bookings), 1, 
                            "Seat 1 was booked multiple times!")
        
        system.shutdown()
    
    def test_bus_merging_preserves_bookings(self):
        """Test that bus merging doesn't lose bookings"""
        system = BusBookingSystem(initial_buses=10, load_threshold_low=0.3)
        
        # Book a few seats
        results = []
        for i in range(20):
            result = system.book_seat_for_client(f"client_{i}", "2025-10-04")
            if result['status'] == 'success':
                results.append(result)
        
        initial_bookings = len(results)
        
        # Merge buses
        system.admin.merge_buses("admin", "admin123")
        
        # Count bookings after merge
        final_bookings = len(system.bookings_db)
        
        self.assertEqual(initial_bookings, final_bookings,
                        f"Lost {initial_bookings - final_bookings} bookings during merge!")
        
        system.shutdown()

if __name__ == "__main__":
    unittest.main()