# FEM Heat Equation Solver

A C++ finite element method solver for the 2D steady-state heat equation
on triangular meshes.

## Building

```
make build
```

## Running

```
./fem_solver
```

Reads mesh from `/app/data/mesh.json` and config from `/app/data/config.json`.
Writes solution to `/app/output/solution.json`.

## Source Files

- `src/main.cpp` - Entry point
- `src/mesh.h/cpp` - Mesh data loading and parsing
- `src/assembly.h/cpp` - FEM stiffness matrix and load vector assembly
- `src/solver.h/cpp` - Conjugate gradient solver with Jacobi preconditioner
- `src/output.h/cpp` - Solution output formatting
