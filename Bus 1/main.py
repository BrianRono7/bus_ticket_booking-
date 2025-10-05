import time
import sys
from datetime import datetime, timedelta
from concurrent.futures import ThreadPoolExecutor
from collections import defaultdict

from booking_system import BusBookingSystem
from monitor import PerformanceMonitor
from clients import Client, LoadGenerator, ClientSimulator, BulkBookingClient
from config import (
    INITIAL_BUS_COUNT, MAX_BUS_COUNT, LOAD_THRESHOLD_HIGH, 
    LOAD_THRESHOLD_LOW, SEAT_RESERVATION_TIMEOUT,
    MONITOR_INTERVAL, ENABLE_DETAILED_STATS
)
from config import validate_config, print_config_summary


def print_header(title: str, width: int = 70):
    """Print formatted header"""
    print(f"\n{title:-^{width}}")


def print_section(title: str, width: int = 70):
    """Print section header"""
    print(f"\n{'=' * width}")
    print(f"{title.center(width)}")
    print(f"{'=' * width}")


def run_comprehensive_simulation():
    """Comprehensive simulation combining all approaches and features"""
    
    print_section("COMPREHENSIVE BUS BOOKING SIMULATION")
    
    # Initialize system with your specifications
    booking_system = BusBookingSystem(
        initial_buses=INITIAL_BUS_COUNT, 
        max_buses=MAX_BUS_COUNT,
        load_threshold_high=LOAD_THRESHOLD_HIGH,
        load_threshold_low=LOAD_THRESHOLD_LOW,
        seat_lock_timeout=SEAT_RESERVATION_TIMEOUT
    )
    monitor = PerformanceMonitor(booking_system)
    monitor.start_monitoring(interval=MONITOR_INTERVAL)

    # Print configuration being used
    print(f"\nSimulation Configuration (from config.py):")
    print(f"  Initial Buses: {INITIAL_BUS_COUNT}")
    print(f"  Max Buses: {MAX_BUS_COUNT}")
    print(f"  Load Threshold (High): {LOAD_THRESHOLD_HIGH:.0%}")
    print(f"  Load Threshold (Low): {LOAD_THRESHOLD_LOW:.0%}")
    print(f"  Seat Lock Timeout: {SEAT_RESERVATION_TIMEOUT}s")
    print(f"  Monitor Interval: {MONITOR_INTERVAL}s")
    print(f"  Detailed Stats: {ENABLE_DETAILED_STATS}")
    
    # Test dates for multiple days
    today = datetime.now().date()
    dates_3_days = [str(today + timedelta(days=i)) for i in range(3)]
    dates_7_days = [str(today + timedelta(days=i)) for i in range(7)]
    dates_30_days = [str(today + timedelta(days=i)) for i in range(30)]
    
    print(f"\nSimulation Configuration:")
    print(f"  3-Day Dates: {', '.join(dates_3_days)}")
    print(f"  7-Day Dates: {', '.join(dates_7_days[:3])}...")
    print(f"  30-Day Dates: {', '.join(dates_30_days[:3])}...")
    print(f"  Initial Buses: {booking_system.initial_buses}")
    print(f"  Max Buses: {booking_system.max_buses}")
    print(f"  Load Threshold (High): {booking_system.load_threshold_high:.0%}")
    print(f"  Load Threshold (Low): {booking_system.load_threshold_low:.0%}")
    print(f"  Seat Lock Timeout: {booking_system.seat_lock_timeout}s ({booking_system.seat_lock_timeout/60} minutes)")
    
    # PHASE 1: Basic Booking Approaches
    print_header("PHASE 1: BASIC BOOKING APPROACHES")
    
    # Iterative Serving (Approach A)
    print_header("A. Iterative Serving", 50)
    start_time = time.time()
    iterative_results = []
    
    for i in range(30):
        date = dates_3_days[i % 3]
        result = booking_system.book_seat_for_client(f"client_iter_{i}", date)
        iterative_results.append(result)
    
    iter_time = time.time() - start_time
    iter_success = sum(1 for r in iterative_results if r['status'] == 'success')
    print(f"  Time: {iter_time:.3f}s")
    print(f"  Success: {iter_success}/{len(iterative_results)} ({iter_success/len(iterative_results)*100:.1f}%)")
    
    # Threading Approach (Approach B)
    print_header("B. Threading Approach", 50)
    start_time = time.time()
    thread_clients = []
    
    for i in range(50):
        date = dates_3_days[i % 3]
        client = Client(f"client_thread_{i}", booking_system, date, booking_delay=0.01)
        client.start()
        thread_clients.append(client)
    
    for client in thread_clients:
        client.join()
    
    thread_time = time.time() - start_time
    thread_results = [c.result for c in thread_clients if c.result]
    thread_success = sum(1 for r in thread_results if r['status'] == 'success')
    print(f"  Time: {thread_time:.3f}s")
    print(f"  Success: {thread_success}/{len(thread_results)} ({thread_success/len(thread_results)*100:.1f}%)")
    print(f"  Speedup: {iter_time/thread_time:.2f}x")
    
    # ThreadPool Executor (Approach C)
    print_header("C. ThreadPool Executor", 50)
    start_time = time.time()
    
    with ThreadPoolExecutor(max_workers=10) as executor:
        futures = []
        for i in range(40):
            date = dates_3_days[i % 3]
            future = executor.submit(
                booking_system.book_seat_for_client,
                f"client_pool_{i}", 
                date
            )
            futures.append(future)
        
        pool_results = [f.result() for f in futures]
    
    pool_time = time.time() - start_time
    pool_success = sum(1 for r in pool_results if r['status'] == 'success')
    print(f"  Time: {pool_time:.3f}s")
    print(f"  Success: {pool_success}/{len(pool_results)} ({pool_success/len(pool_results)*100:.1f}%)")
    print(f"  Speedup: {iter_time/pool_time:.2f}x")

    # For fair comparison, calculate per-booking time
    iter_per_booking = iter_time / len(iterative_results)
    thread_per_booking = thread_time / len(thread_results)
    pool_per_booking = pool_time / len(pool_results)

    print(f"  Speedup: {iter_per_booking/thread_per_booking:.2f}x")
    
    # PHASE 2: Multiple Days Booking & Advanced Patterns
    print_header("PHASE 2: MULTIPLE DAYS & REALISTIC PATTERNS")
    
    simulator = ClientSimulator(booking_system)
    
    print("Simulating 7-day booking patterns with 200 clients...")
    realistic_results = simulator.simulate_normal_day(200, dates_7_days)
    
    print(f"\nRealistic Pattern Results:")
    for period, period_results in realistic_results.items():
        success = sum(1 for r in period_results if r['status'] == 'success')
        print(f"  {period.capitalize():10}: {success}/{len(period_results)} successful")
    
    # Collect all successful booking IDs for cancellation simulation
    all_booking_ids = [
        r['booking_id'] 
        for period_results in realistic_results.values() 
        for r in period_results 
        if r['status'] == 'success'
    ]
    
    print(f"\nSimulating realistic cancellations (10% rate)...")
    cancelled = simulator.simulate_cancellations(all_booking_ids, cancel_rate=0.1)
    print(f"  Cancelled: {cancelled} bookings")
    
    # PHASE 3: Stress Testing with Auto-scaling
    print_header("PHASE 3: STRESS TESTING & AUTO-SCALING")
    
    print(f"Current system state before stress test:")
    print(f"  Active Buses: {len([b for b in booking_system.buses.values() if b.status == 'active'])}")
    print(f"  Load Factor: {booking_system.get_overall_load_factor():.2%}")
    
    load_gen = LoadGenerator(booking_system)
    
    # Burst load to trigger auto-scaling
    print_header("Burst Load Test (Trigger Auto-scaling)", 50)
    start_time = time.time()
    burst_clients = load_gen.generate_burst_load(150, dates_30_days)  # More clients to trigger scaling
    burst_results = load_gen.wait_for_clients(burst_clients)
    burst_time = time.time() - start_time
    burst_success = sum(1 for r in burst_results if r['status'] == 'success')
    
    print(f"  Clients: 150 simultaneous")
    print(f"  Time: {burst_time:.3f}s")
    print(f"  Success: {burst_success}/{len(burst_results)} ({burst_success/len(burst_results)*100:.1f}%)")
    print(f"  Throughput: {len(burst_results)/burst_time:.1f} bookings/sec")
    print(f"  Active Buses After: {len([b for b in booking_system.buses.values() if b.status == 'active'])}")
    print(f"  Load Factor After: {booking_system.get_overall_load_factor():.2%}")
    
    # PHASE 4: System Operations & Admin Functions
    print_header("PHASE 4: SYSTEM OPERATIONS & ADMIN FUNCTIONS")
    
    # Admin Operations
    print_header("Admin Operations - Bus Merging", 50)
    print(f"  Active buses before operations: {len([b for b in booking_system.buses.values() if b.status == 'active'])}")
    print(f"  Current Load Factor: {booking_system.get_overall_load_factor():.2%}")
    
    # Only merge if load factor is below threshold
    current_load = booking_system.get_overall_load_factor()
    if current_load < booking_system.load_threshold_low:
        merge_result = booking_system.admin.merge_buses("admin", "admin123")
        print(f"  Bus merging: {merge_result['status']}")
        
        if merge_result['status'] == 'success':
            print(f"  Merged buses: {len(merge_result.get('merged_buses', []))}")
            print(f"  Active buses after merge: {merge_result.get('new_bus_count', 'N/A')}")
    else:
        print(f"  Load factor ({current_load:.2%}) above minimum threshold ({booking_system.load_threshold_low:.0%}) - skipping merge")
    
    # System Overview
    overview = booking_system.admin.get_system_overview("admin", "admin123")
    if overview:
        print(f"  System Overview:")
        print(f"    Total Buses: {overview['total_buses']}")
        print(f"    Active Buses: {overview['active_buses']}")
        print(f"    Merged Buses: {overview['merged_buses']}")
        print(f"    Load Factor: {overview['load_factor']:.2%}")
        print(f"    Total Visitors: {overview['total_visitors']}")
        print(f"    Total Bookings: {overview['total_bookings']}")
    
    # PHASE 5: Performance Analysis & Resource Monitoring
    print_header("PHASE 5: PERFORMANCE ANALYSIS & RESOURCE MONITORING")
    
    monitor.stop_monitoring()
    perf_report = monitor.get_performance_report()
    disk_stats = booking_system.logger.get_stats()
    
    print(f"CPU & Memory Usage:")
    print(f"  Max CPU: {perf_report['max_cpu_usage']:.2f}%")
    print(f"  Avg CPU: {perf_report['avg_cpu_usage']:.2f}%")
    print(f"  Min CPU: {perf_report['min_cpu_usage']:.2f}%")
    print(f"  CPU Idle Time: {perf_report['cpu_idle_time_seconds']:.2f}s")
    print(f"  Max Physical Memory: {perf_report['max_physical_memory_mb']:.2f} MB")
    print(f"  Max Virtual Memory: {perf_report['max_virtual_memory_mb']:.2f} MB")
    
    print(f"\nThreading & Concurrency:")
    print(f"  Max Threads: {int(perf_report['max_threads'])}")
    print(f"  Avg Threads: {perf_report['avg_threads']:.1f}")
    print(f"  Monitoring Duration: {perf_report['total_monitoring_time']:.2f}s")
    print(f"  Samples Collected: {perf_report['samples_collected']}")
    
    print(f"\nI/O Performance:")
    print(f"  Disk Writes: {disk_stats['total_writes']}")
    print(f"  Total Write Time: {disk_stats['total_write_time']:.4f}s")
    print(f"  Avg Write Time: {disk_stats['avg_write_time']:.6f}s")
    print(f"  Write Method: {disk_stats['write_method']}")
    print(f"  Throughput: {len(booking_system.bookings_db)/perf_report['total_monitoring_time']:.1f} bookings/sec")
    
    # Final System State
    print_header("FINAL SYSTEM STATE")
    print(f"  Total Bookings: {len(booking_system.bookings_db)}")
    print(f"  Overall Load Factor: {booking_system.get_overall_load_factor():.2%}")
    print(f"  Active Buses: {len([b for b in booking_system.buses.values() if b.status == 'active'])}")
    print(f"  Total Visitors: {booking_system.get_total_visitors()}")
    
    bus_statuses = {}
    for bus in booking_system.buses.values():
        bus_statuses[bus.status] = bus_statuses.get(bus.status, 0) + 1
    
    print(f"  Bus Fleet: {', '.join([f'{status.capitalize()}: {count}' for status, count in bus_statuses.items()])}")
    
    return booking_system


def show_all_clients(booking_system):
    """Display all clients who have made bookings"""
    print_header("ALL BOOKED CLIENTS")
    
    # Get all unique clients from bookings
    client_bookings = defaultdict(list)
    
    for booking_id, booking_data in booking_system.bookings_db.items():
        client_id = booking_data["client_id"]
        complete_booking = {
            "booking_id": booking_id,
            "client_id": booking_data["client_id"],
            "bus_id": booking_data["bus_id"],
            "seat": booking_data["seat"],
            "date": booking_data["date"],
            "booking_time": booking_data.get("booking_time", "Unknown")
        }
        client_bookings[client_id].append(complete_booking)
    
    if not client_bookings:
        print("  No clients have made bookings yet.")
        return client_bookings
    
    total_bookings = sum(len(bookings) for bookings in client_bookings.values())
    
    print(f"  Total Unique Clients: {len(client_bookings)}")
    print(f"  Total Bookings: {total_bookings}")
    
    # Show first 20 clients with their booking counts
    print(f"\n  Client Booking Summary (showing first 20):")
    displayed = 0
    for client_id, bookings in sorted(client_bookings.items()):
        if displayed >= 20:
            remaining = len(client_bookings) - 20
            print(f"    ... and {remaining} more clients")
            break
            
        print(f"    {client_id}: {len(bookings)} booking(s)")
        displayed += 1
    
    return client_bookings


def show_client_details(booking_system, client_id):
    """Show detailed information for a specific client"""
    print_header(f"CLIENT DETAILS: {client_id}")
    
    client_bookings = []
    for booking_id, booking_data in booking_system.bookings_db.items():
        if booking_data["client_id"] == client_id:
            complete_booking = {
                "booking_id": booking_id,
                "client_id": booking_data["client_id"],
                "bus_id": booking_data["bus_id"],
                "seat": booking_data["seat"],
                "date": booking_data["date"],
                "booking_time": booking_data.get("booking_time", "Unknown")
            }
            client_bookings.append(complete_booking)
    
    if not client_bookings:
        print(f"  No bookings found for client {client_id}")
        return
    
    print(f"  Total Bookings: {len(client_bookings)}")
    print(f"\n  Booking Details:")
    
    for booking in client_bookings:
        print(f"    Booking ID: {booking['booking_id']}")
        print(f"    Bus: {booking['bus_id']}, Seat: {booking['seat']}")
        print(f"    Date: {booking['date']}")
        print(f"    Booking Time: {booking['booking_time']}")
        print()


def show_bus_fleet_status(booking_system):
    """Show detailed bus fleet status"""
    print_header("BUS FLEET STATUS")
    
    bus_statuses = booking_system.get_all_buses_status()
    active_buses = [bus for bus in bus_statuses if bus['status'] == 'active']
    merging_buses = [bus for bus in bus_statuses if bus['status'] == 'merging']
    other_buses = [bus for bus in bus_statuses if bus['status'] not in ['active', 'merging']]
    
    print(f"  Active Buses: {len(active_buses)}")
    print(f"  Merging Buses: {len(merging_buses)}")
    print(f"  Other Buses: {len(other_buses)}")
    print(f"  Total Buses: {len(bus_statuses)}")
    
    if active_buses:
        print(f"\n  Active Bus Details:")
        for bus in active_buses[:10]:  # Show first 10 active buses
            available_seats = bus.get('available_seats', '?')
            total_seats = bus.get('total_seats', '?')
            load_factor = bus.get('load_factor', 0)
            
            print(f"    Bus {bus['bus_id']}:")
            print(f"      Route: {bus.get('route', 'Nakuru-Nairobi')}")
            print(f"      Seats: {available_seats}/{total_seats} available")
            print(f"      Load: {load_factor:.1%}")
        
        if len(active_buses) > 10:
            print(f"    ... and {len(active_buses) - 10} more active buses")
    
    if merging_buses:
        print(f"\n  Buses Under Alteration:")
        for bus in merging_buses:
            print(f"    Bus {bus['bus_id']}: {bus.get('alert', 'Bus alteration in process')}")
    
    if other_buses:
        print(f"\n  Other Bus Status:")
        for bus in other_buses[:5]:  # Show first 5 others
            print(f"    Bus {bus['bus_id']}: {bus['status']}")


def make_new_booking_interactive(booking_system):
    """Interactive function to make a new booking"""
    print_header("MAKE NEW BOOKING")
    
    client_id = input("Enter client ID: ").strip()
    if not client_id:
        print("  ✗ Client ID cannot be empty")
        return
    
    travel_date = input("Enter travel date (YYYY-MM-DD): ").strip()
    if not travel_date:
        print("  ✗ Travel date cannot be empty")
        return
    
    # Optional: preferred bus and seat
    preferred_bus = input("Enter preferred bus ID (optional): ").strip()
    preferred_seat = input("Enter preferred seat number (optional): ").strip()
    
    try:
        if preferred_bus:
            preferred_bus = int(preferred_bus)
        if preferred_seat:
            preferred_seat = int(preferred_seat)
    except ValueError:
        print("  ✗ Invalid bus ID or seat number")
        return
    
    print(f"\n  Making booking for client {client_id} on {travel_date}...")
    
    result = booking_system.book_seat_for_client(
        client_id, 
        travel_date,
        preferred_bus if preferred_bus else None,
        preferred_seat if preferred_seat else None
    )
    
    if result['status'] == 'success':
        print(f"  ✓ Booking successful!")
        print(f"  Booking ID: {result['booking_id']}")
        print(f"  Bus: {result['bus_id']}, Seat: {result['seat_number']}")
        print(f"  Date: {result['date']}")
        print(f"  Route: {result['route']}")
    else:
        print(f"  ✗ Booking failed: {result['message']}")


def cancel_booking_interactive(booking_system):
    """Interactive function to cancel a booking"""
    print_header("CANCEL BOOKING")
    
    # Show user's bookings first
    client_id = input("Enter your client ID: ").strip()
    if not client_id:
        print("  ✗ Client ID cannot be empty")
        return
    
    # Get client's bookings
    client_bookings = booking_system.get_client_bookings(client_id)
    
    if not client_bookings:
        print(f"  ✗ No bookings found for client {client_id}")
        return
    
    print(f"\n  Your bookings:")
    for booking in client_bookings:
        print(f"    {booking['booking_id']} - Bus {booking['bus_id']}, "
              f"Seat {booking['seat']}, Date {booking['date']}")
    
    booking_id = input("\nEnter booking ID to cancel: ").strip()
    if not booking_id:
        print("  ✗ Booking ID cannot be empty")
        return
    
    # Verify booking belongs to client
    booking = booking_system.get_booking(booking_id)
    if not booking:
        print(f"  ✗ Booking {booking_id} not found")
        print(f"  Hint: Booking IDs look like 'BK000001', not client IDs")
        return
    
    if booking['client_id'] != client_id:
        print(f"  ✗ This booking belongs to a different client")
        return
    
    # Perform cancellation
    success = booking_system.cancel_booking(booking_id, client_id)
    
    if success:
        print(f"  ✓ Booking {booking_id} successfully cancelled!")
        print(f"  Bus {booking['bus_id']}, Seat {booking['seat']} is now available")
    else:
        print(booking_system.cancel_booking(booking_id, client_id))
        print(f"  ✗ Failed to cancel booking {booking_id}")

def show_system_statistics(booking_system):
    """Show comprehensive system statistics"""
    print_header("SYSTEM STATISTICS")
    
    print(f"  Bookings: {len(booking_system.bookings_db)}")
    print(f"  Visitors: {booking_system.get_total_visitors()}")
    print(f"  System Load: {booking_system.get_overall_load_factor():.2%}")
    
    active_buses = [b for b in booking_system.buses.values() if b.status == 'active']
    merging_buses = [b for b in booking_system.buses.values() if b.status == 'merging']
    print(f"  Active Buses: {len(active_buses)}")
    print(f"  Merging Buses: {len(merging_buses)}")
    print(f"  Total Buses: {len(booking_system.buses)}")
    
    # Calculate seats statistics
    total_seats = sum(bus.total_seats for bus in active_buses)
    booked_seats = sum(
        sum(1 for client in bus.seats.values() if client is not None)
        for bus in active_buses
    )
    
    if total_seats > 0:
        print(f"  Total Seats: {total_seats}")
        print(f"  Booked Seats: {booked_seats}")
        print(f"  Available Seats: {total_seats - booked_seats}")
        print(f"  Utilization: {booked_seats/total_seats:.1%}")
    
    # Show expired reservations
    expired_count = booking_system.release_expired_reservations()
    if expired_count > 0:
        print(f"  Expired Reservations Released: {expired_count}")


def run_admin_operations(booking_system):
    """Run admin operations interactively"""
    print_header("ADMIN OPERATIONS")
    
    username = input("Admin username: ").strip() or "admin"
    password = input("Admin password: ").strip() or "admin123"
    
    if username and password:
        # Test authentication first
        if not booking_system.admin.auth.login(username, password):
            print("  ✗ Authentication failed!")
            return
        
        print(f"  ✓ Authenticated as {username}")
        
        # Show system overview
        overview = booking_system.admin.get_system_overview(username, password)
        if overview:
            print(f"\n  System Overview:")
            print(f"    Total Buses: {overview['total_buses']}")
            print(f"    Active Buses: {overview['active_buses']}")
            print(f"    Merged Buses: {overview['merged_buses']}")
            print(f"    Total Seats: {overview['total_seats']}")
            print(f"    Booked Seats: {overview['booked_seats']}")
            print(f"    Load Factor: {overview['load_factor']:.2%}")
            print(f"    Total Visitors: {overview['total_visitors']}")
            print(f"    Total Bookings: {overview['total_bookings']}")
        
        # Admin menu
        while True:
            print(f"\n  Admin Options:")
            print(f"    1. Merge buses (if load < 20%)")
            print(f"    2. Force release a seat")
            print(f"    3. Add new admin user")
            print(f"    4. Back to main menu")
            
            admin_choice = input("  Select option (1-4): ").strip()
            
            if admin_choice == '1':
                print("  Merging buses...")
                merge_result = booking_system.admin.merge_buses(username, password)
                print(f"  Result: {merge_result['status']}")
                if merge_result['status'] == 'success':
                    print(f"  Merged buses: {merge_result.get('merged_buses', [])}")
                    print(f"  Active buses after merge: {merge_result.get('new_bus_count', 'N/A')}")
            
            elif admin_choice == '2':
                try:
                    bus_id = int(input("  Enter bus ID: ").strip())
                    seat_number = int(input("  Enter seat number: ").strip())
                    success = booking_system.admin.force_release_seat(username, password, bus_id, seat_number)
                    print(f"  Force release: {'✓ Success' if success else '✗ Failed'}")
                except ValueError:
                    print("  ✗ Invalid bus ID or seat number")
            
            elif admin_choice == '3':
                new_username = input("  New admin username: ").strip()
                new_password = input("  New admin password: ").strip()
                if new_username and new_password:
                    success = booking_system.admin.auth.add_admin(new_username, new_password)
                    print(f"  Add admin: {'✓ Success' if success else '✗ Failed (username exists)'}")
                else:
                    print("  ✗ Invalid username or password")
            
            elif admin_choice == '4':
                break
            else:
                print("  ✗ Invalid option")
    else:
        print("  ✗ Invalid credentials")

def show_performance_comparison(booking_system):
    """Show comparative performance analysis"""
    print_header("COMPARATIVE PERFORMANCE ANALYSIS")
    
    total_bookings = len(booking_system.bookings_db)
    disk_stats = booking_system.logger.get_stats()
    
    print(f"  Total Bookings Processed: {total_bookings}")
    print(f"\n  Disk I/O Efficiency:")
    print(f"    Actual Writes: {disk_stats['total_writes']}")
    print(f"    Without Batching (estimated): {total_bookings}")
    print(f"    Reduction: {(1 - disk_stats['total_writes']/total_bookings)*100:.1f}%")
    
    print(f"\n  Write Time Efficiency:")
    estimated_without_batching = total_bookings * 0.005  # 5ms per write
    actual_time = disk_stats['total_write_time']
    print(f"    Actual Time: {actual_time:.4f}s")
    print(f"    Without Batching (estimated): {estimated_without_batching:.4f}s")
    print(f"    Time Saved: {estimated_without_batching - actual_time:.4f}s")
    print(f"    Improvement: {(1 - actual_time/estimated_without_batching)*100:.1f}%")
    
def show_performance_analysis(booking_system):
    """Show detailed performance analysis"""
    print_header("PERFORMANCE ANALYSIS")
    
    # This would typically show historical performance data
    # For now, we'll show current system performance metrics
    
    print(f"  Current System Metrics:")
    print(f"    Total Bookings: {len(booking_system.bookings_db)}")
    print(f"    Total Visitors: {booking_system.get_total_visitors()}")
    print(f"    System Load: {booking_system.get_overall_load_factor():.2%}")
    print(f"    Active Buses: {len([b for b in booking_system.buses.values() if b.status == 'active'])}")
    
    # Show disk I/O statistics
    disk_stats = booking_system.logger.get_stats()
    print(f"\n  Disk I/O Performance:")
    print(f"    Total Writes: {disk_stats['total_writes']}")
    print(f"    Total Write Time: {disk_stats['total_write_time']:.4f}s")
    print(f"    Average Write Time: {disk_stats['avg_write_time']:.6f}s")
    print(f"    Write Method: {disk_stats['write_method']}")
    
    print(f"\n  Performance Benefits of Current Approach:")
    print(f"    • Batched writes reduce disk I/O by ~90%")
    print(f"    • Async logging prevents blocking operations")
    print(f"    • Optimized locking strategy minimizes contention")
    print(f"    • Efficient memory usage with dictionary-based storage")


def interactive_menu(booking_system):
    """Interactive menu for user exploration"""
    while True:
        print_section("INTERACTIVE MENU")
        print("1. Show all booked clients")
        print("2. Search client details") 
        print("3. Show bus fleet status")
        print("4. Make a new booking")
        print("5. Cancel a booking")
        print("6. Show system statistics")
        print("7. Run admin operations")
        print("8. Performance analysis")
        print("9. Exit")
        
        choice = input("\nEnter your choice (1-9): ").strip()
        
        if choice == '1':
            show_all_clients(booking_system)
            
        elif choice == '2':
            client_id = input("Enter client ID: ").strip()
            if client_id:
                show_client_details(booking_system, client_id)
            else:
                print("  ✗ Invalid client ID")
                
        elif choice == '3':
            show_bus_fleet_status(booking_system)
                    
        elif choice == '4':
            make_new_booking_interactive(booking_system)
            
        elif choice == '5':
            cancel_booking_interactive(booking_system)
                
        elif choice == '6':
            show_system_statistics(booking_system)
                
        elif choice == '7':
            run_admin_operations(booking_system)
            
        elif choice == '8':
            show_performance_analysis(booking_system)
                
        elif choice == '9':
            print("  Exiting interactive menu...")
            break
            
        else:
            print("  ✗ Invalid choice. Please try again.")
        
        input("\nPress Enter to continue...")


def main():
    """Main entry point"""
    try:
        # Validate configuration first
        config_errors = validate_config()
        if config_errors:
            print("Configuration errors found:")
            for error in config_errors:
                print(f"  - {error}")
            return
        
        # Print configuration summary
        print_config_summary()
        # Run comprehensive simulation
        booking_system = run_comprehensive_simulation()
        
        # Enter interactive mode
        interactive_menu(booking_system)
        
        # Cleanup
        print_header("SYSTEM SHUTDOWN")
        booking_system.shutdown()
        print("  ✓ System shutdown complete")
        print("  ✓ All resources released")
        print("  ✓ Logs archived to disk")
        
        print_section("SIMULATION COMPLETE")
        
    except KeyboardInterrupt:
        print("\n\nSimulation interrupted by user.")
        sys.exit(1)
    except Exception as e:
        print(f"\n\nError during simulation: {e}")
        import traceback
        traceback.print_exc()
        sys.exit(1)


if __name__ == "__main__":
    main()