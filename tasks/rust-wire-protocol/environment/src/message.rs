use serde::Serialize;

use crate::field::Field;

#[derive(Debug, Clone, Serialize)]
pub struct Header {
    pub magic: u8,
    pub version: u8,
    pub msg_type: u8,
    pub field_count: u8,
}

#[derive(Debug, Clone, Serialize)]
pub struct Message {
    pub header: Header,
    pub fields: Vec<Field>,
    pub crc_valid: bool,
}
