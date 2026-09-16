def calculate_total(price, quantity, tax_rate):
    return price * quantity * (1 + tax_rate)


def print_invoice(price, quantity):
    total = calculate_total(price, quantity)
    print(f"Total: {total}")
