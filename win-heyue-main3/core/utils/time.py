"""
Time utilities for Shanghai timezone (Asia/Shanghai, UTC+8)

All business logic uses Asia/Shanghai timezone for:
- Daily quota calculation and reset
- Batch date calculation
- Log timestamps

This ensures consistent business day boundaries at Shanghai midnight (00:00:00+08:00).
"""

from datetime import datetime, timedelta, timezone
from zoneinfo import ZoneInfo

# Shanghai timezone using zoneinfo (handles DST if ever applicable)
# Note: China hasn't used Daylight Saving Time since 1991
SHANGHAI_TZ = ZoneInfo("Asia/Shanghai")

# Legacy alias for backward compatibility
CN_TZ = timezone(timedelta(hours=8))


def now_shanghai() -> datetime:
    """
    Get current time in Shanghai timezone (Asia/Shanghai).
    
    Returns:
        datetime: Current time with Asia/Shanghai timezone info
        
    Example:
        >>> dt = now_shanghai()
        >>> dt.tzinfo.key
        'Asia/Shanghai'
    """
    return datetime.now(tz=SHANGHAI_TZ)


def format_dt_shanghai(dt: datetime) -> str:
    """
    Format datetime to ISO8601 string with +08:00 timezone offset.
    
    Args:
        dt: datetime object (if naive, assumes UTC)
        
    Returns:
        str: ISO8601 formatted string with +08:00 offset
        
    Example:
        >>> dt = datetime(2026, 1, 15, 16, 0, 0, tzinfo=timezone.utc)
        >>> format_dt_shanghai(dt)
        '2026-01-16T00:00:00+08:00'
    """
    if dt.tzinfo is None:
        # Assume naive datetime is UTC
        dt = dt.replace(tzinfo=timezone.utc)
    
    # Convert to Shanghai timezone
    dt_shanghai = dt.astimezone(SHANGHAI_TZ)
    return dt_shanghai.isoformat()


def shanghai_local_date(dt: datetime = None) -> str:
    """
    Get the local date string (YYYY-MM-DD) in Shanghai timezone.
    
    Args:
        dt: datetime object (if None, uses current time; if naive, assumes UTC)
        
    Returns:
        str: Date string in YYYY-MM-DD format according to Shanghai timezone
        
    Example:
        >>> # At 2026-01-15T23:30:00Z (UTC)
        >>> dt = datetime(2026, 1, 15, 23, 30, 0, tzinfo=timezone.utc)
        >>> shanghai_local_date(dt)
        '2026-01-16'  # Next day in Shanghai
    """
    if dt is None:
        dt = now_shanghai()
    elif dt.tzinfo is None:
        # Assume naive datetime is UTC
        dt = dt.replace(tzinfo=timezone.utc)
    
    # Convert to Shanghai timezone
    dt_shanghai = dt.astimezone(SHANGHAI_TZ)
    return dt_shanghai.strftime("%Y-%m-%d")


def utc_to_shanghai(dt_utc: datetime) -> datetime:
    """
    Convert UTC datetime to Shanghai timezone.
    
    Args:
        dt_utc: datetime in UTC (if naive, assumes UTC)
        
    Returns:
        datetime: Same moment in Shanghai timezone
        
    Example:
        >>> dt_utc = datetime(2026, 1, 15, 16, 0, 0, tzinfo=timezone.utc)
        >>> dt_sh = utc_to_shanghai(dt_utc)
        >>> dt_sh.hour
        0  # Midnight in Shanghai
    """
    if dt_utc.tzinfo is None:
        dt_utc = dt_utc.replace(tzinfo=timezone.utc)
    
    return dt_utc.astimezone(SHANGHAI_TZ)


# Legacy functions for backward compatibility
def now_cn():
    """Legacy function - use now_shanghai() instead"""
    return datetime.now(tz=CN_TZ)


def today_cn_str():
    """Legacy function - use shanghai_local_date() instead"""
    return now_cn().strftime("%Y-%m-%d")
