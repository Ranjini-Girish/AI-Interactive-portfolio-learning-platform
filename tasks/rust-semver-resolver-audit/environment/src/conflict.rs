/// Cross-project conflict detection.
///
/// A conflict exists for a package when the intersection of constraints
/// across all projects that reference it is empty and each side can
/// individually resolve to a version.
pub struct ConflictDetector;
