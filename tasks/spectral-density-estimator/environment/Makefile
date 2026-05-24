CXX       = g++
CXXFLAGS  = -std=c++17 -O2 -Wall -Wextra
LDFLAGS   = -lm

SRCS = src/main.cpp src/csv_reader.cpp src/fft.cpp src/window.cpp \
       src/welch.cpp src/peak_detect.cpp src/statistics.cpp src/json_writer.cpp

OBJS = $(SRCS:.cpp=.o)
TARGET = spectral_analyzer

.PHONY: all clean

all: $(TARGET)

$(TARGET): $(OBJS)
	$(CXX) $(CXXFLAGS) -o $@ $^ $(LDFLAGS)

%.o: %.cpp
	$(CXX) $(CXXFLAGS) -c -o $@ $<

clean:
	rm -f $(OBJS) $(TARGET)
