use crate::error::ProtocolError;
use crate::hexutil;
use crate::message::Message;
use crate::parser;

/// Process multiple hex-encoded messages and return results.
pub fn decode_batch(hex_messages: &[String]) -> Vec<Result<Message, ProtocolError>> {
    hex_messages
        .iter()
        .map(|hex| {
            let bytes = hexutil::decode_hex(hex)?;
            parser::parse_message(&bytes)
        })
        .collect()
}

/// Process messages, skipping any that fail to parse.
pub fn decode_batch_lenient(hex_messages: &[String]) -> Vec<Message> {
    hex_messages
        .iter()
        .filter_map(|hex| {
            hexutil::decode_hex(hex)
                .ok()
                .and_then(|bytes| parser::parse_message(&bytes).ok())
        })
        .collect()
}

/// Decode with error collection.
pub fn decode_batch_with_errors(
    hex_messages: &[String],
) -> (Vec<Message>, Vec<(usize, ProtocolError)>) {
    let mut messages = Vec::new();
    let mut errors = Vec::new();
    for (i, hex) in hex_messages.iter().enumerate() {
        match hexutil::decode_hex(hex) {
            Ok(bytes) => match parser::parse_message(&bytes) {
                Ok(msg) => messages.push(msg),
                Err(e) => errors.push((i, e)),
            },
            Err(e) => errors.push((i, e)),
        }
    }
    (messages, errors)
}
