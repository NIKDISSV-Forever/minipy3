from __future__ import annotations
import ast, bz2, gzip, lzma, math, textwrap, zlib
from ast import _Precedence
from contextlib import contextmanager
from decimal import Decimal
from string import whitespace
from textwrap import dedent
from minipy3.semicolon import AddSemicolon, add_semicolons

__all__ = ('Minimize', 'minimize', 'AddSemicolon', 'add_semicolons')


def _get_indent(line):
    return len(line) - len(textwrap.dedent(line))


class Minimize(AddSemicolon, ignore={'Import'}):
    """Class based on ast._Unparse for code compression (see ast.unparse)"""
    __slots__ = ()
    _indent_mem = 0
    blocks = (
        'try', 'else', 'finally', 'except', 'except*', 'class', 'def', '@', 'if', 'elif', 'while', 'with', 'match',
        'for',
        'async')

    def items_view(self, traverser, items):
        if len(items) == 1:
            traverser(items[0])
            self.write(',')
        else:
            self.interleave(lambda: self.write(','), traverser, items)

    def fill(self, text=''):
        if text and text.strip().split()[0] in self.blocks or self._indent != self._indent_mem or (
                self._source and self._source[-1] == ':'):
            self.maybe_newline()
            self._indent_mem = self._indent
            self.write(' ' * self._indent)
        self.write(text)

    @contextmanager
    def delimit(self, start, end):
        if self._source and start.strip() == '(':
            self._source[-1] = self._source[-1].rstrip(' ')
        self.write(start)
        yield
        self.write(end)

    def get_type_comment(self, node):
        comment = self._type_ignores.get(node.lineno) or node.type_comment
        if comment is not None:
            return f'#type:{comment}'

    def traverse(self, node):
        if isinstance(node, list):
            for item in node:
                self.traverse(item)
        else:
            if self.import_names and self.import_names[-1] is not None and (node.__class__.__name__ != 'Import'):
                self.import_names.append(None)
                self.fill('import ')
                self.interleave(lambda: self.write(','), self.traverse, [i for i in self.import_names if i])
                self.write(';')
                self.import_names.clear()
            ast.NodeVisitor.visit(self, node)

    def visit(self, node):
        self._source = []
        self.traverse(node)
        return self.post_process(''.join(self._source))

    @staticmethod
    def post_process(source):
        lines = [line.rstrip(whitespace + ';') for line in source.splitlines()]
        ls2 = len(lines) - 2
        to_del = []
        for i in [i for i, l in enumerate(lines) if l.endswith(':')]:
            line = lines[i]
            back_line = lines[i + 1]
            try:
                next_line = lines[i + 2]
            except IndexError:
                next_line = ''
            it_line_tabs = _get_indent(line)
            if i != ls2 and (it_line_tabs >= _get_indent(back_line) or it_line_tabs < _get_indent(next_line)):
                continue
            lines[i] += back_line.strip()
            to_del.append(i + 1)
        offset = 0
        for i in to_del:
            i -= offset
            del lines[i]
            offset += 1
        return '\n'.join(lines)

    def visit_Constant(self, node):
        value = node.value
        if isinstance(value, tuple):
            with self.delimit('(', ')'):
                self.items_view(self._write_constant, value)
        elif isinstance(value, float):
            self.write('0.' if (short := str(Decimal(str(value))).strip('0')) == '.' else short)
        elif isinstance(value, int):
            if value >= 10**5 and (not math.log10(value) % 1):
                power_10 = int(math.log10(value))
                self.traverse(ast.BinOp(ast.Num(10), ast.Pow(), ast.Num(power_10)))
            elif value >= 2**17 and (not math.log2(value) % 1):
                power_2 = int(math.log2(value))
                self.traverse(ast.BinOp(ast.Num(2), ast.Pow(), ast.Num(power_2)))
            else:
                self.write(repr(value))
        elif value is ...:
            self.write('...')
        else:
            if node.kind == 'u':
                self.write('u')
            self._write_constant(node.value)

    def visit_FunctionType(self, node):
        with self.delimit('(', ')'):
            self.interleave(lambda: self.write(','), self.traverse, node.argtypes)
        self.write('->')
        self.traverse(node.returns)

    def visit_NamedExpr(self, node):
        with self.require_parens(_Precedence.NAMED_EXPR, node):
            self.set_precedence(_Precedence.ATOM, node.target, node.value)
            self.traverse(node.target)
            self.write(':=')
            self.traverse(node.value)

    import_names = []

    def visit_Import(self, node):
        self.import_names.extend(node.names)

    def visit_ImportFrom(self, node):
        self.fill('from ')
        self.write('.' * node.level)
        if node.module:
            self.write(node.module)
        self.write(' import ')
        self.interleave(lambda: self.write(','), self.traverse, node.names)

    def visit_Assign(self, node):
        self.fill()
        for target in node.targets:
            self.set_precedence(_Precedence.TUPLE, target)
            self.traverse(target)
            self.write('=')
        self.traverse(node.value)
        type_comment = self.get_type_comment(node)
        if type_comment:
            self.write(type_comment)

    def visit_AugAssign(self, node):
        self.fill()
        self.traverse(node.target)
        self.write(self.binop[node.op.__class__.__name__] + '=')
        self.traverse(node.value)

    def visit_AnnAssign(self, node):
        self.fill()
        with self.delimit_if('(', ')', not node.simple and isinstance(node.target, ast.Name)):
            self.traverse(node.target)
        self.write(':')
        self.traverse(node.annotation)
        if node.value:
            self.write('=')
            self.traverse(node.value)

    unop = {'Invert': '~', 'Not': 'not', 'UAdd': '+', 'USub': '-'}
    unop_precedence = {'not': _Precedence.NOT, '~': _Precedence.FACTOR, '+': _Precedence.FACTOR,
                       '-': _Precedence.FACTOR}

    def visit_Return(self, node):
        self.fill('return')
        if node.value:
            if (not isinstance(node.value, ast.Constant) or node.value.value is not ...) and (
                    not isinstance(node.value, ast.UnaryOp) or isinstance(node.value.op, ast.Not)):
                self.write(' ')
            self.traverse(node.value)

    def visit_Delete(self, node):
        self.fill('del ')
        self.interleave(lambda: self.write(','), self.traverse, node.targets)

    def visit_Assert(self, node):
        self.fill('assert ')
        self.traverse(node.test)
        if node.msg:
            self.write(',')
            self.traverse(node.msg)

    def visit_Global(self, node):
        self.fill('global ')
        self.interleave(lambda: self.write(','), self.write, node.names)

    def visit_Nonlocal(self, node):
        self.fill('nonlocal ')
        self.interleave(lambda: self.write(','), self.write, node.names)

    def visit_ClassDef(self, node):
        for deco in node.decorator_list:
            self.fill('@')
            self.traverse(deco)
        self.fill('class ' + node.name)
        with self.delimit_if('(', ')', condition=node.bases or node.keywords):
            comma = False
            for e in node.bases:
                if comma:
                    self.write(',')
                else:
                    comma = True
                self.traverse(e)
            for e in node.keywords:
                if comma:
                    self.write(',')
                else:
                    comma = True
                self.traverse(e)
        with self.block():
            self._write_docstring_and_traverse_body(node)

    def _function_helper(self, node, fill_suffix):
        for deco in node.decorator_list:
            self.fill('@')
            self.traverse(deco)
        def_str = fill_suffix + ' ' + node.name
        self.fill(def_str)
        with self.delimit('(', ')'):
            self.traverse(node.args)
        if node.returns:
            self.write('->')
            self.traverse(node.returns)
        with self.block(extra=self.get_type_comment(node)):
            self._write_docstring_and_traverse_body(node)

    def visit_With(self, node):
        self.fill('with ')
        self.interleave(lambda: self.write(','), self.traverse, node.items)
        with self.block(extra=self.get_type_comment(node)):
            self.traverse(node.body)

    def visit_AsyncWith(self, node):
        self.fill('async with ')
        self.interleave(lambda: self.write(','), self.traverse, node.items)
        with self.block(extra=self.get_type_comment(node)):
            self.traverse(node.body)

    def _write_str_avoiding_backslashes(self, string, _=None):
        self.write(repr(dedent(string).strip('\n')))

    def _write_docstring(self, node):
        self.fill()
        if node.kind == 'u':
            self.write('u')
        self._write_str_avoiding_backslashes(node.value)
        self.write(';')

    def visit_List(self, node):
        with self.delimit('[', ']'):
            self.interleave(lambda: self.write(','), self.traverse, node.elts)

    def visit_DictComp(self, node):
        with self.delimit('{', '}'):
            self.traverse(node.key)
            self.write(':')
            self.traverse(node.value)
            for gen in node.generators:
                self.traverse(gen)

    def visit_Set(self, node):
        if node.elts:
            with self.delimit('{', '}'):
                self.interleave(lambda: self.write(','), self.traverse, node.elts)
        else:
            self.write('{*()}')

    def visit_Dict(self, node):

        def write_key_value_pair(k, v):
            self.traverse(k)
            self.write(':')
            self.traverse(v)

        def write_item(item):
            k, v = item
            if k is None:
                self.write('**')
                self.set_precedence(_Precedence.EXPR, v)
                self.traverse(v)
            else:
                write_key_value_pair(k, v)

        with self.delimit('{', '}'):
            self.interleave(lambda: self.write(','), write_item, zip(node.keys, node.values))

    def visit_BinOp(self, node):
        operator = self.binop[node.op.__class__.__name__]
        operator_precedence = self.binop_precedence[operator]
        with self.require_parens(operator_precedence, node):
            if operator in self.binop_rassoc:
                left_precedence = operator_precedence.next()
                right_precedence = operator_precedence
            else:
                left_precedence = operator_precedence
                right_precedence = operator_precedence.next()
            self.set_precedence(left_precedence, node.left)
            self.traverse(node.left)
            self.write(operator)
            self.set_precedence(right_precedence, node.right)
            self.traverse(node.right)

    cmpops = {'Eq': '==', 'NotEq': '!=', 'Lt': '<', 'LtE': '<=', 'Gt': '>', 'GtE': '>=', 'Is': ' is ',
              'IsNot': ' is not ', 'In': ' in ', 'NotIn': ' not in '}

    def visit_Compare(self, node):
        with self.require_parens(_Precedence.CMP, node):
            self.set_precedence(_Precedence.CMP.next(), node.left, *node.comparators)
            self.traverse(node.left)
            for o, e in zip(node.ops, node.comparators):
                self.write(self.cmpops[o.__class__.__name__])
                self.traverse(e)

    def visit_Call(self, node):
        self.set_precedence(_Precedence.ATOM, node.func)
        self.traverse(node.func)
        with self.delimit('(', ')'):
            comma = False
            for e in node.args:
                if comma:
                    self.write(',')
                else:
                    comma = True
                self.traverse(e)
            for e in node.keywords:
                if comma:
                    self.write(',')
                else:
                    comma = True
                self.traverse(e)

    def visit_arg(self, node):
        self.write(node.arg)
        if node.annotation:
            self.write(':')
            self.traverse(node.annotation)

    def visit_arguments(self, node):
        first = True
        all_args = node.posonlyargs + node.args
        defaults = [None] * (len(all_args) - len(node.defaults)) + node.defaults
        for index, elements in enumerate(zip(all_args, defaults), 1):
            a, d = elements
            if first:
                first = False
            else:
                self.write(',')
            self.traverse(a)
            if d:
                self.write('=')
                self.traverse(d)
            if index == len(node.posonlyargs):
                self.write(',/')
        if node.vararg or node.kwonlyargs:
            if first:
                first = False
            else:
                self.write(',')
            self.write('*')
            if node.vararg:
                self.write(node.vararg.arg)
                if node.vararg.annotation:
                    self.write(':')
                    self.traverse(node.vararg.annotation)
        if node.kwonlyargs:
            for a, d in zip(node.kwonlyargs, node.kw_defaults):
                self.write(',')
                self.traverse(a)
                if d:
                    self.write('=')
                    self.traverse(d)
        if node.kwarg:
            if not first:
                self.write(',')
            self.write('**' + node.kwarg.arg)
            if node.kwarg.annotation:
                self.write(':')
                self.traverse(node.kwarg.annotation)

    def visit_keyword(self, node):
        if node.arg is None:
            self.write('**')
        else:
            self.write(node.arg)
            self.write('=')
        self.traverse(node.value)

    def visit_Lambda(self, node):
        with self.require_parens(_Precedence.TEST, node):
            self.write('lambda')
            with self.buffered() as buffer:
                self.traverse(node.args)
            if buffer:
                self.write(' ', *buffer)
            self.write(':')
            self.set_precedence(_Precedence.TEST, node.body)
            self.traverse(node.body)

    def visit_MatchSequence(self, node):
        with self.delimit('[', ']'):
            self.interleave(lambda: self.write(','), self.traverse, node.patterns)

    def visit_MatchMapping(self, node):

        def write_key_pattern_pair(pair):
            k, p = pair
            self.traverse(k)
            self.write(':')
            self.traverse(p)

        with self.delimit('{', '}'):
            keys = node.keys
            self.interleave(lambda: self.write(','), write_key_pattern_pair, zip(keys, node.patterns, strict=True))
            rest = node.rest
            if rest is not None:
                if keys:
                    self.write(',')
                self.write(f'**{rest}')

    def visit_MatchClass(self, node):
        self.set_precedence(_Precedence.ATOM, node.cls)
        self.traverse(node.cls)
        with self.delimit('(', ')'):
            patterns = node.patterns
            self.interleave(lambda: self.write(','), self.traverse, patterns)
            attrs = node.kwd_attrs
            if attrs:

                def write_attr_pattern(pair):
                    attr, pattern = pair
                    self.write(f'{attr}=')
                    self.traverse(pattern)

                if patterns:
                    self.write(',')
                self.interleave(lambda: self.write(','), write_attr_pattern, zip(attrs, node.kwd_patterns, strict=True))

    def visit_MatchOr(self, node):
        with self.require_parens(_Precedence.BOR, node):
            self.set_precedence(_Precedence.BOR.next(), *node.patterns)
            self.interleave(lambda: self.write('|'), self.traverse, node.patterns)


def minimize(raw_code, compress=True, compress_required=False):
    """
    Minimizes the passed code with the help of the Minimizer class;
    And if necessary or gives more compression, applies one of the compression algorithms: (lzma, zlib, gzip, bz2)
    """
    minimized = Minimize().visit(ast.parse(raw_code)).strip(f'{whitespace};')
    codes = min((raw_code, minimized), key=len)
    encoded = minimized.encode()
    if compress_required:
        codes = f"exec(__import__('lzma').decompress({lzma.compress(encoded, lzma.FORMAT_ALONE)!r}))"
        compress = True
    if compress:
        for mod in (lzma, zlib, gzip, bz2):
            if len((_val := f'exec(__import__({mod.__name__!r}).decompress({mod.compress(encoded)!r}))')) < len(codes):
                codes = _val
        return _val if len(
            (_val := f"exec(__import__('lzma').decompress({lzma.compress(encoded, lzma.FORMAT_ALONE)!r}))")) < len(
            codes) else codes
    return codes
