use crate::protocol;

/// Semantic version of the protocol implementation.
pub const IMPL_VERSION: (u8, u8, u8) = (1, 0, 0);

/// Check if a message version byte is compatible with this implementation.
pub fn is_compatible(msg_version: u8) -> bool {
    msg_version == protocol::VERSION
}

/// Returns the minimum message version supported by this implementation.
pub fn min_supported() -> u8 {
    protocol::VERSION
}

/// Returns the maximum message version supported by this implementation.
pub fn max_supported() -> u8 {
    protocol::VERSION
}

pub fn format_version() -> String {
    format!("{}.{}.{}", IMPL_VERSION.0, IMPL_VERSION.1, IMPL_VERSION.2)
}
