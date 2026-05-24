# Edge Cases & Special Handling

## Degenerate Polygons

A polygon is **degenerate** when its area falls below `min_polygon_area`
from `policy.json`. Note that the degenerate *finding* trigger and the
degenerate *orientation* label use different thresholds — consult the
algorithm specifications for each.

For centroid computation, the shoelace centroid formula divides by the
signed area; use the arithmetic mean of vertex coordinates as a fallback
when that divisor is too small to produce a stable result.

## Winding Direction

Polygons may be wound CW or CCW. The shoelace formula produces a
**negative** signed area for CW polygons. The `orientation` field must
reflect this: `"CW"` for negative, `"CCW"` for positive, `"degenerate"`
when |signed area| < epsilon.

Point-in-polygon must work correctly regardless of winding direction.

## Convexity vs. Simplicity

A polygon can have all-same-sign cross products (suggesting convexity)
while still being **self-intersecting** (e.g., a 5-pointed star drawn
vertex-to-vertex). A self-intersecting polygon is **never** convex.
Always check simplicity first.

## Collinear Hull Points

When `hull_collinear_rule` is `"exclude"`, collinear points on the
convex hull boundary must be removed. Only the extreme endpoints of
each collinear run remain.

## Duplicate Points

Two standalone points sharing the same coordinates (within rounding
to 10 decimal places) are flagged as `duplicate_points`. This finding
has a `null` polygon_id since it relates to standalone points, not
polygon geometry. When multiple distinct coordinates each appear more
than once, each generates its own finding.

## Self-Intersecting Polygons with Unusual Area

A self-intersecting polygon (e.g., a "bowtie" shape) can have a net
signed area of zero because its lobes cancel. The area and the
simplicity check are independent computations — evaluate each finding
type according to its own trigger condition without short-circuiting.

## Collinear Overlapping Segments

Two segments that are collinear and share a portion of their length
still count as intersecting. When the general cross-product formula
degenerates (both segments lie on the same line), fall back to
endpoint-on-segment checks to find a representative intersection
point.

## Floating-Point Thresholds

Area comparisons for degenerate findings must use the **raw computed
area**, not a rounded value. The various epsilon-based thresholds in
`policy.json` serve different purposes and should not be conflated.

## Minimum Enclosing Circle

Deduplicate points before running the enclosing circle algorithm.
Collinear points (three points on a line) degenerate the circumcircle
formula (denominator → 0); fall back to the circle defined by the
two farthest-apart points in that case.
