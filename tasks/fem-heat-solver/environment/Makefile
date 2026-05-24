CXX = g++
CXXFLAGS = -std=c++17 -O2 -Wall
SRCDIR = src
SOURCES = $(SRCDIR)/main.cpp $(SRCDIR)/mesh.cpp $(SRCDIR)/assembly.cpp $(SRCDIR)/solver.cpp $(SRCDIR)/output.cpp
TARGET = fem_solver

.PHONY: build clean run

build: $(TARGET)

$(TARGET): $(SOURCES)
	$(CXX) $(CXXFLAGS) -o $@ $^

clean:
	rm -f $(TARGET)

run: build
	./$(TARGET)
