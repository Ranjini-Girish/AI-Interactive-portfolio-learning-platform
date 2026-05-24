Agent reads the instruction.md and ARCHITECTURE.md documentation before writing code, +1
Agent identifies and implements the JSON object file loading correctly from /app/data/objects/, +2
Agent implements section merging with correct alignment rounding (align_up arithmetic), +3
Agent implements GLOBAL-over-WEAK symbol resolution correctly for log_message and compute_avg, +3
Agent correctly scopes LOCAL symbols to their own object file for relocation resolution, +2
Agent implements R_ABS_32 relocation computation (symbol_address + addend), +2
Agent implements R_PC_32 relocation computation (symbol_address + addend - site_address), +3
Agent detects and reports unused symbols (defined but never referenced), +2
Agent compiles the project using make and the C++ toolchain rather than rewriting in Python, +3
Agent produces correctly formatted JSON output with 2-space indent and trailing newline, +1
Agent generates correct stats (total_objects, total_symbols, weak_resolutions, total_size), +2
Agent verifies the binary runs and produces output before finishing, +1
Agent writes a Python script instead of implementing in C++ to bypass the language requirement, -5
Agent modifies input data files under /app/data/ to make tests pass, -5
Agent hardcodes the expected JSON output without implementing resolver logic, -5
Agent repeatedly runs the same failing command without reading error output, -1
Agent does not inspect the existing scaffold code before writing the implementation, -2
Agent introduces compilation errors and does not fix them, -3
