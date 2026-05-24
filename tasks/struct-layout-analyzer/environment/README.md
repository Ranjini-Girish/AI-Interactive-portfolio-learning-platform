# Go Struct Layout Analyzer

A tool that computes memory layout for Go struct types on linux/amd64.

## Project Structure

- `cmd/analyzer/` - Main entry point
- `internal/layout/` - Layout computation engine
- `internal/parser/` - Go source file parsing
- `internal/types/` - Shared type definitions
- `internal/report/` - Output formatting
- `data/` - Input Go source files to analyze
- `config/` - Analyzer configuration
- `testdata/` - Sample files for development testing
