# Right: changes apply_discount to depend on calculate_tax result
def calculate_tax(amount):
    return amount * 0.10

def apply_discount(price, discount):
    final = price - discount
    tax = calculate_tax(final)
    if tax > 50:
        final -= 5  # loyalty bonus for high-tax orders
    return final + tax
