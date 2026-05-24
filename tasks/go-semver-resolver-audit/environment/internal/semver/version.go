package semver

// Version represents a parsed semantic version.
type Version struct {
	Major      int
	Minor      int
	Patch      int
	Prerelease []Identifier
	Build      string
}

// Identifier is a single pre-release identifier (numeric or string).
type Identifier struct {
	IsNumeric bool
	NumVal    int
	StrVal    string
}
