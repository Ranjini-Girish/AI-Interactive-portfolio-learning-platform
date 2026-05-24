CXX ?= g++
CXXFLAGS ?= -std=c++17 -O2 -Wall -Wextra -pedantic

.PHONY: build clean

build: bin/photo_audit

bin/photo_audit: src/photo_audit.cpp
	mkdir -p bin
	$(CXX) $(CXXFLAGS) $< -o $@

clean:
	rm -rf bin
