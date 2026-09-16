# Merged: both additions combined, no interaction
def greet(name):
    return f"Hello, {name}"

def log_event(event_name, timestamp):
    return f"[{timestamp}] {event_name}"

def format_currency(amount, symbol="$"):
    return f"{symbol}{amount:.2f}"
