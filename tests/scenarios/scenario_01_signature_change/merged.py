# Merged: Git combined both — Left's calculate_tax + Right's apply_discount
def calculate_tax(amount, region="US"):
    rates = {"US": 0.08, "EU": 0.20}
    return amount * rates.get(region, 0.10)

def apply_discount(price, discount):
    final = price - discount
    tax = calculate_tax(final)
    if tax > 50:
        final -= 5  # loyalty bonus for high-tax orders
    return final + tax
