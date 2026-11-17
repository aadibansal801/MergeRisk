def recur(n, offset):
    if n <= 0:
        return offset
    print(n)
    return recur(n - 1)
