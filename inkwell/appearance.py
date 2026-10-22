"""Text size and zoom levels, kept free of GTK so they are easy to test."""

DEFAULT_FONT_SIZE = 12  # points
MIN_FONT_SIZE = 6
MAX_FONT_SIZE = 48

DEFAULT_ZOOM = 100  # percent
ZOOM_LEVELS = (50, 67, 75, 80, 90, 100, 110, 125, 150, 175, 200)


def clamp_font_size(value):
    try:
        value = int(round(float(value)))
    except (TypeError, ValueError):
        return DEFAULT_FONT_SIZE
    return max(MIN_FONT_SIZE, min(MAX_FONT_SIZE, value))


def clamp_zoom(value):
    """Snap a stored zoom to the nearest offered level."""
    try:
        value = float(value)
    except (TypeError, ValueError):
        return DEFAULT_ZOOM
    return min(ZOOM_LEVELS, key=lambda level: abs(level - value))


def zoom_in(value):
    value = clamp_zoom(value)
    return next((level for level in ZOOM_LEVELS if level > value), ZOOM_LEVELS[-1])


def zoom_out(value):
    value = clamp_zoom(value)
    return next((level for level in reversed(ZOOM_LEVELS) if level < value), ZOOM_LEVELS[0])
