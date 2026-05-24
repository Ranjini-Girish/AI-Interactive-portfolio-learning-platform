use std::cmp::Ordering;

/// A wrapper for reverse-ordered comparison (min-heap from max-heap).
#[derive(Debug, Clone, Eq, PartialEq)]
#[allow(dead_code)]
pub struct Reverse<T>(pub T);

impl<T: Ord> Ord for Reverse<T> {
    fn cmp(&self, other: &Self) -> Ordering {
        other.0.cmp(&self.0)
    }
}

impl<T: Ord> PartialOrd for Reverse<T> {
    fn partial_cmp(&self, other: &Self) -> Option<Ordering> {
        Some(self.cmp(other))
    }
}

/// Priority level constants.
#[allow(dead_code)]
pub const PRIORITY_CRITICAL: i32 = 5;
#[allow(dead_code)]
pub const PRIORITY_HIGH: i32 = 4;
#[allow(dead_code)]
pub const PRIORITY_MEDIUM: i32 = 3;
#[allow(dead_code)]
pub const PRIORITY_LOW: i32 = 2;
#[allow(dead_code)]
pub const PRIORITY_MINIMAL: i32 = 1;

/// Check if a priority value is valid.
#[allow(dead_code)]
pub fn is_valid_priority(p: i32) -> bool {
    (PRIORITY_MINIMAL..=PRIORITY_CRITICAL).contains(&p)
}
