def calculate_total(price, quantity):
    return price * quantity


def print_invoice(price, quantity):
    total = calculate_total(price, quantity)
    print(f"Total: {total}")
