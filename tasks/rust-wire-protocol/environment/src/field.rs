use serde::Serialize;

#[derive(Debug, Clone, Serialize)]
pub struct Field {
    pub id: u8,
    pub type_name: String,
    pub value: FieldValue,
}

#[derive(Debug, Clone, Serialize)]
#[serde(untagged)]
pub enum FieldValue {
    Unsigned(u64),
    Signed(i64),
    Text(String),
    Binary(Vec<u8>),
    Nested(Vec<Field>),
}
