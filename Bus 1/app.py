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
        'total_bookings': len(booking_system.bookings_db),
        'active_buses': len([b for b in booking_system.buses.values() if b.status == 'active']),
        'available_seats': sum(
            sum(1 for seat in bus.seats.values() if seat is None)
            for bus in booking_system.buses.values()
            if bus.status == 'active'
        )
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
    bookings = booking_system.get_client_bookings(client_id)
    
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
        
        existing_bookings = booking_system.get_client_bookings(client_id)
        if any(b['date'] == travel_date for b in existing_bookings):
            return jsonify({
                'status': 'error',
                'message': f'You already have a booking on {travel_date}.'
            }), 400
            
        result = booking_system.book_seat_for_client(
            client_id,
            travel_date,
            preferred_bus if preferred_bus else None,
            preferred_seat if preferred_seat else None
        )

        
        return jsonify(result)
    
    # GET request - show booking form
    today = datetime.now().date()
    dates = [(today + timedelta(days=i)).strftime('%Y-%m-%d') for i in range(30)]
    
    return render_template('book.html', dates=dates)


@app.route('/api/buses/<date>')
@login_required
def get_buses(date):
    """Get available buses for a date"""
    buses = []
    for bus_id, bus in booking_system.buses.items():
        if bus.status == 'active':
            available_seats = sum(1 for seat in bus.seats.values() if seat is None)
            buses.append({
                'bus_id': bus_id,
                'route': bus.route,
                'total_seats': bus.total_seats,
                'available_seats': available_seats,
                'load_factor': bus.get_load_factor()
            })
    
    return jsonify({'buses': buses})


@app.route('/api/seats/<int:bus_id>/<date>')
@login_required
def get_seats(bus_id, date):
    """Get seat map for a bus"""
    bus = booking_system.buses.get(bus_id)
    if not bus:
        return jsonify({'error': 'Bus not found'}), 404
    
    seat_map = []
    for seat_num in range(1, bus.total_seats + 1):
        client = bus.seats.get(seat_num)
        seat_map.append({
            'number': seat_num,
            'available': client is None,
            'client_id': client if client else None
        })
    
    return jsonify({'seats': seat_map, 'bus_id': bus_id, 'route': bus.route})


@app.route('/cancel/<booking_id>', methods=['POST'])
@login_required
def cancel_booking(booking_id):
    """Cancel a booking"""
    client_id = session['client_id']
    success = booking_system.cancel_booking(booking_id, client_id)
    
    return jsonify({
        'success': success,
        'message': 'Booking cancelled successfully' if success else 'Failed to cancel booking'
    })


@app.route('/my-bookings')
@login_required
def my_bookings():
    """View all user bookings"""
    client_id = session['client_id']
    bookings = booking_system.get_client_bookings(client_id)
    print(f"My bookings for {client_id}: {bookings}")
    
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
    
    return render_template('admin_dashboard.html', 
                         overview=overview, 
                         perf=perf_report,
                         disk=disk_stats,
                         username=username)


@app.route('/admin/buses')
@admin_required
def admin_buses():
    """Admin bus management"""
    bus_statuses = booking_system.get_all_buses_status()
    
    active_buses = [b for b in bus_statuses if b['status'] == 'active']
    merging_buses = [b for b in bus_statuses if b['status'] == 'merging']
    other_buses = [b for b in bus_statuses if b['status'] not in ['active', 'merging']]
    
    return render_template('admin_buses.html',
                         active_buses=active_buses,
                         merging_buses=merging_buses,
                         other_buses=other_buses)


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
    
    all_bookings = []
    for booking_id, booking_data in booking_system.bookings_db.items():
        all_bookings.append({
            'booking_id': booking_id,
            'client_id': booking_data['client_id'],
            'bus_id': booking_data['bus_id'],
            'seat': booking_data['seat'],
            'date': booking_data['date'],
            'booking_time': booking_data.get('booking_time', 'Unknown')
        })
    
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
    buses = booking_system.get_all_buses_status()
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
                         bus_data=bus_data)


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
        global simulation_state
        try:
            # Add logging wrapper
            def log_progress(phase, progress, message):
                with simulation_lock:
                    simulation_state['phase'] = phase
                    simulation_state['progress'] = progress
                    simulation_state['logs'].append({
                        'time': time.time() - simulation_state['start_time'],
                        'phase': phase,
                        'message': message
                    })
            
            log_progress('Initialization', 5, 'Starting simulation...')
            
            # Run simulation with progress tracking
            result = run_comprehensive_simulation()
            
            with simulation_lock:
                simulation_state['running'] = False
                simulation_state['progress'] = 100
                simulation_state['phase'] = 'Completed'
                simulation_state['end_time'] = time.time()
                simulation_state['results'] = {
                    'total_bookings': len(result.bookings_db),
                    'total_visitors': result.get_total_visitors(),
                    'active_buses': len([b for b in result.buses.values() if b.status == 'active']),
                    'load_factor': result.get_overall_load_factor()
                }
        except Exception as e:
            with simulation_lock:
                simulation_state['running'] = False
                simulation_state['phase'] = 'Error'
                simulation_state['logs'].append({
                    'time': time.time() - simulation_state['start_time'],
                    'phase': 'Error',
                    'message': str(e)
                })
    
    thread = threading.Thread(target=run_sim, daemon=True)
    thread.start()
    
    return jsonify({
        'status': 'success',
        'message': 'Simulation started'
    })


@app.route('/admin/simulation-status')
@admin_required
def simulation_status():
    """Get current simulation status"""
    with simulation_lock:
        return jsonify(simulation_state)


# ============================================================================
# API ROUTES
# ============================================================================

@app.route('/api/stats')
def get_stats():
    """Get system statistics"""
    stats = {
        'total_bookings': len(booking_system.bookings_db),
        'total_visitors': booking_system.get_total_visitors(),
        'system_load': booking_system.get_overall_load_factor(),
        'active_buses': len([b for b in booking_system.buses.values() if b.status == 'active']),
        'total_buses': len(booking_system.buses),
        'available_seats': sum(
            sum(1 for seat in bus.seats.values() if seat is None)
            for bus in booking_system.buses.values()
            if bus.status == 'active'
        )
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