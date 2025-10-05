import threading
import time
import psutil
import os
from typing import List, Dict, Optional
from config import MONITOR_INTERVAL, ENABLE_DETAILED_STATS


class PerformanceMonitor:
    """Monitors system performance metrics"""
    
    def __init__(self, booking_system):
        self.booking_system = booking_system
        self.monitoring = False
        self.monitor_thread: Optional[threading.Thread] = None
        self.stats_history: List[Dict] = []
        self.start_time: Optional[float] = None
        self.end_time: Optional[float] = None
        self.enable_detailed_stats = ENABLE_DETAILED_STATS

    def start_monitoring(self, interval: float = MONITOR_INTERVAL):
        """Start performance monitoring"""
        self.monitoring = True
        self.start_time = time.time()
        self.monitor_thread = threading.Thread(
            target=self._monitor_loop, 
            args=(interval,),
            daemon=True
        )
        self.monitor_thread.start()

    def stop_monitoring(self):
        """Stop performance monitoring"""
        self.monitoring = False
        self.end_time = time.time()
        if self.monitor_thread:
            self.monitor_thread.join(timeout=5)

    def _monitor_loop(self, interval: float):
        """Continuous monitoring loop"""
        while self.monitoring:
            stats = self._collect_stats()
            stats['timestamp'] = time.time()
            self.stats_history.append(stats)
            time.sleep(interval)

    def _collect_stats(self) -> Dict:
        """Collect current system statistics"""
        process = psutil.Process(os.getpid())
        cpu_percent = process.cpu_percent(interval=0.1)
        memory_info = process.memory_info()
        cpu_times = process.cpu_times()

        return {
            "cpu_usage": cpu_percent,
            "memory_rss": memory_info.rss / (1024 * 1024),  # MB
            "memory_vms": memory_info.vms / (1024 * 1024),  # MB
            "num_threads": process.num_threads(),
            "cpu_user_time": cpu_times.user,
            "cpu_system_time": cpu_times.system
        }

    def get_current_stats(self) -> Dict:
        """Get current system statistics"""
        return self._collect_stats()

    def get_performance_report(self) -> Dict:
        """Generate comprehensive performance report"""
        if not self.stats_history:
            return {"error": "No performance data collected"}

        cpu_usages = [s["cpu_usage"] for s in self.stats_history]
        memory_rss = [s["memory_rss"] for s in self.stats_history]
        memory_vms = [s["memory_vms"] for s in self.stats_history]
        num_threads = [s["num_threads"] for s in self.stats_history]

        total_time = self.end_time - self.start_time if self.end_time else 0
        
        # CORRECT CALCULATION: Average CPU usage to estimate active time
        avg_cpu_usage = sum(cpu_usages) / len(cpu_usages) if cpu_usages else 0
        active_time = total_time * (avg_cpu_usage / 100.0)
        idle_time = total_time - active_time

        return {
            "max_cpu_usage": max(cpu_usages) if cpu_usages else 0,
            "avg_cpu_usage": avg_cpu_usage,
            "min_cpu_usage": min(cpu_usages) if cpu_usages else 0,
            "max_physical_memory_mb": max(memory_rss) if memory_rss else 0,
            "avg_physical_memory_mb": sum(memory_rss) / len(memory_rss) if memory_rss else 0,
            "max_virtual_memory_mb": max(memory_vms) if memory_vms else 0,
            "avg_virtual_memory_mb": sum(memory_vms) / len(memory_vms) if memory_vms else 0,
            "max_threads": max(num_threads) if num_threads else 0,
            "avg_threads": sum(num_threads) / len(num_threads) if num_threads else 0,
            "cpu_active_time_seconds": active_time,
            "cpu_idle_time_seconds": idle_time,
            "cpu_utilization_percent": avg_cpu_usage,
            "total_monitoring_time": total_time,
            "samples_collected": len(self.stats_history)
        }

    def get_stats_history(self) -> List[Dict]:
        """Get raw statistics history"""
        return self.stats_history.copy()

    def clear_history(self):
        """Clear statistics history"""
        self.stats_history.clear()
        self.start_time = None
        self.end_time = None


class ResourceTracker:
    """Tracks specific resource usage patterns"""
    
    def __init__(self):
        self.lock_contentions = 0
        self.failed_bookings = 0
        self.successful_bookings = 0
        self.cancelled_bookings = 0
        self.lock = threading.Lock()

    def record_lock_contention(self):
        """Record a lock contention event"""
        with self.lock:
            self.lock_contentions += 1

    def record_booking_attempt(self, success: bool):
        """Record a booking attempt"""
        with self.lock:
            if success:
                self.successful_bookings += 1
            else:
                self.failed_bookings += 1

    def record_cancellation(self):
        """Record a booking cancellation"""
        with self.lock:
            self.cancelled_bookings += 1

    def get_stats(self) -> Dict:
        """Get resource tracking statistics"""
        with self.lock:
            total_attempts = self.successful_bookings + self.failed_bookings
            success_rate = (
                self.successful_bookings / total_attempts 
                if total_attempts > 0 else 0
            )
            
            return {
                "lock_contentions": self.lock_contentions,
                "successful_bookings": self.successful_bookings,
                "failed_bookings": self.failed_bookings,
                "cancelled_bookings": self.cancelled_bookings,
                "total_attempts": total_attempts,
                "success_rate": success_rate
            }

    def reset(self):
        """Reset all counters"""
        with self.lock:
            self.lock_contentions = 0
            self.failed_bookings = 0
            self.successful_bookings = 0
            self.cancelled_bookings = 0