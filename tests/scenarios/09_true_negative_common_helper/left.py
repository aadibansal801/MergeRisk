def log(message):
    print(f"[LOG] {message}")


def process_order(order_id):
    log(f"Processing order {order_id}")
    return order_id > 0
