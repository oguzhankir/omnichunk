def add_prefix(multicodec, bytes_):
    
    prefix = get_prefix(multicodec)
    return b''.join([prefix, bytes_])
