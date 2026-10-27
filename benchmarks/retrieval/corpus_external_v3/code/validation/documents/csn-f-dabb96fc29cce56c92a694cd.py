def _prepare_subsection(data, sections, wrapper):
    
    current = data
    for i in sections[:-1]:
        current = current[i]

    current[sections[-1]] = wrapper()
    return current[sections[-1]]
