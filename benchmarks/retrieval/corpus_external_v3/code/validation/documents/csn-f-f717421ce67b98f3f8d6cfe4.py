def from_toml(cls: Type["Config"], filename: FilePath) -> "Config":
        
        file_path = os.fspath(filename)
        with open(file_path) as file_:
            data = toml.load(file_)
        return cls.from_mapping(data)
