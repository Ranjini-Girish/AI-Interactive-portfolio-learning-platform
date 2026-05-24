.PHONY: all build release run fmt check clean

all: release

release:
	cargo build --release

build: release

run:
	cargo run --release

fmt:
	cargo fmt

check:
	cargo check

clean:
	rm -rf target/
