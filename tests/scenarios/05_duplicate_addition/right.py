def existing_helper():
    return True


def validate_input(data):
    return isinstance(data, dict) and len(data) > 0
