use crate::field::{Field, FieldValue};

/// Tracks statistics about parsed messages.
#[derive(Default, Debug)]
pub struct ParseStats {
    pub messages_parsed: usize,
    pub fields_parsed: usize,
    pub nested_depth_max: usize,
    pub crc_failures: usize,
    pub bytes_processed: usize,
    pub type_counts: [usize; 9],
}

impl ParseStats {
    pub fn new() -> Self {
        Self::default()
    }

    pub fn record_field(&mut self, type_code: u8, fields: &[Field]) {
        self.fields_parsed += fields.len();
        for f in fields {
            if (type_code as usize) < self.type_counts.len() {
                self.type_counts[type_code as usize] += 1;
            }
            if let FieldValue::Nested(ref inner) = f.value {
                self.record_nested(inner, 1);
            }
        }
    }

    fn record_nested(&mut self, fields: &[Field], depth: usize) {
        if depth > self.nested_depth_max {
            self.nested_depth_max = depth;
        }
        self.fields_parsed += fields.len();
        for f in fields {
            if let FieldValue::Nested(ref inner) = f.value {
                self.record_nested(inner, depth + 1);
            }
        }
    }

    pub fn summary(&self) -> String {
        format!(
            "Messages: {}, Fields: {}, Max nesting: {}, CRC failures: {}",
            self.messages_parsed,
            self.fields_parsed,
            self.nested_depth_max,
            self.crc_failures
        )
    }
}
