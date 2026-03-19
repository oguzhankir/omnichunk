<?php
/**
 * Fixture: PHP sample for extended-language chunking tests.
 */

declare(strict_types=1);

namespace Demo\App;

interface Resettable
{
    public function reset(): void;
}

final class Metrics
{
    public int $hits = 0;
    public int $misses = 0;

    public function ratio(): float
    {
        $t = $this->hits + $this->misses;
        return $t === 0 ? 0.0 : $this->hits / $t;
    }
}

class Counter implements Resettable
{
    public function __construct(private string $name)
    {
    }

    private int $value = 0;

    public function name(): string
    {
        return $this->name;
    }

    public function value(): int
    {
        return $this->value;
    }

    public function bump(): void
    {
        $this->value++;
    }

    public function reset(): void
    {
        $this->value = 0;
    }
}

class Registry
{
    /** @var list<Counter> */
    private array $items = [];

    public function add(Counter $c): void
    {
        $this->items[] = $c;
    }

    public function total(): int
    {
        $s = 0;
        foreach ($this->items as $c) {
            $s += $c->value();
        }
        return $s;
    }
}

function add_int(int $a, int $b): int
{
    return $a + $b;
}

function run_main(array $argv): int
{
    $m = new Metrics();
    $m->hits = 2;
    $m->misses = 1;
    $c = new Counter('alpha');
    $c->bump();
    $reg = new Registry();
    $reg->add($c);
    echo $c->name() . ' ' . $m->ratio() . ' ' . add_int(1, 2) . ' ' . count($argv) . PHP_EOL;
    return $reg->total() > 0 ? 0 : 1;
}

exit(run_main($argv));
