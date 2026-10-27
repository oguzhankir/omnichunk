def parse_line(parser, record_token, parsed_records):
    

    global SUPPORTED_RECORDS

    line = " ".join(record_token)

    # match parser to record type
    if len(record_token) >= 2 and record_token[1] in SUPPORTED_RECORDS:
        # with no ttl
        record_token = [record_token[1]] + record_token
    elif len(record_token) >= 3 and record_token[2] in SUPPORTED_RECORDS:
        # with ttl
        record_token = [record_token[2]] + record_token
        if record_token[0] == "TXT":
            record_token = record_token[:2] + ["--ttl"] + record_token[2:]
    try:
        rr, unmatched = parser.parse_known_args(record_token)
        assert len(unmatched) == 0, "Unmatched fields: %s" % unmatched
    except (SystemExit, AssertionError, InvalidLineException):
        # invalid argument 
        raise InvalidLineException(line)

    record_dict = rr.__dict__
    if record_token[0] == "TXT" and len(record_dict['txt']) == 1:
        record_dict['txt'] = record_dict['txt'][0]

    # what kind of record? including origin and ttl
    record_type = None
    for key in record_dict.keys():
        if key in SUPPORTED_RECORDS and (key.startswith("$") or record_dict[key] == key):
            record_type = key
            if record_dict[key] == key:
                del record_dict[key]
            break

    assert record_type is not None, "Unknown record type in %s" % rr

    # clean fields
    for field in record_dict.keys():
        if record_dict[field] is None:
            del record_dict[field]

    current_origin = record_dict.get('$ORIGIN', parsed_records.get('$ORIGIN', None))

    # special record-specific fix-ups
    if record_type == 'PTR':
        record_dict['fullname'] = record_dict['name'] + '.' + current_origin

    if len(record_dict) > 0:
        if record_type.startswith("$"):
            # put the value directly
            record_dict_key = record_type.lower()
            parsed_records[record_dict_key] = record_dict[record_type]
        else:
            record_dict_key = record_type.lower()
            parsed_records[record_dict_key].append(record_dict)

    return parsed_records
