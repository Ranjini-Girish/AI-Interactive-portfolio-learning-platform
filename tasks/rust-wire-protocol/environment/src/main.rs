use std::env;
use std::fs;
use std::process;

use wire_protocol::hexutil;
use wire_protocol::parser;

fn main() {
    let args: Vec<String> = env::args().collect();
    if args.len() < 3 {
        eprintln!("Usage: wire-protocol <decode|encode> <input.json>");
        process::exit(1);
    }

    let command = &args[1];
    let input_path = &args[2];

    match command.as_str() {
        "decode" => decode_command(input_path),
        _ => {
            eprintln!("Unknown command: {}", command);
            process::exit(1);
        }
    }
}

fn decode_command(input_path: &str) {
    let raw = match fs::read_to_string(input_path) {
        Ok(s) => s,
        Err(e) => {
            eprintln!("Failed to read {}: {}", input_path, e);
            process::exit(1);
        }
    };

    let input: serde_json::Value = match serde_json::from_str(&raw) {
        Ok(v) => v,
        Err(e) => {
            eprintln!("Failed to parse JSON: {}", e);
            process::exit(1);
        }
    };

    let hex_messages = input["messages_hex"]
        .as_array()
        .expect("expected messages_hex array");

    let mut decoded_messages = Vec::new();

    for hex_val in hex_messages {
        let hex_str = hex_val.as_str().expect("expected hex string");
        let bytes = match hexutil::decode_hex(hex_str) {
            Ok(b) => b,
            Err(e) => {
                eprintln!("Hex decode error: {}", e);
                decoded_messages.push(serde_json::json!({"error": e.to_string()}));
                continue;
            }
        };

        match parser::parse_message(&bytes) {
            Ok(msg) => {
                decoded_messages.push(serde_json::json!({
                    "magic": msg.header.magic,
                    "version": msg.header.version,
                    "msg_type": msg.header.msg_type,
                    "field_count": msg.header.field_count,
                    "fields": msg.fields,
                    "crc_valid": msg.crc_valid,
                }));
            }
            Err(e) => {
                decoded_messages.push(serde_json::json!({"error": e.to_string()}));
            }
        }
    }

    let output = serde_json::json!({ "messages": decoded_messages });
    println!("{}", serde_json::to_string_pretty(&output).unwrap());
}
