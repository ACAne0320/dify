"""
Simple cron expression parser and next execution time calculator
to replace croniter dependency.

This module supports basic cron expressions with the following fields:
* minute (0-59)
* hour (0-23)
* day of month (1-31)
* month (1-12)
* day of week (0-6, 0=Sunday)

Supported special characters:
* *: any value
* ,: value list separator (e.g., "1,3,5")
* -: range of values (e.g., "1-5")
* /: step values (e.g., "*/5")

Example expressions:
* "* * * * *": every minute
* "0 * * * *": every hour at minute 0
* "0 0 * * *": every day at midnight
* "0 0 * * 0": every Sunday at midnight
* "0 0 1 * *": first day of every month at midnight
* "*/15 * * * *": every 15 minutes
"""

from datetime import datetime, timedelta


def validate_cron_expression(cron_expression: str) -> bool:
    """
    Validates if a cron expression is correctly formatted.

    Args:
        cron_expression: The cron expression to validate

    Returns:
        bool: True if the expression is valid, False otherwise

    Raises:
        ValueError: If the cron expression is invalid
    """
    # Split the expression into its components
    parts = cron_expression.strip().split()
    if len(parts) != 5:
        raise ValueError(
            f"Cron expression must have 5 parts (minute, hour, day of month, month, day of week), got {len(parts)}"
        )

    # Field ranges
    ranges = [
        (0, 59),  # minute
        (0, 23),  # hour
        (1, 31),  # day of month
        (1, 12),  # month
        (0, 6),  # day of week
    ]

    # Validate each field
    for i, (part, (min_val, max_val)) in enumerate(zip(parts, ranges)):
        # If it's just an asterisk, it's valid
        if part == "*":
            continue

        # Handle step values (*/n)
        if part.startswith("*/"):
            step = part[2:]
            if not step.isdigit():
                raise ValueError(f"Step value must be a number in field {i + 1}: {part}")
            step_int = int(step)
            if step_int < 1:
                raise ValueError(f"Step value must be at least 1 in field {i + 1}: {part}")
            continue

        # Handle ranges and lists
        for value_part in part.split(","):
            # Handle ranges (a-b)
            if "-" in value_part:
                start, end = value_part.split("-")
                if not start.isdigit() or not end.isdigit():
                    raise ValueError(f"Range values must be numbers in field {i + 1}: {value_part}")
                start_int = int(start)
                end_int = int(end)
                if start_int < min_val or end_int > max_val or start_int > end_int:
                    raise ValueError(
                        f"Range values in field {i + 1} must be between {min_val}-{max_val} and in \
                        ascending order: {value_part}"
                    )
            # Handle steps within ranges (a-b/n)
            elif "/" in value_part:
                range_part, step = value_part.split("/")

                # Parse the range part
                if range_part == "*":
                    range_start, range_end = min_val, max_val
                elif "-" in range_part:
                    start_str, end_str = range_part.split("-")
                    if not start_str.isdigit() or not end_str.isdigit():
                        raise ValueError(f"Range values must be numbers in field {i + 1}: {value_part}")
                    range_start, range_end = int(start_str), int(end_str)
                else:
                    raise ValueError(f"Invalid range format in field {i + 1}: {value_part}")

                # Validate the range
                if range_start < min_val or range_end > max_val or range_start > range_end:
                    raise ValueError(
                        f"Range values in field {i + 1} must be between {min_val}-{max_val} and "
                        f"in ascending order: {value_part}"
                    )

                # Validate the step
                if not step.isdigit():
                    raise ValueError(f"Step value must be a number in field {i + 1}: {value_part}")
                step_int = int(step)
                if step_int < 1:
                    raise ValueError(f"Step value must be at least 1 in field {i + 1}: {value_part}")
            # Handle single values
            else:
                if not value_part.isdigit():
                    raise ValueError(f"Value must be a number in field {i + 1}: {value_part}")
                val_int = int(value_part)
                if val_int < min_val or val_int > max_val:
                    raise ValueError(f"Value in field {i + 1} must be between {min_val}-{max_val}: {value_part}")

    return True


def _parse_cron_field(field: str, min_val: int, max_val: int) -> list[int]:
    """Parse a cron field and return the list of matching values."""
    if field == "*":
        return list(range(min_val, max_val + 1))

    result = []

    # Handle comma-separated values
    for part in field.split(","):
        if "-" in part:
            # Handle ranges (a-b)
            start, end = map(int, part.split("-"))
            result.extend(range(start, end + 1))
        elif part.startswith("*/"):
            # Handle steps (*/n)
            step = int(part[2:])
            result.extend(range(min_val, max_val + 1, step))
        elif "/" in part:
            # Handle ranges with steps (a-b/n)
            range_part, step_part = part.split("/")
            step = int(step_part)

            if range_part == "*":
                range_values = list(range(min_val, max_val + 1))
            else:
                start, end = map(int, range_part.split("-"))
                range_values = list(range(start, end + 1))

            result.extend(range_values[::step])
        else:
            # Handle single values
            result.append(int(part))

    return sorted(set(result))


def get_next_cron_time(cron_expression: str, dt: datetime) -> datetime:
    """
    Calculate the next execution time based on a cron expression and a starting datetime.

    Args:
        cron_expression: The cron expression in format "minute hour day_of_month month day_of_week"
        dt: The base datetime to calculate from

    Returns:
        datetime: The next execution time
    """
    # Parse the cron expression into its components
    parts = cron_expression.strip().split()
    if len(parts) != 5:
        raise ValueError("Invalid cron expression format")

    minute_expr, hour_expr, day_expr, month_expr, weekday_expr = parts

    # Parse each field into a list of allowed values
    minutes = _parse_cron_field(minute_expr, 0, 59)
    hours = _parse_cron_field(hour_expr, 0, 23)
    days = _parse_cron_field(day_expr, 1, 31)
    months = _parse_cron_field(month_expr, 1, 12)
    weekdays = _parse_cron_field(weekday_expr, 0, 6)

    # Start from the next minute
    next_time = dt.replace(second=0, microsecond=0) + timedelta(minutes=1)

    # Try to find the next matching time
    for _ in range(1000):  # Limit iterations to prevent infinite loops
        # Check month
        if next_time.month not in months:
            # Move to the first day of the next matching month
            while next_time.month not in months:
                if next_time.month == 12:
                    next_time = next_time.replace(year=next_time.year + 1, month=1, day=1, hour=0, minute=0)
                else:
                    next_time = next_time.replace(month=next_time.month + 1, day=1, hour=0, minute=0)
            continue

        # Check day: either day of month or day of week must match
        day_of_month_matches = next_time.day in days
        day_of_week_matches = next_time.weekday() in [d % 7 for d in weekdays]

        if day_expr != "*" and weekday_expr != "*":
            # If both day fields are specified, either can match
            if not (day_of_month_matches or day_of_week_matches):
                next_time = next_time.replace(hour=0, minute=0) + timedelta(days=1)
                continue
        else:
            # Otherwise, both must match their respective expressions
            if (day_expr != "*" and not day_of_month_matches) or (weekday_expr != "*" and not day_of_week_matches):
                next_time = next_time.replace(hour=0, minute=0) + timedelta(days=1)
                continue

        # Check hour
        if next_time.hour not in hours:
            # Find the next matching hour
            found_hour = False
            for hour in hours:
                if hour > next_time.hour:
                    next_time = next_time.replace(hour=hour, minute=0)
                    found_hour = True
                    break

            if not found_hour:
                # No matching hour today, move to next day
                next_time = next_time.replace(hour=0, minute=0) + timedelta(days=1)
            continue

        # Check minute
        if next_time.minute not in minutes:
            # Find the next matching minute
            found_minute = False
            for minute in minutes:
                if minute > next_time.minute:
                    next_time = next_time.replace(minute=minute)
                    found_minute = True
                    break

            if not found_minute:
                # No matching minute in this hour, move to next hour
                next_time = next_time.replace(minute=0) + timedelta(hours=1)
            continue

        # If we get here, all parts match
        return next_time

    # If we exit the loop, something went wrong
    raise ValueError("Could not find a valid next execution time")


def calculate_next_run_time(cron_expression: str, timezone_str: str) -> datetime:
    """
    Calculate the next run time based on cron expression and timezone.

    This is a simplified replacement for croniter.get_next() functionality.

    Args:
        cron_expression (str): Cron expression
        timezone (str): Timezone string

    Returns:
        datetime: Next run time in UTC
    """
    import pytz

    # Get current time in the specified timezone
    timezone = pytz.timezone(timezone_str)
    now = datetime.now(timezone)

    # Calculate the next run time
    # Convert to naive datetime for our calculation function
    naive_now = now.replace(tzinfo=None)
    naive_next_run = get_next_cron_time(cron_expression, naive_now)

    # Convert back to timezone-aware datetime
    next_run = timezone.localize(naive_next_run)

    # Convert to UTC for storage
    next_run_utc = next_run.astimezone(pytz.UTC)

    return next_run_utc
