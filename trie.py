from typing import Dict, Set, Iterator, Any
from utils import to_lower_bound_kebab_case
import json

from nodes import Node

class TrieNode:
    def __init__(self):
        self.children: Dict[str, TrieNode] = {}
        self.nodes: Set[Node] = set()

    def __eq__(self, __value: object) -> bool:
        if not isinstance(__value, TrieNode):
            return False
        return self.children == __value.children and self.nodes == __value.nodes

class Trie:
    def __init__(self):
        self.root = TrieNode()
        # self.node_ids: Set[str] = set()
        self.ids_to_nodes: Dict[str, Node] = {}

    def __len__(self) -> int:
        return len(self.ids_to_nodes)
    
    def __iter__(self) -> Iterator[Node]:
        return iter(self.ids_to_nodes.values())

    def __contains__(self, node: 'Node') -> bool:
        return node.id in self.ids_to_nodes
    
    def trie_to_dict(self, node) -> Dict[str, Any]:
        return {
            "nodes": [n.id for n in node.nodes],
            "children": {char: self.trie_to_dict(child) for char, child in node.children.items()}
        }

    def insert(self, node: Node) -> None:
        name = node.name
        if node.id not in self.ids_to_nodes:
            self.ids_to_nodes[node.id] = node
            current = self.root
            current.nodes.add(node)
            for char in to_lower_bound_kebab_case(name):
                if char not in current.children:
                    current.children[char] = TrieNode()
                current = current.children[char]
                current.nodes.add(node)

    def remove(self, node: Node) -> None:
        name = node.name
        if node.id in self.ids_to_nodes:
            del self.ids_to_nodes[node.id]
            current = self.root
            current.nodes.remove(node)
            for char in to_lower_bound_kebab_case(name):
                if char not in current.children:
                    raise RuntimeError("Trie is corrupted")
                current.children[char].nodes.remove(node)
                if len(current.children[char].nodes) == 0:
                    del current.children[char]
                    return
                current = current.children[char]

    def search(self, name: str) -> Set[Node]:
        '''
        Returns a set of nodes that match the given name.
        If id instead of name is given, returns the node with that id.
        '''
        if name in self.ids_to_nodes:
            return {self.ids_to_nodes[name]}
        current = self.root
        for char in to_lower_bound_kebab_case(name):
            if char not in current.children:
                return set()
            current = current.children[char]
        return current.nodes.copy()
    
    def __eq__(self, __value: object) -> bool:
        if not isinstance(__value, Trie):
            return False
        return self.ids_to_nodes == __value.ids_to_nodes
