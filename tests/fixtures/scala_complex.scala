package com.example.app

import scala.collection.mutable
import scala.concurrent.Future

trait Renderable {
  def render(): String
}

trait Persistable[T] {
  def save(item: T): Future[Unit]
  def find(id: Long): Future[Option[T]]
}

class User(val id: Long, val name: String) extends Renderable {
  def render(): String = s"User($id, $name)"
}

class UserStore extends Persistable[User] {
  private val cache: mutable.Map[Long, User] = mutable.Map.empty
  def save(item: User): Future[Unit] = Future.successful(cache.update(item.id, item))
  def find(id: Long): Future[Option[User]] = Future.successful(cache.get(id))
}

object Hello {
  val greeting: String = "hello"

  def main(args: Array[String]): Unit = {
    println(greeting)
    val u = new User(1, "Ada")
    println(u.render())
  }

  object Inner {
    def helper(n: Int): Int = n * n
  }
}

object Math {
  def square(x: Int): Int = x * x
  def cube(x: Int): Int = x * x * x
}
