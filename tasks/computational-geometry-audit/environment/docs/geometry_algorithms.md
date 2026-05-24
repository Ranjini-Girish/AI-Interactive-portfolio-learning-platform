# Geometry Algorithm Specifications

## Polygon Properties

### Signed Area (Shoelace Formula)

For a polygon with vertices `(x₀,y₀), (x₁,y₁), …, (xₙ₋₁,yₙ₋₁)`:

    A_signed = 0.5 × Σᵢ (xᵢ × yᵢ₊₁ − xᵢ₊₁ × yᵢ)

where indices wrap modulo n. Positive means counter-clockwise (CCW),
negative means clockwise (CW). Report `area` as the absolute value.

### Orientation

`"CCW"` when signed area > 0, `"CW"` when signed area < 0,
`"degenerate"` when |signed area| < epsilon.

### Perimeter

Sum of Euclidean distances between consecutive vertices (wrapping).

### Centroid

    Cₓ = (1/(6A)) × Σᵢ (xᵢ + xᵢ₊₁)(xᵢ yᵢ₊₁ − xᵢ₊₁ yᵢ)
    Cᵧ = (1/(6A)) × Σᵢ (yᵢ + yᵢ₊₁)(xᵢ yᵢ₊₁ − xᵢ₊₁ yᵢ)

where A is the **signed** area. When the signed area is too small
for stable division, fall back to the arithmetic mean of vertices.

### Convexity Check

A polygon is convex if and only if it is **simple** (non-self-
intersecting) AND all cross products of consecutive edge pairs have
the same sign. Collinear edges (cross product ≈ 0) are ignored for the
sign check, but a self-intersecting polygon is **never** convex
regardless of its cross-product pattern.

### Self-Intersection (Simplicity) Check

A polygon is **simple** (non-self-intersecting) if no two non-adjacent
edges intersect, except at shared endpoints. Check all pairs of
non-adjacent edges. Two edges sharing a single vertex do not count as
an intersection at that vertex.

## Point-in-Polygon

Use the **ray casting** algorithm. Cast a horizontal ray from the query
point to +∞ and count edge crossings.

**Boundary handling**: before ray casting, check whether the point lies
exactly on any polygon edge (within epsilon). If it does, report
`"boundary"`. The `boundary_rule` in `policy.json` determines whether
boundary points count as inside; when `"inclusive"`, report `"boundary"`
(distinct from `"inside"` and `"outside"`).

Points on polygon **vertices** are also `"boundary"`.

## Convex Hull

Use Andrew's monotone chain or equivalent. Sort points
lexicographically, build lower then upper hull.

When `policy.json → hull_collinear_rule` is `"exclude"`, use a
**strict** left-turn test so that collinear points on the hull boundary
are excluded from the vertex list.

Report hull vertices in CCW order starting from the lexicographically
smallest point.

## Line Segment Intersection

For each pair of segments, compute whether they intersect. Two segments
intersect if their interiors cross **or** if an endpoint of one lies on
the other. Report the intersection point.

When two segments are collinear and overlap, the general cross-product
intersection formula degenerates. Fall back to endpoint-on-segment
checks and report the first such point found.

Sort results by `(segment_a, segment_b)`.

## Closest Pair

Find the closest pair among the scene's **standalone `points`** only
(polygon vertices are not included). Brute-force O(n²) is acceptable
for the given data sizes. Report the pair with smallest Euclidean
distance. Break ties by choosing the pair with the smallest
`(point_a_idx, point_b_idx)`.

## Minimum Enclosing Circle

Compute the smallest circle containing all points (polygon vertices and
standalone points). Deduplicate points before computing. Use Welzl's
algorithm or brute-force all 2-point and 3-point defining subsets.

## Findings

| Finding type                  | Triggered when                                |
|-------------------------------|-----------------------------------------------|
| `self_intersecting_polygon`   | Polygon is not simple                         |
| `degenerate_polygon`          | Polygon area < `min_polygon_area`             |
| `duplicate_points`            | Two standalone points share identical coords  |

Sort findings by `(severity_rank, finding_type, polygon_id)`.
