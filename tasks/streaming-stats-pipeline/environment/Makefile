.PHONY: build clean run

CXX    ?= g++
CFLAGS := -std=c++17 -O2 -Wall
SRC    := pipeline_audit.cpp
BIN    := /usr/local/bin/pipeline_audit

build: $(BIN)

$(BIN): $(SRC)
	$(CXX) $(CFLAGS) -o $(BIN) $(SRC)

run: build
	pipeline_audit /app

clean:
	rm -f $(BIN)
