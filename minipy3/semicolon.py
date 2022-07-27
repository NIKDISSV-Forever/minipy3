from __future__ import annotations

import ast
import functools


class AddSemicolon(ast._Unparser):
    """Adds a semicolon where needed (see also ast.unparse)"""
    __slots__ = ()
    add_semicolon_after = {'Return', 'Delete', 'Assign', 'AugAssign', 'AnnAssign', 'Raise', 'Assert', 'Import',
                           'ImportFrom', 'Global', 'Nonlocal', 'Expr', 'Pass', 'Break', 'Continue'}

    def and_add(self, func):
        """
        Decorate visitor functions.
        Designed for class extensibility.
        """

        @functools.wraps(func)
        def wrapper(*args, **kwargs):
            res = func(*args, **kwargs)
            self.write(';')
            return res

        return wrapper

    def __init_subclass__(cls, **kwargs):
        """
        When inheriting a class,
        the ignore argument will exclude the specified sequence from the add_semicolon_after sequence.
        """
        ignore = kwargs.get('ignore', {*()})
        cls.add_semicolon_after ^= ignore

    def __init__(self, *args, **kwargs):
        """Applies the and_add decorator to visitor nodes specified by add_semicolon_after"""
        super().__init__(*args, **kwargs)
        for name in self.add_semicolon_after:
            name = f'visit_{name}'
            if hasattr(self, name):
                setattr(self, name, self.and_add(getattr(self, name)))


def add_semicolons(raw_code):
    return AddSemicolon().visit(ast.parse(raw_code))
