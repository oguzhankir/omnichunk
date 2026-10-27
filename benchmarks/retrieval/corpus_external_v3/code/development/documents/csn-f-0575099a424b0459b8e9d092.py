def get_unique_pathname(path, root=''):
	
	path = os.path.join(root, path)
	# consider the path supplied, then the paths with numbers appended
	potentialPaths = itertools.chain((path,), __get_numbered_paths(path))
	potentialPaths = six.moves.filterfalse(os.path.exists, potentialPaths)
	return next(potentialPaths)
