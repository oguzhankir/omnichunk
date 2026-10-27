def remove_api_key(file_name):
    
    with open(file_name, 'r') as fp:
        text = fp.read()
    text = re.sub(real_api_regex, zero_token_string, text)
    with open(file_name, 'w') as fp:
        fp.write(text)
    return
