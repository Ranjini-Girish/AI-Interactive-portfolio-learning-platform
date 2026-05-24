package registry

// GetVersions returns all available versions for a package, sorted by precedence.
// TODO: implement
func (r *Registry) GetVersions(pkg string) []string {
	return nil
}

// GetDependencies returns the dependency map for a specific package version.
// TODO: implement
func (r *Registry) GetDependencies(pkg, version string) map[string]string {
	return nil
}
