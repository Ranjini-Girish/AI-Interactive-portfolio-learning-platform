# Monte Carlo Estimator Audit

Numerical integration benchmark comparing four Monte Carlo methods across
ten mathematical test functions at multiple sample sizes.

## Layout

- `data/functions/` — JSON definitions for each test function
- `data/samples/`   — Pre-generated uniform random sample sets
- `config/`         — Method configuration and audit parameters
- `docs/`           — Algorithm specifications
- `src/mc/`         — Java source stubs

## Building

Requires JDK 21+.  Compile from `/app`:

    javac -d build src/mc/*.java

Run:

    java -cp build mc.Main
