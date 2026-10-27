def parse_multipart_form_data(boundary, data, arguments, files):
    
    # The standard allows for the boundary to be quoted in the header,
    # although it's rare (it happens at least for google app engine
    # xmpp).  I think we're also supposed to handle backslash-escapes
    # here but I'll save that until we see a client that uses them
    # in the wild.
    if boundary.startswith(b('"')) and boundary.endswith(b('"')):
        boundary = boundary[1:-1]
    if data.endswith(b("\r\n")):
        footer_length = len(boundary) + 6
    else:
        footer_length = len(boundary) + 4
    parts = data[:-footer_length].split(b("--") + boundary + b("\r\n"))
    for part in parts:
        if not part: continue
        eoh = part.find(b("\r\n\r\n"))
        if eoh == -1:
            logging.warning("multipart/form-data missing headers")
            continue
        headers = HTTPHeaders.parse(part[:eoh].decode("utf-8"))
        disp_header = headers.get("Content-Disposition", "")
        disposition, disp_params = _parse_header(disp_header)
        if disposition != "form-data" or not part.endswith(b("\r\n")):
            logging.warning("Invalid multipart/form-data")
            continue
        value = part[eoh + 4:-2]
        if not disp_params.get("name"):
            logging.warning("multipart/form-data value missing name")
            continue
        name = disp_params["name"]
        if disp_params.get("filename"):
            ctype = headers.get("Content-Type", "application/unknown")
            files.setdefault(name, []).append(dict(
                filename=disp_params["filename"], body=value,
                content_type=ctype))
        else:
            arguments.setdefault(name, []).append(value)
