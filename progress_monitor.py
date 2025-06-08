import threading
import time
import sys
from typing import Callable, Generator, Dict, Any, Optional
from tqdm import tqdm as original_tqdm

# Global progress monitor - set this before importing other modules
_global_monitor = None

class ProgressMonitor:
    def __init__(self):
        self.progress = {"current": 0, "total": 0, "percentage": 0.0, "desc": "", "status": "ready"}
        self.lock = threading.Lock()
        self._exception = None
        self._result = None
    
    def update(self, current: int, total: int, desc: str = ""):
        with self.lock:
            self.progress = {
                "current": current,
                "total": total,
                "percentage": (current / total) * 100 if total > 0 else 0,
                "desc": desc,
                "status": "running",
            }
    
    def get_progress(self) -> Dict[str, Any]:
        with self.lock:
            return dict(self.progress)
    
    def set_error(self, exception: Exception):
        with self.lock:
            self._exception = exception
            self.progress["status"] = "error"
    
    def get_exception(self) -> Optional[Exception]:
        with self.lock:
            return self._exception
    
    def set_result(self, result: Any):
        with self.lock:
            self._result = result
    
    def get_result(self) -> Any:
        with self.lock:
            return self._result
    
    def reset(self):
        with self.lock:
            self.progress = {"current": 0, "total": 0, "percentage": 0.0, "desc": "", "status": "ready"}
            self._exception = None
            self._result = None

class MonitoredTqdm(original_tqdm):
    def __init__(self, iterable=None, total=None, desc="", file=None, disable=False, **kwargs):
        # Store our own copies of important attributes in case disable=True
        self._desc = desc or ""
        self._total = total
        self._disable = disable
        
        # Initialize parent with file=None to disable normal output
        super().__init__(
            iterable=iterable, 
            total=total, 
            desc=desc, 
            file=open('/dev/null', 'w') if file is None else file,  # Suppress output by default
            disable=disable,
            **kwargs
        )
        
        # Use global monitor if available (even when disabled, we want to track)
        if _global_monitor and not disable:
            _global_monitor.update(0, self._get_total(), self._get_desc())
    
    def _get_total(self):
        """Safely get total, handling disabled case."""
        return getattr(self, 'total', self._total) or 0
    
    def _get_desc(self):
        """Safely get description, handling disabled case."""
        return getattr(self, 'desc', self._desc) or ""
    
    def _get_n(self):
        """Safely get current position, handling disabled case."""
        return getattr(self, 'n', 0) or 0
    
    def update(self, n=1):
        """Override update to send progress to global monitor."""
        # Call parent update to maintain internal state (even if disabled)
        result = super().update(n)
        
        # Update global monitor (even when disabled, we want progress tracking)
        if _global_monitor:
            _global_monitor.update(self._get_n(), self._get_total(), self._get_desc())
        
        return result
    
    def refresh(self, nolock=False, lock_args=None):
        """Override refresh to update monitor instead of displaying."""
        # Update global monitor instead of displaying (even when disabled)
        if _global_monitor:
            _global_monitor.update(self._get_n(), self._get_total(), self._get_desc())
        
        # Don't call parent refresh to avoid output
        return
    
    def close(self):
        """Override close to ensure final progress update."""
        if _global_monitor and not self._disable:
            total = self._get_total()
            if total > 0:
                _global_monitor.update(total, total, self._get_desc())
        
        # Call parent close for cleanup
        super().close()
    
    def __iter__(self):
        """Override iterator to ensure progress updates."""
        try:
            for obj in super().__iter__():
                # Progress is automatically updated by parent's __iter__ calling update()
                yield obj
        except Exception as e:
            if _global_monitor:
                _global_monitor.set_error(e)
            raise
    
    def __enter__(self):
        return self
    
    def __exit__(self, exc_type, exc_val, exc_tb):
        self.close()
        return super().__exit__(exc_type, exc_val, exc_tb)

def patch_tqdm():
    """
    Patch tqdm globally. Call this BEFORE importing any modules that use tqdm.
    """
    global _global_monitor
    if _global_monitor is None:
        _global_monitor = ProgressMonitor()
    
    # Patch tqdm in the tqdm module itself
    import tqdm
    tqdm.tqdm = MonitoredTqdm
    
    # Also patch it in sys.modules for any future imports
    if 'tqdm' in sys.modules:
        sys.modules['tqdm'].tqdm = MonitoredTqdm

def unpatch_tqdm():
    """
    Restore original tqdm functionality.
    """
    import tqdm
    tqdm.tqdm = original_tqdm
    if 'tqdm' in sys.modules:
        sys.modules['tqdm'].tqdm = original_tqdm

def get_global_monitor() -> Optional[ProgressMonitor]:
    """Get the global progress monitor."""
    return _global_monitor

def reset_global_monitor():
    """Reset the global monitor's state."""
    if _global_monitor:
        _global_monitor.reset()

def run_with_progress(target_func: Callable, *args, poll_interval: float = 0.5, **kwargs) -> Generator[Dict[str, Any], None, None]:
    """
    Run a function in a thread and monitor its progress using the global monitor.
    
    Usage:
        # IMPORTANT: Call patch_tqdm() before importing modules that use tqdm
        patch_tqdm()
        
        # Now import your modules
        from your_module import some_function_that_uses_tqdm
        
        # Run with progress monitoring
        for progress in run_with_progress(some_function_that_uses_tqdm, arg1, arg2):
            print(f"Progress: {progress['percentage']:.1f}%")
    """
    if _global_monitor is None:
        raise RuntimeError("Global monitor not initialized. Call patch_tqdm() first.")
    
    # Reset monitor for this run
    _global_monitor.reset()
    
    def wrapped_target():
        try:
            result = target_func(*args, **kwargs)
            _global_monitor.set_result(result)
        except Exception as e:
            _global_monitor.set_error(e)
    
    thread = threading.Thread(target=wrapped_target)
    thread.start()
    
    try:
        while thread.is_alive():
            progress = _global_monitor.get_progress()
            yield progress
            time.sleep(poll_interval)
        
        thread.join()
        
        # Check for exceptions
        exception = _global_monitor.get_exception()
        if exception:
            raise exception
        
        # Yield final progress with result
        final_progress = _global_monitor.get_progress()
        final_progress['status'] = 'completed'
        final_progress['result'] = _global_monitor.get_result()
        yield final_progress
        
    except KeyboardInterrupt:
        print("Interrupted, waiting for thread to finish...")
        thread.join(timeout=5.0)
        if thread.is_alive():
            print("Warning: Thread did not finish cleanly")
        raise

def run_and_wait(target_func: Callable, *args, **kwargs) -> tuple[Dict[str, Any], Any]:
    """
    Run a function and return both final progress and result.
    """
    final_progress = None
    for progress in run_with_progress(target_func, *args, **kwargs):
        final_progress = progress
    
    result = final_progress.get('result') if final_progress else None
    return final_progress, result
