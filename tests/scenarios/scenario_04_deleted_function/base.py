# Base: helper function used by process_order
def validate_coupon(code):
    valid = {"SAVE10", "SAVE20", "VIP"}
    return code in valid

def process_order(items, coupon_code):
    discount = 0
    if validate_coupon(coupon_code):
        discount = 10
    return sum(items) - discount
