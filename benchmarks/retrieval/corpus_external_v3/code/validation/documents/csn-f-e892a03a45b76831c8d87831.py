def remove_class(text):
    

    # see RFC 1035 for list of classes
    lines = text.split("\n")
    ret = []
    for line in lines:
        tokens = tokenize_line(line)
        tokens_upper = [t.upper() for t in tokens]

        if "IN" in tokens_upper:
            tokens.remove("IN")
        elif "CS" in tokens_upper:
            tokens.remove("CS")
        elif "CH" in tokens_upper:
            tokens.remove("CH")
        elif "HS" in tokens_upper:
            tokens.remove("HS")

        ret.append(serialize(tokens))

    return "\n".join(ret)
