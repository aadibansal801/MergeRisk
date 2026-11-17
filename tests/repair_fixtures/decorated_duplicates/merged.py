def decorate(fn): return fn

@decorate
def f(): return 1

@decorate
def f(): return 1
