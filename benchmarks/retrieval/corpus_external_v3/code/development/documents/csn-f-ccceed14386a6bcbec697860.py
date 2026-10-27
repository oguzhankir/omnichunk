def get_initial(self):
        
        self.query = self.get_queryset()
        mongo_ids = {'mongo_id': [str(x.id) for x in self.query]}
        return mongo_ids
