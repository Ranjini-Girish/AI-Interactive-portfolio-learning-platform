package registry

// Registry holds all known packages and their versions.
type Registry struct {
	Packages map[string]Package
}

// Package contains all published versions.
type Package struct {
	Versions map[string]VersionInfo
}

// VersionInfo contains the dependencies for a specific version.
type VersionInfo struct {
	Dependencies map[string]string
}

// Load reads the registry from a JSON file.
// TODO: implement
func Load(path string) (*Registry, error) {
	return nil, nil
}
