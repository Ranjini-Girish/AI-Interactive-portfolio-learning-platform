package resolver

// Request represents a resolution request.
type Request struct {
	ID          string
	Constraints map[string]string
}

// Result represents the outcome of a resolution attempt.
type Result struct {
	RequestID string
	Status    string
	Resolved  []ResolvedPackage
	Conflicts []Conflict
	Stats     Stats
}

// ResolvedPackage is a successfully resolved dependency.
type ResolvedPackage struct {
	Name              string
	Version           string
	Depth             int
	RequestedBy       []string
	ConstraintSources map[string]string
}

// Conflict describes an unresolvable constraint set.
type Conflict struct {
	Package     string
	Constraints map[string]string
	Reason      string
}

// Stats contains resolution statistics.
type Stats struct {
	TotalResolved   int
	TotalConflicts  int
	MaxDepth        int
	ResolutionOrder []string
}
