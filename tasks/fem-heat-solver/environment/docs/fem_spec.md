# FEM Heat Equation Specification

## Governing Equation

Solve the 2D steady-state heat equation:

    -k * (d²T/dx² + d²T/dy²) = Q

where:
- k = thermal conductivity (W/(m·K))
- T = temperature (K)
- Q = volumetric heat source (W/m²)

## Finite Element Formulation

### Element Stiffness Matrix

For a triangular element with nodes (x1,y1), (x2,y2), (x3,y3):

1. Compute the element area:
   A = 0.5 * |x1*(y2-y3) + x2*(y3-y1) + x3*(y1-y2)|

2. Compute shape function gradients:
   b1 = y2 - y3,  b2 = y3 - y1,  b3 = y1 - y2
   c1 = x3 - x2,  c2 = x1 - x3,  c3 = x2 - x1

3. Element stiffness matrix (3x3):
   Ke[i][j] = (k / (4*A)) * (b[i]*b[j] + c[i]*c[j])

### Element Load Vector

For uniform source Q over a triangle with area A:
   Fe[i] = Q * A / 3   for each node i

## Assembly

The global stiffness matrix K and load vector F are assembled by
adding each element's contributions to the appropriate global rows
and columns based on the element's node connectivity.

## Boundary Conditions

Dirichlet (fixed temperature) boundary conditions are applied by:
1. Setting K[i][i] = 1 and K[i][j] = 0 for all j != i
2. Setting F[i] = prescribed_value
3. For each non-boundary row j, subtracting K[j][i] * prescribed_value from F[j]
4. Setting K[j][i] = 0

This must be done AFTER full assembly of the global system.

## Linear Solver

Use the Conjugate Gradient (CG) method:
1. Initialize: r0 = F - K*x0, p0 = r0
2. Iterate:
   a. alpha = (r·r) / (p·K·p)
   b. x_new = x + alpha*p
   c. r_new = r - alpha*K*p
   d. beta = (r_new·r_new) / (r·r)
   e. p_new = r_new + beta*p
3. Converge when ||r|| < tolerance

### Jacobi Preconditioner

When using Jacobi preconditioning:
- M = diag(K)
- Solve M*z = r instead of using r directly
- z[i] = r[i] / K[i][i]
- Use z in place of r for computing beta and direction updates

## Output Format

The solution JSON must contain:
- "metadata": solver info, mesh stats, convergence data
- "node_temperatures": array of {node_id, x, y, temperature} sorted by node_id
- "element_data": array of {element_id, nodes, avg_temperature, heat_flux_x, heat_flux_y}
- "summary": min/max/mean temperature, total heat flux

### Heat Flux Computation

For each element, the heat flux is:
   qx = -k * (b1*T1 + b2*T2 + b3*T3) / (2*A)
   qy = -k * (c1*T1 + c2*T2 + c3*T3) / (2*A)

where b and c are the shape function gradients and T are node temperatures.

### Summary Statistics

- min_temperature: minimum over all node temperatures
- max_temperature: maximum over all node temperatures  
- mean_temperature: arithmetic mean of all node temperatures
- total_heat_flux_x: sum of element qx values
- total_heat_flux_y: sum of element qy values

All floating-point values rounded to output precision (6 decimal places).
