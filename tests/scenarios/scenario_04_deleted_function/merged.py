# Merged: Git combines Left's deletion with Right's unchanged code.
# validate_coupon is gone, but process_order from Right still calls it.
def process_order(items, coupon_code):
    discount = 0
    if validate_coupon(coupon_code):
        discount = 10
    return sum(items) - discount
