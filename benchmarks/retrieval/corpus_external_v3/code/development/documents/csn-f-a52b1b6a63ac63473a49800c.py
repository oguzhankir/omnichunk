def remove_prefix(bytes_):
    
    prefix_int = extract_prefix(bytes_)
    prefix = varint.encode(prefix_int)
    return bytes_[len(prefix):]
