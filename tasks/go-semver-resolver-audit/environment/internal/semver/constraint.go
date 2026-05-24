package semver

// Constraint represents a version constraint (e.g., ^1.2.0, ~0.0.3, >=1.0.0 <2.0.0).
type Constraint struct {
	Raw string
}

// ParseConstraint parses a constraint string.
// TODO: implement
func ParseConstraint(s string) (Constraint, error) {
	return Constraint{Raw: s}, nil
}

// Match checks if a version satisfies this constraint.
// Must implement pre-release matching rules from SPEC.md §4.
// TODO: implement
func (c Constraint) Match(v Version) bool {
	return false
}
