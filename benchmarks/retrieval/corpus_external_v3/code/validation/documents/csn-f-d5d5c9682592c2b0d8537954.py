def from_object(cls: Type["Config"], instance: Union[object, str]) -> "Config":
        
        if isinstance(instance, str):
            try:
                path, config = instance.rsplit(".", 1)
            except ValueError:
                path = instance
                instance = importlib.import_module(instance)
            else:
                module = importlib.import_module(path)
                instance = getattr(module, config)

        mapping = {
            key: getattr(instance, key)
            for key in dir(instance)
            if not isinstance(getattr(instance, key), types.ModuleType)
        }
        return cls.from_mapping(mapping)
