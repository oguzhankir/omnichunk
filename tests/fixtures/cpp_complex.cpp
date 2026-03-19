// Fixture: C++ sample for extended-language tests.
#include <cstdint>
#include <iostream>
#include <memory>
#include <string>
#include <vector>

namespace demo {
namespace internal {

constexpr std::size_t kMax = 128;

struct Metrics {
    std::uint64_t hits{0};
    std::uint64_t misses{0};
};

}  // namespace internal
}  // namespace demo

class Counter {
public:
    explicit Counter(std::string label) : label_(std::move(label)) {}

    void bump() { ++value_; }

    std::uint64_t read() const { return value_; }

    const std::string &label() const { return label_; }

private:
    std::string label_;
    std::uint64_t value_{0};
};

class BufferPool {
public:
    BufferPool() = default;

    void reserve(std::size_t n) { storage_.reserve(n); }

    void push(int v) { storage_.push_back(v); }

    std::size_t size() const { return storage_.size(); }

private:
    std::vector<int> storage_;
};

static int add(int a, int b) { return a + b; }

static std::unique_ptr<Counter> make_counter(const char *name) {
    return std::make_unique<Counter>(name ? name : "anon");
}

int run_demo(int argc, char **argv) {
    (void)argc;
    (void)argv;
    demo::internal::Metrics m{};
    m.hits = 1;
    auto c = make_counter("main");
    c->bump();
    BufferPool pool;
    pool.reserve(demo::internal::kMax);
    pool.push(add(2, 3));
    std::cout << c->label() << " " << c->read() << " pool=" << pool.size() << "\n";
    return 0;
}

int main(int argc, char **argv) { return run_demo(argc, argv); }
