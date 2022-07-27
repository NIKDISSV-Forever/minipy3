import argparse
import ast
import os
import time
from pathlib import Path

from minipy3 import minimize


def parse_args():
    parser = argparse.ArgumentParser('minipy3')
    parser.add_argument('input', type=Path().glob, help='Input files rglob')
    parser.add_argument('-o', '--out', type=Path().glob, help='Output files rglob')
    parser.add_argument('--no-compress', action='store_false', default=True,
                        help="Don't use compression algorithms (lzma, zlib, gzip or bz2)")
    parser.add_argument('--unparse', action='store_true', help='Return from compressed to standard view')
    parser.add_argument('--no-suffix', action='store_false', default=True,
                        help='Add suffix to file name (max for --unparse else min)')
    return parser.parse_args()


def get_relative_path(from_path):
    cwd = os.getcwd()
    try:
        return from_path.relative_to(cwd)
    except ValueError:
        return from_path


def minimizer(mod, inpout, compress):
    for inp, out in inpout:
        with open(inp, encoding='UTF-8') as inp_f:
            raw = inp_f.read()
            if not raw:
                print('Empty input file.')
                continue
        with open(out, 'w', encoding='UTF-8') as out_f:
            compressed = mod(raw, compress)
            out_f.write(compressed)
        print(
            f"{get_relative_path(inp)}{f' -> {get_relative_path(out)}'} | Compressing level {1.0 - len(compressed) / len(raw):.3%}")


def main():
    args = parse_args()
    suf = '.min'
    mod = minimize
    if args.unparse:
        suf = '.max'

        def mod(code, compress):
            if compress:
                try:
                    consts = compile(code, '', 'exec').co_consts
                    return ast.unparse(ast.parse(__import__(consts[0]).decompress(consts[1])))
                except Exception:
                    pass
            return f'{ast.unparse(ast.parse(code)).strip()}\n'
    if not args.no_suffix:
        suf = ''
    input = args.input
    output = args.out
    zipped = zip(input, output) if output else ((inp, inp.with_stem(inp.stem + suf)) for inp in input)
    st = time.perf_counter()
    minimizer(mod, zipped, args.no_compress)
    print(f'Total time = {time.perf_counter() - st:g}s')


if __name__ == '__main__':
    main()
