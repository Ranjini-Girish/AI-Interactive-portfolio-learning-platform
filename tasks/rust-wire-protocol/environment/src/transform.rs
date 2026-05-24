use crate::field::{Field, FieldValue};
use crate::message::Message;

/// Apply post-processing transformations to a parsed message.
pub fn normalize(msg: &mut Message) {
    flatten_nested_ids(&mut msg.fields, 0);
}

fn flatten_nested_ids(fields: &mut [Field], depth: u8) {
    for field in fields.iter_mut() {
        if depth > 0 {
            field.id = field.id.wrapping_add(depth * 100);
        }
        if let FieldValue::Nested(ref mut inner) = field.value {
            flatten_nested_ids(inner, depth + 1);
        }
    }
}

pub fn filter_by_type<'a>(msg: &'a Message, type_name: &str) -> Vec<&'a Field> {
    msg.fields
        .iter()
        .filter(|f| f.type_name == type_name)
        .collect()
}

pub fn count_fields_recursive(fields: &[Field]) -> usize {
    let mut count = fields.len();
    for f in fields {
        if let FieldValue::Nested(ref inner) = f.value {
            count += count_fields_recursive(inner);
        }
    }
    count
}

pub fn extract_numeric_values(fields: &[Field]) -> Vec<i64> {
    let mut values = Vec::new();
    for f in fields {
        match &f.value {
            FieldValue::Unsigned(v) => values.push(*v as i64),
            FieldValue::Signed(v) => values.push(*v),
            FieldValue::Nested(inner) => {
                values.extend(extract_numeric_values(inner));
            }
            _ => {}
        }
    }
    values
}
