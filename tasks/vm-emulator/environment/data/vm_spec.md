# VM Specification

## Architecture

The VM has 8 general-purpose registers R0–R7 (32-bit signed integers, initially 0), byte-addressable memory (initially zero, size from `config.json`), and a stack pointer (SP) starting at `stack_start` growing downward. Four boolean flags — Z (zero), N (negative), V (overflow), E (error) — all start false. E is sticky: once set it stays set for the rest of that program's execution. Memory stores 32-bit values in little-endian byte order.

## Program Format

Each `.json` file in `programs/` has `name` (string) and `instructions` (array of `{"op","args"}`). An arg is either a register name string `"R0"`–`"R7"` or an integer immediate. Execute starting at PC=0; each instruction increments PC by 1 unless a jump/call/ret redirects it. Each executed instruction is one cycle. Stop on HALT (status `halted`) or when cycles exceed `max_cycles` (status `timeout`).

## Instruction Set

| Instruction | Args | Action | Flags Set |
|---|---|---|---|
| MOV | dst, src | dst = src | — |
| ADD | dst, src | dst += src (two's complement wrap) | Z N V |
| SUB | dst, src | dst -= src (two's complement wrap) | Z N V |
| MUL | dst, src | dst = low32(dst * src) | Z N |
| DIV | dst, src | dst = trunc(dst / src) signed toward zero | Z N (or E if src=0) |
| MOD | dst, src | dst = dst % src signed toward zero | Z N (or E if src=0) |
| AND | dst, src | dst &= src | Z N |
| OR | dst, src | dst \|= src | Z N |
| XOR | dst, src | dst ^= src | Z N |
| NOT | dst | dst = ~dst | Z N |
| SHL | dst, amt | dst <<= amt (logical left shift) | Z N |
| SHR | dst, amt | dst = (uint32)dst >> amt (**logical** right shift, fills with zeros) | Z N |
| CMP | a, b | compute a − b for flags only, no destination write | Z N V |
| JMP | target | PC = target | — |
| JZ | target | if Z: PC = target | — |
| JNZ | target | if !Z: PC = target | — |
| JG | target | if !Z and N==V: PC = target | — |
| JL | target | if N!=V: PC = target | — |
| JGE | target | if N==V: PC = target | — |
| JLE | target | if Z or N!=V: PC = target | — |
| PUSH | src | if SP<4: set E; else SP-=4, write 32-bit LE at mem[SP] | E on error |
| POP | dst | if SP>=memory_size: set E, leave dst unchanged; else read 32-bit LE from mem[SP], SP+=4 | E on error |
| CALL | target | push PC+1, then set PC=target | E on error |
| RET | — | pop into PC | E on error |
| LOAD | dst, addr | if addr<0 or addr+3>=memory_size: set E, leave dst unchanged; else dst=mem32_LE[addr] | E on error |
| STORE | src, addr | if addr<0 or addr+3>=memory_size: set E; else write mem32_LE[addr]=src | E on error |
| HALT | — | stop execution | — |
| NOP | — | no operation | — |

## Flag Semantics

- **Z (zero):** true if the result is zero.
- **N (negative):** true if the result is negative (bit 31 set).
- **V (overflow):** true if signed overflow occurred. Only set by ADD, SUB, and CMP.
- **E (error):** set on any error condition. Sticky — once set, stays set.

Each instruction updates only the flags listed in the table above. Unlisted flags are preserved.

## Overflow and Wrapping

V is set when the mathematical signed result exceeds the 32-bit signed range (greater than 2147483647 or less than -2147483648). The stored result wraps via two's complement.

## Division and Modulo

DIV and MOD use signed truncation toward zero (C++ semantics). On division by zero: set E, leave the destination register unchanged, do NOT update Z or N flags.

## Shift Operations

SHL is a logical left shift. SHR is a **logical** (unsigned) right shift — vacated bits are filled with zeros, not sign-extended. This means SHR of a negative number produces a positive result.

## Error Handling

On any error (division by zero, stack overflow/underflow, memory out of bounds), the faulting instruction is treated as a no-op (except for setting E and appending to the error log). Execution continues at PC+1.

Error types:
- `division_by_zero` — DIV or MOD with a zero divisor
- `stack_overflow` — PUSH or CALL when SP < 4
- `stack_underflow` — POP or RET when SP >= memory_size
- `memory_out_of_bounds` — LOAD or STORE when addr < 0 or addr+3 >= memory_size
