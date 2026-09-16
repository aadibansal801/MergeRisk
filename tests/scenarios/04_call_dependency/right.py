def get_discount(is_member):
    return 0.1 if is_member else 0.0


def apply_discount(price, is_member):
    discount = get_discount(is_member)
    return price * (1 - discount)
