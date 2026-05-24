# Boundary Condition Application

## Dirichlet Boundary Conditions

When applying Dirichlet (fixed-value) boundary conditions to the
assembled global system K*T = F, the standard elimination method
is used. The detailed procedure is specified in `fem_spec.md`
section "Boundary Conditions".

The implementation must correctly handle the interaction between
the boundary nodes and interior nodes to preserve the accuracy
of the interior solution.
