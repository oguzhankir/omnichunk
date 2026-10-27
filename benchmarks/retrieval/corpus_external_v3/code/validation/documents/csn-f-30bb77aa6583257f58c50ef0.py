def splat(f: Callable[..., A]) -> Callable[[Iterable], A]:
    

    def splatted(args):
        return f(*args)

    return splatted
