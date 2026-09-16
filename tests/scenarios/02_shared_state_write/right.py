inventory_count = 100


def restock(amount):
    global inventory_count
    inventory_count += amount


def sell(amount):
    global inventory_count
    inventory_count -= amount
    if inventory_count < 0:
        inventory_count = 0
