def recur(n, offset):
    if n <= 0:
        return offset
    return recur(n - 1)
