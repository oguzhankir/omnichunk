use std::fmt::{self, Display, Formatter};
use std::collections::HashMap;

macro_rules! say_hi {
    () => {
        println!("hi");
    };
    ($name:expr) => {
        println!("hi {}", $name);
    };
}

macro_rules! square {
    ($x:expr) => { $x * $x };
}

pub trait Renderable {
    fn render(&self) -> String;
}

pub struct Greeter {
    pub name: String,
}

impl Greeter {
    pub(crate) fn new(name: String) -> Self {
        Greeter { name }
    }

    pub(super) fn greet(&self) {
        say_hi!(self.name);
    }
}

impl Renderable for Greeter {
    fn render(&self) -> String {
        format!("Greeter({})", self.name)
    }
}

impl Display for Greeter {
    fn fmt(&self, f: &mut Formatter<'_>) -> fmt::Result {
        write!(f, "{}", self.name)
    }
}

pub fn pick<'a, T: Clone + 'a>(items: &'a [T], idx: usize) -> Option<&'a T> {
    items.get(idx)
}

pub fn merge<'a, K, V>(a: &'a HashMap<K, V>, b: &'a HashMap<K, V>) -> HashMap<&'a K, &'a V>
where
    K: std::hash::Hash + Eq,
{
    let mut out: HashMap<&K, &V> = HashMap::new();
    for (k, v) in a.iter().chain(b.iter()) {
        out.insert(k, v);
    }
    out
}
