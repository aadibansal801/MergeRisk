# Right: adds a completely independent string formatter
def greet(name):
    return f"Hello, {name}"

def format_currency(amount, symbol="$"):
    return f"{symbol}{amount:.2f}"
