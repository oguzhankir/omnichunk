def _ml_anc_marginal(self, store_compressed=False, final=True, sample_from_profile=False,
                         debug=False, **kwargs):
        

        tree = self.tree
        # number of nucleotides changed from prev reconstruction
        N_diff = 0

        L = self.multiplicity.shape[0]
        n_states = self.gtr.alphabet.shape[0]
        self.logger("TreeAnc._ml_anc_marginal: type of reconstruction: Marginal", 2)

        self.logger("Attaching sequence profiles to leafs... ", 3)
        #  set the leaves profiles
        for leaf in tree.get_terminals():
            # in any case, set the profile
            leaf.marginal_subtree_LH = seq2prof(leaf.original_cseq, self.gtr.profile_map)
            leaf.marginal_subtree_LH_prefactor = np.zeros(L)

        self.logger("Walking up the tree, computing likelihoods... ", 3)
        # propagate leaves --> root, set the marginal-likelihood messages
        for node in tree.get_nonterminals(order='postorder'): #leaves -> root
            # regardless of what was before, set the profile to ones
            tmp_log_subtree_LH = np.zeros((L,n_states), dtype=float)
            node.marginal_subtree_LH_prefactor = np.zeros(L, dtype=float)
            for ch in node.clades:
                ch.marginal_log_Lx = self.gtr.propagate_profile(ch.marginal_subtree_LH,
                    self._branch_length_to_gtr(ch), return_log=True) # raw prob to transfer prob up
                tmp_log_subtree_LH += ch.marginal_log_Lx
                node.marginal_subtree_LH_prefactor += ch.marginal_subtree_LH_prefactor

            node.marginal_subtree_LH, offset = normalize_profile(tmp_log_subtree_LH, log=True)
            node.marginal_subtree_LH_prefactor += offset # and store log-prefactor

        self.logger("Computing root node sequence and total tree likelihood...",3)
        # Msg to the root from the distant part (equ frequencies)
        if len(self.gtr.Pi.shape)==1:
            tree.root.marginal_outgroup_LH = np.repeat([self.gtr.Pi], tree.root.marginal_subtree_LH.shape[0], axis=0)
        else:
            tree.root.marginal_outgroup_LH = np.copy(self.gtr.Pi.T)

        tree.root.marginal_profile, pre = normalize_profile(tree.root.marginal_outgroup_LH*tree.root.marginal_subtree_LH)
        marginal_LH_prefactor = tree.root.marginal_subtree_LH_prefactor + pre

        # choose sequence characters from this profile.
        # treat root node differently to avoid piling up mutations on the longer branch
        if sample_from_profile=='root':
            root_sample_from_profile = True
            other_sample_from_profile = False
        elif isinstance(sample_from_profile, bool):
            root_sample_from_profile = sample_from_profile
            other_sample_from_profile = sample_from_profile

        seq, prof_vals, idxs = prof2seq(tree.root.marginal_profile,
                                        self.gtr, sample_from_prof=root_sample_from_profile, normalize=False)

        self.tree.sequence_LH = marginal_LH_prefactor
        self.tree.total_sequence_LH = (self.tree.sequence_LH*self.multiplicity).sum()
        self.tree.root.cseq = seq
        gc.collect()

        if final:
            if self.is_vcf:
                self.tree.root.sequence = self.dict_sequence(self.tree.root)
            else:
                self.tree.root.sequence = self.expanded_sequence(self.tree.root)

        self.logger("Walking down the tree, computing maximum likelihood sequences...",3)
        # propagate root -->> leaves, reconstruct the internal node sequences
        # provided the upstream message + the message from the complementary subtree
        for node in tree.find_clades(order='preorder'):
            if node.up is None: # skip if node is root
                continue

            # integrate the information coming from parents with the information
            # of all children my multiplying it to the prev computed profile
            node.marginal_outgroup_LH, pre = normalize_profile(np.log(node.up.marginal_profile) - node.marginal_log_Lx,
                                                               log=True, return_offset=False)
            tmp_msg_from_parent = self.gtr.evolve(node.marginal_outgroup_LH,
                                                 self._branch_length_to_gtr(node), return_log=False)

            node.marginal_profile, pre = normalize_profile(node.marginal_subtree_LH * tmp_msg_from_parent, return_offset=False)

            # choose sequence based maximal marginal LH.
            seq, prof_vals, idxs = prof2seq(node.marginal_profile, self.gtr,
                                            sample_from_prof=other_sample_from_profile, normalize=False)

            if hasattr(node, 'cseq') and node.cseq is not None:
                N_diff += (seq!=node.cseq).sum()
            else:
                N_diff += L

            #assign new sequence
            node.cseq = seq
            if final:
                if self.is_vcf:
                    node.sequence = self.dict_sequence(node)
                else:
                    node.sequence = self.expanded_sequence(node)
                node.mutations = self.get_mutations(node)


        # note that the root doesn't contribute to N_diff (intended, since root sequence is often ambiguous)
        self.logger("TreeAnc._ml_anc_marginal: ...done", 3)
        if store_compressed:
            self._store_compressed_sequence_pairs()

        # do clean-up:
        if not debug:
            for node in self.tree.find_clades():
                try:
                    del node.marginal_log_Lx
                    del node.marginal_subtree_LH_prefactor
                except:
                    pass
        gc.collect()

        return N_diff
