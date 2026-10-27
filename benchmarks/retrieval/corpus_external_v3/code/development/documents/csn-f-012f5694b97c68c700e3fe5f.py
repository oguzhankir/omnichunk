def combine_filenames(filenames, max_length=40):
    
    # Get the SHA for each file, then sha all the shas.

    path = None
    names = []
    extension = None
    timestamps = []
    shas = []
    filenames.sort()
    concat_names = "_".join(filenames)
    if concat_names in COMBINED_FILENAMES_GENERATED:
        return COMBINED_FILENAMES_GENERATED[concat_names]

    for filename in filenames:
        name = os.path.basename(filename)
        if not extension:
            extension = os.path.splitext(name)[1]
        elif os.path.splitext(name)[1] != extension:
            raise ValueError("Can't combine multiple file extensions")

        for base in MEDIA_ROOTS:
            try:
                shas.append(md5(os.path.join(base, filename)))
                break
            except IOError:
                pass


        if path is None:
            path = os.path.dirname(filename)
        else:
            if len(os.path.dirname(filename)) < len(path):
                path = os.path.dirname(filename)

    m = hashlib.md5()
    m.update(",".join(shas))

    new_filename = "%s-inkmd" % m.hexdigest()

    new_filename = new_filename[:max_length]
    new_filename += extension
    COMBINED_FILENAMES_GENERATED[concat_names] = new_filename

    return os.path.join(path, new_filename)
