"""
Configuration file for the Bus Booking System
"""

# Bus Configuration
DEFAULT_SEATS_PER_BUS = 50
DEFAULT_ROUTE = "Nakuru-Nairobi"
INITIAL_BUS_COUNT = 10
MAX_BUS_COUNT = 100

# Load Management
LOAD_THRESHOLD_HIGH = 0.8  # Add buses when 80% full
LOAD_THRESHOLD_LOW = 0.2   # Merge buses when below 20%

# Timeouts (in seconds)
SEAT_RESERVATION_TIMEOUT = 300  # 5 minutes
BOOKING_CONFIRMATION_TIMEOUT = 600  # 10 minutes

# Logging Configuration
LOG_FILE = "nakuru_nairobi_booking_archive.log"
LOG_BATCH_SIZE = 10  # Number of entries to batch before writing
LOG_FLUSH_INTERVAL = 5.0  # Seconds between forced flushes

# Performance Monitoring
MONITOR_INTERVAL = 2.0  # Seconds between monitoring samples
ENABLE_DETAILED_STATS = True

# Threading Configuration
MAX_WORKER_THREADS = 10
THREAD_POOL_SIZE = 20

# Admin Configuration
DEFAULT_ADMIN_USERNAME = "admin"
DEFAULT_ADMIN_PASSWORD = "admin123"  # Change in production!

# Business Rules
ALLOW_MULTIPLE_BOOKINGS_PER_CLIENT = True
ALLOW_SAME_DAY_CANCELLATIONS = True
CANCELLATION_PENALTY = 0.0  # Percentage penalty on cancellation

# System Limits
MAX_BOOKINGS_PER_CLIENT = 10
MAX_CONCURRENT_REQUESTS = 1000

# Feature Flags
ENABLE_AUTO_BUS_SCALING = True
ENABLE_BUS_MERGING = True
ENABLE_EXPIRED_RESERVATION_CLEANUP = True
ENABLE_PERFORMANCE_MONITORING = True
ENABLE_ASYNC_LOGGING = True

# Database Configuration (for future expansion)
DB_TYPE = "sqlite"  # Change from "memory" to "sqlite"
DB_CONNECTION_STRING = "bus_booking.db"
ENABLE_DATABASE = True  # Add this flag

# API Configuration (for future expansion)
API_ENABLED = False
API_HOST = "0.0.0.0"
API_PORT = 8000
API_MAX_REQUESTS_PER_MINUTE = 100

# Notification Configuration (for future expansion)
ENABLE_NOTIFICATIONS = False
NOTIFICATION_EMAIL_ENABLED = False
NOTIFICATION_SMS_ENABLED = False


class SystemConfig:
    """System configuration class for easy access"""
    
    def __init__(self):
        self.seats_per_bus = DEFAULT_SEATS_PER_BUS
        self.route = DEFAULT_ROUTE
        self.initial_buses = INITIAL_BUS_COUNT
        self.max_buses = MAX_BUS_COUNT
        self.load_threshold_high = LOAD_THRESHOLD_HIGH
        self.load_threshold_low = LOAD_THRESHOLD_LOW
        self.seat_timeout = SEAT_RESERVATION_TIMEOUT
        self.log_file = LOG_FILE
        self.log_batch_size = LOG_BATCH_SIZE
        self.log_flush_interval = LOG_FLUSH_INTERVAL
        
    def to_dict(self):
        """Convert configuration to dictionary"""
        return {
            "seats_per_bus": self.seats_per_bus,
            "route": self.route,
            "initial_buses": self.initial_buses,
            "max_buses": self.max_buses,
            "load_threshold_high": self.load_threshold_high,
            "load_threshold_low": self.load_threshold_low,
            "seat_timeout": self.seat_timeout,
            "log_file": self.log_file
        }
    
    @classmethod
    def from_dict(cls, config_dict):
        """Create configuration from dictionary"""
        config = cls()
        for key, value in config_dict.items():
            if hasattr(config, key):
                setattr(config, key, value)
        return config


def get_config():
    """Get system configuration"""
    return SystemConfig()

def validate_config():
    """Validate configuration settings"""
    errors = []
    
    if INITIAL_BUS_COUNT <= 0:
        errors.append("INITIAL_BUS_COUNT must be positive")
    
    if MAX_BUS_COUNT < INITIAL_BUS_COUNT:
        errors.append("MAX_BUS_COUNT must be >= INITIAL_BUS_COUNT")
    
    if not (0 <= LOAD_THRESHOLD_LOW < LOAD_THRESHOLD_HIGH <= 1):
        errors.append("Load thresholds must be between 0 and 1, with LOW < HIGH")
    
    if SEAT_RESERVATION_TIMEOUT <= 0:
        errors.append("SEAT_RESERVATION_TIMEOUT must be positive")
    
    if LOG_BATCH_SIZE <= 0:
        errors.append("LOG_BATCH_SIZE must be positive")
    
    if LOG_FLUSH_INTERVAL <= 0:
        errors.append("LOG_FLUSH_INTERVAL must be positive")
    
    if MONITOR_INTERVAL <= 0:
        errors.append("MONITOR_INTERVAL must be positive")
    
    return errors

def print_config_summary():
    """Print a summary of the current configuration"""
    config = get_config()
    print("\n=== Current System Configuration ===")
    for key, value in config.to_dict().items():
        print(f"  {key}: {value}")
    print("====================================\n")