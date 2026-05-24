# C++ Project Structure

This directory contains a multi-target C++ project for linkage analysis.

## Layout

- `project/include/` — Header files (.h) with include guards
- `project/src/` — Source files (.cpp) with compilation units
- `project/build_targets.json` — Build target specifications
- `project/symbol_registry.json` — Symbol definitions and references per source file
- `project/dirty_files.json` — Recently modified files for rebuild analysis
- `project/policy.json` — Severity configuration for quality findings
