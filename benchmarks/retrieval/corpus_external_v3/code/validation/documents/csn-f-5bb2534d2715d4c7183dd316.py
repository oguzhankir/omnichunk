def setup_TreeRegression(self, covariation=True):
        
        from .treeregression import TreeRegression
        tip_value = lambda x:np.mean(x.raw_date_constraint) if (x.is_terminal() and (x.bad_branch is False)) else None
        branch_value = lambda x:x.mutation_length
        if covariation:
            om = self.one_mutation
            branch_variance = lambda x:((x.clock_length if hasattr(x,'clock_length') else x.mutation_length)
                                        +(self.tip_slack**2*om if x.is_terminal() else 0.0))*om
        else:
            branch_variance = lambda x:1.0 if x.is_terminal() else 0.0

        Treg = TreeRegression(self.tree, tip_value=tip_value,
                             branch_value=branch_value, branch_variance=branch_variance)
        Treg.valid_confidence = covariation
        return Treg
