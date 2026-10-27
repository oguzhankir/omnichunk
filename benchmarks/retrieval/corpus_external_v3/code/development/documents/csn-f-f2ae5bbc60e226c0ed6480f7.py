def splitext_files_only(filepath):
	
	return (
		(filepath, '') if os.path.isdir(filepath) else os.path.splitext(filepath)
	)
