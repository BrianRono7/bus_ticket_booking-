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


# Global progress callback for Flask integration
_progress_callback = None

def set_progress_callback(callback):
    """Set a callback function for progress updates"""
    global _progress_callback
    _progress_callback = callback

def log_progress(phase, progress, message):
    """Log progress to callback or console"""
    if _progress_callback:
        _progress_callback(phase, progress, message)
    print(f"[{progress}%] {phase}: {message}")


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
    
    log_progress("Initialization", 0, "Starting comprehensive simulation")
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

    log_progress("Initialization", 5, "System initialized")
    
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
    
    # PHASE 1: Basic Booking Approaches
    log_progress("Phase 1", 10, "Testing basic booking approaches")
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
    
    log_progress("Phase 1", 20, f"Iterative: {iter_success}/{len(iterative_results)} successful")
    
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
    
    log_progress("Phase 1", 30, f"Threading: {thread_success}/{len(thread_results)} successful")
    
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
    
    log_progress("Phase 1", 35, "Phase 1 completed")
    
    # PHASE 2: Multiple Days Booking & Advanced Patterns
    log_progress("Phase 2", 40, "Simulating realistic booking patterns")
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
    
    log_progress("Phase 2", 50, f"Created {len(all_booking_ids)} bookings across 7 days")
    
    print(f"\nSimulating realistic cancellations (10% rate)...")
    cancelled = simulator.simulate_cancellations(all_booking_ids, cancel_rate=0.1)
    print(f"  Cancelled: {cancelled} bookings")
    
    log_progress("Phase 2", 55, f"Cancelled {cancelled} bookings")
    
    # PHASE 3: Stress Testing with Auto-scaling
    log_progress("Phase 3", 60, "Starting stress test")
    print_header("PHASE 3: STRESS TESTING & AUTO-SCALING")
    
    print(f"Current system state before stress test:")
    print(f"  Active Buses: {len([b for b in booking_system.buses.values() if b.status == 'active'])}")
    print(f"  Load Factor: {booking_system.get_overall_load_factor():.2%}")
    
    load_gen = LoadGenerator(booking_system)
    
    # Burst load to trigger auto-scaling
    print_header("Burst Load Test (Trigger Auto-scaling)", 50)
    start_time = time.time()
    burst_clients = load_gen.generate_burst_load(150, dates_30_days)
    burst_results = load_gen.wait_for_clients(burst_clients)
    burst_time = time.time() - start_time
    burst_success = sum(1 for r in burst_results if r['status'] == 'success')
    
    print(f"  Clients: 150 simultaneous")
    print(f"  Time: {burst_time:.3f}s")
    print(f"  Success: {burst_success}/{len(burst_results)} ({burst_success/len(burst_results)*100:.1f}%)")
    print(f"  Throughput: {len(burst_results)/burst_time:.1f} bookings/sec")
    print(f"  Active Buses After: {len([b for b in booking_system.buses.values() if b.status == 'active'])}")
    print(f"  Load Factor After: {booking_system.get_overall_load_factor():.2%}")
    
    log_progress("Phase 3", 70, f"Stress test: {burst_success}/{len(burst_results)} successful")
    
    # PHASE 4: System Operations & Admin Functions
    log_progress("Phase 4", 75, "Running admin operations")
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
            log_progress("Phase 4", 80, f"Merged {len(merge_result.get('merged_buses', []))} buses")
    else:
        print(f"  Load factor ({current_load:.2%}) above minimum threshold - skipping merge")
        log_progress("Phase 4", 80, "Skipped bus merge - load above threshold")
    
    # System Overview
    overview = booking_system.admin.get_system_overview("admin", "admin123")
    if overview:
        print(f"  System Overview:")
        print(f"    Total Buses: {overview['total_buses']}")
        print(f"    Active Buses: {overview['active_buses']}")
        print(f"    Total Bookings: {overview['total_bookings']}")
        print(f"    Total Visitors: {overview['total_visitors']}")
    
    # PHASE 5: Performance Analysis & Resource Monitoring
    log_progress("Phase 5", 85, "Analyzing performance metrics")
    print_header("PHASE 5: PERFORMANCE ANALYSIS & RESOURCE MONITORING")
    
    monitor.stop_monitoring()
    perf_report = monitor.get_performance_report()
    disk_stats = booking_system.logger.get_stats()
    
    print(f"CPU & Memory Usage:")
    print(f"  Max CPU: {perf_report['max_cpu_usage']:.2f}%")
    print(f"  Avg CPU: {perf_report['avg_cpu_usage']:.2f}%")
    print(f"  Max Physical Memory: {perf_report['max_physical_memory_mb']:.2f} MB")
    
    print(f"\nI/O Performance:")
    print(f"  Disk Writes: {disk_stats['total_writes']}")
    print(f"  Total Write Time: {disk_stats['total_write_time']:.4f}s")
    print(f"  Throughput: {len(booking_system.bookings_db)/perf_report['total_monitoring_time']:.1f} bookings/sec")
    
    log_progress("Phase 5", 95, "Performance analysis complete")
    
    # Final System State
    log_progress("Complete", 100, "Simulation completed successfully")
    print_header("FINAL SYSTEM STATE")
    print(f"  Total Bookings: {len(booking_system.bookings_db)}")
    print(f"  Overall Load Factor: {booking_system.get_overall_load_factor():.2%}")
    print(f"  Active Buses: {len([b for b in booking_system.buses.values() if b.status == 'active'])}")
    print(f"  Total Visitors: {booking_system.get_total_visitors()}")
    
    return booking_system


# ... (keep all the other functions from the original main.py)

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