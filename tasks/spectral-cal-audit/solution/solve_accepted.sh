#!/usr/bin/env bash
# Oracle solution: writes the canonical C++17 reference implementation under
# /app/src + /app/Makefile, then builds and runs /app/build/calibrate.
#
# This is the *expected* level of detail for a passing submission — agents
# may structure their tree differently, as long as `make` from /app builds
# /app/build/calibrate and that binary writes the documented outputs.
set -euo pipefail

APP_ROOT="${APP_ROOT:-/app}"
export APP_ROOT
mkdir -p "$APP_ROOT/src" "$APP_ROOT/build" "$APP_ROOT/output"
cd "$APP_ROOT"

# ---------------------------------------------------------------------------
# Makefile
# ---------------------------------------------------------------------------
cat > Makefile <<'MAKEFILE'
CXX      ?= g++
CXXFLAGS ?= -std=c++17 -O2 -Wall -Wextra -Wpedantic -Werror

SRCS := $(wildcard src/*.cpp)
OBJS := $(patsubst src/%.cpp,build/%.o,$(SRCS))

.PHONY: all clean
all: build/calibrate

build/calibrate: $(OBJS) | build
	$(CXX) $(CXXFLAGS) -o $@ $(OBJS)

build/%.o: src/%.cpp | build
	$(CXX) $(CXXFLAGS) -Isrc -c $< -o $@

build:
	@mkdir -p build

clean:
	rm -rf build
MAKEFILE

# ---------------------------------------------------------------------------
# src/json.hpp -- minimal JSON parser interface (no dependencies)
# ---------------------------------------------------------------------------
cat > src/json.hpp <<'HPP'
#pragma once
#include <cstddef>
#include <map>
#include <stdexcept>
#include <string>
#include <variant>
#include <vector>

namespace cjson {

class Value;
using Object = std::map<std::string, Value>;
using Array  = std::vector<Value>;

class Value {
public:
    enum class Kind { Null, Bool, Number, String, Array, Object };

    Value() : kind_(Kind::Null), num_(0.0), boolean_(false) {}
    explicit Value(bool b) : kind_(Kind::Bool), num_(0.0), boolean_(b) {}
    explicit Value(double d) : kind_(Kind::Number), num_(d), boolean_(false) {}
    explicit Value(std::string s) : kind_(Kind::String), num_(0.0), boolean_(false), str_(std::move(s)) {}
    explicit Value(Array a) : kind_(Kind::Array), num_(0.0), boolean_(false), arr_(std::move(a)) {}
    explicit Value(Object o) : kind_(Kind::Object), num_(0.0), boolean_(false), obj_(std::move(o)) {}

    Kind kind() const { return kind_; }
    bool is_null()   const { return kind_ == Kind::Null; }
    bool is_bool()   const { return kind_ == Kind::Bool; }
    bool is_number() const { return kind_ == Kind::Number; }
    bool is_string() const { return kind_ == Kind::String; }
    bool is_array()  const { return kind_ == Kind::Array; }
    bool is_object() const { return kind_ == Kind::Object; }

    bool                as_bool()   const { return boolean_; }
    double              as_number() const { return num_; }
    const std::string&  as_string() const { return str_; }
    const Array&        as_array()  const { return arr_; }
    const Object&       as_object() const { return obj_; }

    bool contains(const std::string& key) const {
        return kind_ == Kind::Object && obj_.find(key) != obj_.end();
    }
    const Value& at(const std::string& key) const {
        auto it = obj_.find(key);
        if (it == obj_.end()) throw std::runtime_error("missing key: " + key);
        return it->second;
    }

private:
    Kind kind_;
    double num_;
    bool boolean_;
    std::string str_;
    Array arr_;
    Object obj_;
};

Value parse(const std::string& text);
Value parse_file(const std::string& path);

} // namespace cjson
HPP

# ---------------------------------------------------------------------------
# src/json.cpp -- recursive-descent JSON parser implementation
# ---------------------------------------------------------------------------
cat > src/json.cpp <<'CPP'
#include "json.hpp"
#include <cctype>
#include <fstream>
#include <sstream>

namespace cjson {

namespace {

class Parser {
public:
    explicit Parser(const std::string& text) : text_(text), pos_(0) {}

    Value parse_value() {
        skip_ws();
        if (pos_ >= text_.size()) throw std::runtime_error("unexpected eof");
        char c = text_[pos_];
        if (c == '{') return parse_object();
        if (c == '[') return parse_array();
        if (c == '"') return Value(parse_string());
        if (c == 't' || c == 'f') return Value(parse_bool());
        if (c == 'n') { parse_null(); return Value(); }
        if (c == '-' || std::isdigit(static_cast<unsigned char>(c))) {
            return Value(parse_number());
        }
        throw std::runtime_error("unexpected character at " + std::to_string(pos_));
    }

private:
    const std::string& text_;
    std::size_t pos_;

    void skip_ws() {
        while (pos_ < text_.size() &&
               std::isspace(static_cast<unsigned char>(text_[pos_]))) {
            ++pos_;
        }
    }

    void expect(char c) {
        skip_ws();
        if (pos_ >= text_.size() || text_[pos_] != c) {
            throw std::runtime_error(std::string("expected '") + c + "'");
        }
        ++pos_;
    }

    Value parse_object() {
        Object obj;
        expect('{');
        skip_ws();
        if (pos_ < text_.size() && text_[pos_] == '}') { ++pos_; return Value(std::move(obj)); }
        while (true) {
            skip_ws();
            std::string key = parse_string();
            expect(':');
            Value v = parse_value();
            obj.emplace(std::move(key), std::move(v));
            skip_ws();
            if (pos_ < text_.size() && text_[pos_] == ',') { ++pos_; continue; }
            expect('}');
            break;
        }
        return Value(std::move(obj));
    }

    Value parse_array() {
        Array arr;
        expect('[');
        skip_ws();
        if (pos_ < text_.size() && text_[pos_] == ']') { ++pos_; return Value(std::move(arr)); }
        while (true) {
            arr.push_back(parse_value());
            skip_ws();
            if (pos_ < text_.size() && text_[pos_] == ',') { ++pos_; continue; }
            expect(']');
            break;
        }
        return Value(std::move(arr));
    }

    std::string parse_string() {
        skip_ws();
        if (pos_ >= text_.size() || text_[pos_] != '"') throw std::runtime_error("expected string");
        ++pos_;
        std::string out;
        while (pos_ < text_.size() && text_[pos_] != '"') {
            char c = text_[pos_++];
            if (c == '\\') {
                if (pos_ >= text_.size()) throw std::runtime_error("bad escape");
                char e = text_[pos_++];
                switch (e) {
                    case '"':  out.push_back('"'); break;
                    case '\\': out.push_back('\\'); break;
                    case '/':  out.push_back('/'); break;
                    case 'n':  out.push_back('\n'); break;
                    case 't':  out.push_back('\t'); break;
                    case 'r':  out.push_back('\r'); break;
                    case 'b':  out.push_back('\b'); break;
                    case 'f':  out.push_back('\f'); break;
                    default: throw std::runtime_error("unsupported escape");
                }
            } else {
                out.push_back(c);
            }
        }
        if (pos_ >= text_.size()) throw std::runtime_error("unterminated string");
        ++pos_;
        return out;
    }

    bool parse_bool() {
        if (text_.compare(pos_, 4, "true") == 0) { pos_ += 4; return true; }
        if (text_.compare(pos_, 5, "false") == 0) { pos_ += 5; return false; }
        throw std::runtime_error("bad bool literal");
    }

    void parse_null() {
        if (text_.compare(pos_, 4, "null") == 0) { pos_ += 4; return; }
        throw std::runtime_error("bad null literal");
    }

    double parse_number() {
        std::size_t start = pos_;
        if (text_[pos_] == '-') ++pos_;
        while (pos_ < text_.size() &&
               (std::isdigit(static_cast<unsigned char>(text_[pos_])) ||
                text_[pos_] == '.' || text_[pos_] == 'e' || text_[pos_] == 'E' ||
                text_[pos_] == '+' || text_[pos_] == '-')) {
            ++pos_;
        }
        return std::stod(text_.substr(start, pos_ - start));
    }
};

} // namespace

Value parse(const std::string& text) {
    Parser p(text);
    return p.parse_value();
}

Value parse_file(const std::string& path) {
    std::ifstream in(path);
    if (!in) throw std::runtime_error("cannot open " + path);
    std::stringstream ss;
    ss << in.rdbuf();
    return parse(ss.str());
}

} // namespace cjson
CPP

# ---------------------------------------------------------------------------
# src/stats.hpp -- numerical helpers
# ---------------------------------------------------------------------------
cat > src/stats.hpp <<'HPP'
#pragma once
#include <utility>
#include <vector>

namespace stats {

class Welford {
public:
    void push(double x);
    long long count() const { return n_; }
    double mean() const { return n_ > 0 ? mean_ : 0.0; }
    double sample_variance() const { return n_ > 1 ? m2_ / static_cast<double>(n_ - 1) : 0.0; }

private:
    long long n_ = 0;
    double mean_ = 0.0;
    double m2_   = 0.0;
};

// Asymptotic Rousseeuw-Croux Qn scale estimator.
//   Qn(x) = 2.21914 * d_(k)
// where d_(k) is the k-th order statistic (1-indexed) of pairwise absolute
// differences { |x_i - x_j| : i < j }, h = floor(n/2) + 1, k = h*(h-1)/2.
// Returns 0.0 for n < 2.
double qn_asymptotic(std::vector<double> x);

struct IterativeWLSResult {
    double slope = 0.0;
    double intercept = 0.0;
    double residual_stddev = 0.0;
    int n_outliers_removed = 0;
    int iterations_used = 0;
};

IterativeWLSResult iterative_wls(
    const std::vector<std::tuple<double, double, double>>& points,
    double k_sigma,
    int max_iter);

} // namespace stats
HPP

# ---------------------------------------------------------------------------
# src/stats.cpp
# ---------------------------------------------------------------------------
cat > src/stats.cpp <<'CPP'
#include "stats.hpp"
#include <algorithm>
#include <cmath>
#include <set>
#include <tuple>

namespace stats {

void Welford::push(double x) {
    ++n_;
    double delta = x - mean_;
    mean_ += delta / static_cast<double>(n_);
    double delta2 = x - mean_;
    m2_ += delta * delta2;
}

double qn_asymptotic(std::vector<double> x) {
    const std::size_t n = x.size();
    if (n < 2) return 0.0;
    std::vector<double> diffs;
    diffs.reserve(n * (n - 1) / 2);
    for (std::size_t i = 0; i < n; ++i) {
        for (std::size_t j = i + 1; j < n; ++j) {
            diffs.push_back(std::fabs(x[i] - x[j]));
        }
    }
    std::sort(diffs.begin(), diffs.end());
    const std::size_t h = n / 2 + 1;
    const std::size_t k = h * (h - 1) / 2;
    return 2.21914 * diffs[k - 1];
}

namespace {

struct WlsFit {
    double slope = 0.0;
    double intercept = 0.0;
    double rstd = 0.0;
};

WlsFit weighted_fit(
    const std::vector<std::tuple<double, double, double>>& pts,
    const std::vector<int>& kept) {
    WlsFit fit;
    if (kept.empty()) return fit;
    double sw = 0.0;
    for (int i : kept) sw += std::get<2>(pts[i]);
    if (sw == 0.0) return fit;

    std::set<double> distinct_xs;
    for (int i : kept) distinct_xs.insert(std::get<0>(pts[i]));

    if (distinct_xs.size() < 2) {
        double wy = 0.0;
        for (int i : kept) wy += std::get<2>(pts[i]) * std::get<1>(pts[i]);
        fit.slope = 0.0;
        fit.intercept = wy / sw;
        double sse = 0.0;
        for (int i : kept) {
            double r = std::get<1>(pts[i]) - fit.intercept;
            sse += std::get<2>(pts[i]) * r * r;
        }
        fit.rstd = std::sqrt(sse / sw);
        return fit;
    }

    double xbar = 0.0, ybar = 0.0;
    for (int i : kept) {
        xbar += std::get<2>(pts[i]) * std::get<0>(pts[i]);
        ybar += std::get<2>(pts[i]) * std::get<1>(pts[i]);
    }
    xbar /= sw;
    ybar /= sw;

    double sxx = 0.0, sxy = 0.0;
    for (int i : kept) {
        double w = std::get<2>(pts[i]);
        double dx = std::get<0>(pts[i]) - xbar;
        double dy = std::get<1>(pts[i]) - ybar;
        sxx += w * dx * dx;
        sxy += w * dx * dy;
    }
    if (sxx == 0.0) {
        fit.slope = 0.0;
        fit.intercept = ybar;
    } else {
        fit.slope = sxy / sxx;
        fit.intercept = ybar - fit.slope * xbar;
    }
    double sse = 0.0;
    for (int i : kept) {
        double r = std::get<1>(pts[i]) - (fit.slope * std::get<0>(pts[i]) + fit.intercept);
        sse += std::get<2>(pts[i]) * r * r;
    }
    fit.rstd = std::sqrt(sse / sw);
    return fit;
}

} // namespace

IterativeWLSResult iterative_wls(
    const std::vector<std::tuple<double, double, double>>& pts,
    double k_sigma,
    int max_iter) {
    IterativeWLSResult res;
    int n = static_cast<int>(pts.size());
    if (n == 0) return res;
    std::vector<int> kept;
    kept.reserve(n);
    for (int i = 0; i < n; ++i) kept.push_back(i);

    int iters = 0;
    WlsFit fit;
    while (iters < max_iter) {
        ++iters;
        fit = weighted_fit(pts, kept);
        if (fit.rstd == 0.0) break;
        double threshold = k_sigma * fit.rstd;
        std::vector<int> new_kept;
        new_kept.reserve(kept.size());
        for (int i : kept) {
            double pred = fit.slope * std::get<0>(pts[i]) + fit.intercept;
            double r = std::get<1>(pts[i]) - pred;
            if (std::fabs(r) <= threshold) new_kept.push_back(i);
        }
        if (new_kept.size() < 2 ||
            new_kept.size() == kept.size()) {
            break;
        }
        kept = std::move(new_kept);
    }
    res.slope = fit.slope;
    res.intercept = fit.intercept;
    res.residual_stddev = fit.rstd;
    res.n_outliers_removed = n - static_cast<int>(kept.size());
    res.iterations_used = iters;
    return res;
}

} // namespace stats
CPP

# ---------------------------------------------------------------------------
# src/io.hpp -- IO helpers, types
# ---------------------------------------------------------------------------
cat > src/io.hpp <<'HPP'
#pragma once
#include <map>
#include <string>
#include <vector>

namespace io {

struct PeakSpec {
    std::string label;
    double expected_nm = 0.0;
    double window_lo = 0.0;
    double window_hi = 0.0;
};

struct ManifestRun {
    std::string run_id;
    std::string instrument;
    std::string batch;
    std::string spectrum;
    bool has_operator = false;
    std::string operator_;
    bool has_temperature = false;
    double temperature_c = 0.0;
    bool has_quality = false;
    std::string quality_flag;
    bool has_calibrant = false;
    std::string calibrant;
};

struct InstrumentMeta {
    std::string operator_;
    double temperature_c = 0.0;
    std::string quality_flag;
    double wavelength_offset_nm = 0.0;
};

struct BatchMeta {
    std::string operator_;
    double temperature_c = 0.0;
    std::string quality_flag;
    bool has_calibrant = false;
    std::string calibrant;
};

struct SpectrumRow {
    double wavelength_nm = 0.0;
    double intensity = 0.0;
};

// Reads CSV with header `wavelength_nm,intensity`. Skips rows where either
// field is non-numeric or non-finite.
std::vector<SpectrumRow> read_spectrum_csv(const std::string& path);

// Lists every regular file under `root`, returns relative paths sorted ASCII.
std::vector<std::string> list_files_recursive(const std::string& root);

} // namespace io
HPP

# ---------------------------------------------------------------------------
# src/io.cpp
# ---------------------------------------------------------------------------
cat > src/io.cpp <<'CPP'
#include "io.hpp"
#include <algorithm>
#include <cmath>
#include <cstring>
#include <dirent.h>
#include <fstream>
#include <sstream>
#include <stdexcept>
#include <sys/stat.h>

namespace io {

namespace {

bool parse_double(const std::string& s, double& out) {
    if (s.empty()) return false;
    try {
        std::size_t pos = 0;
        double v = std::stod(s, &pos);
        while (pos < s.size() && std::isspace(static_cast<unsigned char>(s[pos]))) ++pos;
        if (pos != s.size()) return false;
        if (!std::isfinite(v)) return false;
        out = v;
        return true;
    } catch (...) {
        return false;
    }
}

} // namespace

std::vector<SpectrumRow> read_spectrum_csv(const std::string& path) {
    std::ifstream in(path);
    if (!in) throw std::runtime_error("cannot open " + path);
    std::vector<SpectrumRow> rows;
    std::string line;
    bool header_skipped = false;
    while (std::getline(in, line)) {
        if (!line.empty() && line.back() == '\r') line.pop_back();
        if (!header_skipped) { header_skipped = true; continue; }
        if (line.empty()) continue;
        auto comma = line.find(',');
        if (comma == std::string::npos) continue;
        SpectrumRow r;
        if (!parse_double(line.substr(0, comma), r.wavelength_nm)) continue;
        if (!parse_double(line.substr(comma + 1), r.intensity)) continue;
        rows.push_back(r);
    }
    return rows;
}

void walk(const std::string& root, const std::string& rel,
          std::vector<std::string>& out) {
    std::string dir = root + (rel.empty() ? "" : "/" + rel);
    DIR* d = opendir(dir.c_str());
    if (!d) return;
    struct dirent* entry;
    while ((entry = readdir(d)) != nullptr) {
        std::string name = entry->d_name;
        if (name == "." || name == "..") continue;
        std::string full = dir + "/" + name;
        std::string sub  = rel.empty() ? name : (rel + "/" + name);
        struct stat st;
        if (::stat(full.c_str(), &st) != 0) continue;
        if (S_ISDIR(st.st_mode)) {
            walk(root, sub, out);
        } else if (S_ISREG(st.st_mode)) {
            out.push_back(sub);
        }
    }
    closedir(d);
}

std::vector<std::string> list_files_recursive(const std::string& root) {
    std::vector<std::string> out;
    walk(root, "", out);
    std::sort(out.begin(), out.end());
    return out;
}

} // namespace io
CPP

# ---------------------------------------------------------------------------
# src/main.cpp -- pipeline + output writers
# ---------------------------------------------------------------------------
cat > src/main.cpp <<'CPP'
#include "io.hpp"
#include "json.hpp"
#include "stats.hpp"

#include <algorithm>
#include <cmath>
#include <cstdio>
#include <cstdlib>
#include <fstream>
#include <iostream>
#include <map>
#include <set>
#include <sstream>
#include <string>
#include <utility>
#include <vector>

namespace {

constexpr double DRIFT_K_SIGMA = 2.5;
constexpr int    DRIFT_MAX_ITER = 5;

// Round-half-away-from-zero to 6 decimals (matches Python's round() for
// canonical values). Returns -0.0 normalised to +0.0.
double round6(double x) {
    if (!std::isfinite(x)) return x;
    double scaled = x * 1e6;
    double rounded;
    if (scaled >= 0) {
        rounded = std::floor(scaled + 0.5);
    } else {
        rounded = -std::floor(-scaled + 0.5);
    }
    double r = rounded / 1e6;
    if (r == 0.0) r = 0.0; // strip -0.0
    return r;
}

double round4(double x) {
    if (!std::isfinite(x)) return x;
    double scaled = x * 1e4;
    double rounded;
    if (scaled >= 0) rounded = std::floor(scaled + 0.5);
    else rounded = -std::floor(-scaled + 0.5);
    double r = rounded / 1e4;
    if (r == 0.0) r = 0.0;
    return r;
}

// Number formatter: emit a 6-decimal double the way Python's json.dump does:
// drop trailing zeros but always keep at least one digit after the decimal,
// and strip a leading "-" for -0.0.
std::string fmt_num(double v) {
    if (!std::isfinite(v)) {
        std::ostringstream o; o << v; return o.str();
    }
    char buf[64];
    std::snprintf(buf, sizeof(buf), "%.6f", v);
    std::string s = buf;
    if (s == "-0.000000") s = "0.000000";
    auto dot = s.find('.');
    if (dot != std::string::npos) {
        std::size_t end = s.size();
        while (end > dot + 2 && s[end-1] == '0') --end;
        s.resize(end);
    }
    return s;
}

std::string fmt_int(long long v) {
    std::ostringstream o; o << v; return o.str();
}

std::string json_quote(const std::string& s) {
    std::string out = "\"";
    for (char c : s) {
        switch (c) {
            case '"':  out += "\\\""; break;
            case '\\': out += "\\\\"; break;
            case '\n': out += "\\n"; break;
            case '\t': out += "\\t"; break;
            case '\r': out += "\\r"; break;
            default:   out.push_back(c);
        }
    }
    out += '"';
    return out;
}

// ----- input merging ----------------------------------------------------

struct Merged {
    std::string run_id;
    std::string instrument;
    std::string batch;
    std::string operator_;
    std::string calibrant;
    double temperature_c = 0.0;
    double wavelength_offset_nm = 0.0;
    std::string quality_flag;
    std::string spectrum;
    bool valid = false;
};

template <class T>
const std::string& js_string(const cjson::Value& v, T fallback) {
    static thread_local std::string holder;
    if (v.is_string()) return v.as_string();
    holder = fallback;
    return holder;
}

bool js_str_present(const cjson::Value& obj, const char* key, std::string& out) {
    if (!obj.contains(key)) return false;
    const auto& v = obj.at(key);
    if (!v.is_string()) return false;
    out = v.as_string();
    return !out.empty();
}

bool js_num_present(const cjson::Value& obj, const char* key, double& out) {
    if (!obj.contains(key)) return false;
    const auto& v = obj.at(key);
    if (!v.is_number()) return false;
    out = v.as_number();
    return true;
}

Merged merge_metadata(const cjson::Value& run,
                      const std::map<std::string, cjson::Value>& instruments,
                      const std::map<std::string, cjson::Value>& batches) {
    Merged m;
    if (!js_str_present(run, "run_id", m.run_id)) return m;
    if (!js_str_present(run, "instrument", m.instrument)) return m;
    if (!js_str_present(run, "batch", m.batch)) return m;
    auto inst_it = instruments.find(m.instrument);
    auto batch_it = batches.find(m.batch);
    if (inst_it == instruments.end() || !inst_it->second.is_object()) return m;
    if (batch_it == batches.end()    || !batch_it->second.is_object()) return m;
    const auto& inst = inst_it->second;
    const auto& batch = batch_it->second;

    // operator: instrument < batch < run
    js_str_present(inst,  "operator", m.operator_);
    js_str_present(batch, "operator", m.operator_);
    js_str_present(run,   "operator", m.operator_);

    js_num_present(inst,  "temperature_c", m.temperature_c);
    js_num_present(batch, "temperature_c", m.temperature_c);
    js_num_present(run,   "temperature_c", m.temperature_c);

    js_str_present(inst,  "quality_flag", m.quality_flag);
    js_str_present(batch, "quality_flag", m.quality_flag);
    js_str_present(run,   "quality_flag", m.quality_flag);

    js_str_present(inst,  "calibrant", m.calibrant);
    js_str_present(batch, "calibrant", m.calibrant);
    js_str_present(run,   "calibrant", m.calibrant);

    js_num_present(inst,  "wavelength_offset_nm", m.wavelength_offset_nm);
    js_num_present(batch, "wavelength_offset_nm", m.wavelength_offset_nm);
    js_num_present(run,   "wavelength_offset_nm", m.wavelength_offset_nm);

    js_str_present(run, "spectrum", m.spectrum);

    bool ok = !m.run_id.empty() && !m.instrument.empty() && !m.batch.empty()
              && !m.operator_.empty() && !m.calibrant.empty()
              && !m.quality_flag.empty() && !m.spectrum.empty();
    m.valid = ok;
    return m;
}

// ----- per-run pass 1 ---------------------------------------------------

struct RawPeak {
    std::string run_id;
    std::string instrument;
    std::string batch;
    std::string calibrant;
    std::string peak_label;
    double expected_nm = 0.0;
    double observed_nm_raw = 0.0;
    double raw_error_nm = 0.0;
    double peak_area_raw = 0.0;
};

struct IncludedPartial {
    std::string run_id;
    std::string instrument;
    std::string batch;
    std::string operator_;
    std::string calibrant;
    double temperature_c = 0.0;
    double wavelength_offset_nm = 0.0;
    double baseline = 0.0;          // MAD-filtered mean of off-peak pool
    double noise_floor_qn = 0.0;    // Rousseeuw-Croux Qn over off-peak pool
    double intensity_var = 0.0;     // sample variance (n-1) of all valid rows
};

struct Pass1Result {
    bool included = false;
    IncludedPartial partial;
    std::vector<RawPeak> peaks;
    std::string excluded_reason; // when !included
};

bool inside_window(double w, double lo, double hi) { return w >= lo && w <= hi; }

bool outside_all(double w, const std::vector<io::PeakSpec>& peaks) {
    for (const auto& p : peaks) {
        if (inside_window(w, p.window_lo, p.window_hi)) return false;
    }
    return true;
}

double median_of(std::vector<double> v) {
    if (v.empty()) return 0.0;
    std::sort(v.begin(), v.end());
    size_t n = v.size();
    if (n % 2 == 1) return v[n/2];
    return 0.5 * (v[n/2 - 1] + v[n/2]);
}

Pass1Result pass1(const Merged& md,
                  const std::vector<io::PeakSpec>& peaks_spec,
                  const std::string& experiments_root) {
    Pass1Result out;
    if (md.quality_flag != "ok") { out.excluded_reason = "quality_flag"; return out; }
    std::string spec_path = experiments_root + "/" + md.spectrum;
    std::ifstream check(spec_path);
    if (!check) { out.excluded_reason = "missing_metadata"; return out; }

    std::vector<io::SpectrumRow> rows = io::read_spectrum_csv(spec_path);
    if (rows.size() < 8) { out.excluded_reason = "insufficient_rows"; return out; }

    // Sample variance (n-1) over every valid intensity row.
    stats::Welford intensity_stats;
    for (const auto& r : rows) intensity_stats.push(r.intensity);

    // Off-peak pool — used for both the robust baseline filter and the Qn
    // noise floor.
    std::vector<double> off_peak;
    for (const auto& r : rows) {
        if (outside_all(r.wavelength_nm, peaks_spec)) {
            off_peak.push_back(r.intensity);
        }
    }
    if (off_peak.empty()) { out.excluded_reason = "no_baseline"; return out; }

    // Rousseeuw-Croux Qn scale estimator over the off-peak pool.
    double noise_floor_qn = stats::qn_asymptotic(off_peak);

    // 3 * MAD filter around the median, then arithmetic mean of survivors.
    double med = median_of(off_peak);
    std::vector<double> deviations;
    deviations.reserve(off_peak.size());
    for (double x : off_peak) deviations.push_back(std::fabs(x - med));
    double mad = median_of(deviations);
    std::vector<double> kept;
    kept.reserve(off_peak.size());
    if (mad == 0.0) {
        for (double x : off_peak) if (x == med) kept.push_back(x);
    } else {
        for (double x : off_peak) if (std::fabs(x - med) <= 3.0 * mad) kept.push_back(x);
    }
    if (kept.empty()) { out.excluded_reason = "no_baseline"; return out; }
    double baseline = 0.0;
    for (double x : kept) baseline += x;
    baseline /= static_cast<double>(kept.size());

    // Per-peak intensity-weighted centroid + raw observed/error.
    std::vector<RawPeak> peaks;
    peaks.reserve(peaks_spec.size());
    for (const auto& peak : peaks_spec) {
        double area = 0.0, num = 0.0;
        for (const auto& r : rows) {
            if (!inside_window(r.wavelength_nm, peak.window_lo, peak.window_hi)) continue;
            double c = r.intensity - baseline;
            if (c > 0) {
                area += c;
                num  += r.wavelength_nm * c;
            }
        }
        if (area <= 0) { out.excluded_reason = "missing_peak"; return out; }
        double w_raw = num / area;
        double observed_raw = w_raw - md.wavelength_offset_nm;
        RawPeak p;
        p.run_id = md.run_id;
        p.instrument = md.instrument;
        p.batch = md.batch;
        p.calibrant = md.calibrant;
        p.peak_label = peak.label;
        p.expected_nm = peak.expected_nm;
        p.observed_nm_raw = observed_raw;
        p.raw_error_nm = observed_raw - peak.expected_nm;
        p.peak_area_raw = area;
        peaks.push_back(p);
    }

    out.included = true;
    out.partial.run_id = md.run_id;
    out.partial.instrument = md.instrument;
    out.partial.batch = md.batch;
    out.partial.operator_ = md.operator_;
    out.partial.calibrant = md.calibrant;
    out.partial.temperature_c = md.temperature_c;
    out.partial.wavelength_offset_nm = md.wavelength_offset_nm;
    out.partial.baseline = baseline;
    out.partial.noise_floor_qn = noise_floor_qn;
    out.partial.intensity_var = intensity_stats.sample_variance();
    out.peaks = std::move(peaks);
    return out;
}

// ----- output writers ---------------------------------------------------

struct CorrectedPeak {
    std::string run_id;
    std::string instrument;
    std::string batch;
    std::string calibrant;
    std::string peak_label;
    double expected_nm = 0.0;
    double observed_nm = 0.0;
    double error_nm = 0.0;
    double peak_area = 0.0;
    double unrounded_error = 0.0;
};

struct GroupFitMeta {
    double residual_stddev = 0.0;
    int n_outliers_removed = 0;
    int iterations_used = 0;
};

void write_run_audit(const std::string& path,
                     const std::vector<IncludedPartial>& included_partials,
                     const std::map<std::string, double>& rms_by_run,
                     const std::vector<std::pair<std::string, std::string>>& excluded,
                     const std::vector<std::string>& source_files) {
    std::ofstream out(path);
    out << "{\n";
    out << "  \"included_runs\": [";
    std::vector<IncludedPartial> sorted_inc = included_partials;
    std::sort(sorted_inc.begin(), sorted_inc.end(),
              [](const IncludedPartial& a, const IncludedPartial& b) {
                  return a.run_id < b.run_id;
              });
    for (size_t i = 0; i < sorted_inc.size(); ++i) {
        const auto& r = sorted_inc[i];
        out << (i == 0 ? "\n" : ",\n");
        out << "    {\n";
        out << "      \"run_id\": "             << json_quote(r.run_id) << ",\n";
        out << "      \"instrument\": "         << json_quote(r.instrument) << ",\n";
        out << "      \"batch\": "              << json_quote(r.batch) << ",\n";
        out << "      \"operator\": "           << json_quote(r.operator_) << ",\n";
        out << "      \"calibrant\": "          << json_quote(r.calibrant) << ",\n";
        out << "      \"temperature_c\": "      << fmt_num(r.temperature_c) << ",\n";
        out << "      \"wavelength_offset_nm\": " << fmt_num(r.wavelength_offset_nm) << ",\n";
        out << "      \"baseline\": "           << fmt_num(round6(r.baseline)) << ",\n";
        out << "      \"noise_floor_qn\": "     << fmt_num(round6(r.noise_floor_qn)) << ",\n";
        out << "      \"intensity_var\": "      << fmt_num(round6(r.intensity_var)) << ",\n";
        double rms = 0.0;
        auto it = rms_by_run.find(r.run_id);
        if (it != rms_by_run.end()) rms = it->second;
        out << "      \"rms_error_nm\": "       << fmt_num(round6(rms)) << ",\n";
        out << "      \"status\": \"included\"\n";
        out << "    }";
    }
    if (!sorted_inc.empty()) out << "\n  ";
    out << "],\n";

    out << "  \"excluded_runs\": [";
    std::vector<std::pair<std::string,std::string>> sorted_exc = excluded;
    std::sort(sorted_exc.begin(), sorted_exc.end());
    for (size_t i = 0; i < sorted_exc.size(); ++i) {
        out << (i == 0 ? "\n" : ",\n");
        out << "    {\n";
        out << "      \"run_id\": "  << json_quote(sorted_exc[i].first) << ",\n";
        out << "      \"status\": \"excluded\",\n";
        out << "      \"reason\": "  << json_quote(sorted_exc[i].second) << "\n";
        out << "    }";
    }
    if (!sorted_exc.empty()) out << "\n  ";
    out << "],\n";

    out << "  \"source_files\": [";
    std::vector<std::string> files = source_files;
    std::sort(files.begin(), files.end());
    for (size_t i = 0; i < files.size(); ++i) {
        out << (i == 0 ? "\n" : ",\n");
        out << "    " << json_quote(files[i]);
    }
    if (!files.empty()) out << "\n  ";
    out << "]\n}\n";
}

void write_calibration_summary(
    const std::string& path,
    const std::vector<CorrectedPeak>& peaks,
    const std::map<std::pair<std::string, std::string>, GroupFitMeta>& meta,
    const std::vector<IncludedPartial>& included_partials,
    const std::map<std::string, double>& rms_by_run) {

    std::map<std::pair<std::string, std::string>, std::vector<double>> errs_by_g;
    std::map<std::pair<std::string, std::string>, std::set<std::string>> runs_by_g;
    for (const auto& p : peaks) {
        auto key = std::make_pair(p.calibrant, p.instrument);
        errs_by_g[key].push_back(p.unrounded_error);
        runs_by_g[key].insert(p.run_id);
    }
    std::vector<std::pair<std::string, std::string>> keys;
    for (const auto& kv : errs_by_g) keys.push_back(kv.first);
    std::sort(keys.begin(), keys.end());

    std::ofstream out(path);
    out << "{\n  \"calibrants\": [";
    for (size_t i = 0; i < keys.size(); ++i) {
        const auto& key = keys[i];
        const auto& errs = errs_by_g[key];
        double sum = 0.0, sumsq = 0.0;
        for (double e : errs) { sum += e; sumsq += e * e; }
        double mean = sum / static_cast<double>(errs.size());
        double rms  = std::sqrt(sumsq / static_cast<double>(errs.size()));
        const auto& m = meta.at(key);
        out << (i == 0 ? "\n" : ",\n");
        out << "    {\n";
        out << "      \"calibrant\": " << json_quote(key.first) << ",\n";
        out << "      \"instrument\": " << json_quote(key.second) << ",\n";
        out << "      \"run_count\": " << fmt_int(static_cast<long long>(runs_by_g[key].size())) << ",\n";
        out << "      \"peak_count\": " << fmt_int(static_cast<long long>(errs.size())) << ",\n";
        out << "      \"mean_error_nm\": " << fmt_num(round6(mean)) << ",\n";
        out << "      \"rms_error_nm\": " << fmt_num(round6(rms)) << ",\n";
        out << "      \"residual_stddev_nm\": " << fmt_num(round6(m.residual_stddev)) << ",\n";
        out << "      \"n_outliers_removed\": " << fmt_int(m.n_outliers_removed) << ",\n";
        out << "      \"iterations_used\": " << fmt_int(m.iterations_used) << "\n";
        out << "    }";
    }
    if (!keys.empty()) out << "\n  ";
    out << "],\n";

    // best_run_by_calibrant
    std::map<std::string, std::vector<double>> abs_err_by_run;
    for (const auto& p : peaks) abs_err_by_run[p.run_id].push_back(std::fabs(p.unrounded_error));
    struct Cand { IncludedPartial run; double max_abs; };
    std::map<std::string, std::vector<Cand>> by_cal;
    for (const auto& r : included_partials) {
        Cand c;
        c.run = r;
        const auto it = abs_err_by_run.find(r.run_id);
        c.max_abs = (it == abs_err_by_run.end() || it->second.empty()) ? 0.0
                    : *std::max_element(it->second.begin(), it->second.end());
        by_cal[r.calibrant].push_back(c);
    }
    std::vector<std::string> cals;
    for (const auto& kv : by_cal) cals.push_back(kv.first);
    std::sort(cals.begin(), cals.end());

    out << "  \"best_run_by_calibrant\": [";
    bool wrote = false;
    for (size_t i = 0; i < cals.size(); ++i) {
        auto& cands = by_cal[cals[i]];
        std::sort(cands.begin(), cands.end(), [&](const Cand& a, const Cand& b){
            double ar = round4(rms_by_run.at(a.run.run_id));
            double br = round4(rms_by_run.at(b.run.run_id));
            if (ar != br) return ar < br;
            if (a.max_abs != b.max_abs) return a.max_abs < b.max_abs;
            return a.run.run_id < b.run.run_id;
        });
        const auto& chosen = cands.front().run;
        out << (wrote ? ",\n" : "\n");
        wrote = true;
        out << "    {\n";
        out << "      \"calibrant\": " << json_quote(cals[i]) << ",\n";
        out << "      \"run_id\": " << json_quote(chosen.run_id) << ",\n";
        out << "      \"instrument\": " << json_quote(chosen.instrument) << ",\n";
        out << "      \"rms_error_nm\": " << fmt_num(round6(rms_by_run.at(chosen.run_id))) << "\n";
        out << "    }";
    }
    if (wrote) out << "\n  ";
    out << "]\n}\n";
}

void write_peak_table(const std::string& path,
                      std::vector<CorrectedPeak> peaks) {
    std::sort(peaks.begin(), peaks.end(), [](const CorrectedPeak& a, const CorrectedPeak& b){
        if (a.run_id != b.run_id) return a.run_id < b.run_id;
        return a.peak_label < b.peak_label;
    });
    std::ofstream out(path);
    out << "run_id,instrument,batch,calibrant,peak_label,"
        << "expected_nm,observed_nm,error_nm,peak_area\r\n";
    out.close();
    // Use \n only; Python csv writer uses \r\n by default but our test does
    // line-based parsing with universal newlines, so either works. Be
    // consistent with Python's default csv.DictWriter (uses \r\n on POSIX).
    out.open(path);
    out << "run_id,instrument,batch,calibrant,peak_label,"
        << "expected_nm,observed_nm,error_nm,peak_area\r\n";
    for (const auto& p : peaks) {
        out << p.run_id << ',' << p.instrument << ',' << p.batch << ','
            << p.calibrant << ',' << p.peak_label << ','
            << fmt_num(p.expected_nm) << ','
            << fmt_num(round6(p.observed_nm)) << ','
            << fmt_num(round6(p.error_nm)) << ','
            << fmt_num(round6(p.peak_area))
            << "\r\n";
    }
}

} // namespace

int main() {
    const char* env_app = std::getenv("APP_ROOT");
    std::string app_root = env_app ? env_app : "/app";
    std::string exp_dir = app_root + "/experiments";
    std::string out_dir = app_root + "/output";

    cjson::Value manifest_v   = cjson::parse_file(exp_dir + "/manifest.json");
    cjson::Value instruments_v = cjson::parse_file(exp_dir + "/config/instruments.json");
    cjson::Value batches_v    = cjson::parse_file(exp_dir + "/config/batches.json");
    cjson::Value calibrants_v = cjson::parse_file(exp_dir + "/config/calibrants.json");

    if (!manifest_v.is_object() || !manifest_v.contains("runs")) {
        std::cerr << "manifest.json missing 'runs'\n";
        return 1;
    }
    const auto& instruments = instruments_v.as_object();
    const auto& batches     = batches_v.as_object();

    std::map<std::string, std::vector<io::PeakSpec>> calibrant_specs;
    if (calibrants_v.is_object()) {
        for (const auto& kv : calibrants_v.as_object()) {
            std::vector<io::PeakSpec> specs;
            if (!kv.second.is_array()) continue;
            for (const auto& peak : kv.second.as_array()) {
                if (!peak.is_object()) continue;
                io::PeakSpec ps;
                if (!peak.contains("label") || !peak.at("label").is_string()) continue;
                if (!peak.contains("expected_nm") || !peak.at("expected_nm").is_number()) continue;
                if (!peak.contains("window_nm") || !peak.at("window_nm").is_array()) continue;
                ps.label = peak.at("label").as_string();
                ps.expected_nm = peak.at("expected_nm").as_number();
                const auto& win = peak.at("window_nm").as_array();
                if (win.size() != 2) continue;
                ps.window_lo = win[0].as_number();
                ps.window_hi = win[1].as_number();
                specs.push_back(ps);
            }
            calibrant_specs[kv.first] = std::move(specs);
        }
    }

    std::vector<IncludedPartial> included_partials;
    std::vector<std::pair<std::string, std::string>> excluded;
    std::vector<RawPeak> raw_peaks;

    for (const auto& run : manifest_v.at("runs").as_array()) {
        std::string run_id;
        if (run.contains("run_id") && run.at("run_id").is_string()) {
            run_id = run.at("run_id").as_string();
        }
        Merged md = merge_metadata(run, instruments, batches);
        if (!md.valid || calibrant_specs.find(md.calibrant) == calibrant_specs.end()) {
            excluded.emplace_back(run_id, "missing_metadata");
            continue;
        }
        Pass1Result p1 = pass1(md, calibrant_specs[md.calibrant], exp_dir);
        if (!p1.included) {
            excluded.emplace_back(md.run_id, p1.excluded_reason);
            continue;
        }
        included_partials.push_back(p1.partial);
        for (auto& rp : p1.peaks) raw_peaks.push_back(std::move(rp));
    }

    // Pass 2: iterative reweighted WLS per (calibrant, instrument).
    std::map<std::pair<std::string, std::string>, std::vector<RawPeak*>> by_group;
    for (auto& rp : raw_peaks) by_group[{rp.calibrant, rp.instrument}].push_back(&rp);
    std::map<std::pair<std::string, std::string>, GroupFitMeta> meta;
    std::map<std::pair<std::string, std::string>, std::pair<double, double>> fits;
    for (auto& kv : by_group) {
        std::vector<std::tuple<double, double, double>> pts;
        pts.reserve(kv.second.size());
        for (const auto* rp : kv.second) {
            pts.emplace_back(rp->expected_nm, rp->raw_error_nm, rp->peak_area_raw);
        }
        auto r = stats::iterative_wls(pts, DRIFT_K_SIGMA, DRIFT_MAX_ITER);
        fits[kv.first] = {r.slope, r.intercept};
        GroupFitMeta gm;
        gm.residual_stddev = r.residual_stddev;
        gm.n_outliers_removed = r.n_outliers_removed;
        gm.iterations_used = r.iterations_used;
        meta[kv.first] = gm;
    }

    std::vector<CorrectedPeak> corrected;
    corrected.reserve(raw_peaks.size());
    std::map<std::string, std::vector<double>> err_sq_by_run;
    for (const auto& rp : raw_peaks) {
        const auto& fit = fits[{rp.calibrant, rp.instrument}];
        double trend = fit.first * rp.expected_nm + fit.second;
        double observed = rp.observed_nm_raw - trend;
        double error = observed - rp.expected_nm;
        CorrectedPeak cp;
        cp.run_id = rp.run_id;
        cp.instrument = rp.instrument;
        cp.batch = rp.batch;
        cp.calibrant = rp.calibrant;
        cp.peak_label = rp.peak_label;
        cp.expected_nm = rp.expected_nm;
        cp.observed_nm = observed;
        cp.error_nm = error;
        cp.peak_area = rp.peak_area_raw;
        cp.unrounded_error = error;
        corrected.push_back(cp);
        err_sq_by_run[rp.run_id].push_back(error);
    }
    std::map<std::string, double> rms_by_run;
    for (const auto& kv : err_sq_by_run) {
        double s = 0.0;
        for (double e : kv.second) s += e * e;
        rms_by_run[kv.first] = std::sqrt(s / static_cast<double>(kv.second.size()));
    }

    // Inventory of every source file under /app/experiments (sorted ASCII).
    std::vector<std::string> source_files;
    for (const auto& rel : io::list_files_recursive(exp_dir)) {
        source_files.push_back("/app/experiments/" + rel);
    }

    write_run_audit(out_dir + "/run_audit.json", included_partials, rms_by_run,
                    excluded, source_files);
    write_calibration_summary(out_dir + "/calibration_summary.json", corrected,
                              meta, included_partials, rms_by_run);
    write_peak_table(out_dir + "/peak_table.csv", corrected);
    return 0;
}
CPP

# ---------------------------------------------------------------------------
# Build & run
# ---------------------------------------------------------------------------
make -s clean
make -s
./build/calibrate
