package main

//go:generate stringer -type=Color
//go:generate mockgen -source=service.go

import (
	"fmt"
	"strings"
)

type Color int

const (
	Red Color = iota
	Green
	Blue
)

type Comparable[T any] interface {
	Compare(other T) int
}

type Renderer interface {
	Render() string
}

type Box[T any] struct {
	value T
}

func (b *Box[T]) Get() T {
	return b.value
}

type Alias = Color

type StringPair = [2]string

func init() {
	fmt.Println("package init")
}

func Map[T, U any](xs []T, f func(T) U) []U {
	out := make([]U, len(xs))
	for i, x := range xs {
		out[i] = f(x)
	}
	return out
}

func Filter[T any](xs []T, pred func(T) bool) []T {
	out := make([]T, 0, len(xs))
	for _, x := range xs {
		if pred(x) {
			out = append(out, x)
		}
	}
	return out
}

func Join(parts []string, sep string) string {
	return strings.Join(parts, sep)
}
