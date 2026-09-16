# Base: two functions that both read a config global
TAX_RATE = 0.10

def compute_tax(amount):
    return amount * TAX_RATE

def format_receipt(amount):
    return f"Total: {amount}"
