def completely_parse_reader(parser: Parser[Input, Output], reader: Reader[Input]) -> Result[Output]:
    
    result = (parser << eof).consume(reader)

    if isinstance(result, Continue):
        return Success(result.value)
    else:
        used = set()
        unique_expected = []
        for expected_lambda in result.expected:
            expected = expected_lambda()
            if expected not in used:
                used.add(expected)
                unique_expected.append(expected)

        return Failure(result.farthest.expected_error(' or '.join(unique_expected)))
