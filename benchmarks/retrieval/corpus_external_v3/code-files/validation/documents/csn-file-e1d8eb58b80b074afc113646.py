from typing import Callable, TypeVar, Iterable

A = TypeVar('Input')


def constant(x: A) -> Callable[..., A]:
    

    def constanted(*args, **kwargs):
        return x

    return constanted


def splat(f: Callable[..., A]) -> Callable[[Iterable], A]:
    

    def splatted(args):
        return f(*args)

    return splatted


def unsplat(f: Callable[[Iterable], A]) -> Callable[..., A]:
    

    def unsplatted(*args):
        return f(args)

    return unsplatted


__all__ = ['constant', 'splat', 'unsplat']
