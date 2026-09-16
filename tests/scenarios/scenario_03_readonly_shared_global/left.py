# Left: changes compute_tax to apply a cap, still reads TAX_RATE
TAX_RATE = 0.10

def compute_tax(amount):
    raw = amount * TAX_RATE
    return min(raw, 500)  # cap tax at 500

def format_receipt(amount):
    return f"Total: {amount}"
