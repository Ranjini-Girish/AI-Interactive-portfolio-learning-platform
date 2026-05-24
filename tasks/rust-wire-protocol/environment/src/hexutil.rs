use crate::error::ProtocolError;

pub fn decode_hex(hex: &str) -> Result<Vec<u8>, ProtocolError> {
    let hex = hex.trim();
    if hex.len() % 2 != 0 {
        return Err(ProtocolError::InvalidHex("odd length".into()));
    }
    let mut bytes = Vec::with_capacity(hex.len() / 2);
    for i in (0..hex.len()).step_by(2) {
        let byte_str = &hex[i..i + 2];
        let byte = u8::from_str_radix(byte_str, 16)
            .map_err(|_| ProtocolError::InvalidHex(byte_str.into()))?;
        bytes.push(byte);
    }
    Ok(bytes)
}

pub fn encode_hex(data: &[u8]) -> String {
    data.iter().map(|b| format!("{:02x}", b)).collect()
}
