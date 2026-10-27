def optimal_branch_length(self, node):
        
        if node.up is None:
            return self.one_mutation

        parent = node.up
        if hasattr(node, 'compressed_sequence'):
            new_len = self.gtr.optimal_t_compressed(node.compressed_sequence['pair'],
                                                    node.compressed_sequence['multiplicity'])
        else:
            new_len = self.gtr.optimal_t(parent.cseq, node.cseq,
                                         pattern_multiplicity=self.multiplicity,
                                         ignore_gaps=self.ignore_gaps)
        return new_len
