def rep(parser: Union[Parser, Sequence[Input]]) -> RepeatedParser:
    
    if isinstance(parser, str):
        parser = lit(parser)
    return RepeatedParser(parser)
