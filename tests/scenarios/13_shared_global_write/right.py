inventory_count = 100

def restock():
    return 1

def sell():
    global inventory_count
    inventory_count += 1
