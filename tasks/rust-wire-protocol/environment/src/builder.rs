use crate::field::{Field, FieldValue};
use crate::serializer;

pub struct MessageBuilder {
    msg_type: u8,
    fields: Vec<Field>,
}

impl MessageBuilder {
    pub fn new(msg_type: u8) -> Self {
        MessageBuilder {
            msg_type,
            fields: Vec::new(),
        }
    }

    pub fn add_u8(mut self, id: u8, value: u8) -> Self {
        self.fields.push(Field {
            id,
            type_name: "u8".into(),
            value: FieldValue::Unsigned(value as u64),
        });
        self
    }

    pub fn add_u16(mut self, id: u8, value: u16) -> Self {
        self.fields.push(Field {
            id,
            type_name: "u16".into(),
            value: FieldValue::Unsigned(value as u64),
        });
        self
    }

    pub fn add_u32(mut self, id: u8, value: u32) -> Self {
        self.fields.push(Field {
            id,
            type_name: "u32".into(),
            value: FieldValue::Unsigned(value as u64),
        });
        self
    }

    pub fn add_u64(mut self, id: u8, value: u64) -> Self {
        self.fields.push(Field {
            id,
            type_name: "u64".into(),
            value: FieldValue::Unsigned(value),
        });
        self
    }

    pub fn add_i32(mut self, id: u8, value: i32) -> Self {
        self.fields.push(Field {
            id,
            type_name: "i32".into(),
            value: FieldValue::Signed(value as i64),
        });
        self
    }

    pub fn add_i64(mut self, id: u8, value: i64) -> Self {
        self.fields.push(Field {
            id,
            type_name: "i64".into(),
            value: FieldValue::Signed(value),
        });
        self
    }

    pub fn add_str(mut self, id: u8, value: &str) -> Self {
        self.fields.push(Field {
            id,
            type_name: "str".into(),
            value: FieldValue::Text(value.to_string()),
        });
        self
    }

    pub fn add_bytes(mut self, id: u8, value: Vec<u8>) -> Self {
        self.fields.push(Field {
            id,
            type_name: "bytes".into(),
            value: FieldValue::Binary(value),
        });
        self
    }

    pub fn build(self) -> Vec<u8> {
        serializer::serialize_message(self.msg_type, &self.fields)
    }
}
