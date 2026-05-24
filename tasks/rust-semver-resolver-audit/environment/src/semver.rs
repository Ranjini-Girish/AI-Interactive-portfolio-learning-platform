/// Semantic version representation and comparison.
#[derive(Debug, Clone)]
pub struct Version {
    pub major: u64,
    pub minor: u64,
    pub patch: u64,
    pub pre: Vec<PreRelease>,
    pub build: Vec<String>,
}

#[derive(Debug, Clone)]
pub enum PreRelease {
    Numeric(u64),
    Alpha(String),
}

/// A parsed version constraint (operator + target version).
#[derive(Debug, Clone)]
pub struct Constraint {
    pub operator: ConstraintOp,
    pub version: Version,
}

#[derive(Debug, Clone)]
pub enum ConstraintOp {
    Caret,
    Tilde,
    Exact,
}
