use crate::field::{Field, FieldValue};
use crate::message::Message;
use std::fmt;

impl fmt::Display for Message {
    fn fmt(&self, f: &mut fmt::Formatter<'_>) -> fmt::Result {
        writeln!(
            f,
            "Message(type={}, version={}, fields={}, crc={})",
            self.header.msg_type,
            self.header.version,
            self.fields.len(),
            if self.crc_valid { "OK" } else { "FAIL" }
        )?;
        for field in &self.fields {
            writeln!(f, "  {}", field)?;
        }
        Ok(())
    }
}

impl fmt::Display for Field {
    fn fmt(&self, f: &mut fmt::Formatter<'_>) -> fmt::Result {
        write!(f, "Field(id={}, type={}, value=", self.id, self.type_name)?;
        match &self.value {
            FieldValue::Unsigned(v) => write!(f, "{}", v)?,
            FieldValue::Signed(v) => write!(f, "{}", v)?,
            FieldValue::Text(s) => write!(f, "\"{}\"", s)?,
            FieldValue::Binary(b) => write!(f, "<{} bytes>", b.len())?,
            FieldValue::Nested(fields) => write!(f, "<{} nested fields>", fields.len())?,
        }
        write!(f, ")")
    }
}
