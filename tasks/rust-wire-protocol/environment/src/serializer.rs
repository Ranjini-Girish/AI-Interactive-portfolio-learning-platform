use crate::crc32;
use crate::field::{Field, FieldValue};
use crate::protocol;

pub fn serialize_message(msg_type: u8, fields: &[Field]) -> Vec<u8> {
    let mut buf = Vec::new();

    buf.push(protocol::MAGIC);
    buf.push(protocol::VERSION);
    buf.push(msg_type);
    buf.push(fields.len() as u8);

    for field in fields {
        serialize_field(&mut buf, field);
    }

    let crc = crc32::crc32(&buf);
    buf.extend_from_slice(&crc.to_le_bytes());

    buf
}

fn serialize_field(buf: &mut Vec<u8>, field: &Field) -> () {
    buf.push(field.id);

    match &field.value {
        FieldValue::Unsigned(val) => {
            let type_byte = match field.type_name.as_str() {
                "u8" => {
                    buf.push(0);
                    buf.push(*val as u8);
                    return;
                }
                "u16" => {
                    buf.push(1);
                    buf.extend_from_slice(&(*val as u16).to_le_bytes());
                    return;
                }
                "u32" => {
                    buf.push(2);
                    buf.extend_from_slice(&(*val as u32).to_le_bytes());
                    return;
                }
                "u64" => {
                    buf.push(3);
                    buf.extend_from_slice(&val.to_le_bytes());
                    return;
                }
                _ => 0,
            };
            buf.push(type_byte);
        }
        FieldValue::Signed(val) => match field.type_name.as_str() {
            "i32" => {
                buf.push(4);
                buf.extend_from_slice(&(*val as i32).to_le_bytes());
            }
            "i64" => {
                buf.push(5);
                buf.extend_from_slice(&val.to_le_bytes());
            }
            _ => {
                buf.push(5);
                buf.extend_from_slice(&val.to_le_bytes());
            }
        },
        FieldValue::Text(s) => {
            buf.push(6);
            let bytes = s.as_bytes();
            buf.extend_from_slice(&(bytes.len() as u16).to_le_bytes());
            buf.extend_from_slice(bytes);
        }
        FieldValue::Binary(data) => {
            buf.push(7);
            buf.extend_from_slice(&(data.len() as u16).to_le_bytes());
            buf.extend_from_slice(data);
        }
        FieldValue::Nested(nested_fields) => {
            buf.push(8);
            let mut nested_buf = Vec::new();
            for nf in nested_fields {
                serialize_field(&mut nested_buf, nf);
            }
            buf.extend_from_slice(&(nested_buf.len() as u32).to_le_bytes());
            buf.extend_from_slice(&nested_buf);
        }
    }
}
