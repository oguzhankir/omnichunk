def recursive_glob(root, spec):
	
	specs = (
		os.path.join(dirpath, dirname, spec)
		for dirpath, dirnames, filenames in os.walk(root)
		for dirname in dirnames
	)

	return itertools.chain.from_iterable(
		glob.iglob(spec)
		for spec in specs
	)
