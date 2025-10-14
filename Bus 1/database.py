# database.py
import sqlite3
import threading
from contextlib import contextmanager
from config import DB_TYPE, DB_CONNECTION_STRING

class DatabaseManager:
    """Simple SQLite database manager"""
    
    def __init__(self, db_path="bus_booking.db"):
        self.db_path = db_path
        self._local = threading.local()
        self._init_db()
    
    def _init_db(self):
        """Initialize database tables"""
        with self._get_connection() as conn:
            cursor = conn.cursor()
            
            # Bookings table
            cursor.execute('''
                CREATE TABLE IF NOT EXISTS bookings (
                    booking_id TEXT PRIMARY KEY,
                    client_id TEXT NOT NULL,
                    bus_id INTEGER NOT NULL,
                    seat INTEGER NOT NULL,
                    date TEXT NOT NULL,
                    booking_time TEXT NOT NULL
                )
            ''')
            
            # Buses table (for persistence)
            cursor.execute('''
                CREATE TABLE IF NOT EXISTS buses (
                    bus_id INTEGER PRIMARY KEY,
                    total_seats INTEGER NOT NULL,
                    route TEXT NOT NULL,
                    status TEXT NOT NULL DEFAULT 'active'
                )
            ''')
            
            # Bus seats table
            cursor.execute('''
                CREATE TABLE IF NOT EXISTS bus_seats (
                    bus_id INTEGER,
                    seat_number INTEGER,
                    client_id TEXT,
                    departure_date TEXT,
                    PRIMARY KEY (bus_id, seat_number, departure_date),
                    FOREIGN KEY (bus_id) REFERENCES buses (bus_id)
                )
            ''')
            
            conn.commit()
    
    @contextmanager
    def _get_connection(self):
        """Thread-safe connection management"""
        if not hasattr(self._local, 'conn'):
            self._local.conn = sqlite3.connect(self.db_path, check_same_thread=False)
            self._local.conn.row_factory = sqlite3.Row
        
        try:
            yield self._local.conn
        except Exception:
            self._local.conn.rollback()
            raise
        else:
            self._local.conn.commit()
    
    @contextmanager
    def atomic_transaction(self):
        """Provide an atomic database transaction context"""
        with self._get_connection() as conn:
            try:
                conn.execute("BEGIN IMMEDIATE;")  # locks DB for write safety
                yield conn
            except Exception:
                conn.rollback()
                raise
            else:
                conn.commit()

    
    def save_booking(self, booking_data, conn=None):
        """Save a booking to database (optionally inside an active transaction)"""
        internal = False
        if conn is None:
            internal = True
            conn_ctx = self._get_connection()
            conn = conn_ctx.__enter__()
        
        try:
            cursor = conn.cursor()
            cursor.execute('''
                INSERT OR REPLACE INTO bookings 
                (booking_id, client_id, bus_id, seat, date, booking_time)
                VALUES (?, ?, ?, ?, ?, ?)
            ''', (
                booking_data['booking_id'],
                booking_data['client_id'],
                booking_data['bus_id'],
                booking_data['seat'],
                booking_data['date'],
                booking_data['booking_time']
            ))
            if internal:
                conn_ctx.__exit__(None, None, None)
        except Exception as e:
            if internal:
                conn_ctx.__exit__(type(e), e, e.__traceback__)
            raise

    
    def delete_booking(self, booking_id):
        """Delete a booking from database"""
        with self._get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute('DELETE FROM bookings WHERE booking_id = ?', (booking_id,))
    
    def get_all_bookings(self):
        """Get all bookings from database"""
        with self._get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute('SELECT * FROM bookings')
            return [dict(row) for row in cursor.fetchall()]
    
    def get_client_bookings(self, client_id):
        """Get all bookings for a client"""
        with self._get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute('SELECT * FROM bookings WHERE client_id = ?', (client_id,))
            return [dict(row) for row in cursor.fetchall()]
    
    def save_bus_seat(self, bus_id, seat_number, client_id, departure_date):
        """Save bus seat assignment"""
        with self._get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute('''
                INSERT OR REPLACE INTO bus_seats 
                (bus_id, seat_number, client_id, departure_date)
                VALUES (?, ?, ?, ?)
            ''', (bus_id, seat_number, client_id, departure_date))
    
    def delete_bus_seat(self, bus_id, seat_number, departure_date):
        """Remove bus seat assignment"""
        with self._get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute('''
                DELETE FROM bus_seats 
                WHERE bus_id = ? AND seat_number = ? AND departure_date = ?
            ''', (bus_id, seat_number, departure_date))
    
    def get_bus_seats(self, bus_id, departure_date):
        """Get all seat assignments for a bus on a date"""
        with self._get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute('''
                SELECT * FROM bus_seats 
                WHERE bus_id = ? AND departure_date = ?
            ''', (bus_id, departure_date))
            return {row['seat_number']: row['client_id'] for row in cursor.fetchall()}
    
    def close(self):
        """Close database connection"""
        if hasattr(self._local, 'conn'):
            self._local.conn.close()