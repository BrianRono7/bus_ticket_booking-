import logging
import threading
import queue
import time
from typing import List
from datetime import datetime
from config import LOG_FILE, LOG_BATCH_SIZE, LOG_FLUSH_INTERVAL 


class AsyncLogger:
    """Asynchronous logger with batched writes for improved performance"""
    
    def __init__(self, log_file: str = LOG_FILE,
                 batch_size: int = LOG_BATCH_SIZE, 
                 flush_interval: float = LOG_FLUSH_INTERVAL):
        self.log_file = log_file
        self.batch_size = batch_size
        self.flush_interval = flush_interval
        self.log_queue = queue.Queue()
        self.logging_active = True
        self.logger_thread = None
        
        # Statistics
        self.disk_write_count = 0
        self.disk_write_time = 0.0
        self.lock = threading.Lock()
        
        # In-memory log
        self.booking_log: List[str] = []
        
        self._setup_logging()
        self._start_async_logging()

    def _setup_logging(self):
        """Configure the logging system"""
        logging.basicConfig(
            filename=self.log_file,
            level=logging.INFO,
            format='%(asctime)s - %(threadName)s - %(message)s',
            filemode='a'
        )

    def _start_async_logging(self):
        """Start the async logging thread"""
        self.logger_thread = threading.Thread(
            target=self._async_log_writer, 
            daemon=True
        )
        self.logger_thread.start()

    def _async_log_writer(self):
        """Batch writes to reduce disk I/O operations"""
        batch = []
        last_write = time.time()

        while self.logging_active or not self.log_queue.empty():
            try:
                log_entry = self.log_queue.get(timeout=1)
                batch.append(log_entry)

                # Write batch if size reached or interval elapsed
                should_flush = (
                    len(batch) >= self.batch_size or 
                    (time.time() - last_write) > self.flush_interval
                )
                
                if should_flush:
                    self._write_batch(batch)
                    batch = []
                    last_write = time.time()

            except queue.Empty:
                # Write remaining batch if any
                if batch:
                    self._write_batch(batch)
                    batch = []
                    last_write = time.time()

    def _write_batch(self, batch: List[str]):
        """Write a batch of log entries to disk"""
        if not batch:
            return
            
        start_time = time.time()
        for entry in batch:
            logging.info(entry)
        write_time = time.time() - start_time

        with self.lock:
            self.disk_write_count += 1
            self.disk_write_time += write_time

    def log(self, message: str):
        """Add a log entry (async, non-blocking)"""
        timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        log_entry = f"[{timestamp}] {message}"
        
        with self.lock:
            self.booking_log.append(log_entry)
        
        self.log_queue.put(message)

    def get_stats(self) -> dict:
        """Get logging statistics"""
        with self.lock:
            avg_write_time = (
                self.disk_write_time / self.disk_write_count 
                if self.disk_write_count > 0 else 0
            )
            return {
                "total_writes": self.disk_write_count,
                "total_write_time": self.disk_write_time,
                "avg_write_time": avg_write_time,
                "write_method": f"Async Batched ({self.batch_size} entries or {self.flush_interval}s interval)"
            }

    def get_log_history(self) -> List[str]:
        """Get in-memory log history"""
        with self.lock:
            return self.booking_log.copy()

    def shutdown(self):
        """Stop logging and flush remaining entries"""
        self.logging_active = False
        if self.logger_thread:
            self.logger_thread.join(timeout=10)