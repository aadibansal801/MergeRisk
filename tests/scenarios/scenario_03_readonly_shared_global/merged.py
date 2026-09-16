# Merged: both changes combined
TAX_RATE = 0.10

def compute_tax(amount):
    raw = amount * TAX_RATE
    return min(raw, 500)

def format_receipt(amount):
    tax_line = amount * TAX_RATE
    return f"Subtotal: {amount}\nTax: {tax_line}\nTotal: {amount + tax_line}"
