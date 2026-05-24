package semver

import "sort"

// Sort sorts versions by precedence (lowest first).
// TODO: implement
func Sort(versions []Version) {
	sort.Slice(versions, func(i, j int) bool {
		return Compare(versions[i], versions[j]) < 0
	})
}
