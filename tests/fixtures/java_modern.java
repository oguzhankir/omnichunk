package com.example.modern;

import java.util.List;
import java.util.Objects;

public @interface Loggable {
    String value() default "";
    int level() default 0;
}

public record Point(int x, int y) {
    public double distance(Point other) {
        return Math.hypot(x - other.x, y - other.y);
    }
}

public record User(String name, int age) {
    public User {
        Objects.requireNonNull(name);
        if (age < 0) throw new IllegalArgumentException();
    }
}

public sealed interface Shape permits Circle, Rectangle, Square {
    double area();
}

public final class Circle implements Shape {
    private final double r;

    public Circle(double r) { this.r = r; }

    @Override
    @Deprecated
    public double area() {
        return Math.PI * r * r;
    }

    static {
        System.out.println("Circle loaded");
    }
}

public final class Rectangle implements Shape {
    private final double w, h;
    public Rectangle(double w, double h) { this.w = w; this.h = h; }
    @Override public double area() { return w * h; }
}

public final class Square implements Shape {
    private final double s;
    public Square(double s) { this.s = s; }
    @Override public double area() { return s * s; }
}
