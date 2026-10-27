def to_line_string(self, closed=True):
        
        from imgaug.augmentables.lines import LineString
        if not closed or len(self.exterior) <= 1:
            return LineString(self.exterior, label=self.label)
        return LineString(
            np.concatenate([self.exterior, self.exterior[0:1, :]], axis=0),
            label=self.label)
