inventory_count = 100


def restock(amount):
    global inventory_count
    inventory_count += amount


def sell(amount):
    global inventory_count
    inventory_count -= amount
