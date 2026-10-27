def find(self, path, all=False):
        
        bits = path.split('/')
        dirs_to_serve = ['jspm_packages', settings.SYSTEMJS_OUTPUT_DIR]
        if not bits or bits[0] not in dirs_to_serve:
            return []
        return super(SystemFinder, self).find(path, all=all)
