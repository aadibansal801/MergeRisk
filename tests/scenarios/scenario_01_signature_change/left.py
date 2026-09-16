# Left: changes calculate_tax signature (adds region param)
def calculate_tax(amount, region="US"):
    rates = {"US": 0.08, "EU": 0.20}
    return amount * rates.get(region, 0.10)

def apply_discount(price, discount):
    final = price - discount
    tax = calculate_tax(final)
    return final + tax
