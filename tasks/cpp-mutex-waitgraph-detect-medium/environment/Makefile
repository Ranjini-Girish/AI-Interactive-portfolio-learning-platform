CXX ?= g++
CXXFLAGS ?= -std=c++17 -O2 -Wall -Wextra
PREFIX ?= /usr/local
SRC_DIR ?= /app/src
INC_DIR ?= /app/include
BIN := $(PREFIX)/bin/mtxgraph

.PHONY: build clean

build: $(BIN)

$(BIN): $(SRC_DIR)/main.cpp $(INC_DIR)/types.hpp
	$(CXX) $(CXXFLAGS) -I$(INC_DIR) $(SRC_DIR)/main.cpp -o $(BIN)

clean:
	rm -f $(BIN)
