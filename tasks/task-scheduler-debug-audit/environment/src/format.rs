/// Format a duration in milliseconds to a human-readable string.
#[allow(dead_code)]
pub fn format_duration(ms: u64) -> String {
    if ms < 1000 {
        format!("{}ms", ms)
    } else if ms < 60000 {
        format!("{:.1}s", ms as f64 / 1000.0)
    } else {
        let minutes = ms / 60000;
        let seconds = (ms % 60000) / 1000;
        format!("{}m {}s", minutes, seconds)
    }
}

/// Format a ratio as a percentage string.
#[allow(dead_code)]
pub fn format_percentage(ratio: f64) -> String {
    format!("{:.1}%", ratio * 100.0)
}

/// Pad a string to a minimum width with spaces.
#[allow(dead_code)]
pub fn pad_right(s: &str, width: usize) -> String {
    if s.len() >= width {
        s.to_string()
    } else {
        format!("{}{}", s, " ".repeat(width - s.len()))
    }
}

/// Truncate a string to a maximum length, adding "..." if truncated.
#[allow(dead_code)]
pub fn truncate(s: &str, max_len: usize) -> String {
    if s.len() <= max_len {
        s.to_string()
    } else if max_len > 3 {
        format!("{}...", &s[..max_len - 3])
    } else {
        s[..max_len].to_string()
    }
}
