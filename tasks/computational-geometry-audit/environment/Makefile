.PHONY: build clean run

CXX    ?= g++
CFLAGS := -std=c++17 -O2 -Wall
SRC    := geometry_audit.cpp
BIN    := /usr/local/bin/geometry_audit

build: $(BIN)

$(BIN): $(SRC)
	$(CXX) $(CFLAGS) -o $(BIN) $(SRC)

run: build
	geometry_audit /app

clean:
	rm -f $(BIN)
