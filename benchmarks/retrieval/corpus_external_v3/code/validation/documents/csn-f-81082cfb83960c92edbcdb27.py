def loads(data, wrapper=dict):
    
    if not isinstance(data, str):
        raise TypeError('can only load a str as an ACF but got ' + type(data).__name__)

    parsed = wrapper()
    current_section = parsed
    sections = []

    lines = (line.strip() for line in data.splitlines())

    for line in lines:
        try:
            key, value = line.split(None, 1)
            key = key.replace('"', '').lstrip()
            value = value.replace('"', '').rstrip()
        except ValueError:
            if line == SECTION_START:
                # Initialize the last added section.
                current_section = _prepare_subsection(parsed, sections, wrapper)
            elif line == SECTION_END:
                # Remove the last section from the queue.
                sections.pop()
            else:
                # Add a new section to the queue.
                sections.append(line.replace('"', ''))
            continue

        current_section[key] = value

    return parsed
