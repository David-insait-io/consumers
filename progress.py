"""Batch progress tracking for simulations."""

import logging
import time
from datetime import timedelta
from typing import Optional

logger = logging.getLogger(__name__)


class ProgressTracker:
    """Track progress of batch processing."""

    def __init__(self, total_count: Optional[int] = None, log_interval: int = 100):
        """
        Initialize progress tracker.

        Args:
            total_count: Total number of simulations (can be set later)
            log_interval: Log progress every N completions
        """
        self.total_count = total_count
        self.completed_count = 0
        self.failed_count = 0
        self.log_interval = log_interval
        self.start_time = time.time()
        self.last_log_time = self.start_time
        self.last_log_count = 0

    def set_total(self, count: int):
        """Set the total count after initialization."""
        self.total_count = count

    def record_completion(self):
        """Record a successful completion."""
        self.completed_count += 1

        # Log progress at intervals
        if self.completed_count % self.log_interval == 0:
            self._log_progress()

    def record_failure(self):
        """Record a failed simulation."""
        self.failed_count += 1

    def _log_progress(self):
        """Log current progress with rate and ETA."""
        current_time = time.time()
        elapsed = current_time - self.start_time
        elapsed_since_last = current_time - self.last_log_time

        # Calculate rates
        total_processed = self.completed_count + self.failed_count
        overall_rate = total_processed / elapsed if elapsed > 0 else 0

        # Calculate recent rate (since last log)
        recent_processed = total_processed - self.last_log_count
        recent_rate = recent_processed / elapsed_since_last if elapsed_since_last > 0 else 0

        # Build log message
        msg_parts = [
            f"Progress: {self.completed_count} completed, {self.failed_count} failed"
        ]

        if self.total_count:
            remaining = self.total_count - total_processed
            percentage = (total_processed / self.total_count) * 100
            msg_parts.append(f"({total_processed}/{self.total_count}, {percentage:.1f}%)")

            # Calculate ETA
            if recent_rate > 0:
                eta_seconds = remaining / recent_rate
                eta = timedelta(seconds=int(eta_seconds))
                msg_parts.append(f"ETA: {eta}")

        # Add rates
        msg_parts.append(f"Rate: {overall_rate:.2f}/s (recent: {recent_rate:.2f}/s)")

        logger.info(" | ".join(msg_parts))

        # Update tracking variables
        self.last_log_time = current_time
        self.last_log_count = total_processed

    def log_final_summary(self):
        """Log final summary of the batch."""
        elapsed = time.time() - self.start_time
        total_processed = self.completed_count + self.failed_count
        overall_rate = total_processed / elapsed if elapsed > 0 else 0

        summary = [
            "\n" + "=" * 80,
            "BATCH PROCESSING COMPLETE",
            "=" * 80,
            f"Total Processed: {total_processed}",
            f"  Completed: {self.completed_count}",
            f"  Failed: {self.failed_count}",
            f"Total Time: {timedelta(seconds=int(elapsed))}",
            f"Average Rate: {overall_rate:.2f} simulations/second",
        ]

        if self.total_count:
            success_rate = (self.completed_count / self.total_count) * 100
            summary.append(f"Success Rate: {success_rate:.2f}%")

        summary.append("=" * 80)

        logger.info("\n".join(summary))

    def get_stats(self) -> dict:
        """Get current progress statistics."""
        elapsed = time.time() - self.start_time
        total_processed = self.completed_count + self.failed_count
        rate = total_processed / elapsed if elapsed > 0 else 0

        stats = {
            "completed": self.completed_count,
            "failed": self.failed_count,
            "total_processed": total_processed,
            "elapsed_seconds": elapsed,
            "rate": rate
        }

        if self.total_count:
            stats["total"] = self.total_count
            stats["remaining"] = self.total_count - total_processed
            stats["percentage"] = (total_processed / self.total_count) * 100

            if rate > 0:
                stats["eta_seconds"] = stats["remaining"] / rate

        return stats
