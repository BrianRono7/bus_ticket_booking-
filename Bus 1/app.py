from flask import Flask, render_template, request, jsonify, session, redirect, url_for
from datetime import datetime, timedelta
from functools import wraps
import secrets
import threading
import time
from main import run_comprehensive_simulation

from booking_system import BusBookingSystem
from monitor import PerformanceMonitor
from config import (
    INITIAL_BUS_COUNT, MAX_BUS_COUNT, LOAD_THRESHOLD_HIGH,
    LOAD_THRESHOLD_LOW, SEAT_RESERVATION_TIMEOUT, MONITOR_INTERVAL
)

app = Flask(__name__)
app.secret_key = secrets.token_hex(32)

# Initialize booking system
booking_system = BusBookingSystem(
    initial_buses=INITIAL_BUS_COUNT,
    max_buses=MAX_BUS_COUNT,
    load_threshold_high=LOAD_THRESHOLD_HIGH,
    load_threshold_low=LOAD_THRESHOLD_LOW,
    seat_lock_timeout=SEAT_RESERVATION_TIMEOUT
)

# Initialize performance monitor
monitor = PerformanceMonitor(booking_system)
monitor.start_monitoring(interval=MONITOR_INTERVAL)

# Simulation state tracking
simulation_state = {
    'running': False,
    'progress': 0,
    'phase': '',
    'results': {},
    'start_time': None,
    'end_time': None,
    'logs': []
}
simulation_lock = threading.Lock()


def login_required(f):
    """Decorator for routes that require login"""
    @wraps(f)
    def decorated_function(*args, **kwargs):
        if 'client_id' not in session:
            return redirect(url_for('login'))
        return f(*args, **kwargs)
    return decorated_function


def admin_required(f):
    """Decorator for routes that require admin access"""
    @wraps(f)
    def decorated_function(*args, **kwargs):
        if 'admin_user' not in session:
            return redirect(url_for('admin_login'))
        return f(*args, **kwargs)
    return decorated_function


# ============================================================================
# PUBLIC ROUTES
# ============================================================================

@app.route('/')
def index():
    """Landing page"""
    stats = {
        'total_bookings': len(booking_system.db.get_all_bookings()),
        'active_buses': len([b for b in booking_system.get_all_buses() if b['status'] == 'active']),
        'available_seats': sum(bus['total_seats'] for bus in [b for b in booking_system.get_all_buses() if b['status'] == 'active']) - len(booking_system.db.get_all_bookings()),
    }
    return render_template('index.html', stats=stats)


@app.route('/login', methods=['GET', 'POST'])
def login():
    """User login"""
    if request.method == 'POST':
        client_id = request.form.get('client_id', '').strip()
        if client_id:
            session['client_id'] = client_id
            return redirect(url_for('dashboard'))
    return render_template('login.html')


@app.route('/logout')
def logout():
    """User logout"""
    session.pop('client_id', None)
    return redirect(url_for('index'))


# ============================================================================
# USER ROUTES
# ============================================================================

@app.route('/dashboard')
@login_required
def dashboard():
    """User dashboard"""
    client_id = session['client_id']
    bookings = booking_system.db.get_client_bookings(client_id)
    
    # Get system stats
    stats = {
        'my_bookings': len(bookings),
        'system_load': booking_system.get_overall_load_factor(),
        'active_buses': len([b for b in booking_system.buses.values() if b.status == 'active'])
    }
    
    return render_template('dashboard.html', bookings=bookings, stats=stats, client_id=client_id)


@app.route('/book', methods=['GET', 'POST'])
@login_required
def book():
    """Book a seat"""
    if request.method == 'POST':
        data = request.get_json()
        client_id = session['client_id']
        travel_date = data.get('date')
        preferred_bus = data.get('bus_id')
        preferred_seat = data.get('seat_number')
        
        existing_bookings = booking_system.db.get_client_bookings(client_id)
        bookings_on_date = [b for b in existing_bookings if b['date'] == travel_date]
        if len(bookings_on_date) >= 2:
            return jsonify({
                'status': 'error',
                'message': f'You already have 2 bookings on {travel_date}. Maximum 2 bookings per day allowed.'
            }), 400
            
        result = booking_system.book_seat_for_client(
            client_id,
            travel_date,
            preferred_bus,
            preferred_seat
        )

        
        return jsonify(result)
    
    # GET request - show booking form
    today = datetime.now().date()
    dates = [(today + timedelta(days=i)).strftime('%Y-%m-%d') for i in range(30)]
    
    return render_template('book.html', dates=dates)


@app.route('/api/buses/<date>')
@login_required
def get_buses(date: str):
    """Get all available buses for a given date (memory + DB safe)"""
    buses = []

    try:
        # Synchronize memory with database
        booking_system._load_from_database()

        #  Get list of all active buses from DB (authoritative source) 
        db_buses = booking_system.db.get_all_buses()
        db_buses = [b for b in db_buses if b['status'] == 'active']

        #  Build response combining memory + DB seat data 
        for bus_record in db_buses:
            bus_id = bus_record['bus_id']
            route = bus_record.get('route', 'Unknown Route')
            total_seats = bus_record.get('total_seats', 0)

            #  From memory (if loaded) 
            bus = booking_system.buses.get(bus_id)

            # Prefer in-memory seats if available; else fall back to DB
            if bus and date in bus.seats_by_date:
                available_seats = len(bus.get_available_seats(date))
                load_factor = bus.get_load_factor_for_date(date)
            else:
                #  From DB fallback 
                try:
                    seat_map = booking_system.db.get_bus_seats(bus_id, date)
                    booked = sum(1 for seat, client in seat_map.items() if client)
                    available_seats = total_seats - booked
                    load_factor = booked / total_seats if total_seats > 0 else 0.0
                except Exception as e:
                    booking_system.logger.log(
                        f"Warning: DB seat load failed for bus {bus_id} on {date}: {e}"
                    )
                    available_seats = total_seats
                    load_factor = 0.0

            buses.append({
                'bus_id': bus_id,
                'route': route,
                'total_seats': total_seats,
                'available_seats': available_seats,
                'load_factor': round(load_factor, 3),
                'load_percentage': round(load_factor * 100, 2),
            })

        # Return clean JSON summary 
        return jsonify({
            'buses': buses,
            'date': date,
            'total_available_seats': sum(bus['available_seats'] for bus in buses)
        })

    except Exception as e:
        booking_system.logger.log(f"Error in get_buses({date}): {e}")
        return jsonify({'error': str(e), 'date': date}), 500


@app.route('/api/seats/<int:bus_id>/<date>')
# @admin_required
# @login_required
def get_seats(bus_id: int, date: str):
    """Get full seat map for a specific bus and date (memory + DB safe)"""
    try:
        # --- Step 1: Ensure DB sync before access ---
        booking_system._load_from_database()

        # --- Step 2: Try to locate bus in memory or DB ---
        bus = booking_system.buses.get(bus_id)
        if not bus:
            # Fallback to DB
            bus_record = booking_system.db.get_bus_by_id(bus_id)
            if not bus_record:
                return jsonify({'error': f'Bus {bus_id} not found'}), 404
            
            # Create lightweight temporary object if missing from memory
            class TempBus:
                def __init__(self, record):
                    self.bus_id = record['bus_id']
                    self.route = record.get('route', 'Unknown Route')
                    self.total_seats = record.get('total_seats', 0)
                    self.status = record.get('status', 'inactive')
            
            bus = TempBus(bus_record)

        # --- Step 3: Retrieve seat map (prefer memory, fallback to DB) ---
        seat_map_data = {}

        if hasattr(bus, "seats_by_date") and date in bus.seats_by_date:
            # Prefer in-memory seat map
            seat_map_data = bus.seats_by_date[date]
        else:
            # Fallback to DB
            try:
                seat_map_data = booking_system.db.get_bus_seats(bus.bus_id, date)
            except Exception as e:
                booking_system.logger.log(f"DB seat map retrieval failed for Bus {bus_id} on {date}: {e}")
                seat_map_data = {}

        # --- Step 4: Build clean seat list ---
        seat_map = []
        booked_count = 0
        total_seats = getattr(bus, "total_seats", 0) or 0

        for seat_num in range(1, total_seats + 1):
            client_id = seat_map_data.get(seat_num)
            is_available = client_id is None
            if not is_available:
                booked_count += 1

            seat_map.append({
                'number': seat_num,
                'available': is_available,
                'client_id': client_id if client_id else None
            })

        # --- Step 5: Compute metrics safely ---
        available_seats = total_seats - booked_count
        load_factor = booked_count / total_seats if total_seats > 0 else 0.0

        return jsonify({
            'seats': seat_map,
            'bus_id': bus.bus_id,
            'route': getattr(bus, "route", "Unknown Route"),
            'date': date,
            'total_seats': total_seats,
            'available_seats': available_seats,
            'booked_seats': booked_count,
            'load_factor': round(load_factor, 3),
            'load_percentage': round(load_factor * 100, 2)
        })

    except Exception as e:
        booking_system.logger.log(f"Error in get_seats(bus_id={bus_id}, date={date}): {e}")
        return jsonify({'error': str(e), 'bus_id': bus_id, 'date': date}), 500


@app.route('/cancel/<booking_id>', methods=['POST'])
@login_required
def cancel_booking(booking_id):
    """Cancel a booking"""
    client_id = session['client_id']
    result = booking_system.cancel_booking(booking_id, client_id)

    return jsonify(result)


@app.route('/my-bookings')
@login_required
def my_bookings():
    """View all user bookings"""
    client_id = session['client_id']
    bookings = booking_system.db.get_client_bookings(client_id)
    
    return render_template('my_bookings.html', bookings=bookings, client_id=client_id)


# ============================================================================
# ADMIN ROUTES
# ============================================================================

@app.route('/admin/login', methods=['GET', 'POST'])
def admin_login():
    """Admin login"""
    if request.method == 'POST':
        username = request.form.get('username', '').strip()
        password = request.form.get('password', '').strip()
        
        if booking_system.admin.auth.login(username, password):
            session['admin_user'] = username
            return redirect(url_for('admin_dashboard'))
        else:
            return render_template('admin_login.html', error='Invalid credentials')
    
    return render_template('admin_login.html')


@app.route('/admin/logout')
def admin_logout():
    """Admin logout"""
    session.pop('admin_user', None)
    return redirect(url_for('index'))


@app.route('/admin/dashboard')
@admin_required
def admin_dashboard():
    """Admin dashboard"""
    username = session['admin_user']
    overview = booking_system.admin.get_system_overview(username, 'admin123')
    
    # Get performance metrics
    perf_report = monitor.get_performance_report()
    disk_stats = booking_system.logger.get_stats()

    # Handle case where overview might be None (authentication failed)
    if overview is None:
        # You might want to redirect or show an error here
        # For now, we'll create a safe default
        overview = {
            "total_seats": 0,
            "booked_seats": 0
        }
    
    # Calculate safe width for progress bar
    if overview["total_seats"] > 0:
        utilization_percentage = (overview["booked_seats"] / overview["total_seats"]) * 100
        # Clamp the percentage between 0 and 100
        safe_width = max(0, min(100, utilization_percentage))
    else:
        safe_width = 0
    
    return render_template('admin_dashboard.html', 
                         overview=overview,
                         safe_width=safe_width, 
                         perf=perf_report,
                         disk=disk_stats,
                         username=username)

@app.route('/admin/buses')
@admin_required
def admin_buses():
    """Admin bus management"""
    bus_dates = booking_system.db.get_all_dates()
    # Get selected date from query parameter, default to first date
    selected_date = request.args.get('date', bus_dates[0] if bus_dates else None)
    
    # Validate selected date is in available dates
    if selected_date not in bus_dates:
        selected_date = bus_dates[0] if bus_dates else None
    
    bus_statuses = booking_system.get_all_buses_status(selected_date)
    
    active_buses = [b for b in bus_statuses if b['status'] == 'active']
    merging_buses = [b for b in bus_statuses if b['status'] == 'merging']
    other_buses = [b for b in bus_statuses if b['status'] not in ['active', 'merging']]
    
    return render_template('admin_buses.html',
                         active_buses=active_buses,
                         merging_buses=merging_buses,
                         other_buses=other_buses,
                         bus_dates=bus_dates,
                         selected_date=selected_date)


@app.route('/admin/merge-buses', methods=['POST'])
@admin_required
def admin_merge_buses():
    """Merge underutilized buses"""
    username = session['admin_user']
    result = booking_system.admin.merge_buses(username, 'admin123')
    
    return jsonify(result)


@app.route('/admin/force-release', methods=['POST'])
@admin_required
def admin_force_release():
    """Force release a seat"""
    username = session['admin_user']
    data = request.get_json()
    
    bus_id = data.get('bus_id')
    seat_number = data.get('seat_number')
    
    success = booking_system.admin.force_release_seat(username, 'admin123', bus_id, seat_number)
    
    return jsonify({
        'success': success,
        'message': 'Seat released successfully' if success else 'Failed to release seat'
    })


@app.route('/admin/bookings')
@admin_required
def admin_bookings():
    """View all bookings"""
    # Get all bookings with pagination
    page = request.args.get('page', 1, type=int)
    per_page = 50
    
    all_bookings = booking_system.get_all_bookings()
    
    # Sort by booking time (most recent first)
    all_bookings.sort(key=lambda x: x['booking_time'], reverse=True)
    
    # Paginate
    start = (page - 1) * per_page
    end = start + per_page
    bookings = all_bookings[start:end]
    total_pages = (len(all_bookings) + per_page - 1) // per_page
    
    return render_template('admin_bookings.html',
                         bookings=bookings,
                         page=page,
                         total_pages=total_pages,
                         total_bookings=len(all_bookings))


@app.route('/admin/analytics')
@admin_required
def admin_analytics():
    """View system analytics"""
    # Prepare analytics data
    perf_report = monitor.get_performance_report()
    disk_stats = booking_system.logger.get_stats()
    
    # Bus utilization data
    bus_dates = booking_system.db.get_all_dates()
    # Get selected date from query parameter, default to first date
    selected_date = request.args.get('date', bus_dates[0] if bus_dates else None)
    
    # Validate selected date is in available dates
    if selected_date not in bus_dates:
        selected_date = bus_dates[0] if bus_dates else None
    
    buses = booking_system.get_all_buses_status(selected_date)

    bus_data = []
    for bus in buses:
        if bus['status'] == 'active':
            bus_data.append({
                'bus_id': bus['bus_id'],
                'load_factor': bus.get('load_factor', 0) * 100,
                'available_seats': bus.get('available_seats', 0),
                'total_seats': bus.get('total_seats', 0)
            })
    
    return render_template('admin_analytics.html',
                         perf=perf_report,
                         disk=disk_stats,
                         bus_data=bus_data,
                         bus_dates=bus_dates,
                         selected_date=selected_date)


@app.route('/admin/simulation')
@admin_required
def admin_simulation():
    """Simulation tracking page"""
    return render_template('admin_simulation.html')


@app.route('/admin/run-simulation', methods=['POST'])
@admin_required
def admin_run_simulation():
    """Run comprehensive simulation - Admin only"""
    global simulation_state
    
    with simulation_lock:
        if simulation_state['running']:
            return jsonify({
                'status': 'error',
                'message': 'Simulation already running'
            }), 400
        
        # Reset simulation state
        simulation_state = {
            'running': True,
            'progress': 0,
            'phase': 'Starting...',
            'results': {},
            'start_time': time.time(),
            'end_time': None,
            'logs': []
        }
    
    def run_sim():
        global simulation_state, booking_system  # Add booking_system to global access
        
        try:
            from main import simulation_progress, run_comprehensive_simulation
            
            # Run simulation
            simulated_system = run_comprehensive_simulation()
            
            # CRITICAL: Copy simulation data to web app's booking system
            with simulation_lock:
                # Update buses
                booking_system.buses.clear()
                booking_system.buses.update(simulated_system.buses)
                
                # Update bookings
                booking_system.bookings_db.clear()
                booking_system.bookings_db.update(simulated_system.bookings_db)
                
                # Update visitor count
                booking_system.visitor_count = simulated_system.get_total_visitors()
                
                simulation_state['running'] = False
                simulation_state['progress'] = 100
                simulation_state['phase'] = 'Completed'
                simulation_state['end_time'] = time.time()
                simulation_state['logs'] = simulation_progress['logs']
                simulation_state['results'] = {
                    'total_bookings': len(booking_system.bookings_db),  # Use updated count
                    'total_visitors': booking_system.get_total_visitors(),
                    'active_buses': len([b for b in booking_system.buses.values() if b.status == 'active']),
                    'load_factor': booking_system.get_overall_load_factor()
                }
            
            print(f"SIMULATION DATA COPIED: {len(booking_system.bookings_db)} bookings, {booking_system.get_total_visitors()} visitors")
                
        except Exception as e:
            # ... error handling ...
            with simulation_lock:
                simulation_state['running'] = False
                simulation_state['phase'] = 'Error'
                simulation_state['end_time'] = time.time()
                simulation_state['logs'].append({
                    'time': time.time() - simulation_state['start_time'],
                    'phase': 'Error',
                    'message': str(e)
                })
            import traceback
            print(f"Simulation error: {traceback.format_exc()}")
    
    thread = threading.Thread(target=run_sim, daemon=True)
    thread.start()
    
    return jsonify({
        'status': 'success',
        'message': 'Simulation started'
    })


@app.route('/admin/simulation-status')
@admin_required
def simulation_status():
    """Get current simulation status with live logs"""
    global simulation_state
    
    # If simulation is running, get live progress from main.py
    if simulation_state['running']:
        try:
            from main import simulation_progress
            
            with simulation_lock:
                # Update our state with live data from main.py
                simulation_state['phase'] = simulation_progress.get('phase', simulation_state['phase'])
                simulation_state['progress'] = simulation_progress.get('progress', simulation_state['progress'])
                simulation_state['logs'] = simulation_progress.get('logs', simulation_state['logs'])
        except Exception as e:
            print(f"Error syncing simulation progress: {e}")
    
    with simulation_lock:
        return jsonify(simulation_state)

# ============================================================================
# API ROUTES
# ============================================================================

@app.route('/api/stats')
def get_stats():
    """Get system statistics"""
    active_buses = [b for b in booking_system.get_all_buses() if b['status'] == 'active']
    stats = {
        'total_bookings': len(booking_system.db.get_all_bookings()),
        'total_visitors': booking_system.get_total_visitors(),
        'system_load': booking_system.get_overall_load_factor(),
        'active_buses': len(active_buses),
        'total_buses': len(booking_system.get_all_buses()),
        'available_seats': sum(bus['total_seats'] for bus in [b for b in booking_system.get_all_buses() if b['status'] == 'active']) - len(booking_system.db.get_all_bookings())
    }
    return jsonify(stats)


@app.route('/api/release-expired')
def release_expired():
    """Release expired seat reservations"""
    count = booking_system.release_expired_reservations()
    return jsonify({'released': count})


# ============================================================================
# ERROR HANDLERS
# ============================================================================

@app.errorhandler(404)
def not_found(e):
    """404 error handler"""
    return render_template('404.html'), 404


@app.errorhandler(500)
def server_error(e):
    """500 error handler"""
    return render_template('500.html'), 500


# ============================================================================
# CLEANUP
# ============================================================================

def cleanup():
    """Cleanup on shutdown"""
    monitor.stop_monitoring()
    booking_system.shutdown()
    if hasattr(booking_system, 'db') and booking_system.db:
        booking_system.db.close()


import atexit
atexit.register(cleanup)


if __name__ == '__main__':
    app.run(debug=True, host='0.0.0.0', port=5000, threaded=True)