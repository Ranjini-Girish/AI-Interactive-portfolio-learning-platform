CXX      := g++
CXXFLAGS := -std=c++17 -O2 -Wall -Wextra -Wpedantic
SRC      := decay_audit.cpp
BIN      := /usr/local/bin/decay_audit

.PHONY: all build run clean

all: build

build:
	$(CXX) $(CXXFLAGS) $(SRC) -o $(BIN)

run: build
	$(BIN)

clean:
	rm -f $(BIN)
