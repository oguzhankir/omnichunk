# frozen_string_literal: true

# Fixture: Ruby module for extended-language chunking tests.

module Demo
  VERSION = '0.1.0'

  module Internal
    MAX_ITEMS = 128

    def self.slug(s)
      s.downcase.gsub(/\s+/, '-')
    end
  end

  class Point
    attr_reader :x, :y

    def initialize(x, y)
      @x = x.to_i
      @y = y.to_i
    end

    def distance_sq(other)
      dx = @x - other.x
      dy = @y - other.y
      dx * dx + dy * dy
    end
  end

  class Counter
    def initialize(name)
      @name = name.to_s
      @value = 0
    end

    attr_reader :name, :value

    def bump
      @value += 1
    end
  end

  class Registry
    def initialize
      @list = []
    end

    def add(obj)
      @list << obj
    end

    def size
      @list.size
    end
  end
end

def add_numbers(a, b)
  a + b
end

def run_demo(argv)
  p1 = Demo::Point.new(3, 4)
  p2 = Demo::Point.new(0, 0)
  c = Demo::Counter.new('main')
  c.bump
  reg = Demo::Registry.new
  reg.add(c)
  puts "#{Demo::Internal.slug('Hello World')} #{p1.distance_sq(p2)} #{add_numbers(2, 3)} #{argv.size}"
  reg.size
end

exit(run_demo(ARGV).positive? ? 0 : 1)
