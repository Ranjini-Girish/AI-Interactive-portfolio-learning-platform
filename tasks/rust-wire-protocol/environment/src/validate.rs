use crate::message::Message;
use crate::protocol;

pub fn validate_message(msg: &Message) -> Vec<String> {
    let mut errors = Vec::new();

    if msg.header.magic != protocol::MAGIC {
        errors.push(format!("invalid magic: 0x{:02X}", msg.header.magic));
    }

    if msg.header.version != protocol::VERSION {
        errors.push(format!("unsupported version: {}", msg.header.version));
    }

    if !msg.crc_valid {
        errors.push("CRC checksum mismatch".into());
    }

    if msg.fields.len() != msg.header.field_count as usize {
        errors.push(format!(
            "field count mismatch: header says {}, got {}",
            msg.header.field_count,
            msg.fields.len()
        ));
    }

    errors
}
