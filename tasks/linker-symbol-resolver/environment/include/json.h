#pragma once
#include <string>
#include <vector>
#include <map>
#include <variant>
#include <stdexcept>
#include <sstream>
#include <fstream>
#include <cctype>
#include <cstdio>
#include <cstdint>

namespace json {

struct Value;
using Object = std::map<std::string, Value>;
using Array  = std::vector<Value>;

struct Value {
    std::variant<std::nullptr_t, bool, int64_t, double, std::string, Array, Object> d;

    Value() : d(nullptr) {}
    Value(std::nullptr_t) : d(nullptr) {}
    Value(bool b) : d(b) {}
    Value(int n) : d(static_cast<int64_t>(n)) {}
    Value(int64_t n) : d(n) {}
    Value(double v) : d(v) {}
    Value(const char* s) : d(std::string(s)) {}
    Value(std::string s) : d(std::move(s)) {}
    Value(Array a) : d(std::move(a)) {}
    Value(Object o) : d(std::move(o)) {}

    bool is_null()   const { return std::holds_alternative<std::nullptr_t>(d); }
    bool is_bool()   const { return std::holds_alternative<bool>(d); }
    bool is_int()    const { return std::holds_alternative<int64_t>(d); }
    bool is_double() const { return std::holds_alternative<double>(d); }
    bool is_string() const { return std::holds_alternative<std::string>(d); }
    bool is_array()  const { return std::holds_alternative<Array>(d); }
    bool is_object() const { return std::holds_alternative<Object>(d); }

    bool           gbool() const { return std::get<bool>(d); }
    int64_t        gint()  const { if (is_double()) return (int64_t)std::get<double>(d); return std::get<int64_t>(d); }
    double         gdbl()  const { if (is_int()) return (double)std::get<int64_t>(d); return std::get<double>(d); }
    const std::string& gstr() const { return std::get<std::string>(d); }
    const Array&   garr()  const { return std::get<Array>(d); }
    const Object&  gobj()  const { return std::get<Object>(d); }

    bool has(const std::string& k) const { return is_object() && gobj().count(k); }
    const Value& at(const std::string& k) const { return gobj().at(k); }
    size_t size() const { if (is_array()) return garr().size(); if (is_object()) return gobj().size(); return 0; }
};

inline std::string _ser(const Value& v, int ind, int dep) {
    std::string p(dep * ind, ' '), p1((dep + 1) * ind, ' ');
    if (v.is_null()) return "null";
    if (v.is_bool()) return v.gbool() ? "true" : "false";
    if (v.is_int()) return std::to_string(v.gint());
    if (v.is_double()) { char b[64]; std::snprintf(b, 64, "%g", v.gdbl()); return b; }
    if (v.is_string()) {
        std::string r = "\"";
        for (char c : v.gstr()) {
            if (c == '"') r += "\\\""; else if (c == '\\') r += "\\\\";
            else if (c == '\n') r += "\\n"; else r += c;
        }
        return r + "\"";
    }
    if (v.is_array()) {
        auto& a = v.garr();
        if (a.empty()) return "[]";
        std::string r = "[\n";
        for (size_t i = 0; i < a.size(); i++) {
            r += p1 + _ser(a[i], ind, dep + 1);
            if (i + 1 < a.size()) r += ",";
            r += "\n";
        }
        return r + p + "]";
    }
    auto& o = v.gobj();
    if (o.empty()) return "{}";
    std::string r = "{\n";
    size_t i = 0;
    for (auto& [k, val] : o) {
        r += p1 + "\"" + k + "\": " + _ser(val, ind, dep + 1);
        if (++i < o.size()) r += ",";
        r += "\n";
    }
    return r + p + "}";
}

inline std::string serialize(const Value& v, int indent = 2) { return _ser(v, indent, 0); }

namespace detail {
struct Parser {
    const std::string& s;
    size_t p = 0;
    void ws() { while (p < s.size() && std::isspace((unsigned char)s[p])) p++; }
    char peek() { ws(); return p < s.size() ? s[p] : 0; }
    void expect(char c) {
        ws();
        if (p >= s.size() || s[p] != c)
            throw std::runtime_error(std::string("expected '") + c + "' at pos " + std::to_string(p));
        p++;
    }
    std::string rstr() {
        expect('"');
        std::string r;
        while (p < s.size() && s[p] != '"') {
            if (s[p] == '\\') {
                p++;
                if (p < s.size()) {
                    if (s[p] == 'n') r += '\n';
                    else if (s[p] == 't') r += '\t';
                    else r += s[p];
                }
            } else r += s[p];
            p++;
        }
        if (p < s.size()) p++;
        return r;
    }
    Value rnum() {
        ws();
        size_t st = p;
        bool flt = false;
        if (s[p] == '-') p++;
        while (p < s.size() && std::isdigit((unsigned char)s[p])) p++;
        if (p < s.size() && s[p] == '.') { flt = true; p++; while (p < s.size() && std::isdigit((unsigned char)s[p])) p++; }
        if (p < s.size() && (s[p] == 'e' || s[p] == 'E')) { flt = true; p++; if (p < s.size() && (s[p] == '+' || s[p] == '-')) p++; while (p < s.size() && std::isdigit((unsigned char)s[p])) p++; }
        std::string n = s.substr(st, p - st);
        if (flt) return Value(std::stod(n));
        return Value((int64_t)std::stoll(n));
    }
    Value rval() {
        char c = peek();
        if (c == '"') return Value(rstr());
        if (c == '{') return robj();
        if (c == '[') return rarr();
        if (c == 't') { p += 4; return Value(true); }
        if (c == 'f') { p += 5; return Value(false); }
        if (c == 'n') { p += 4; return Value(nullptr); }
        return rnum();
    }
    Value robj() {
        expect('{');
        Object o;
        if (peek() != '}') {
            do { std::string k = rstr(); expect(':'); o[k] = rval(); } while (peek() == ',' && (p++, true));
        }
        expect('}');
        return Value(std::move(o));
    }
    Value rarr() {
        expect('[');
        Array a;
        if (peek() != ']') {
            do { a.push_back(rval()); } while (peek() == ',' && (p++, true));
        }
        expect(']');
        return Value(std::move(a));
    }
};
}

inline Value parse(const std::string& s) { detail::Parser p{s}; return p.rval(); }

inline Value load(const std::string& path) {
    std::ifstream f(path);
    if (!f) throw std::runtime_error("Cannot open: " + path);
    std::string s((std::istreambuf_iterator<char>(f)), std::istreambuf_iterator<char>());
    return parse(s);
}

}
