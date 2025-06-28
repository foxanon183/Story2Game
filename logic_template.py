from __future__ import annotations 
from typing import List, Tuple, Union, Dict, Any
from operation import GraphOperation, GraphOperationFactory
from condition import Condition, ComplexCondition
from nodes import Character
from dataclasses import dataclass
import re
from typing import TYPE_CHECKING
from utils import remove_extra_spaces, to_literal, replace_placeholders
from action import Action
from event import Event
from type import GameState
if TYPE_CHECKING:
    from game import Game


@dataclass
class Template:
    name: str

    def __post_init__(self):
        self.name = remove_extra_spaces(self.name.lower())

    @staticmethod
    def _generate_pattern(s:str) -> Tuple[str, List[str]]:
        # This regex will match placeholders like {enum(obj)}, {object1}, etc.
        regex = r"\{(.*?)\}"
        placeholders = re.findall(regex, s)

        pattern = re.sub(regex, r"(.*)", s)
        
        return pattern, placeholders

    def match(self, s: str)->Tuple[bool, Dict[str,str]]:
        s = s.replace('{','').replace('}', '')
        pattern, placeholders = self._generate_pattern(self.name)
        #print("MATCHING")
        #print(self.name)
        #print(pattern)
        #print(placeholders)
        s = remove_extra_spaces(s)
        m = re.match(pattern, s, re.IGNORECASE)
        if not m:
            return False, {}
        return True, {key: m.group(index+1) for index, key in enumerate(placeholders)}

@dataclass
class ActionTemplate(Template):
    name: str # Example 1: eat {enum(obj)}, Example 2: get {object1}, Example 3: go to {room1}, Example 4: give {object1} to {npc1}
    operations: str # Move {enum(object)} to {inventory}; Display {object1.message}
    precondition: str='' # {container1.is_open==False} and ({container1.is_locked==False} or {player has key})
    # attribute_check: str='' #{object1.is_open==False}; {object1.is_container==True}; {object1.is_locked==False}
    # location_check:str='' # at village
    # inventory_check: str='' # has gun; has sword
    # event_check: str='' #adventurer speak with the village elders; adventurer has the sword. (Not used for action)
    description: str=''
    node_must_be_in_the_same_location: bool = True # TODO: Implement this feature. Otherwise, the player can take an object from a room that is not in the same location as the player.

    def __str__(self) -> str:
        return f'{self.name}\nOperations: {self.operations}\nPrecondition: {self.precondition}\nDescription: {self.description}'

    def serialize(self) -> Dict[str, Any]:
        return self.__dict__
    
    @staticmethod
    def deserialize(data:Dict[str, Any]) -> ActionTemplate:
        return ActionTemplate(**data)
        # name = data['name']
        # operations = data['operations']
        # precondition = data['precondition']
        # description = data['description']
        # node_must_be_in_the_same_location = data['node_must_be_in_the_same_location']
        # return ActionTemplate(name, operations, precondition, description, node_must_be_in_the_same_location)

    '''
    We are not gonna check if the fields match right now.
    '''
    # def is_valid_template(self) -> Tuple[bool, str]:
    #     '''
    #     Check if the fields match the operations and conditions.
    #     # TODO: Currently, parameters in the action name can only be nodes. So you can't define an action like "change the color of {object1} to {color1}", but only "change the color of {object1} to yellow". To solve this, we need to modify get_parameters_needed, etc.
    #     # TODO: Currently, we only check the validity of "operations" and "attribute_check" template.
    #     '''
    #     _, placeholders = self._generate_pattern(self.name)
    #     nodes_involved_in_operations = GraphOperationFactory.get_arguments_needed(self.operations, placeholders)
    #     # if there are placeholders in the operations that are not in the action name, then the template is invalid.
    #     if set(nodes_involved_in_operations) - set(placeholders):
    #         return False, f'Placeholders {placeholders} in the action name parameters and operations parameters do not match.'
    #     attribute_check_pattern = r"\{(\w+)\.(\w+)==(\w+)\}"
    #     attribute_check_matches = re.findall(attribute_check_pattern, self.attribute_check)
    #     nodes_involved_in_attribute_check = [match[0] for match in attribute_check_matches]
    #     # if there are placeholders in the attribute check that are not in the action name, then the template is invalid.
    #     if set(nodes_involved_in_attribute_check) - set(placeholders):
    #         return False, f'Nodes {nodes_involved_in_attribute_check} in the action name parameters and attribute check parameters do not match.'
    #     return True, ''

    def standardize_arguments(self, game:Game, initiator:str='', arguments:Dict[str, str]={}) -> Tuple[str, Dict[str, str]]:
        '''
        Replace the arguments passed to the action template with the full name of the nodes the arguments refer to.
        initiator will be replaced with the full name of the initiator.
        arguments will be replaced with the full name of the nodes.
        '''
        player = game.world.player
        assert player is not None, 'Player is not in the world.'
        initiator = remove_extra_spaces(initiator.lower())
        arguments = {remove_extra_spaces(key): remove_extra_spaces(value.lower()) for key, value in arguments.items()}
        if initiator=='player' or not initiator:
            initiator = player.name
            initiator_node = player
        else:
            try:
                initiator_node = game.world.find_node(initiator, find_removed=True)
                #assert isinstance(initiator_node, Character), f'{initiator} is not a character.'
                initiator = initiator_node.name
            except Exception:
                # initiator does not exist right now. It might be because it will beadded later. We just don't modify the argument first.
                initiator_node = None
                pass
        for key in arguments:
            if key == 'player':
                arguments[key] = player.name
            if key == 'environment':
                arguments[key] = initiator_node.get_room().name if initiator_node else arguments[key]
            else:
                is_literal, _ = to_literal(arguments[key])
                if is_literal:
                    continue
                else: # the argument is not a literal, so it might be a node.
                    try:
                        node = game.world.find_node(arguments[key], initiator_node.get_room().id, True, find_removed=True) if self.node_must_be_in_the_same_location and initiator_node else game.world.find_node(arguments[key], find_removed=True)
                        arguments[key] = node.name
                    except Exception:
                        # Node not found. It might be a string literal or it might be because a node has not been created yet. We just do not modify the argument.
                        pass
        return initiator, arguments

    def is_valid(self, game:Game, initiator:str, arguments:Dict[str, str]={}) -> Tuple[bool, Union[str, Tuple[str, List[GraphOperation], ComplexCondition]]]:
        '''
        Check if we can build an action instance from the template given the arguments.
        Node: an action instance can be built if it passes this check. However, it may still fail when it is executed. 
        For example, when the action does not satisfy the conditions.
        '''
        # is_valid_template, message = self.is_valid_template()
        # if not is_valid_template:
        #     return False, message
        #print("ACTION TEMPLATE IS_VALID CHECK", initiator, arguments)
        try:
            '''
            Currently not checking if the arguments match the placeholders in the template. 
            Otherwise, if the template has something like {book.is_open==True}, where "book" does not need to be replaced by an argument, the action will fail.
            '''
            # # Check if the arguments match the placeholders in the template.
            # _, placeholders = self._generate_pattern(self.name)
            # missing_arguments = set(placeholders) - set(arguments.keys())
            # if missing_arguments: # there are placeholders in the template that are not in the arguments, meaning something is not provided.
            #     return False, f"{', '.join(missing_arguments)} are not provided."
            operations = GraphOperationFactory.create_operations(self.operations, game.world, initiator, arguments)
            #print("IS VALID CONDITIONS, preconditions and arguments given:")
            #print(self.precondition, arguments)
            conditions = ComplexCondition.build_from_string(game, expression = self.precondition, node_must_be_nearby=True, initiator=initiator, arguments=arguments)
            action_name = remove_extra_spaces(replace_placeholders(self.name, arguments).lower())
            #print("OPERATIONS, CONDITIONS, ACTION_NAME")
            #print(operations, conditions)
            #print(action_name)
            return True, (action_name, operations, conditions)
        except Exception as e:
            return False, str(e)
        
    def build_action(self, game:Game, initiator:str='', arguments:Dict[str, str]={}) -> Action:
        #BUILD_ACTION, STANDARDIZE ARGUMENT")
        #print(initiator, arguments)
        #print(self.operations)
        initiator, arguments = self.standardize_arguments(game, initiator, arguments)
        is_valid, result = self.is_valid(game, initiator, arguments)
        if not is_valid:
            message = result
            assert isinstance(message, str)
            raise ValueError(f'Invalid template: {message}')
        else:
            assert isinstance(result, tuple)
            action_name, operations, conditions = result
            #print("BUILD_ACTION RESULT")
            #print(conditions)
            return Action(action_name, initiator, operations, conditions, self.description, '', [])
        
@dataclass
class EventTemplate(Template):
    '''
    Event currently can only be triggered by a player's action.
    '''
    name: str # adventurer buys sword with gold
    triggering_action: str = '' # speak to village elders
    # attribute_check: str='' # {object1.is_open==False}; {object1.is_container==True}; {object1.is_locked==False}
    # location_check:str='' # {at village}
    # inventory_check: str='' # {has gun}; {has sword}
    # event_check: str='' # {"adventurer speak with the village elders"}; {"adventurer kills the dragon"}
    precondition: str='' # {container1.is_open==False} and ({container1.is_locked==False} or {player has key})
    desired_effect: str='' # {"has gun"}; {"has sword"} # TODO: May make it more flexible.
    description: str=''
    next_state: str='continue'
    reward: int = 10

    def __str__(self) -> str:
        return f'{self.name}\nTriggering action: {self.triggering_action}\nPrecondition: {self.precondition}\nDesired effect: {self.desired_effect}\nDescription: {self.description}'

    def serialize(self) -> Dict[str, Any]:
        return self.__dict__
    
    @staticmethod
    def deserialize(data:Dict[str, Any]) -> EventTemplate:
        return EventTemplate(**data)
        # name = data['name']
        # triggering_action = data['triggering_action']
        # precondition = data['precondition']
        # desired_effect = data['desired_effect']
        # description = data['description']
        # next_state = data['next_state']
        # reward = data['reward']
        # return EventTemplate(name, triggering_action, precondition, desired_effect, description, next_state, reward)
    
    def is_valid_template(self) -> Tuple[bool, Union[Tuple[Condition, Condition], str]]:
        # TODO: Currently, we only check the validity conditions and desired effect. Need to check triggering_action.
        try:
            conditions = ComplexCondition.build_from_string(self.precondition, node_must_be_nearby=True)
            desired_effect = ComplexCondition.build_from_string(self.desired_effect, node_must_be_nearby=False)
            assert self.next_state in ['won', 'lost', 'continue'], f'next_state {self.next_state} is not valid. It must be one of "won", "lost", or "continue".'
            return True, (conditions, desired_effect)
        except Exception as e:
            return False, str(e)
    
    def build_event(self) -> Event:
        is_valid, result = self.is_valid_template()
        if not is_valid:
            message = result
            assert isinstance(message, str)
            raise ValueError(f'Invalid template: {message}')
        else:
            assert isinstance(result, tuple)
            assert len(result) == 2
            conditions, _ = result
            next_state = GameState.WON if self.next_state == 'won' else GameState.LOST if self.next_state == 'lost' else GameState.UNFINISHED
            return Event(self.name, self.triggering_action, conditions, self.desired_effect, self.description, reward=self.reward, next_state=next_state)
