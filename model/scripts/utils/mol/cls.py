from scripts.utils.mol.basic import get_mol, get_smiles
from scripts.utils.mol.chemutils import get_clique_mol, brics_decomp, tree_decomp, set_atommap, sanitize
from scripts.utils.mol.assemble import enum_assemble
import rdkit
import copy
import rdkit.Chem as Chem
from torch.utils.data import Dataset


def get_slots(smiles):
    mol = Chem.MolFromSmiles(smiles)
    return [(atom.GetSymbol(), atom.GetFormalCharge(), atom.GetTotalNumHs()) for atom in mol.GetAtoms()]


class Vocab(Dataset):
    def __init__(self, vocab_file):
        self.vocab = [x.strip("\r\n ") for x in open(vocab_file)]
        self.vmap = {x:i for i,x in enumerate(self.vocab)}
        self.slots = [get_slots(smiles) for smiles in self.vocab]

    def get_index(self, smiles):
        return self.vmap[smiles]

    def get_smiles(self, idx):
        return self.vocab[idx]

    def get_slots(self, idx):
        return copy.deepcopy(self.slots[idx])

    def size(self):
        return len(self.vocab)


class MolTreeNode(object):

    def __init__(self, smiles, clique=[]):
        self.smiles = smiles
        self.mol = get_mol(self.smiles)
        # self.mol = cmol

        self.clique = [x for x in clique]  # copy
        self.neighbors = []

    def add_neighbor(self, nei_node):
        self.neighbors.append(nei_node)

    def recover(self, original_mol):
        clique = []
        clique.extend(self.clique)
        if not self.is_leaf:
            for cidx in self.clique:
                original_mol.GetAtomWithIdx(cidx).SetAtomMapNum(self.nid)

        for nei_node in self.neighbors:
            clique.extend(nei_node.clique)
            if nei_node.is_leaf:  # Leaf node, no need to mark
                continue
            for cidx in nei_node.clique:
                # allow singleton node override the atom mapping
                if cidx not in self.clique or len(nei_node.clique) == 1:
                    atom = original_mol.GetAtomWithIdx(cidx)
                    atom.SetAtomMapNum(nei_node.nid)

        clique = list(set(clique))
        label_mol = get_clique_mol(original_mol, clique)
        self.label = Chem.MolToSmiles(Chem.MolFromSmiles(get_smiles(label_mol)))
        self.label_mol = get_mol(self.label)

        for cidx in clique:
            original_mol.GetAtomWithIdx(cidx).SetAtomMapNum(0)

        return self.label

    def assemble(self):
        neighbors = [nei for nei in self.neighbors if nei.mol.GetNumAtoms() > 1]
        neighbors = sorted(neighbors, key=lambda x: x.mol.GetNumAtoms(), reverse=True)
        singletons = [nei for nei in self.neighbors if nei.mol.GetNumAtoms() == 1]
        neighbors = singletons + neighbors

        cands = enum_assemble(self, neighbors)
        if len(cands) > 0:
            self.cands, self.cand_mols, _ = zip(*cands)
            self.cands = list(self.cands)
            self.cand_mols = list(self.cand_mols)
        else:
            self.cands = []
            self.cand_mols = []


class MolTree(object):
    def __init__(self, smiles):
        self.smiles = smiles
        self.mol = get_mol(smiles)

        '''
        #Stereo Generation
        mol = Chem.MolFromSmiles(smiles)
        self.smiles3D = Chem.MolToSmiles(mol, isomericSmiles=True)
        self.smiles2D = Chem.MolToSmiles(mol)
        self.stereo_cands = decode_stereo(self.smiles2D)
        '''

        cliques, edges = brics_decomp(self.mol)
        if len(edges) <= 1:
            cliques, edges = tree_decomp(self.mol)
        self.nodes = []
        root = 0
        for i, c in enumerate(cliques):
            cmol = get_clique_mol(self.mol, c)
            node = MolTreeNode(get_smiles(cmol), c)
            self.nodes.append(node)
            if min(c) == 0:
                root = i

        for x, y in edges:
            self.nodes[x].add_neighbor(self.nodes[y])
            self.nodes[y].add_neighbor(self.nodes[x])

        if root > 0:
            self.nodes[0], self.nodes[root] = self.nodes[root], self.nodes[0]

        for i, node in enumerate(self.nodes):
            node.nid = i + 1
            if len(node.neighbors) > 1:  # Leaf node mol is not marked
                set_atommap(node.mol, node.nid)
            node.is_leaf = (len(node.neighbors) == 1)

    def size(self):
        return len(self.nodes)

    def recover(self):
        for node in self.nodes:
            node.recover(self.mol)

    def assemble(self):
        for node in self.nodes:
            node.assemble()

if __name__ == "__main__":
    import sys
    import csv
    from rdkit import RDLogger

    cset = set()
    zinc_pass_list = []
    counts = {}

    print("start")

    with open("", "r") as f:
        reader = csv.DictReader(f)
        for i, row in enumerate(reader):
            smiles = row['smiles'] 
            try:
                mol = MolTree(smiles)
                for c in mol.nodes:
                    cset.add(c.smiles)
                    if c.smiles not in counts:
                        counts[c.smiles] = 1
                    else:
                        counts[c.smiles] += 1
                zinc_pass_list.append(smiles)
                print(i, smiles)
            except Exception as e:
                print("Fail. Not Considered.", e)

    print("Preprocessing Completed!")
    clique_list = list(cset)
    with open('', 'w') as file:
        for c in zinc_pass_list:
            file.write(c)
            file.write('\n')

    with open('', 'w') as file:
        for c in clique_list:
            file.write(c)
            file.write('\n')