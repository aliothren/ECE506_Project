#!/usr/bin/env python3
"""Independent exact-integer FFN oracle and deterministic fixture generator."""
import argparse
import hashlib
import json
from pathlib import Path
import random
import struct

ROOT = Path(__file__).resolve().parents[1]


def quantize(value, relu=False):
    if relu:
        value = max(value, 0)
    magnitude, remainder = divmod(abs(value), 1024)
    magnitude += remainder >= 512
    rounded = -magnitude if value < 0 else magnitude
    return min(32767, max(-32768, rounded))


def layer(weights, bias, inputs, relu):
    n = len(inputs)
    return [quantize(sum(w*x for w, x in zip(weights[i*n:(i+1)*n], inputs))
                     + b*1024, relu) for i, b in enumerate(bias)]


def infer(params, inputs):
    hidden = layer(params[:8192], params[8192:8320], inputs, True)
    out = layer(params[8320:16512], params[16512:], hidden, False)
    return hidden, out


def write_i16(path, values):
    path.write_bytes(struct.pack('<' + 'h'*len(values), *values))


def cases():
    for seed in (506, 507, 508):
        rng = random.Random(seed)
        params = ([rng.randint(-128, 128) for _ in range(8192)]
                  + [rng.randint(-256, 256) for _ in range(128)]
                  + [rng.randint(-128, 128) for _ in range(8192)]
                  + [rng.randint(-256, 256) for _ in range(64)])
        inputs = [[rng.randint(-1024, 1024) for _ in range(64)] for _ in range(64)]
        yield f'random_{seed}', params, inputs
    yield 'zero', [0]*16576, [[0]*64, [-32768]*64, [32767]*64]
    params = [0]*16576
    params[8192:8320] = [(-1 if i % 2 else 1)*32767 for i in range(128)]
    params[16512:] = [-32768, 32767, -1, 1]*16
    yield 'bias_only', params, [[0]*64]
    params = [0]*16576
    for i in range(128):
        params[i*64 + i % 64] = 1024
    for i in range(64):
        params[8320+i*128+i] = 1024 if i % 2 else -1024
    yield 'routing', params, [[(i-32)*512 for i in range(64)]] + [
        [1024 if i == j else 0 for i in range(64)] for j in (0, 31, 63)]
    # Explicit full-range accumulation, including >32-bit sums and saturation.
    params = [32767]*8192 + [32767]*128
    params += [(-32768 if i % 2 else 32767) for i in range(64) for _ in range(128)]
    params += [0]*64
    yield 'extremes', params, [[32767]*64, [-32768]*64]
    params = [v for _ in range(128) for v in ([32767, -32767]*32)]
    params += [1]*128 + [v for _ in range(64) for v in ([32767, -32767]*64)] + [0]*64
    yield 'cancellation', params, [[32767]*64, [-32768]*64]
    # Products land just before, on, and after half-steps in both layers.
    params = [0]*16576
    for i in range(128):
        params[i*64] = (511, 512, 513, -511, -512, -513)[i % 6]
        params[8192+i] = 1
    for i in range(64):
        params[8320+i*128+1] = (255, 256, 257, -255, -256, -257)[i % 6]
    yield 'rounding', params, [[1]+[0]*63, [-1]+[0]*63]


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--output', type=Path, default=ROOT/'data')
    args = parser.parse_args()
    boundaries = {0:0, 511:0, 512:1, 513:1, -511:0, -512:-1, -513:-1,
                  32767*1024:32767, 32768*1024:32767, -32769*1024:-32768}
    for value, expected in boundaries.items():
        assert quantize(value) == expected
        assert quantize(value, True) == max(0, expected)
    args.output.mkdir(parents=True, exist_ok=True)
    index, descriptions = [], []
    for name, params, inputs in cases():
        assert len(params) == 16576
        folder = args.output/name
        folder.mkdir(exist_ok=True)
        hidden, outputs = [], []
        for x in inputs:
            h, z = infer(params, x)
            hidden.extend(h)
            outputs.extend(z)
        write_i16(folder/'params.bin', params)
        write_i16(folder/'input.bin', [v for x in inputs for v in x])
        write_i16(folder/'hidden.bin', hidden)
        write_i16(folder/'output.bin', outputs)
        index.append(f'{name} {len(inputs)}\n')
        descriptions.append({'name':name, 'inferences':len(inputs)})
    (args.output/'index.txt').write_text(''.join(index))
    hashes = {str(p.relative_to(args.output)):hashlib.sha256(p.read_bytes()).hexdigest()
              for p in sorted(args.output.rglob('*')) if p.is_file() and p.name != 'manifest.json'}
    manifest = {'format':'little-endian int16 raw / 1024', 'generator':'Python random.Random, randint',
                'seeds':[506,507,508], 'cases':descriptions, 'sha256':hashes}
    (args.output/'manifest.json').write_text(json.dumps(manifest, indent=2)+'\n')
    print(f'GOLDEN_PASS: {len(index)} parameter sets, {sum(c["inferences"] for c in descriptions)} inferences')


if __name__ == '__main__':
    main()
