"""Utility functions for the Haven TUI.

This package contains helper functions and utilities used throughout
the TUI application.
"""


def format_bytes(bytes_value: int, precision: int = 2) -> str:
    """Format bytes to human-readable string.
    
    Args:
        bytes_value: Number of bytes.
        precision: Decimal precision for the result.
        
    Returns:
        Human-readable string like "1.50 MB".
        
    Example:
        >>> format_bytes(1536000)
        '1.50 MB'
    """
    if bytes_value < 0:
        return "-" + format_bytes(-bytes_value, precision)
    
    if bytes_value == 0:
        return "0 B"
    
    units = ["B", "KB", "MB", "GB", "TB", "PB"]
    unit_index = 0
    value = float(bytes_value)
    
    while value >= 1024 and unit_index < len(units) - 1:
        value /= 1024
        unit_index += 1
    
    return f"{value:.{precision}f} {units[unit_index]}"


def format_duration(seconds: int) -> str:
    """Format duration in seconds to human-readable string.
    
    Args:
        seconds: Duration in seconds.
        
    Returns:
        Human-readable string like "2h 30m".
        
    Example:
        >>> format_duration(9000)
        '2h 30m'
    """
    if seconds < 0:
        return "-" + format_duration(-seconds)
    
    if seconds < 60:
        return f"{seconds}s"
    
    minutes = seconds // 60
    seconds %= 60
    
    if minutes < 60:
        if seconds > 0:
            return f"{minutes}m {seconds}s"
        return f"{minutes}m"
    
    hours = minutes // 60
    minutes %= 60
    
    if hours < 24:
        if minutes > 0:
            return f"{hours}h {minutes}m"
        return f"{hours}h"
    
    days = hours // 24
    hours %= 24
    
    if hours > 0:
        return f"{days}d {hours}h"
    return f"{days}d"


def format_speed(bytes_per_sec: float) -> str:
    """Format speed in bytes/sec to human-readable string.
    
    Args:
        bytes_per_sec: Speed in bytes per second.
        
    Returns:
        Human-readable string like "1.50 MB/s".
        
    Example:
        >>> format_speed(1536000)
        '1.50 MB/s'
    """
    return format_bytes(int(bytes_per_sec)) + "/s"


def truncate_text(text: str, max_length: int, suffix: str = "...") -> str:
    """Truncate text to maximum length.
    
    Args:
        text: Input text.
        max_length: Maximum length.
        suffix: Suffix to add if truncated.
        
    Returns:
        Truncated text.
        
    Example:
        >>> truncate_text("Hello World", 8)
        'Hello...'
    """
    if len(text) <= max_length:
        return text
    
    if max_length <= len(suffix):
        return suffix[:max_length]
    
    return text[: max_length - len(suffix)] + suffix


__all__ = [
    "format_bytes",
    "format_duration",
    "format_speed",
    "truncate_text",
]
