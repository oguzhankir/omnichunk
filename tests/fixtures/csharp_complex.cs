// Fixture: C# sample for extended-language chunking tests.
using System;
using System.Collections.Generic;
using System.Linq;

namespace Demo.App
{
    internal static class Constants
    {
        public const int DefaultCapacity = 64;
    }

    public sealed class Metrics
    {
        public long Hits { get; set; }
        public long Misses { get; set; }

        public double Ratio()
        {
            var t = Hits + Misses;
            return t == 0 ? 0.0 : (double)Hits / t;
        }
    }

    public interface IResettable
    {
        void Reset();
    }

    public class Counter : IResettable
    {
        private readonly string _name;
        private int _value;

        public Counter(string name)
        {
            _name = name ?? "anon";
        }

        public string Name => _name;

        public int Value => _value;

        public void Inc() => _value++;

        public void Reset() => _value = 0;
    }

    public class Registry
    {
        private readonly List<Counter> _items = new();

        public void Add(Counter c) => _items.Add(c);

        public int Total()
        {
            return _items.Sum(c => c.Value);
        }
    }

    internal static class Helpers
    {
        public static int Add(int a, int b) => a + b;
    }

    public static class Program
    {
        public static int Main(string[] args)
        {
            var m = new Metrics { Hits = 2, Misses = 1 };
            var c = new Counter("alpha");
            c.Inc();
            var reg = new Registry();
            reg.Add(c);
            Console.WriteLine($"{c.Name} {m.Ratio()} {Helpers.Add(1, 2)} {Constants.DefaultCapacity}");
            return reg.Total() > 0 ? 0 : 1;
        }
    }
}
