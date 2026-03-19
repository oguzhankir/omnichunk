// Fixture: Kotlin sample for extended-language chunking tests.
package demo.app

private const val DEFAULT_CAP = 64

internal data class Metrics(var hits: Long = 0, var misses: Long = 0) {
    fun ratio(): Double {
        val t = hits + misses
        return if (t == 0L) 0.0 else hits.toDouble() / t.toDouble()
    }
}

interface Resettable {
    fun reset()
}

class Counter(private val name: String) : Resettable {
    private var value: Int = 0

    fun label(): String = name

    fun read(): Int = value

    fun bump() {
        value++
    }

    override fun reset() {
        value = 0
    }
}

class Registry {
    private val items = mutableListOf<Counter>()

    fun add(c: Counter) {
        items.add(c)
    }

    fun total(): Int = items.sumOf { it.read() }
}

object Helpers {
    fun add(a: Int, b: Int): Int = a + b
}

fun runDemo(args: Array<String>): Int {
    val m = Metrics(hits = 2, misses = 1)
    val c = Counter("alpha")
    c.bump()
    val reg = Registry()
    reg.add(c)
    println("${c.label()} ${m.ratio()} ${Helpers.add(1, 2)} ${args.size} $DEFAULT_CAP")
    return if (reg.total() > 0) 0 else 1
}

fun main(args: Array<String>) {
    kotlin.system.exitProcess(runDemo(args))
}

// --- additional helpers (fixture bulk) ---
private fun clamp(v: Int, lo: Int, hi: Int): Int = maxOf(lo, minOf(hi, v))

private class RingBuffer(private val cap: Int) {
    private val buf = IntArray(cap)
    private var head = 0
    private var size = 0

    fun push(x: Int) {
        buf[head % cap] = x
        head = (head + 1) % cap
        if (size < cap) size++
    }

    fun sum(): Int {
        var s = 0
        for (i in 0 until size) s += buf[i]
        return s
    }
}

fun extraKotlinFixtureNoise(seed: Int): Int {
    val r = RingBuffer(8)
    for (i in 0 until 12) r.push(seed + i)
    return clamp(r.sum(), 0, 1_000_000)
}
