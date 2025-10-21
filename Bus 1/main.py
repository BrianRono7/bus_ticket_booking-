"""
Comprehensive Bus Booking System Simulation
Demonstrates threading, concurrency, and system stress testing
"""

import time
import random
from datetime import datetime, timedelta
from typing import List, Dict, Tuple
from concurrent.futures import ThreadPoolExecutor, as_completed

from booking_system import BusBookingSystem
from clients import Client, LoadGenerator, ClientSimulator
from monitor import PerformanceMonitor
from config import (
    INITIAL_BUS_COUNT, MAX_BUS_COUNT, LOAD_THRESHOLD_HIGH,
    LOAD_THRESHOLD_LOW, SEAT_RESERVATION_TIMEOUT
)

# Global simulation state for progress tracking
simulation_progress = {
    'phase': '',
    'progress': 0,
    'logs': [],
    'start_time': 0
}

def log_progress(phase: str, progress: int, message: str):
    """Log simulation progress with timestamp"""
    elapsed = time.time() - simulation_progress['start_time']
    simulation_progress['phase'] = phase
    simulation_progress['progress'] = progress
    simulation_progress['logs'].append({
        'time': elapsed,
        'phase': phase,
        'message': message
    })
    print(f"[{elapsed:.2f}s] {phase} ({progress}%): {message}")


def generate_test_dates(days: int = 7) -> List[str]:
    """Generate list of test dates"""
    today = datetime.now().date()
    return [(today + timedelta(days=i)).strftime('%Y-%m-%d') for i in range(days)]


def run_phase1_basic_booking(system: BusBookingSystem, dates: List[str]) -> Dict:
    """Phase 1: Basic Booking Operations"""
    log_progress("Phase 1: Basic Booking", 10, "Starting basic booking tests...")
    results = {
        'iterative': {'success': 0, 'failed': 0, 'time': 0},
        'threading': {'success': 0, 'failed': 0, 'time': 0},
        'threadpool': {'success': 0, 'failed': 0, 'time': 0}
    }
    
    # Test 1: Iterative booking
    log_progress("Phase 1: Basic Booking", 12, "Running iterative booking test...")
    start_time = time.time()
    for i in range(50):
        date = random.choice(dates)
        # Get available buses and seats
        available_buses = [b for b in system.buses.values() if b.status == 'active']
        if available_buses:
            bus = random.choice(available_buses)
            available_seats = bus.get_available_seats(date)
            if available_seats:
                seat = random.choice(available_seats)
                result = system.book_seat_for_client(
                    f"iter_client_{i}", date, bus.bus_id, seat
                )
                if result['status'] == 'success':
                    results['iterative']['success'] += 1
                else:
                    results['iterative']['failed'] += 1
    results['iterative']['time'] = time.time() - start_time
    log_progress("Phase 1: Basic Booking", 15, 
                f"Iterative: {results['iterative']['success']} bookings in {results['iterative']['time']:.2f}s")
    
    # Test 2: Threading
    log_progress("Phase 1: Basic Booking", 17, "Running threading test...")
    start_time = time.time()
    clients = []
    for i in range(50):
        date = random.choice(dates)
        available_buses = [b for b in system.buses.values() if b.status == 'active']
        if available_buses:
            bus = random.choice(available_buses)
            available_seats = bus.get_available_seats(date)
            if available_seats:
                seat = random.choice(available_seats)
                client = Client(f"thread_client_{i}", system, date, 
                              booking_delay=0.01, preferred_bus=bus.bus_id, 
                              preferred_seat=seat)
                client.start()
                clients.append(client)
    
    for client in clients:
        client.join()
        if client.result and client.result['status'] == 'success':
            results['threading']['success'] += 1
        else:
            results['threading']['failed'] += 1
    results['threading']['time'] = time.time() - start_time
    log_progress("Phase 1: Basic Booking", 20, 
                f"Threading: {results['threading']['success']} bookings in {results['threading']['time']:.2f}s")
    
    # Test 3: ThreadPool
    log_progress("Phase 1: Basic Booking", 22, "Running threadpool test...")
    start_time = time.time()
    
    def book_with_pool(client_id: str, date: str, bus_id: int, seat: int):
        return system.book_seat_for_client(client_id, date, bus_id, seat)
    
    with ThreadPoolExecutor(max_workers=10) as executor:
        futures = []
        for i in range(50):
            date = random.choice(dates)
            available_buses = [b for b in system.buses.values() if b.status == 'active']
            if available_buses:
                bus = random.choice(available_buses)
                available_seats = bus.get_available_seats(date)
                if available_seats:
                    seat = random.choice(available_seats)
                    future = executor.submit(book_with_pool, f"pool_client_{i}", 
                                           date, bus.bus_id, seat)
                    futures.append(future)
        
        for future in as_completed(futures):
            try:
                result = future.result()
                if result['status'] == 'success':
                    results['threadpool']['success'] += 1
                else:
                    results['threadpool']['failed'] += 1
            except Exception:
                results['threadpool']['failed'] += 1
    
    results['threadpool']['time'] = time.time() - start_time
    log_progress("Phase 1: Basic Booking", 25, 
                f"ThreadPool: {results['threadpool']['success']} bookings in {results['threadpool']['time']:.2f}s")
    
    return results


def run_phase2_realistic_patterns(system: BusBookingSystem, dates: List[str]) -> Dict:
    """Phase 2: Realistic Booking Patterns"""
    log_progress("Phase 2: Realistic Patterns", 30, "Starting realistic booking patterns...")
    results = {
        'multi_day_bookings': 0,
        'cancellations': 0,
        'rebookings': 0,
        'peak_load': 0
    }
    
    # Multi-day bookings
    log_progress("Phase 2: Realistic Patterns", 32, "Simulating multi-day bookings...")
    clients = []
    for i in range(30):
        # Each client books 2-3 different dates
        num_bookings = random.randint(2, 3)
        client_dates = random.sample(dates, min(num_bookings, len(dates)))
        
        for date in client_dates:
            available_buses = [b for b in system.buses.values() if b.status == 'active']
            if available_buses:
                bus = random.choice(available_buses)
                available_seats = bus.get_available_seats(date)
                if available_seats:
                    seat = random.choice(available_seats)
                    client = Client(f"multi_client_{i}_{date}", system, date,
                                  booking_delay=0.01, preferred_bus=bus.bus_id,
                                  preferred_seat=seat)
                    client.start()
                    clients.append(client)
    
    for client in clients:
        client.join()
        if client.result and client.result['status'] == 'success':
            results['multi_day_bookings'] += 1
    
    log_progress("Phase 2: Realistic Patterns", 35, 
                f"Multi-day bookings: {results['multi_day_bookings']} successful")
    
    # Simulate cancellations
    log_progress("Phase 2: Realistic Patterns", 37, "Simulating cancellations...")
    all_bookings = list(system.bookings_db.keys())
    cancel_count = min(20, len(all_bookings))
    bookings_to_cancel = random.sample(all_bookings, cancel_count)
    
    for booking_id in bookings_to_cancel:
        booking = system.bookings_db.get(booking_id)
        if booking:
            result = system.cancel_booking(booking_id, booking['client_id'])
            if result.get('success'):
                results['cancellations'] += 1
    
    log_progress("Phase 2: Realistic Patterns", 40, 
                f"Cancellations: {results['cancellations']} processed")
    
    # Rebooking after cancellations
    log_progress("Phase 2: Realistic Patterns", 42, "Simulating rebookings...")
    for i in range(results['cancellations']):
        date = random.choice(dates)
        available_buses = [b for b in system.buses.values() if b.status == 'active']
        if available_buses:
            bus = random.choice(available_buses)
            available_seats = bus.get_available_seats(date)
            if available_seats:
                seat = random.choice(available_seats)
                result = system.book_seat_for_client(
                    f"rebook_client_{i}", date, bus.bus_id, seat
                )
                if result['status'] == 'success':
                    results['rebookings'] += 1
    
    log_progress("Phase 2: Realistic Patterns", 45, 
                f"Rebookings: {results['rebookings']} successful")
    
    # Calculate peak load
    results['peak_load'] = system.get_overall_load_factor()
    log_progress("Phase 2: Realistic Patterns", 48, 
                f"Peak load factor: {results['peak_load']:.2%}")
    
    return results


def run_phase3_stress_testing(system: BusBookingSystem, dates: List[str]) -> Dict:
    """Phase 3: System Stress Testing"""
    log_progress("Phase 3: Stress Testing", 50, "Starting stress testing...")
    results = {
        'burst_bookings': 0,
        'concurrent_conflicts': 0,
        'auto_scaling_triggered': 0,
        'max_load_reached': 0
    }
    
    initial_bus_count = len([b for b in system.buses.values() if b.status == 'active'])
    
    # Burst load test
    log_progress("Phase 3: Stress Testing", 52, "Executing burst load test...")
    clients = []
    for i in range(100):
        date = random.choice(dates)
        available_buses = [b for b in system.buses.values() if b.status == 'active']
        if available_buses:
            bus = random.choice(available_buses)
            available_seats = bus.get_available_seats(date)
            if available_seats:
                seat = random.choice(available_seats)
                client = Client(f"burst_client_{i}", system, date,
                              booking_delay=0.001, preferred_bus=bus.bus_id,
                              preferred_seat=seat)
                client.start()
                clients.append(client)
    
    for client in clients:
        client.join()
        if client.result and client.result['status'] == 'success':
            results['burst_bookings'] += 1
    
    log_progress("Phase 3: Stress Testing", 58, 
                f"Burst test: {results['burst_bookings']} bookings completed")
    
    # Check auto-scaling
    final_bus_count = len([b for b in system.buses.values() if b.status == 'active'])
    results['auto_scaling_triggered'] = final_bus_count - initial_bus_count
    
    if results['auto_scaling_triggered'] > 0:
        log_progress("Phase 3: Stress Testing", 62, 
                    f"Auto-scaling: {results['auto_scaling_triggered']} new buses added")
    
    # Concurrent conflicts test (same seat, same date)
    log_progress("Phase 3: Stress Testing", 65, "Testing concurrent conflict resolution...")
    if system.buses:
        test_bus = list(system.buses.values())[0]
        test_date = dates[0]
        test_seat = 1
        
        # Release seat if occupied
        test_bus.release_seat(test_seat, test_date)
        
        # Try to book same seat concurrently
        conflict_clients = []
        for i in range(10):
            client = Client(f"conflict_client_{i}", system, test_date,
                          booking_delay=0.001, preferred_bus=test_bus.bus_id,
                          preferred_seat=test_seat)
            client.start()
            conflict_clients.append(client)
        
        successful = 0
        for client in conflict_clients:
            client.join()
            if client.result and client.result['status'] == 'success':
                successful += 1
        
        results['concurrent_conflicts'] = 10 - successful
        log_progress("Phase 3: Stress Testing", 68, 
                    f"Conflict test: {successful} succeeded, {results['concurrent_conflicts']} prevented")
    
    # Max load test
    results['max_load_reached'] = system.get_overall_load_factor()
    log_progress("Phase 3: Stress Testing", 70, 
                f"Maximum load achieved: {results['max_load_reached']:.2%}")
    
    return results


def run_phase4_admin_operations(system: BusBookingSystem) -> Dict:
    """Phase 4: Admin Operations Testing"""
    log_progress("Phase 4: Admin Operations", 75, "Testing admin operations...")
    results = {
        'system_overview': None,
        'bus_merge_attempts': 0,
        'buses_merged': 0
    }
    
    # Get system overview
    log_progress("Phase 4: Admin Operations", 77, "Fetching system overview...")
    overview = system.admin.get_system_overview('admin', 'admin123')
    results['system_overview'] = overview
    log_progress("Phase 4: Admin Operations", 80, 
                f"System overview: {overview['total_bookings']} bookings, "
                f"{overview['active_buses']} active buses")
    
    # Try bus merging (if load is low)
    log_progress("Phase 4: Admin Operations", 82, "Attempting bus merging...")
    merge_result = system.admin.merge_buses('admin', 'admin123')
    results['bus_merge_attempts'] = 1
    
    if merge_result.get('status') == 'success':
        results['buses_merged'] = merge_result.get('merged_count', 0)
        log_progress("Phase 4: Admin Operations", 85, 
                    f"Bus merging: {results['buses_merged']} buses merged")
    else:
        log_progress("Phase 4: Admin Operations", 85, 
                    f"Bus merging: {merge_result.get('message', 'No action taken')}")
    
    return results


def run_phase5_performance_analysis(system: BusBookingSystem, monitor: PerformanceMonitor) -> Dict:
    """Phase 5: Performance Analysis"""
    log_progress("Phase 5: Performance Analysis", 88, "Analyzing system performance...")
    results = {
        'performance_report': None,
        'disk_stats': None,
        'load_distribution': None
    }
    
    # Get performance metrics
    log_progress("Phase 5: Performance Analysis", 90, "Collecting performance metrics...")
    try:
        perf_report = monitor.get_performance_report()
        results['performance_report'] = perf_report
        log_progress("Phase 5: Performance Analysis", 92, 
                    f"CPU: {perf_report.get('cpu_percent', 0):.1f}%, "
                    f"Memory: {perf_report.get('memory_percent', 0):.1f}%")
    except Exception as e:
        log_progress("Phase 5: Performance Analysis", 92, f"Performance metrics unavailable: {e}")
    
    # Get disk stats
    log_progress("Phase 5: Performance Analysis", 94, "Collecting disk I/O statistics...")
    disk_stats = system.logger.get_stats()
    results['disk_stats'] = disk_stats
    log_progress("Phase 5: Performance Analysis", 96, 
                f"Disk: {disk_stats.get('total_logs', 0)} logs, "
                f"{disk_stats.get('total_flushes', 0)} flushes")
    
    # Get load distribution across dates
    log_progress("Phase 5: Performance Analysis", 97, "Analyzing load distribution...")
    load_distribution = system.get_daily_load_factors(days=7)
    results['load_distribution'] = load_distribution
    avg_load = sum(load_distribution.values()) / len(load_distribution) if load_distribution else 0
    log_progress("Phase 5: Performance Analysis", 98, 
                f"Average daily load: {avg_load:.2%}")
    
    return results


def run_comprehensive_simulation() -> BusBookingSystem:
    """Run complete simulation with all phases"""
    simulation_progress['start_time'] = time.time()
    simulation_progress['logs'] = []
    
    log_progress("Initialization", 0, "Initializing bus booking system...")
    
    # Initialize system
    system = BusBookingSystem(
        initial_buses=INITIAL_BUS_COUNT,
        max_buses=MAX_BUS_COUNT,
        load_threshold_high=LOAD_THRESHOLD_HIGH,
        load_threshold_low=LOAD_THRESHOLD_LOW,
        seat_lock_timeout=SEAT_RESERVATION_TIMEOUT
    )
    
    # Initialize monitor
    monitor = PerformanceMonitor(system)
    monitor.start_monitoring(interval=5)
    
    log_progress("Initialization", 5, f"System initialized with {INITIAL_BUS_COUNT} buses")
    
    # Generate test dates
    dates = generate_test_dates(days=7)
    log_progress("Initialization", 8, f"Generated {len(dates)} test dates")
    
    try:
        # Phase 1: Basic Booking
        phase1_results = run_phase1_basic_booking(system, dates)
        
        # Phase 2: Realistic Patterns
        phase2_results = run_phase2_realistic_patterns(system, dates)
        
        # Phase 3: Stress Testing
        phase3_results = run_phase3_stress_testing(system, dates)
        
        # Phase 4: Admin Operations
        phase4_results = run_phase4_admin_operations(system)
        
        # Phase 5: Performance Analysis
        phase5_results = run_phase5_performance_analysis(system, monitor)
        
        # Final summary
        log_progress("Completed", 100, "Simulation completed successfully!")
        
        total_time = time.time() - simulation_progress['start_time']
        log_progress("Completed", 100, 
                    f"Total execution time: {total_time:.2f}s, "
                    f"Total bookings: {len(system.bookings_db)}, "
                    f"Total visitors: {system.get_total_visitors()}")
        
    except Exception as e:
        log_progress("Error", 0, f"Simulation failed: {str(e)}")
        raise
    finally:
        # Cleanup
        monitor.stop_monitoring()
    
    return system


def print_simulation_summary(system: BusBookingSystem):
    """Print comprehensive simulation summary"""
    print("\n" + "="*80)
    print("SIMULATION SUMMARY")
    print("="*80)
    
    print(f"\nTotal Visitors: {system.get_total_visitors()}")
    print(f"Total Bookings: {len(system.bookings_db)}")
    print(f"Active Buses: {len([b for b in system.buses.values() if b.status == 'active'])}")
    print(f"Overall Load Factor: {system.get_overall_load_factor():.2%}")
    
    print("\nDaily Load Distribution:")
    daily_loads = system.get_daily_load_factors(days=7)
    for date, load in sorted(daily_loads.items()):
        print(f"  {date}: {load:.2%}")
    
    print("\n" + "="*80)


if __name__ == "__main__":
    print("Starting Comprehensive Bus Booking System Simulation...")
    print("This will test threading, concurrency, and system performance.\n")
    
    system = run_comprehensive_simulation()
    print_simulation_summary(system)
    
    print("\nSimulation complete. Check logs for detailed information.")