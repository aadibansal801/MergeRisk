# Base: original tax calculation
def calculate_tax(amount):
    return amount * 0.10

def apply_discount(price, discount):
    final = price - discount
    tax = calculate_tax(final)
    return final + tax
