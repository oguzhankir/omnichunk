def opt(parser: Union[Parser, Sequence[Input]]) -> OptionalParser:
    
    if isinstance(parser, str):
        parser = lit(parser)
    return OptionalParser(parser)
