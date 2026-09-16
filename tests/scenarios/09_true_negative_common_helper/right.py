def log(message):
    print(f"[LOG] {message}")


def process_order(order_id):
    log(f"Processing order {order_id}")
    return True


def cancel_order(order_id):
    log(f"Cancelling order {order_id}")
    return True
