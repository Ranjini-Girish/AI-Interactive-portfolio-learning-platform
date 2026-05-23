# Hash Family

`policy.hash_family` is fixed at the single value `"fnv1a_double_hashing"`.
The simulator MUST use exactly the recipe described here. Any other hash
function — even a different FNV-1a offset or prime — produces output that
fails the byte-exact comparison.

## Two FNV-1a 64-bit instances

The recipe uses two FNV-1a 64-bit instances with different seeds. Both run
the standard FNV-1a inner loop (XOR-then-multiply over the UTF-8 bytes of
the key string).

Instance A:
- `offset = 0xCBF29CE484222325`
- `prime  = 0x100000001B3`

Instance B:
- `offset = 0x84222325CBF29CE4`
- `prime  = 0x100000001B3`

Inner loop (identical for both, applied to the UTF-8 bytes of the key):

```
h = offset
for each byte b of the key as unsigned 64-bit:
    h = h XOR b
    h = h * prime          # 64-bit unsigned wrap-around
return h
```

Call `h_a = FNV1a_A(key)` and `h_b = FNV1a_B(key)`. Both are unsigned
64-bit values.

## Double hashing

The `k` Bloom filter positions for a key are computed from `h_a` and
`h_b` as:

```
position[i] = (h_a + i * h_b) mod m         for i = 0, 1, ..., k - 1
```

The arithmetic `h_a + i * h_b` is performed in unsigned 64-bit modular
arithmetic; the final `mod m` is the array index.

## Position multiset

The `k` positions are NOT deduplicated before they are applied to the
counter array. Two indices `i != j` whose `position[i] == position[j]`
both contribute their separate increments / decrements to that single
counter slot. This is the standard counting Bloom filter convention; it
is what makes counters ever go above 1 for a single `add` of a single
key.

## Worked example

For an empty key (the empty string `""`), the inner loop runs zero
iterations, so `h_a = 0xCBF29CE484222325` and
`h_b = 0x84222325CBF29CE4`. With `m = 16` and `k = 4` that yields
positions `[0xCBF29CE484222325 % 16, ..., (h_a + 3 * h_b) % 16] =
[5, 9, 13, 1]` (verified via Python:
`hex(0xCBF29CE484222325 % 16) == "0x5"`).

This worked example is also reproduced verbatim in
`/app/examples/` so the byte layout is unambiguous.
