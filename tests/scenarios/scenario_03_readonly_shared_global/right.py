# Right: changes format_receipt to include tax line, now reads TAX_RATE
TAX_RATE = 0.10

def compute_tax(amount):
    return amount * TAX_RATE

def format_receipt(amount):
    tax_line = amount * TAX_RATE
    return f"Subtotal: {amount}\nTax: {tax_line}\nTotal: {amount + tax_line}"
