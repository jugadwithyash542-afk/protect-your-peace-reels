"""
Retry Utilities with Exponential Backoff
Provides reusable retry logic for auto-posting operations.
"""

import time
import functools
import requests
from typing import Callable, Any, Optional, Tuple


class RetryError(Exception):
    """Raised when all retry attempts are exhausted."""
    def __init__(self, message: str, last_exception: Optional[Exception] = None):
        super().__init__(message)
        self.last_exception = last_exception


def retry_with_backoff(
    max_retries: int = 3,
    base_delay: float = 2.0,
    max_delay: float = 60.0,
    exponential_base: float = 2.0,
    exceptions: tuple = (Exception,)
):
    """
    Decorator for retrying functions with exponential backoff.
    
    Args:
        max_retries: Maximum number of retry attempts (default: 3)
        base_delay: Initial delay in seconds (default: 2.0)
        max_delay: Maximum delay between retries (default: 60.0)
        exponential_base: Base for exponential backoff (default: 2.0)
        exceptions: Tuple of exceptions to catch and retry
    
    Returns:
        Decorated function with retry logic
    """
    def decorator(func: Callable) -> Callable:
        @functools.wraps(func)
        def wrapper(*args, **kwargs) -> Any:
            delay = base_delay
            last_exception = None
            
            for attempt in range(max_retries + 1):
                try:
                    return func(*args, **kwargs)
                except exceptions as e:
                    last_exception = e
                    
                    if attempt < max_retries:
                        print(f"⚠️  {func.__name__} failed (attempt {attempt + 1}/{max_retries + 1}): {str(e)}")
                        print(f"   Retrying in {delay:.1f}s...")
                        time.sleep(delay)
                        delay = min(delay * exponential_base, max_delay)
                    else:
                        print(f"❌ {func.__name__} failed after {max_retries + 1} attempts")
                        raise RetryError(
                            f"{func.__name__} failed after {max_retries + 1} attempts: {str(e)}",
                            last_exception=e
                        )
            
            return None
        return wrapper
    return decorator


def retry_operation(
    operation: Callable,
    *args,
    max_retries: int = 3,
    base_delay: float = 2.0,
    max_delay: float = 60.0,
    exponential_base: float = 2.0,
    exceptions: tuple = (Exception,),
    **kwargs
) -> Tuple[bool, Any, Optional[str]]:
    """
    Execute an operation with retry logic and exponential backoff.
    
    Args:
        operation: Function to execute
        *args: Positional arguments for the operation
        max_retries: Maximum number of retry attempts
        base_delay: Initial delay in seconds
        max_delay: Maximum delay between retries
        exponential_base: Base for exponential backoff
        exceptions: Tuple of exceptions to catch and retry
        **kwargs: Keyword arguments for the operation
    
    Returns:
        Tuple of (success: bool, result: Any, error_message: Optional[str])
    """
    delay = base_delay
    last_exception = None
    
    for attempt in range(max_retries + 1):
        try:
            result = operation(*args, **kwargs)
            return True, result, None
        except exceptions as e:
            last_exception = e
            
            if attempt < max_retries:
                print(f"⚠️  Operation failed (attempt {attempt + 1}/{max_retries + 1}): {str(e)}")
                print(f"   Retrying in {delay:.1f}s...")
                time.sleep(delay)
                delay = min(delay * exponential_base, max_delay)
            else:
                error_msg = f"Operation failed after {max_retries + 1} attempts: {str(e)}"
                print(f"❌ {error_msg}")
                return False, None, error_msg
    
    return False, None, "Unknown error"


def is_retryable_exception(exception: Exception) -> bool:
    """
    Determine if an exception is retryable.
    
    Retryable exceptions include:
    - Network timeouts
    - Connection errors
    - HTTP 5xx server errors
    - Rate limiting (HTTP 429)
    
    Args:
        exception: The exception to check
    
    Returns:
        True if the exception is retryable
    """
    if isinstance(exception, requests.exceptions.Timeout):
        return True
    
    if isinstance(exception, requests.exceptions.ConnectionError):
        return True
    
    if isinstance(exception, requests.exceptions.HTTPError):
        status_code = exception.response.status_code if exception.response else 0
        # Retry on server errors (5xx) and rate limiting (429)
        return status_code >= 500 or status_code == 429
    
    if isinstance(exception, RetryError):
        return False
    
    # Default: assume it's retryable
    return True
