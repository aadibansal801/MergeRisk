MAX_ITEMS = 50


def can_add_item(current_count):
    return current_count < MAX_ITEMS and current_count >= 0


def is_near_limit(current_count):
    return current_count >= MAX_ITEMS - 5
