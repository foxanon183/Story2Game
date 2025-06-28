from __future__ import annotations 
from typing import List, Set, Tuple, Union, Dict, Any, cast, Type
from nodes import Node
from dataclasses import dataclass
import re
import regex as reg
from operation import GraphOperation, MoveNodeOperation, SetNodeAttributeOperation
from utils import replace_placeholders, remove_extra_spaces, to_literal, print_warning
from typing import TYPE_CHECKING
from nodes import Room, Item, ContainerItem, Character, Player
from type import OperatorString, NodeType
from simpleeval import simple_eval # type: ignore
import ast
from copy import deepcopy
from llm.llm import LLM
import game_construct_prompt

if TYPE_CHECKING:
    from game import Game
    from world import World

class Condition:

    def get_canonical_form(self) -> str:
        return str(self)

    def evaluate(self, game:Game, verbose:bool=False) -> Tuple[bool, List[str]]:
        raise NotImplementedError('evaluate() not implemented.')
    
    def get_individual_field_info(self, game:Game) -> Dict[str, Tuple[bool, str]]:
        raise NotImplementedError('get_info() not implemented.')
    
    def get_fixes_with_llm(self, game:Game, llm: LLM) -> List[GraphOperation]:
        #print("GETTING FIXES WITH LLM")
        #print(self.get_individual_field_info(game))
        _, _, fixes = game_construct_prompt.fix_precondition(llm, self.get_canonical_form(), self.get_individual_field_info(game))
    
        # Now, test if the fixes are valid.
        game_copy = deepcopy(game)
        for fix in fixes:
            fix.apply(game_copy.world)
        
        is_fix_satisfied, messages = self.evaluate(game_copy, verbose=True)
        if is_fix_satisfied:
            return fixes
        else:
            raise ValueError(f'Attempts to fix the game state to satisfy the preconditions ({str(self)}) failed. The fixes ({fixes}) are not valid: {messages}. Please modify the preconditions.')
    
    def get_fixes(self, game:Game, llm: Union[LLM, None]=None, force_using_llm:bool=False) -> List[GraphOperation]:
        raise NotImplementedError('get_fixes() not implemented.')

    def __eq__(self, __value: object) -> bool:
        if not isinstance(__value, Condition):
            return False
        if self.__class__ != __value.__class__:
            return False
        return self.__dict__ == __value.__dict__ # TODO: need a better comparison: standardize all fields in post_init

class ConditionField:
    def evaluate(self, game:Game, verbose:bool=False) -> Tuple[bool, str]:
        raise NotImplementedError('evaluate() not implemented.')
    
    def get_fixes(self, game:Game, test_in_copied_game:bool=True) -> Tuple[bool, List[GraphOperation]]:
        raise NotImplementedError('get_fixes() not implemented.')

@dataclass
class NodeLocationConditionField(ConditionField):
    location: Union[str, Room]
    nodes: Union[str, Node, List[str], List[Node], None] = ''

    def __post_init__(self) -> None:
        if isinstance(self.location, str):
            self.location = remove_extra_spaces(self.location)
            if ';' in self.location:
                raise ValueError('A node cannot be in multiple locations at the same time.')
        
        # Standardize the self.nodes into a list of strings.
        if isinstance(self.nodes, Node):
            self.nodes = [self.nodes.id]
        elif isinstance(self.nodes, str):
            self.nodes = [remove_extra_spaces(i) for i in self.nodes.split(';') if remove_extra_spaces(i)]
        elif isinstance(self.nodes, list):
            self.nodes = [i.id if isinstance(i, Node) else remove_extra_spaces(i) for i in self.nodes]
            self.nodes = [i for i in self.nodes if i] # remove empty strings
        else:
            self.nodes = ['player'] # default to player
        if not self.nodes: # empty list, None, or ''
            self.nodes = ['player']

    def __str__(self) -> str:
        self.nodes = cast(List[str], self.nodes)
        location = self.location if isinstance(self.location, str) else self.location.name
        nodes = ';'.join(self.nodes)
        return f'{{{nodes} at {location}}}'

    def evaluate(self, game:Game, verbose:bool=False) -> Tuple[bool, str]:
        '''
        Check if the condition is satisfied.
        '''
        #print("EVALUATING NODE_LOCATION", self)
        try:
            if isinstance(self.location, str):
                location = game.world.find_node(self.location, error_message_verbose=verbose) # will raise error if node not found
            else:
                location = self.location
                assert location in game.world.nodes, f'{location} is not in the world.'
            if not isinstance(location, Room):
                return False, "Location is not a room"
            
            self.nodes = cast(List[str], self.nodes)
            for node_name in self.nodes:
                assert isinstance(node_name, str), "Bug! node is not a string."
                if node_name == 'player':
                    node = game.world.player
                    if node is None:
                        return False, "Player is None"
                else:
                    try:
                        node = game.world.find_node(node_name, room=location.id, local=True, error_message_verbose=verbose)
                    except Exception:
                        node = game.world.find_node(node_name, error_message_verbose=verbose)
                    if isinstance(node, Room):
                        return True, ''
                if node_name == 'player' and node.get_room() != location:
                    return False, f'{node} is not in {self.location}.'
                else:
                    if node.get_room() != location:
                        return False, f'{node} is not in {self.location}.'
        except Exception as e:
            return False, str(e)
        return True, ''
    
    def get_fixes(self, game:Game, test_in_copied_game:bool=True) -> Tuple[bool, List[GraphOperation]]:
        '''
        Get the fixes for the condition.

        Returns:
            Tuple[Bool, List[GraphOperation]]: A tuple of the form (is_fixable, [fix1, fix2, ...]). If is_fixable is False, the list of fixes is empty.
        '''
        fixes: List[GraphOperation] = []
        #print("FIXING NODE_LOCATION")
        #print(self)
        try:
            if isinstance(self.location, str):
                location = game.world.find_node(self.location, error_message_verbose=True) # will raise error if node not found
            else:
                location = self.location
            self.nodes = cast(List[str], self.nodes)
            #print(self.nodes)
            for node_name in self.nodes:
                if node_name == 'player':
                    node = game.world.player
                    assert node is not None, "Player is None"
                else:
                    node = game.world.find_node(node_name, error_message_verbose=True)
                    #print("CHECKING IF ROOM IN ROOM")
                    for thing in fixes:
                        if thing.node_name == node_name:
                            #print("YES, it has been moved already")
                            continue
                    #print(node, node_name, node.get_room(), type(node.container), location, type(location))
                    if isinstance(node, Room) and node.container == location:
                        continue
                    elif node.get_room() != location:
                        fixes.append(MoveNodeOperation(node.id, location.id))
            #print("NODELOCATION FIXES")
            #print(fixes)
            if test_in_copied_game:
            # Now, test if the fixes are valid.
                game_copy = deepcopy(game)
                for fix in fixes:
                    fix.apply(game_copy.world)
                
                is_fix_satisfied, messages = self.evaluate(game_copy, verbose=True)
                if is_fix_satisfied:
                    return True, fixes
                else:
                    print_warning(f'Fixes {fixes} are not valid: {messages}')
                    return False, []
            else:
                return True, fixes
        except Exception as e:
            print_warning(e)
            return False, []
    
@dataclass
class NodeVisibleConditionField(ConditionField):
    '''
    Check if nodes are visible to the agent. If the node is a room, check if the agent is in the room or the room is adjacent to the agent's room. Else, check if the node is in the same room as the agent.
    '''
    nodes : Union[List[str], List[Node]]
    agent: Union[str, Character, None] = ''

    def __post_init__(self) -> None:
        if isinstance(self.agent, str):
            self.agent = remove_extra_spaces(self.agent)
            if self.agent == 'player':
                self.agent = None
        # Input might be a list of string, each string might be a series of node names separated by ';'.
        nodes = self.nodes
        if len(nodes) > 0:
            if isinstance(nodes[0], str):
                node_names: List[str] = [node for node in nodes if isinstance(node, str)]
                assert len(node_names) == len(nodes), f'Node names must be all strings or all Nodes. {nodes} is not valid.'
                node_names_extended = [i.split(';') for i in node_names]
                self.nodes = [j for i in node_names_extended for j in i] # flatten the list

    def __str__(self) -> str:
        agent = self.agent if self.agent else 'player'
        agent = agent if isinstance(agent, str) else agent.name
        nodes = [node if isinstance(node, str) else node.name for node in self.nodes]
        return f'{{{nodes} is available to {agent}}}'

    def evaluate(self, game:Game, verbose:bool=False) -> Tuple[bool, str]:
        '''
        Check if the condition is satisfied.
        '''
        return True, ''
        try:
            if self.agent:
                if isinstance(self.agent, str):
                    agent_node = game.world.find_node(self.agent, error_message_verbose=verbose) # will raise error if node not found
                else:
                    agent_node = self.agent
                    assert agent_node in game.world.nodes, f'{agent_node} is not in the world.'
                if not isinstance(agent_node, Character):
                    return False, "Agent is not a character"
            else:
                agent_node = game.world.player
                if agent_node is None:
                    return False, "Player is None"
            print("NodeVisible evaluate getting agent_node")
            agent_room = agent_node.get_room()
            print(agent_room)
            for node in self.nodes:
                if isinstance(node, str):
                    node = game.world.find_node(node, room=agent_room.id, local=True, error_message_verbose=verbose)
                else:
                    assert node in game.world.nodes, f'No node with name "{node.name}" can be found in the world.'
                    if not (isinstance(node, Room) or node.get_room() == agent_room):
                        return False, f'No node with name "{node.name}" can be found where {agent_node.name} is located. However, {node.name} exists at {node.get_room()}.' if verbose else f'No node with name "{node.name}" can be found'
        except Exception as e:
            return False, str(e)
        return True, ''
    
    def get_fixes(self, game:Game, test_in_copied_game:bool=True) -> Tuple[bool, List[GraphOperation]]:
        fixes: List[GraphOperation] = []
        #return True, fixes
        try:
            agent_node = game.world.player if not self.agent else game.world.find_node(self.agent, error_message_verbose=True) if isinstance(self.agent, str) else self.agent
            #assert isinstance(agent_node, Character), "Agent is not a character"
            agent_room = agent_node.get_room()
            nodes:List[Node] = []
            for node in self.nodes:
                if isinstance(node, str):
                    try:
                        node = game.world.find_node(node, room=agent_room.id, local=True, error_message_verbose=True)
                    except Exception:
                        node = game.world.find_node(node, error_message_verbose=True)
                    nodes.append(node)
                else:
                    nodes.append(node)
            #print("VISIBLE FIXING")
            #print(self, agent_node, agent_room, nodes)
            for node in nodes:
                #print("VISIBLE NODES")
                #print(nodes)
                if isinstance(node, Room):
                    #print_warning(f'Cannot fix the condition because the room is not visible to the agent. Please manually move the agent.')
                    #print(agent_node.id, agent_room.id, node.id)
                    if agent_room.id == node.id:
                        continue
                    else:
                        fixes.append(MoveNodeOperation(agent_node.id, node.id))
                    #return False, []
                else:
                    #print("CHECKING IF ITEM ALREADY IN INVENTORY")
                    #print(node, node.container, agent_node.inventory, node.get_room(), agent_room)
                    if isinstance(node, Item) and node in agent_node.inventory:
                        continue
                    if node.get_room() != agent_room:
                        #print_warning(f'Moving operation from non-player node to room.')
                        #print(agent_node.id, agent_room.id, node.id)
                        continue
                        fixes.append(MoveNodeOperation(node.id, agent_room.id))
    
            if test_in_copied_game:
            # Now, test if the fixes are valid.
                game_copy = deepcopy(game)
                for fix in fixes:
                    fix.apply(game_copy.world)
                
                is_fix_satisfied, messages = self.evaluate(game_copy, verbose=True)
                if is_fix_satisfied:
                    return True, fixes
                else:
                    print_warning(f'Fixes {fixes} are not valid: {messages}')
                    return False, []
            else:
                return True, fixes
        except Exception as e:
            print_warning(e)
            return False, []
        
@dataclass
class InventoryConditionField(ConditionField):
    items: Union[str, Item, List[str], List[Item]]
    owners: Union[str, Character, List[str], List[Character], None] = ''

    def __post_init__(self) -> None:
        # Standardize the inputs into a list of strings.
        if isinstance(self.items, Item):
            self.items = [self.items.id]
        elif isinstance(self.items, str):
            self.items = [remove_extra_spaces(i) for i in self.items.split(';') if remove_extra_spaces(i)]
        else:
            self.items = [i.id if isinstance(i, Item) else remove_extra_spaces(i) for i in self.items]
        
        if isinstance(self.owners, Character):
            self.owners = [self.owners.id]
        elif isinstance(self.owners, str):
            self.owners = [remove_extra_spaces(i) for i in self.owners.split(';') if remove_extra_spaces(i)]
        elif isinstance(self.owners, list):
            self.owners = [i.id if isinstance(i, Character) else remove_extra_spaces(i) for i in self.owners]
            self.owners = [i for i in self.owners if i] # remove empty strings
        else:
            self.owners = ['player']
        if not self.owners: # empty list, None, or ''
            self.owners = ['player']
            
    def __str__(self) -> str:
        self.owners = cast(List[str], self.owners)
        self.items = cast(List[str], self.items)
        owner = ';'.join(self.owners)
        item = ';'.join(self.items)
        return f'{{{owner} has {item}}}'

    def evaluate(self, game:Game, verbose:bool=False) -> Tuple[bool, str]:
        '''
        Check if the condition is satisfied.
        '''
        try:
            self.owners = cast(List[str], self.owners)
            self.items = cast(List[str], self.items)
            for owner in self.owners:
                assert isinstance(owner, str), "Bug! Owner is not a string."
                if owner == 'player':
                    owner = game.world.player
                    if owner is None:
                        return False, "Player is None"
                else:
                    owner = game.world.find_node(owner, error_message_verbose=verbose)
                #if not isinstance(owner, Character):
                #    return False, "Owner is not a character"
                
                for item in self.items:
                    assert isinstance(item, str), "Bug! Item is not a string."
                    try:
                        item = game.world.find_node(item, room=owner.get_room().id, local=True, error_message_verbose=verbose)
                    except Exception:
                        item = game.world.find_node(item, error_message_verbose=verbose)
                    if not isinstance(item, Item):
                        return False, "Item is not an item"
                    owner_has_item, message = self._evaluate(owner, item)
                    if not owner_has_item:
                        return False, message
            return True, ''
        except Exception as e:
            return False, str(e)

    def _evaluate(self, owner: Character, item: Item) -> Tuple[bool, str]:
        container = item.container
        while container is not None:
            if container == owner:
                return True, ''
            container = container.container
        return False, f'{owner.name} does not have {item.name}. {owner.name} has {[i.name for i in owner.inventory]}.'

    def get_fixes(self, game:Game, test_in_copied_game:bool=True) -> Tuple[bool, List[GraphOperation]]:
        '''
        Get the fixes for the condition.

        Returns:
            Tuple[Bool, List[GraphOperation]]: A tuple of the form (is_fixable, [fix1, fix2, ...]). If is_fixable is False, the list of fixes is empty.
        '''
        fixes: List[GraphOperation] = []
        #return True, fixes
        try:
            self.owners = cast(List[str], self.owners)
            self.items = cast(List[str], self.items)
            #print("INVENTORY CONDITION FIXING")
            #print(self.owners)
            #print(self.items)
            for owner in self.owners:
                if owner == 'player':
                    owner = game.world.player
                    assert owner is not None, "Player is None"
                else:
                    owner = game.world.find_node(owner, error_message_verbose=True)
                #assert isinstance(owner, Character), "Owner is not a character"
                
                for item in self.items:
                    item = game.world.find_node(item, error_message_verbose=True)
                    assert isinstance(item, Item), "Item is not an item"
                    owner_has_item, _ = self._evaluate(owner, item)
                    if not owner_has_item:
                            fixes.append(MoveNodeOperation(item.id, owner.id))
            
            if test_in_copied_game:
            # Now, test if the fixes are valid.
                game_copy = deepcopy(game)
                for fix in fixes:
                    fix.apply(game_copy.world)
                
                is_fix_satisfied, messages = self.evaluate(game_copy, verbose=True)
                if is_fix_satisfied:
                    return True, fixes
                else:
                    print_warning(f'Fixes {fixes} are not valid: {messages}')
                    return False, []
            else:
                return True, fixes
        except Exception as e:
            print_warning(e)
            return False, []

@dataclass
class NodeAttributeConditionField(ConditionField):
    nodes: Union[str, Node, List[Node]]
    attribute: str
    value: Union[str, Any]
    operator: OperatorString = '=='

    def __str__(self) -> str:
        nodes = self.nodes if isinstance(self.nodes, str) else ';'.join([node.name for node in self.nodes]) if isinstance(self.nodes, list) else self.nodes.name
        return f'{{{nodes}.{self.attribute}{self.operator}{self.value}}}'

    def evaluate(self, game:Game, verbose:bool=False) -> Tuple[bool, str]:
        '''
        Check if the condition is satisfied.
        '''
        try:
            if isinstance(self.nodes, Node):
                nodes: List[Node] = [self.nodes]
            elif isinstance(self.nodes, str):
                node_names: List[str] = [remove_extra_spaces(i) for i in self.nodes.split(';')]
                for i in range(len(node_names)): 
                    if node_names[i] == 'player':
                        player_node = game.world.player
                        if player_node is None:
                            return False, "Player is None"
                        node_names[i] = player_node.id
                nodes: List[Node] = [game.world.find_node(node_name, error_message_verbose=verbose) for node_name in node_names] # will raise error if node not found
            else:
                nodes = self.nodes
            if "is_" in self.attribute:
                return True, ' '
            if self.attribute not in Node.additional_attribute_list:
                raise Exception(f'Attribute {self.attribute} is not registered for any nodes in the game.')
            _, _, belonging_class, _, _ = Node.additional_attribute_list[self.attribute]
            for node in nodes:
                assert node in game.world.nodes, f'{node} is not in the world.'
                if not isinstance(node, belonging_class):
                    raise Exception(f'Attribute {self.attribute} of node {node.name} is not of type {belonging_class}.')
                # TODO: For value comparison, we may need to convert the value to the correct type.
                if isinstance(self.value, str):
                    _, literal_value = to_literal(self.value)
                    attempt_succeeded = False
                    # TODO: Allow comparing two attributes, such as player.money and item.price
                    # First, try directly comparing the literal value.
                    try:
                        # special: when node attribute is None, the attribute is not specified, so we cannot compare it with a value.
                        if node.get_attribute(self.attribute) is None and literal_value is not None:
                            return False, f'Attribute "{self.attribute}" is not specified for {node.name}. We do not know if {node.name}.{self.attribute} {self.operator} {self.value}.'
                        if self. operator == '==':
                            if node.get_attribute(self.attribute) == literal_value:     
                                attempt_succeeded = True
                        elif self.operator == '!=':
                            if node.get_attribute(self.attribute) != literal_value:
                                attempt_succeeded = True
                        elif self.operator == '>':
                            if node.get_attribute(self.attribute) > literal_value:
                                attempt_succeeded = True
                        elif self.operator == '<':
                            if node.get_attribute(self.attribute) < literal_value:
                                attempt_succeeded = True
                        elif self.operator == '>=':
                            if node.get_attribute(self.attribute) >= literal_value:
                                attempt_succeeded = True
                        elif self.operator == '<=':
                            if node.get_attribute(self.attribute) <= literal_value:
                                attempt_succeeded = True
                        else:
                            raise ValueError(f'Invalid operator: {self.operator}')
                    except Exception:
                        pass
                    if not attempt_succeeded: # Then, try directly comparing the string value.
                        if self.operator == '==':
                            if remove_extra_spaces(str(node.get_attribute(self.attribute)).lower()) == remove_extra_spaces(self.value.lower()):
                                attempt_succeeded = True
                        elif self.operator == '!=':
                            if remove_extra_spaces(str(node.get_attribute(self.attribute)).lower()) != remove_extra_spaces(self.value.lower()):
                                attempt_succeeded = True
                        else: # we cannot compare strings with >, <, >=, <= (dictionary order is not the same as numerical order)
                            return False, f'Unable to compare {node.name}.{self.attribute} with {self.value} using operator {self.operator}. {node.name}.{self.attribute} = {node.get_attribute(self.attribute)} is of type {type(node.get_attribute(self.attribute))}. {self.value} is of type {type(self.value)}.'
                    if not attempt_succeeded:
                        if node.get_attribute(self.attribute) is None:
                            return False, f'Attribute "{self.attribute}" is not specified for {node.name}. We do not know if {node.name}.{self.attribute} {self.operator} {self.value}.'
                        return False, f'{node.name}.{self.attribute} is not {self.value}. {node.name}.{self.attribute} = {node.get_attribute(self.attribute)}.'
                else:
                    if self.operator == '==':
                        if node.get_attribute(self.attribute) is None and self.value is not None:
                            return False, f'Attribute "{self.attribute}" is not specified for {node.name}. We do not know if it is {self.value}.'
                        if not node.get_attribute(self.attribute) == self.value:
                            return False, f'{node.name}.{self.attribute} is not {self.value}.{node.name}.{self.attribute} = {node.get_attribute(self.attribute)}.'
                    elif self.operator == '!=':
                        # special: when node attribute is None, the attribute is not specified, so we cannot compare it with a value.
                        if node.get_attribute(self.attribute) is None and self.value is not None:
                            return False, f'Attribute "{self.attribute}" is not specified for {node.name}. We do not know if it is {self.value}.'
                        if not node.get_attribute(self.attribute) != self.value:
                            return False, f'{node.name}.{self.attribute} is {self.value}.'
                    elif self.operator == '>':
                        if not node.get_attribute(self.attribute) > self.value:
                            return False, f'{node.name}.{self.attribute} is not greater than {self.value}. {node.name}.{self.attribute} = {node.get_attribute(self.attribute)}.'
                    elif self.operator == '<':
                        if not node.get_attribute(self.attribute) < self.value:
                            return False, f'{node.name}.{self.attribute} is not less than {self.value}. {node.name}.{self.attribute} = {node.get_attribute(self.attribute)}.'
                    elif self.operator == '>=':
                        if not node.get_attribute(self.attribute) >= self.value:
                            return False, f'{node.name}.{self.attribute} is not greater than or equal to {self.value}. {node.name}.{self.attribute} = {node.get_attribute(self.attribute)}.'
                    elif self.operator == '<=':
                        if not node.get_attribute(self.attribute) <= self.value:
                            return False, f'{node.name}.{self.attribute} is not less than or equal to {self.value}. {node.name}.{self.attribute} = {node.get_attribute(self.attribute)}.'
                    else:
                        raise ValueError(f'Invalid operator: {self.operator}')
        except Exception as e:
            return False, str(e)
        return True, ''     
    

    ##NODE ATTRIBUTE CONDITION FIX
    def get_fixes(self, game:Game, test_in_copied_game:bool=True) -> Tuple[bool, List[GraphOperation]]:
        '''
        Get the fixes for the condition.

        Returns:
            Tuple[Bool, List[GraphOperation]]: A tuple of the form (is_fixable, [fix1, fix2, ...]). If is_fixable is False, the list of fixes is empty.
        '''
        fixes: List[GraphOperation] = []
        #print("ATTRIBUTE FIXING")
        #print(self.nodes)
        #print(self, self.nodes, self.attribute, self.value, self.operator)
        try:
            if isinstance(self.nodes, Node):
                nodes: List[Node] = [self.nodes]
            elif isinstance(self.nodes, str):
                node_names: List[str] = [remove_extra_spaces(i) for i in self.nodes.split(';')]
                for i in range(len(node_names)):
                    if node_names[i] == 'player':
                        player_node = game.world.player
                        if player_node is None:
                            return False, []
                        node_names[i] = player_node.id
                nodes: List[Node] = [game.world.find_node(node_name, error_message_verbose=True) for node_name in node_names] # will raise error if node not found
            else:
                nodes = self.nodes
            if "is_" in self.attribute:
                if self.attribute[3:] == "character" and not nodes[0].is_character:
                    raise Exception(f'Failed is_character attribute requirement')
                if self.attribute[3:] == "room" and not nodes[0].is_room:
                    raise Exception(f'Failed is_room attribute requirement')
            elif self.attribute not in Node.additional_attribute_list:
                raise Exception(f'Attribute {self.attribute} not registered.')
            else:
                attribute_type, _, belonging_class, _, _ = Node.additional_attribute_list[self.attribute]
                #print("ATTRIBUTING TYPES")
                #print(attribute_type, belonging_class, self.attribute, Node.additional_attribute_list)
                for node in nodes:
                    assert node in game.world.nodes, f'{node} is not in the world.'
                    if not isinstance(node, belonging_class):
                        return False, []
                    # TODO: For value comparison, we may need to convert the value to the correct type.
                    #if isinstance(self.value, str):
                    #    _, literal_value = to_literal(self.value)
                    #else:
                    #    literal_value = self.value
                    #str_value = str(literal_value)
                    #print(literal_value, type(literal_value))
                    #if not isinstance(literal_value, attribute_type):
                    #    print("C")
                    #    return False, []
                    #print(node, node.get_attribute(self.attribute), type(node.get_attribute(self.attribute)), int(self.value), self.operator, type(self.operator))
                    #print(node.additional_attributes)
                    #print(self.operator == '>', self.operator == '<', self.operator == '=')
                    node_value = node.get_attribute(self.attribute)
                    #print(node_value)
                    #print("ATTRIBUTE VALUE COMPARISON")
                    #print(node_value, type(node_value), self.value, type(self.value))
                    if self.value == "True":
                        if node_value:
                            continue
                        else:
                            fixes.append(SetNodeAttributeOperation(node.id, self.attribute, self.value))
                    elif self.value == "False":
                        if not node_value:
                            continue
                        else:
                            fixes.append(SetNodeAttributeOperation(node.id, self.attribute, self.value))
                    if node_value is None:
                        if self.operator == '>':
                            fixes.append(SetNodeAttributeOperation(node.id, self.attribute, str(int(self.value) + 1)))
                        elif self.operator == '<':
                            fixes.append(SetNodeAttributeOperation(node.id, self.attribute, str(int(self.value) - 1)))
                        elif self.operator == '=':
                            fixes.append(SetNodeAttributeOperation(node.id, self.attribute, self.value))
                    elif node_value <= int(self.value) and self.operator == '>':
                        fixes.append(SetNodeAttributeOperation(node.id, self.attribute, str(int(self.value) + 1)))
                    elif node_value >= int(self.value) and self.operator == '<':
                        fixes.append(SetNodeAttributeOperation(node.id, self.attribute, str(int(self.value) - 1)))
                    elif node_value != int(self.value) and self.operator == '=':
                        fixes.append(SetNodeAttributeOperation(node.id, self.attribute, self.value))
                    elif (node_value < int(self.value) and self.operator == '<') or (node_value > int(self.value) and self.operator == '>') or (node_value == int(self.value) and self.operator == '='):
                        continue
                    else:
                        #print("D")
                        return False, []
                
            if test_in_copied_game:
            # Now, test if the fixes are valid.
                game_copy = deepcopy(game)
                for fix in fixes:
                    #print('apply attribute fix')
                    fix.apply(game_copy.world)
                #print('eval attribute fix')
                is_fix_satisfied, messages = self.evaluate(game_copy, verbose=True)
                if is_fix_satisfied:
                    return True, fixes
                else:
                    print_warning(f'Fixes {fixes} are not valid: {messages}')
                    return False, []
            else:
                return True, fixes
        except Exception as e:
            print_warning(e)
            return False, []

@dataclass
class EventConditionField(ConditionField):
    event: Union[str, Event]

    def __str__(self) -> str:
        event = self.event if isinstance(self.event, str) else self.event.name
        return f'{{"{event}"}}'

    def evaluate(self, game:Game, verbose:bool=False) -> Tuple[bool, str]:
        '''
        Check if the condition is satisfied.
        '''
        try:
            if game.has_event_happened(self.event):
                return True, ''
            else:
                return False, f'Event {self.event} has not happened.'
        except Exception as e:
            return False, str(e)
        
    def get_fixes(self, game: Game, test_in_copied_game:bool=True) -> Tuple[bool, List[GraphOperation]]:
        return False, []
        
class ConditionFieldFactory:
    @staticmethod
    def is_attribute_check_match(condition: str) -> Tuple[bool, Tuple[str, str, str, str]]:
        '''
        Check if the condition pattern matches {node.attribute==value}.
        '''
        #print("CHECK MATCH CONDITION")
        condition = remove_extra_spaces(condition)
        #print(condition)
        #old_strict_pattern = r"\{([\w\s;\-]+)\.(\w+)\s*?(==|!=|>|<|>=|<=)\s*([^{}\s].*?)\}"
        strict_pattern = r"\{([\w\s;'\-]+)\s*\.\s*(\w+)\s*?(==|!=|>|<|>=|<=)\s*([^{}\s].*?)\}"
        strict_matches = re.search(strict_pattern, condition)
        #print(strict_matches)
        if strict_matches:
            node, attribute, operator, value = strict_matches.group(1), strict_matches.group(2), strict_matches.group(3), strict_matches.group(4)
            node, attribute, value = remove_extra_spaces(node), remove_extra_spaces(attribute), remove_extra_spaces(value)
            return True, (node, attribute, operator, value)
        return False, ('', '', '', '')
    
    @staticmethod
    def is_location_check_match(condition: str) -> Tuple[bool, Tuple[str, str]]:
        condition = remove_extra_spaces(condition)
        strict_pattern = r"\{(([^{}]*?) |)at ([^{}]*?)\}"
        strict_matches = re.search(strict_pattern, condition)
        if strict_matches:
            node, location = strict_matches.group(1), strict_matches.group(3)
            node, location = remove_extra_spaces(node), remove_extra_spaces(location)
            return True, (node, location)
        strict_pattern = r"\{(([^{}]*?) |)in ([^{}]*?)\}"
        strict_matches = re.search(strict_pattern, condition)
        if strict_matches:
            node, location = strict_matches.group(1), strict_matches.group(3)
            node, location = remove_extra_spaces(node), remove_extra_spaces(location)
            return True, (node, location)
        return False, ('', '')        
    
    @staticmethod
    def is_inventory_check_match(condition: str) -> Tuple[bool, Tuple[str, str]]:
        condition = remove_extra_spaces(condition)
        strict_pattern = r"\{(([^{}]*?) |)has ([^{}]*?)\}"
        strict_matches = re.search(strict_pattern, condition)
        if strict_matches:
            owner, item = strict_matches.group(1), strict_matches.group(3)
            owner, item = remove_extra_spaces(owner), remove_extra_spaces(item)
            return True, (owner, item)
        return False, ('', '')
    
    @staticmethod
    def is_event_check_match(condition: str) -> Tuple[bool, Tuple[str]]:
        condition = remove_extra_spaces(condition)
        strict_pattern = r'\{\s*\"(.*)\"\s*\}'
        strict_matches = re.search(strict_pattern, condition)
        if strict_matches:
            event = strict_matches.group(1)
            event = remove_extra_spaces(event)
            return True, (event,)
        return False, ('',)
    
    @staticmethod
    def create_condition_field(condition: str, initiator:str='') -> ConditionField:
        # TODO: initiator is not used.
        '''
        Check if the condition pattern matches {node.attribute==value}.
        '''
        #print("CREATING")
        #print(condition)
        is_attribute_check_match, (node, attribute, operator, value) = ConditionFieldFactory.is_attribute_check_match(condition)
        if is_attribute_check_match:
            if operator not in ['==', '!=', '>', '<', '>=', '<=']:
                raise ValueError(f'Invalid operator: {operator}')
            if node.startswith('enum(') and node.endswith(')'):
                raise ValueError(f'"No arguments for {node} are provided.')
            #if "is_" in attribute:
            #    print(attribute)
            #    attribute = attribute.replace("is_", "")
            #    print(attribute)
            return NodeAttributeConditionField(node, attribute, value, cast(OperatorString, operator))
        
        '''
        Check if the condition pattern matches {node at location}.
        '''
        is_location_check_match, (node, location) = ConditionFieldFactory.is_location_check_match(condition)
        if is_location_check_match:
            return NodeLocationConditionField(location, node)
        
        '''
        Check if the condition pattern matches {character has item}.
        '''
        is_inventory_check_match, (owner, item) = ConditionFieldFactory.is_inventory_check_match(condition)
        if is_inventory_check_match:
            return InventoryConditionField(item, owner)
        
        '''
        Check if the condition pattern matches {"some event happened"}.
        '''
        is_event_check_match, (event,) = ConditionFieldFactory.is_event_check_match(condition)
        if is_event_check_match:
            if not event:
                raise ValueError(f'Empty event name: {condition}')
            return EventConditionField(event)
        
        raise ValueError(f'Invalid format: {condition}')
    
class ComplexCondition(Condition):
    '''
    A complex condition is a condition that involves complex logic.
    Example: {container1.is_open==False} and ({container1.is_locked==False} or {player has key})
    In the constructor, 
    the corresponding processed_condition_expression is FIELD_1 and (FIELD_2 or FIELD_3)
    and the corresponding condition_fields is the dictionary 
    {'FIELD_1': NodeAttributeConditionField('container1', 'is_open', 'False', '=='), ...}
    '''
    def __init__(self, processed_condition_expression: str, condition_fields:Dict[str, ConditionField]) -> None:
        self.processed_condition_expression = processed_condition_expression
        self.condition_fields = condition_fields
    
    def __str__(self) -> str:
        if not self.condition_fields:
            return 'None'
        processed_condition_expression = self.processed_condition_expression
        for placeholder, condition_field in self.condition_fields.items():
            processed_condition_expression = processed_condition_expression.replace(placeholder, str(condition_field))
        return processed_condition_expression

    @staticmethod
    def _replace_fields_with_placeholders(text: str) -> Tuple[str, Dict[str, str]]:
        # This dictionary will store the mappings
        mappings : Dict[str, str] = {}
        counter :int = 0
        # This function will be called for each match
        def replacer(match: re.Match[str]):
            # Increment the counter
            nonlocal counter
            counter += 1
            
            # Extract the original matched text
            original_text = match.group(0)
            
            # Store in the mappings dictionary
            replacement = 'FIELD_' + str(counter)
            mappings[replacement] = original_text
            
            return  ' ' + replacement + ' ' # if the player enters, {condition1}and{condition2} without spaces, the parser will fail if we do not add spaces here.
        
        # Replace all occurrences of the pattern
        #replaced_text = re.sub(r'{.*?}', replacer, text)
        pattern = r'(\{(?:[^\{\}]+|(?R))*\})'
        replaced_text = reg.sub(pattern, replacer, text)
        return remove_extra_spaces(replaced_text), mappings


    def evaluate(self, game: Game, verbose:bool=False) -> Tuple[bool, List[str]]:
        #print("FINAL EVALUATION")
        field_results: Dict[str, Tuple[bool, str]] = {key: value.evaluate(game, verbose=verbose) for key, value in self.condition_fields.items()}
        #print(self.condition_fields)
        #print(field_results)
        #print({key: value[0] for key, value in field_results.items()})
        #print(self.processed_condition_expression)
        final_result:Any = simple_eval(self.processed_condition_expression, names={key: value[0] for key, value in field_results.items()})
        assert isinstance(final_result, bool), f'Invalid final result: {final_result} (should be a boolean).'
        messages = [f'Condition "{key}" is not satisfied: {value[1]}' for key, value in field_results.items() if not value[0]] # TODO: have better messages.
        return final_result, messages

    def get_individual_field_info(self, game:Game) -> Dict[str, Tuple[bool, str]]:
        field_results: Dict[str, Tuple[bool, str]] = {str(condition): condition.evaluate(game, verbose=True) for _, condition in self.condition_fields.items()}
        return field_results

    @staticmethod
    def add_precondition_to_expression(expression:str, preconditions:List[str]) -> str:
        '''
        Add a precondition to the expression using the AND operator.
        '''
        preconditions = [remove_extra_spaces(i) for i in preconditions]
        preconditions = [i for i in preconditions if i and i.lower() not in ['none', 'null', 'true']]
        expression = remove_extra_spaces(expression)
        if not expression or expression.lower()  in ['none', 'null', 'true']:
            expression = 'True'
        precondition_joined = ' and '.join(preconditions)
        return f'({expression}) and {precondition_joined}'
    
    @staticmethod
    def get_required_node_attributes(game: Game, expression:str) -> List[Tuple[str, NodeType, type]]:
        #print("GETTING REQUIRED NODE ATTRIBUTES")
        #print(expression)
        result:List[Tuple[str, NodeType, type]] = []
        _, text_mappings = ComplexCondition._replace_fields_with_placeholders(expression)
        #print(text_mappings)
        for _, condition in text_mappings.items():
            is_attribute_check_match, (placeholder, attribute, _, default_value) = ConditionFieldFactory.is_attribute_check_match(condition)
            #print(is_attribute_check_match, is_attribute_check_match, (placeholder, attribute, _, default_value))
            is_literal, default_value_parsed = to_literal(default_value)

            if not is_literal or default_value_parsed is None:
                #print_warning(f'Unable to parse default value {default_value} for attribute {attribute}.', 'ComplexCondition')
                attribute_type = str
            else:
                attribute_type = type(default_value_parsed)

            if is_attribute_check_match:
                if 'item' in placeholder:
                    result.append((attribute, 'Item', attribute_type))
                elif 'container' in placeholder:
                    result.append((attribute, 'ContainerItem', attribute_type))
                elif 'character' in placeholder:
                    result.append((attribute, 'Character', attribute_type))
                elif 'room' in placeholder:
                    result.append((attribute, 'Room', attribute_type))
                elif 'player' in placeholder:
                    result.append((attribute, 'Player', attribute_type))
                else:
                    #print("No indexing given to placeholder for attribute", placeholder)
                    cls = game.world.find_node(placeholder)
                    #print(cls, type(cls))
                    if type(cls) == Item:
                        result.append((attribute, 'Item', attribute_type))
                    else:
                        result.append((attribute, 'Character', attribute_type))
                
        return result

    @staticmethod
    def build_from_string(game: Game, expression:str, node_must_be_nearby:bool=True, initiator:str='', arguments:Dict[str, str]={}) -> ComplexCondition:
        #print("BUILDING CONDITION FROM STRING")
        #print(expression, arguments)
        expression = remove_extra_spaces(expression)
        if not expression or expression.lower()  in ['none', 'null', 'true']:
            expression = 'True'
        expression = replace_placeholders(expression, arguments)
        processed_expression, text_mappings = ComplexCondition._replace_fields_with_placeholders(expression)
        print(processed_expression, text_mappings)
        mappings = {key: ConditionFieldFactory.create_condition_field(value, initiator=initiator) for key, value in text_mappings.items()}
        if node_must_be_nearby:
            processed_expression = f'({processed_expression}) and NODE_MUST_BE_NEARBY_FIELD'
            validArguments = ComplexCondition.checkNodes(game, arguments)
            
            nodes_to_check = []
            first_room = True

            for key, value in arguments.items():
                if type(value) == Room and first_room:
                    nodes_to_check.append(value)
                    first_room = False  
                else:
                    # item or character always require nearby
                    nodes_to_check.append(value)

            mappings['NODE_MUST_BE_NEARBY_FIELD'] = NodeVisibleConditionField(nodes_to_check, agent=initiator)
        #if node_must_be_nearby:
        #    processed_expression = f'({processed_expression}) and NODE_MUST_BE_NEARBY_FIELD'
        #    validArguments = ComplexCondition.checkNodes(game, arguments)
        #    
        #
        #    mappings['NODE_MUST_BE_NEARBY_FIELD'] = NodeVisibleConditionField([arguments[key] for key in arguments], agent=initiator)
        #print(processed_expression, mappings)
        return ComplexCondition(processed_expression, mappings)
    
    def checkNodes(self, game: Game, arguments:Dict[str, str]={}) -> Dict[str, str]:
        validArguments = {}
        for key in arguments:
            #print(arguments[key])
            node = game.world.find_node(arguments[key], room=None, local=True)
            if not isinstance(node, Room):
                validArguments[key] = arguments[key]
        return validArguments
    
    def is_simple_condition(self) -> bool:
        #print("CHECKING IS_SIMPLE_CONDITION", self)
        tree = ast.parse(self.processed_condition_expression, mode='eval')
        visitor = SimpleConditionExpressionVisitor()
        visitor.visit(tree)
        #print(self)
        #print(visitor)
        #print(tree)
        return visitor.is_valid
    
    def to_simple_condition(self) -> SimpleCondition:
        if self.is_simple_condition():
            return SimpleCondition([value for _, value in self.condition_fields.items()])
        else:
            raise ValueError(f'Condition {self} is not a simple condition.')

    def get_fixes_complex(self, game:Game, llm:Union[LLM, None]=None, force_using_llm:bool=False) -> List[GraphOperation]:
        if self.is_simple_condition() and not force_using_llm:
            #print("SIMPLE")
            #print("COMPLEX CONDITION FIELDS", self.processed_condition_expression, self.condition_fields)
            return self.to_simple_condition().get_fixes_simple(game, llm, force_using_llm)
        else:
            #print("NOT SIMPLE")
            if not llm:
                raise ValueError('LLM not specified and fix failed!')
            return self.get_fixes_with_llm(game, llm)

class SimpleCondition(Condition):
    '''
    A simple field condition is a condition that checks if each attribute specified in the condition is equal to the specified value.
    No complex logic is involved.
    '''
    def __init__(self, conditions: List[ConditionField]) -> None:
        '''
        a condition field is a tuple of (node, attribute, value, message)
        '''
        self.conditions = conditions

    def __str__(self) -> str:
        if not self.conditions:
            return 'None'
        return ' and '.join([str(condition) for condition in self.conditions])
        
    def get_fixes_simple(self, game:Game, llm: Union[LLM, None]=None, force_using_llm:bool=False) -> List[GraphOperation]:
        if force_using_llm:
            if not llm:
                    raise ValueError('LLM not specified and fix failed!')
            return self.get_fixes_with_llm(game, llm)
        
        fixes : Set[GraphOperation] = set()
        #print("CONDITIONS")
        # THIS LIST OF CONDITIONS IS WRONG LIKELY DUE TO TO SIMPLE CONDITION METHOD
        #print(self.conditions)
        for condition in self.conditions:
            #print("CONDITION", condition)
            #if "inventory" in condition.__str__():
            #    print("inventory skip")
            #    continue
            #print(condition, type(condition))
            is_fixable, field_fixes = condition.get_fixes(game, test_in_copied_game=False)
            #print(is_fixable, field_fixes)
            if not is_fixable:
                if not llm:
                    raise ValueError('LLM not specified and fix failed!')
                return self.get_fixes_with_llm(game, llm) # A simple fix is not possible. Try to use LLM to fix the condition.
            for fix in field_fixes:
                fixes.add(fix)
                    
        #print("FIXES GENERATED")
        #print(self.conditions)
        #print(fixes)
        # Now, test if the fixes are valid.
        game_copy = deepcopy(game)
        for fix in fixes:
            fix.apply(game_copy.world)
        #print("CHECKING SATISFACTION")
        is_fix_satisfied, messages = self.evaluate(game_copy, verbose=True)
        if is_fix_satisfied:
            return fixes
        else:
            print_warning(f'Fixes {fixes} are not valid: {messages}')
            if not llm:
                    raise ValueError('LLM not specified and fix failed!')
            return self.get_fixes_with_llm(game, llm) # A simple fix is not possible. Try to use LLM to fix the condition.
    

    def evaluate(self, game:Game, verbose:bool=False) -> Tuple[bool, List[str]]:
        '''
        Check if all conditions are satisfied.
        '''
        messages:List[str] = []
        result = True
        for condition in self.conditions:
            #print("EVALUATING CONDITION")
            #print(condition)
            is_satisfied, additional_message = condition.evaluate(game, verbose=verbose)
            #print(is_satisfied, additional_message)
            result = result and is_satisfied
            if not is_satisfied:
                messages.append(f'Condition "{condition}" is not satisfied: {additional_message}')
        return result, messages
    
    def get_individual_field_info(self, game:Game) -> Dict[str, Tuple[bool, str]]:
        field_results: Dict[str, Tuple[bool, str]] = {str(condition): condition.evaluate(game, verbose=True) for condition in self.conditions}
        return field_results
    
    @staticmethod
    def build_from_string(attribute_check: str='', location_check:str='', inventory_check: str='', event_check: str='', node_must_be_nearby:bool=True, initiator:str='', arguments:Dict[str, str]={}) -> SimpleCondition:

        attribute_check = replace_placeholders(attribute_check, arguments)
        location_check = replace_placeholders(location_check, arguments)
        inventory_check = replace_placeholders(inventory_check, arguments)

        general_pattern = r'{.*?}'


        '''
        STEP 1: 
        attribute_check: "{object1.is_open==False}; {object1.is_container==True}; {object1.is_locked==False}; {enum(npc).is_alive==True}"
        arguments: {"object1": "box", "enum(npc)": "adventurer;merchant"}
        result:
        [
            NodeAttributeConditionField('object1', 'is_open', 'False'),
            NodeAttributeConditionField('object1', 'is_container', 'True'),
            NodeAttributeConditionField('object1', 'is_locked', 'False'),
            NodeAttributeConditionField('adventurer;merchant', 'is_alive', 'True')
        ]
        '''
        attribute_check = remove_extra_spaces(attribute_check)
        attribute_check_condition_fields : List[NodeAttributeConditionField] = []
        if attribute_check:
            general_matches = re.findall(general_pattern, attribute_check)
            if general_matches:
                for general_match in general_matches:
                    attribute_check_condition_field = ConditionFieldFactory.create_condition_field(general_match, initiator=initiator)
                    assert isinstance(attribute_check_condition_field, NodeAttributeConditionField), "Bug! attribute_check_condition_field is not a NodeAttributeConditionField."
                    attribute_check_condition_fields.append(attribute_check_condition_field)
            else:
                 raise ValueError(f'No rules found in "{attribute_check}". Rules should be inside curly brackets.')

        '''
        STEP 2: Location Check
        location_check: "{player at village};{character1 at dungeon};{character2 at dungeon}"
        '''
        location_check = remove_extra_spaces(location_check)
        node_location_check_condition_fields : List[NodeLocationConditionField] = []
        if location_check:
            general_matches : List[str] = re.findall(general_pattern, location_check)
            if general_matches:
                for general_match in general_matches:
                    agent_location_check_condition_field = ConditionFieldFactory.create_condition_field(general_match, initiator=initiator)
                    assert isinstance(agent_location_check_condition_field, NodeLocationConditionField), "Bug! agent_location_check_condition_field is not a NodeLocationConditionField."
                    node_location_check_condition_fields.append(agent_location_check_condition_field)
            else:
                raise ValueError(f'No rules found in "{location_check}". Rules should be inside curly brackets.')

        '''
        STEP 3: Inventory Check
        inventory_check: "{player has item1}; {player has item2}; {player has item3}"
        # TODO: not just player's inventory
        '''
        inventory_check = remove_extra_spaces(inventory_check)
        inventory_check_condition_fields : List[InventoryConditionField] = []
        if inventory_check:
            general_matches : List[str] = re.findall(general_pattern, inventory_check)
            if general_matches:
                for general_match in general_matches:
                    inventory_check_condition_field = ConditionFieldFactory.create_condition_field(general_match, initiator=initiator)
                    assert isinstance(inventory_check_condition_field, InventoryConditionField), "Bug! inventory_check_condition_field is not a InventoryConditionField."
                    inventory_check_condition_fields.append(inventory_check_condition_field)
            else:
                raise ValueError(f'No rules found in "{inventory_check}". Rules should be inside curly brackets.')

        '''
        STEP 4: Event Check
        event_check: {"adventure destroy the cursed artifact"} ; {"adventurer investigate the abandoned mansion"}
        '''
        event_check = remove_extra_spaces(event_check)
        event_check_condition_fields : List[ConditionField] = []
        if event_check:
            general_matches : List[str] = re.findall(general_pattern, event_check)
            if general_matches:
                for general_match in general_matches:
                    event_check_condition_field = ConditionFieldFactory.create_condition_field(general_match, initiator=initiator)
                    assert isinstance(event_check_condition_field, EventConditionField), "Bug! event_check_condition_field is not a EventConditionField."
                    event_check_condition_fields.append(event_check_condition_field)
            else:
                raise ValueError(f'No rules found in "{event_check}". Rules should be inside curly brackets.')

        '''
        STEP 5: Node Location Check: Are the nodes visible to the agent?
        '''
        node_visible_check_condition_fields : List[NodeVisibleConditionField] = []
        if node_must_be_nearby:
            node_visible_check_condition_fields = [NodeVisibleConditionField([arguments[key] for key in arguments], agent=initiator)]

        '''
        STEP 6: Combine all conditions
        '''
        all_condition_fields : List[ConditionField] = []
        all_condition_fields.extend(attribute_check_condition_fields)
        all_condition_fields.extend(node_location_check_condition_fields)
        all_condition_fields.extend(inventory_check_condition_fields)
        all_condition_fields.extend(event_check_condition_fields)
        all_condition_fields.extend(node_visible_check_condition_fields)

        return SimpleCondition(all_condition_fields)
    
class AlwaysTrueCondition(Condition):
    def __str__(self) -> str:
        return 'None'
    
    def evaluate(self, game:Game, verbose:bool=False) -> Tuple[bool, List[str]]:
        return True, []
    
    def get_individual_field_info(self, game:Game) -> Dict[str, Tuple[bool, str]]:
        return {}
    
    def get_fixes_with_llm(self, game: Game, llm: LLM) -> List[GraphOperation]:
        return []
    
    def get_fixes(self, game:Game, llm:Union[LLM, None]=None, force_using_llm:bool=False) -> List[GraphOperation]:
        return []
    
class SimpleConditionExpressionVisitor(ast.NodeVisitor):
    def __init__(self):
        self.is_valid: bool = True

    def visit_Expression(self, node: ast.Expression) -> None:
        # Allow Expression root node
        super().generic_visit(node)
    
    def visit_Load(self, node: ast.Load) -> None:
        # Allow load context for variables
        super().generic_visit(node)
    
    def visit_BoolOp(self, node: ast.BoolOp) -> None:
        # Check if the boolean operation is something other than 'and'
        if not isinstance(node.op, ast.And):
            self.is_valid = False
        super().generic_visit(node)

    def visit_And(self, node: ast.And) -> None:
        super().generic_visit(node)

    def visit_Name(self, node: ast.Name) -> None:
        # Allow variable names
        super().generic_visit(node)

    def visit_Constant(self, node: ast.Constant) -> None:
        # Allow constants (True, False, numbers, strings, etc.)
        super().generic_visit(node)

    def generic_visit(self, node: ast.AST) -> None:
        # This is the catch-all function that gets called if no explicit visitor function exists for a node.
        # Set is_valid to False for any node type that hasn't been explicitly allowed.
        self.is_valid = False
        print(f'Node type {type(node)} is not allowed in simple conditions.')
        super().generic_visit(node)

if __name__ == '__main__':
    import unittest
    from world import World
    from nodes import Room, Item, ContainerItem, Character, Player
    from game import Game
    from logic_template import ActionTemplate
    from event import Event
    import logging, sys
    from game_construct_prompt import fix_precondition
    from llm.chatgpt import ChatGPT

    # world = World()
    # library = Room('School Library')
    # cafeteria = Room('School Cafeteria')
    # pencil = Item('pencil')
    # iphone = Item('iPhone 14')
    # player = Player('Student')
    # stone = Item('Large Stone')
    # world.add_node(library, (0, 0))
    # world.add_node(cafeteria, (0, 1))
    # world.add_node(pencil, library)
    # world.add_node(player, library)
    # world.add_node(iphone, library)
    # world.add_node(stone, cafeteria)
    # Item.register_new_attribute('is_moveable', bool, None)
    # Item.register_new_attribute('is_gettable', bool, None)
    # stone.set_attribute('is_moveable', False)
    # game = Game(world, [], [])
    # get_precondition_1 = ConditionFieldFactory.create_condition_field('{pencil.is_moveable==True}')
    # get_precondition_2 = ConditionFieldFactory.create_condition_field('{pencil.is_gettable==True}')
    # is_fixable, fixes = get_precondition_1.get_fixes(game)
    # print(is_fixable, fixes)
    # exit()

    class TestSimpleCondition(unittest.TestCase):
        def setUp(self) -> None:
            super().setUp()
            self.log = logging.getLogger("SomeTest.testSomething")

        def test_fix(self):
            world = World()
            library = Room('School Library')
            cafeteria = Room('School Cafeteria')
            pencil = Item('pencil')
            iphone = Item('iPhone 14')
            player = Player('Student')
            stone = Item('Large Stone')
            world.add_node(library, (0, 0))
            world.add_node(cafeteria, (0, 1))
            world.add_node(pencil, library)
            world.add_node(player, library)
            world.add_node(iphone, library)
            world.add_node(stone, cafeteria)
            Item.register_new_attribute('is_moveable', bool, None)
            Item.register_new_attribute('is_gettable', bool, None)
            Character.register_new_attribute('mood', str, None)
            Player.register_new_attribute('money', int, 0)
            stone.set_attribute('is_moveable', False)
            game = Game(world, [], [])
        

            # Test fix for get_precondition_1
            get_precondition_1 = ConditionFieldFactory.create_condition_field('{pencil.is_moveable==True}')
            self.assertFalse(get_precondition_1.evaluate(game)[0])
            is_fixable, fixes = get_precondition_1.get_fixes(game)
            self.assertTrue(is_fixable)
            for fix in fixes:
                fix.apply(game.world)
            self.assertTrue(get_precondition_1.evaluate(game)[0])
            self.assertEqual(pencil.get_attribute('is_moveable'), True)
            
            # Test fix for get_precondition_2
            get_precondition_2 = ConditionFieldFactory.create_condition_field('{pencil.is_gettable==True}')
            self.assertFalse(get_precondition_2.evaluate(game)[0])
            is_fixable, fixes = get_precondition_2.get_fixes(game)
            self.assertTrue(is_fixable)
            for fix in fixes:
                fix.apply(game.world)
            self.assertTrue(get_precondition_2.evaluate(game)[0])
            self.assertEqual(pencil.get_attribute('is_gettable'), True)         

            get_precondition_2 = ConditionFieldFactory.create_condition_field('{pencil.is_gettable==True}') # test when condition is already satisfied
            self.assertTrue(get_precondition_2.evaluate(game)[0])
            is_fixable, fixes = get_precondition_2.get_fixes(game)
            self.assertTrue(is_fixable)
            self.assertFalse(fixes)

            # Test fix for mood
            mood_precondition = ConditionFieldFactory.create_condition_field('{player.mood==happy}')
            self.assertFalse(mood_precondition.evaluate(game)[0])
            is_fixable, fixes = mood_precondition.get_fixes(game)
            self.assertTrue(is_fixable)
            for fix in fixes:
                fix.apply(game.world)
            self.assertTrue(mood_precondition.evaluate(game)[0])
            self.assertEqual(player.get_attribute('mood'), 'happy')

            mood_precondition = ConditionFieldFactory.create_condition_field('{player.mood==happy}') # test when condition is already satisfied
            self.assertTrue(mood_precondition.evaluate(game)[0])
            is_fixable, fixes = mood_precondition.get_fixes(game)
            self.assertTrue(is_fixable)
            self.assertFalse(fixes)

            mood_precondition = ConditionFieldFactory.create_condition_field('{player.mood==\'sad\'}')
            self.assertFalse(mood_precondition.evaluate(game)[0])
            is_fixable, fixes = mood_precondition.get_fixes(game)
            self.assertTrue(is_fixable)
            for fix in fixes:
                fix.apply(game.world)
            self.assertTrue(mood_precondition.evaluate(game)[0])
            self.assertEqual(player.get_attribute('mood'), 'sad')

            # Test fix for money
            money_precondition = ConditionFieldFactory.create_condition_field('{player.money==100}')
            self.assertFalse(money_precondition.evaluate(game)[0])
            is_fixable, fixes = money_precondition.get_fixes(game)
            self.assertTrue(is_fixable)
            for fix in fixes:
                fix.apply(game.world)
            self.assertTrue(money_precondition.evaluate(game)[0])
            self.assertEqual(player.get_attribute('money'), 100)

            # Test node location field
            location_precondition = ConditionFieldFactory.create_condition_field('{player;iphone at school cafeteria}')
            self.assertFalse(location_precondition.evaluate(game)[0])
            is_fixable, fixes = location_precondition.get_fixes(game)
            self.assertTrue(is_fixable)
            for fix in fixes:
                fix.apply(game.world)
            self.assertTrue(location_precondition.evaluate(game)[0])
            self.assertEqual(player.get_room(), cafeteria)
            self.assertEqual(iphone.get_room(), cafeteria)

            location_precondition = ConditionFieldFactory.create_condition_field('{player;iphone at school cafeteria}') # test when condition is already satisfied
            self.assertTrue(location_precondition.evaluate(game)[0])
            is_fixable, fixes = location_precondition.get_fixes(game)
            self.assertTrue(is_fixable)
            self.assertFalse(fixes)

            # Test node visible field
            visible_precondition = NodeVisibleConditionField(['pencil', 'iphone'], agent='player')
            self.assertFalse(visible_precondition.evaluate(game)[0])
            is_fixable, fixes = visible_precondition.get_fixes(game)
            self.assertTrue(is_fixable)
            for fix in fixes:
                fix.apply(game.world)
            self.assertTrue(visible_precondition.evaluate(game)[0])
            self.assertEqual(pencil.get_room(), cafeteria)
            self.assertEqual(iphone.get_room(), cafeteria)

            visible_precondition = NodeVisibleConditionField(['pencil', 'iphone'], agent='player') # test when condition is already satisfied
            self.assertTrue(visible_precondition.evaluate(game)[0])
            is_fixable, fixes = visible_precondition.get_fixes(game)
            self.assertTrue(is_fixable)
            self.assertFalse(fixes)

            # Test inventory field
            inventory_precondition = ConditionFieldFactory.create_condition_field('{player has pencil;iphone 14}')
            self.assertFalse(inventory_precondition.evaluate(game)[0])
            is_fixable, fixes = inventory_precondition.get_fixes(game)
            self.assertTrue(is_fixable)
            for fix in fixes:
                fix.apply(game.world)
            self.assertTrue(inventory_precondition.evaluate(game)[0])
            self.assertEqual(pencil.get_parent(), player)
            self.assertEqual(iphone.get_parent(), player)

            inventory_precondition = ConditionFieldFactory.create_condition_field('{player has pencil;iphone 14}') # test when condition is already satisfied
            self.assertTrue(inventory_precondition.evaluate(game)[0])
            is_fixable, fixes = inventory_precondition.get_fixes(game)
            self.assertTrue(is_fixable)
            self.assertFalse(fixes)

            gun = Item('gun')
            Item.register_new_attribute('is_weapon', bool)
            thief = Character('thief')
            Character.register_new_attribute('is_friendly', bool)
            world.add_node(gun, library)
            world.add_node(thief, library)

            complex_condition = ComplexCondition.build_from_string(game, expression = '{gun.is_weapon==True} and ( { thief.is_friendly == False })')
            self.assertFalse(complex_condition.evaluate(game)[0])
            self.assertTrue(complex_condition.is_simple_condition())
            fixes = complex_condition.get_fixes(game)
            self.assertEqual(len(fixes), 2)
            for fix in fixes:
                fix.apply(game.world)
            self.assertTrue(complex_condition.evaluate(game)[0])

            complex_condition = ComplexCondition.build_from_string(game, expression = 'None')
            self.assertTrue(complex_condition.evaluate(game)[0])
            self.assertTrue(complex_condition.is_simple_condition())
            fixes = complex_condition.get_fixes(game)
            self.assertEqual(len(fixes), 0)
                        
        def test_fix_with_llm(self):
            # read = ActionTemplate('read {enum(item)}', 'Display You read {enum(item)}', precondition='{enum(item).is_book==True}')
            world = World()
            library = Room('Library')
            book = Item('Machine Learning')
            student = Player('Student')
            world.add_node(library, (0,0))
            world.add_node(student, library)
            world.add_node(book, library)
            game = Game(world, [], [])

            complex_condition = ComplexCondition.build_from_string(game, expression = '{enum(item).is_book==True}', arguments={'enum(item)': book.id})
            Item.register_new_attribute('is_book', bool, None)

            self.assertFalse(complex_condition.evaluate(game)[0])
            self.assertTrue(complex_condition.is_simple_condition())
            fixes = complex_condition.get_fixes(game)
            self.log.debug(fixes)
            self.assertEqual(len(fixes), 1)

            llm = ChatGPT()

            fixes_with_llm = complex_condition.get_fixes(game, llm, force_using_llm=True)
            self.log.debug(fixes_with_llm)
            self.assertEqual(fixes, fixes_with_llm)
            for fix in fixes:
                fix.apply(game.world)
            self.assertTrue(complex_condition.evaluate(game)[0])

                    
        def test_build_from_string(self):
            attribute_check = 'attributes check: {object1.is_open==False}; {object1.is_container==True}; {enum(object).is_locked==False}'
            location_check = '{enum(character) at dungeon}'
            inventory_check = "{has weapons};{has armor};{has enum(object)}"
            event_check = '{"adventure destroy the cursed artifact"}; {  " adventurer investigate the abandoned mansion "    }'
            condition = SimpleCondition.build_from_string(attribute_check, location_check, inventory_check, event_check, node_must_be_nearby=False, 
            arguments={'enum(object)':'object2;object3', 'enum(character)':'character1;character2'})
            conditions = condition.conditions
            self.assertEqual(len(conditions), 9)
            condition0, condition1, condition2, condition3, condition4, condition5, condition6, condition7, condition8 = conditions
            assert isinstance(condition0, NodeAttributeConditionField)
            assert isinstance(condition1, NodeAttributeConditionField)
            assert isinstance(condition2, NodeAttributeConditionField)
            assert isinstance(condition3, NodeLocationConditionField)
            assert isinstance(condition4, InventoryConditionField)
            assert isinstance(condition5, InventoryConditionField)
            assert isinstance(condition6, InventoryConditionField)
            assert isinstance(condition7, EventConditionField)
            assert isinstance(condition8, EventConditionField)
            self.assertEqual(condition0.nodes, 'object1')
            self.assertEqual(condition0.attribute, 'is_open')
            self.assertEqual(condition0.value, 'False')
            self.assertEqual(condition1.nodes, 'object1')
            self.assertEqual(condition1.attribute, 'is_container')
            self.assertEqual(condition1.value, 'True')
            self.assertEqual(condition2.nodes, 'object2;object3')
            self.assertEqual(condition2.attribute, 'is_locked')
            self.assertEqual(condition2.value, 'False')
            self.assertEqual(condition3.location, 'dungeon')
            self.assertEqual(condition3.nodes, ['character1', 'character2'])
            self.assertEqual(condition4.items, ['weapons'])
            self.assertEqual(condition5.items, ['armor'])
            self.assertEqual(condition6.items, ['object2', 'object3'])
            self.assertEqual(condition7.event, 'adventure destroy the cursed artifact')
            self.assertEqual(condition8.event, 'adventurer investigate the abandoned mansion')

        def test_location_inventory_event_check(self):
            do_nothing = ActionTemplate('do nothing',';;;;')
            go = ActionTemplate('go to {room}', 'Move {player} to {room}')
            world = World()
            room1 = Room('School Library')
            room2 = Room('School Cafeteria')
            item1 = Item('pencil')
            item2 = Item('iPhone 14')
            player = Player('Student')
            world.add_node(room1, (0, 0))
            world.add_node(room2, (0, 1))
            world.add_node(item1, room1)
            world.add_node(player, room1)
            world.add_node(item2, player)
            game = Game(world, [do_nothing, go], [Event('first event', 'do nothing', None, ''), Event('second event', '', SimpleCondition.build_from_string(location_check='{at school cafeteria}'), '')])
            
            condition = SimpleCondition.build_from_string(location_check='{at school library}')
            self.assertTrue(condition.evaluate(game)[0])

            condition = SimpleCondition.build_from_string(location_check='{player at school library}')
            self.assertTrue(condition.evaluate(game)[0])

            condition = SimpleCondition.build_from_string(location_check='{Student at school library}')
            self.assertTrue(condition.evaluate(game)[0])

            condition = SimpleCondition.build_from_string(location_check='{Teacher at school library}')
            self.assertFalse(condition.evaluate(game)[0])

            condition = SimpleCondition.build_from_string(location_check='{iphone at school library}')
            self.assertTrue(condition.evaluate(game)[0])

            condition = SimpleCondition.build_from_string(location_check='{iphone at school cafeteria}')
            self.assertFalse(condition.evaluate(game)[0])

            condition = SimpleCondition.build_from_string(inventory_check='{has pencil};{player has iphone 14}')
            self.assertFalse(condition.evaluate(game)[0])

            world.move_node(item1, player)

            condition = SimpleCondition.build_from_string(inventory_check='{has pencil};{player has iphone 14}')
            self.assertTrue(condition.evaluate(game)[0])

            condition = SimpleCondition.build_from_string(event_check='{"first event"}')
            self.assertFalse(condition.evaluate(game)[0])
            game.execute_command('do nothing')
            self.assertTrue(condition.evaluate(game)[0])
            condition = SimpleCondition.build_from_string(event_check='{"second event"}')
            self.assertFalse(condition.evaluate(game)[0])
            game.execute_command('go to school cafeteria')
            self.assertTrue(condition.evaluate(game)[0])

        def test_attribute_check(self):
            Character.register_new_attribute('dialog_history', list, [])
            Room.register_new_attribute('humidity', int, 50)
            world = World()
            room1 = Room('room1')
            room2 = Room('room2')
            room3 = Room('room3')
            item1 = Item('item1')
            item2 = Item('item2')
            item3 = Item('item3')
            container1 = ContainerItem('container1')
            container1.set_attribute('capacity', 2)
            character1 = Character('aaacharacter1')
            character2 = Character('character2')
            player1 = Player('player1')
            character2.set_attribute('dialog_history', ['Hi'])
            world.add_node(room1, (0, 0))
            world.add_node(room2, (0, 1))
            world.add_room(room3, (0, 2))
            world.add_node(character1, room1)
            world.add_node(container1, character1)
            world.add_node(item1, container1)
            world.add_node(item2, container1)
            world.add_node(item3, room2)
            world.add_node(player1, room1)

            game = Game(world, [], [])
            condition = SimpleCondition.build_from_string("{room1.humidity==50} {room2.humidity==50} {container1.capacity==2} {character2.dialog_history==['Hi']}")
            self.assertFalse(condition.evaluate(game)[0])
            world.add_node(character2, room1)
            condition = SimpleCondition.build_from_string("{room1.humidity==50} {room2.humidity==50} {container1.capacity==2} {character2.dialog_history==[  \"Hi\"  ]}", node_must_be_nearby=False) # TODO: Should be robust to extra spaces. Currently, { room1 . humidity ==50} is not valid.
            self.assertTrue(len(condition.conditions), 4)
            self.assertTrue(condition.conditions[0].__str__() == '{room1.humidity==50}')
            self.assertTrue(condition.evaluate(game)[0])
            condition = SimpleCondition.build_from_string('{enum(room).humidity==50}', arguments={'enum(room)': 'room1;room2'})
            self.assertTrue(condition.evaluate(game)[0])
            condition = SimpleCondition.build_from_string('{room1.humidity == 100}')
            self.assertFalse(condition.evaluate(game)[0])
            condition = SimpleCondition.build_from_string('{room1.humidity> 45}')
            self.assertTrue(condition.evaluate(game)[0])
            condition = SimpleCondition.build_from_string('{room1.humidity >=55}')
            self.assertFalse(condition.evaluate(game)[0])
            self.assertRaises(ValueError, SimpleCondition.build_from_string, 'invalid string')
            condition = SimpleCondition.build_from_string('{room1.fsdmfsdmfklds==100}')
            self.assertFalse(condition.evaluate(game)[0])

        def test_complex_condition(self):
            world = World()
            room1 = Room('room1')
            item1 = Item('item1')
            item2 = Item('item2')
            key = Item('key')
            container1 = ContainerItem('container1')
            container1.is_locked = True
            container1.is_open = False
            player = Player('player')
            world.add_node(room1, (0, 0))
            world.add_node(container1, room1)
            world.add_node(item1, container1)
            world.add_node(item2, container1)
            world.add_node(player, room1)
            world.add_node(key, room1)
            game = Game(world, [], [])
            condition = ComplexCondition.build_from_string(game, expression = '{container1.is_open==False} and ({container1.is_locked==False} or {player has key})', node_must_be_nearby=True, initiator='player')
            self.assertFalse(condition.evaluate(game)[0])
            container1.set_attribute('is_locked', False)
            self.assertTrue(condition.evaluate(game)[0])
            container1.set_attribute('is_locked', True)
            world.move_node(key, player)
            self.assertTrue(condition.evaluate(game)[0])
            container1.set_attribute('is_open', True)
            self.assertFalse(condition.evaluate(game)[0])


    logging.basicConfig(stream=sys.stderr)
    logging.getLogger("SomeTest.testSomething").setLevel(logging.DEBUG)
    unittest.main()