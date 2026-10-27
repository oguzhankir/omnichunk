def get_sized_root_folder(self):
        
        folder, filename = os.path.split(self.name)
        return os.path.join(VERSATILEIMAGEFIELD_SIZED_DIRNAME, folder, '')
