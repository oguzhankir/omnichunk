use std::collections::HashMap;

pub struct Config {
    pub host: String,
    pub port: u16,
}

impl Config {
    pub fn url(&self) -> String {
        format!("{}:{}", self.host, self.port)
    }
}

pub fn make_map() -> HashMap<String, usize> {
    let mut map = HashMap::new();
    map.insert("a".to_string(), 1);
    map.insert("b".to_string(), 2);
    map
}
