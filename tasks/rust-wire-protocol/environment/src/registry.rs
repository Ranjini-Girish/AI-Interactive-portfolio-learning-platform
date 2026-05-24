use crate::protocol::FieldType;

/// Static field type metadata for validation and introspection.
pub struct FieldTypeMeta {
    pub code: u8,
    pub name: &'static str,
    pub is_numeric: bool,
    pub is_signed: bool,
    pub is_variable: bool,
    pub byte_width: Option<usize>,
}

const FIELD_TYPE_TABLE: [FieldTypeMeta; 9] = [
    FieldTypeMeta {
        code: 0,
        name: "u8",
        is_numeric: true,
        is_signed: false,
        is_variable: false,
        byte_width: Some(1),
    },
    FieldTypeMeta {
        code: 1,
        name: "u16",
        is_numeric: true,
        is_signed: false,
        is_variable: false,
        byte_width: Some(2),
    },
    FieldTypeMeta {
        code: 2,
        name: "u32",
        is_numeric: true,
        is_signed: false,
        is_variable: false,
        byte_width: Some(4),
    },
    FieldTypeMeta {
        code: 3,
        name: "u64",
        is_numeric: true,
        is_signed: false,
        is_variable: false,
        byte_width: Some(8),
    },
    FieldTypeMeta {
        code: 4,
        name: "i32",
        is_numeric: true,
        is_signed: true,
        is_variable: false,
        byte_width: Some(4),
    },
    FieldTypeMeta {
        code: 5,
        name: "i64",
        is_numeric: true,
        is_signed: true,
        is_variable: false,
        byte_width: Some(8),
    },
    FieldTypeMeta {
        code: 6,
        name: "str",
        is_numeric: false,
        is_signed: false,
        is_variable: true,
        byte_width: None,
    },
    FieldTypeMeta {
        code: 7,
        name: "bytes",
        is_numeric: false,
        is_signed: false,
        is_variable: true,
        byte_width: None,
    },
    FieldTypeMeta {
        code: 8,
        name: "nested",
        is_numeric: false,
        is_signed: false,
        is_variable: true,
        byte_width: None,
    },
];

pub fn lookup(ft: FieldType) -> &'static FieldTypeMeta {
    &FIELD_TYPE_TABLE[ft as usize]
}

pub fn lookup_by_code(code: u8) -> Option<&'static FieldTypeMeta> {
    FIELD_TYPE_TABLE.iter().find(|m| m.code == code)
}

pub fn all_types() -> &'static [FieldTypeMeta] {
    &FIELD_TYPE_TABLE
}
