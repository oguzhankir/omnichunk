def from_mapping(
        cls: Type["Config"], mapping: Optional[Mapping[str, Any]] = None, **kwargs: Any
    ) -> "Config":
        
        mappings: Dict[str, Any] = {}
        if mapping is not None:
            mappings.update(mapping)
        mappings.update(kwargs)
        config = cls()
        for key, value in mappings.items():
            try:
                setattr(config, key, value)
            except AttributeError:
                pass

        return config
