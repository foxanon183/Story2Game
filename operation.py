from __future__ import annotations

from typing import Dict, List, Union, Tuple, Any, Set
from world import World

from nodes import Node, Room, Character, Item, ContainerItem
import re
import json
import numpy as np

from utils import replace_placeholders, remove_extra_spaces
from llm.chatgpt import ChatGPT


class GraphOperation:
    def __init__(self):
        pass

    def is_valid(self, world: World) -> Tuple[bool, Union[List[Any], str]]:
        raise NotImplementedError('is_valid() not implemented.')

    def apply(self, world: World) -> None:
        raise NotImplementedError('apply() not implemented.')

    def __eq__(self, __value: object) -> bool:
        if not isinstance(__value, GraphOperation):
            return False
        if self.__class__ != __value.__class__:
            return False
        return self.__dict__ == __value.__dict__
    
    def __hash__(self) -> int:
        """Generate a hash based on the class and instance attributes."""
        return hash((self.__class__, frozenset(self.__dict__.items())))
    
    def __repr__(self) -> str:
        return self.__str__()
    
    def __str__(self) -> str:
        raise NotImplementedError

    @staticmethod
    def _replace_placeholders(string: str, world: World) -> str:
        # Pattern matches strings like {player-1234.inventory}, and replaces them with the actual value
        # TODO: add support for nested placeholders
        # pattern = re.compile(r'\{(.*?)\.(.*?)\}')

        # STEP 1: Replace {node.attribute} with the actual value
        pattern = re.compile(r'\{([^{}]*?)\.([^{}]*?)\}')

        def replacer1(match: re.Match[str]) -> str:
            node_id = match.group(1)
            assert isinstance(node_id, str), "Node ID must be a string"
            attribute = match.group(2)
            assert isinstance(attribute, str), "Attribute must be a string"
            node = world.find_node(node_id)
            return str(node.get_attribute(attribute))

        #print("REPLACING PLACEHOLDERS")
        #print(string)
        string = pattern.sub(replacer1, string)
        #print(string)

        # STEP 2: Replace {node} with node name
        pattern = re.compile(r'\{([^{}]*?)\}')

        def replacer2(match: re.Match[str]) -> str:
            node_id = match.group(1)
            assert isinstance(node_id, str), "Node ID must be a string"
            node = world.find_node(node_id)
            return node.name
        
        string = pattern.sub(replacer2, string)
        print(string)
        
        assert '{' not in string and '}' not in string, 'Prompt contains unmatched curly braces.'
        return string.strip()

class GraphOperationFactory:
    @staticmethod
    def _expand_operation(command:str) -> List[str]:
        # Match any string inside {}
        matches = re.findall(r'\{([^{}]*?;[^{}]*?)\}', command)
        if not matches:
            return [command]
        if len(matches) > 1:
            raise ValueError(f"Invalid action format: {command}. Semicolons can only occur inside a single brace pair.")
        # If there's a match
        items = matches[0].split(';')  # Split by semicolon
        # If there's a period in the last item, process accordingly
        if '.' in items[-1]:
            splitted = items[-1].split('.')
            if len(splitted) != 2:
                raise ValueError(f"Invalid Operation: {command}. Nested attributes are not supported.")
            items[-1], suffix = splitted
            items = [f"{item.strip()}.{suffix.strip()}" for item in items]
        else:
            items = [item.strip() for item in items]
        # Reconstruct the items
        remaining_text = command.replace(f'{{{matches[0]}}}', '{$PLACEHOLDER$}')
        new_items = [remaining_text.replace('$PLACEHOLDER$', item) for item in items]
        # new_items = [f"{{{item}}}{remaining_text.strip()}" for item in items]
        return new_items

    @staticmethod
    def create_operations(commands: str, world: Union[World, None] = None, initiator:str='', arguments:Dict[str, str]={}) -> List[GraphOperation]:
        '''
        Create a list of GraphOperations from a string.
        Sample string: "Set {object1.is_open} to {True}; Move {item3; item4} to {inventory} ; Delete {item1; item2}"
        Return:
        [
            SetNodeAttributeOperation('object1', 'is_open', 'True'), 
            MoveNodeOperation('item3', 'inventory'), 
            MoveNodeOperation('item4', 'inventory'), 
            DeleteNodeOperation('item1'), 
            DeleteNodeOperation('item2')
        ]
        '''
        #print("PRE_CREATE_OPERATIONS")
        # Preprocessing: replace placeholders with the actual value.
        #print(commands, arguments)
        commands = replace_placeholders(commands, arguments)
        #print(commands)

        # Split the commands by semicolon, but ignore semicolons inside the braces.
        command_list = [remove_extra_spaces(action)
                        for action in re.split(r';(?![^{]*\})', commands) if remove_extra_spaces(action)]
        
        # Expand the actions. For example, "Move {item1; item2} to {inventory}" will be expanded to "Move {item1} to {inventory}" and "Move {item2} to {inventory}".
        expanded_command_list: List[str] = []
        for command in command_list:
            expanded_command_list.extend(GraphOperationFactory._expand_operation(command))
        return [GraphOperationFactory._create_operation(command, world) for command in expanded_command_list]

    @staticmethod
    def _create_operation(command: str, world: Union[World, None] = None, initiator:str='') -> GraphOperation:
        #print("CREATING OPERATION")
        #print(command)
        '''
        Return a GraphOperation and a set of strings denoting unknown arguments that need to be filled in.
        '''
        # Preprocessing: replace reserved word {environment} with the room that the player is in, {inventory} with the player's inventory, {player} with the player.
        if world is not None and world.player is not None:
            print(world.player.container)
            room = world.player.container
            assert isinstance(room, Room), "Bug: player should be in a room"
            # command = command.replace(r'{environment}', f'{{{room.id}}}')
            # command = command.replace(r'{inventory}', f'{{{world.player.id}}}.inventory')
            # command = command.replace(r'{player}', f'{{{world.player.id}}}')
            command = replace_placeholders(command, {'environment': room.id, 'inventory': f'{world.player.id}.inventory', 'player': world.player.id})

        # Preprocessing: Remove ".inventory" for AddNodeOperation and MoveNodeOperation because moving an item to a player's inventory is the same as moving it to the player.
        if command.startswith('Add ') or command.startswith('Move '):
            command = re.sub(r'\..*?}', '}', command)
        
        # Move {entity1} to {entity2}
        move_match = re.match(r"Move\s\{(.+?)\}\sto\s\{(.+?)\}", command)
        if move_match:
            return MoveNodeOperation(move_match.group(1), move_match.group(2))

        # Set {entity.some_attribute} to {value}
        # TODO: There are issues with this regex. For example if value is a dict, it will not be parsed correctly.
        # set_match = re.match(r"Set\s\{(.+?)\.(.+?)\}\sto\s\{(.+?)\}", command)
        # if set_match:
        #     return SetNodeAttributeOperation(set_match.group(1), set_match.group(2), set_match.group(3))
        
        #set_match = re.match(r"Set\s\{(.+?)\}\sto\s\{(.+?)\}", command)
        set_match = re.match(r"Set\s\{(.+?)\}\.(\w+)\s+to\s+(.+)", command)
        #print("Command:", command)
        if set_match:
            return SetNodeAttributeOperation(set_match.group(1), set_match.group(2), set_match.group(3))

        # Delete {entity}
        delete_match = re.match(r"Delete\s\{(.+?)\}", command)
        if delete_match:
            return DeleteNodeOperation(delete_match.group(1))

        # Display You got the leaflet! It says:\n {entity.message}
        display_match = re.match(r"Display (.+)$", command, re.DOTALL)
        if display_match:
            # entity_matches = re.findall(r'\{([^{}]*?)\.([^{}]*?)\}', display_match.group(1))
            # entities:Set[str] = set([entity_match[0] for entity_match in entity_matches])                
            return DisplayMessageOperation(display_match.group(1))

        # DisplayLlmResponseTo You are playing Zork. This is the environment: \n {entity.message} \n Please generate a brief description of the environment.
        llm_match = re.match(r"DisplayLlmResponseTo (.+)$", command, re.DOTALL)
        if llm_match:
            # entity_matches = re.findall(r'\{([^{}]*?)\.([^{}]*?)\}', llm_match.group(1))
            # entities:Set[str] = set([entity_match[0] for entity_match in entity_matches])       
            return DisplayStreamingMessageOperation(llm_match.group(1))
        
        # Add {entity} of type {Item/ContainerItem/Character} to {entity} with description {item description}
        # add_match = re.match(
        #     r"Add\s\{(.+?)\}\sof\stype\s\{(Item|ContainerItem|Character)\}\sto\s\{(.+?)\}\swith\sdescription\s\{(.+?)\}", command, re.DOTALL)
        # print("Command is", command)
        # print("Regex is", add_match)
        # if add_match:
        #     return AddNodeOperation(add_match.group(1), add_match.group(2), add_match.group(3), add_match.group(4))
        add_match = re.match(
            r"Add\s(.+?)\sof\stype\s(Item|ContainerItem|Character|Room)\sto\s(.+?)\swith\sdescription\s'(.+?)'", command, re.DOTALL)
        print(command, add_match)
        if add_match:
            return AddNodeOperation(add_match.group(1), add_match.group(2), add_match.group(3), add_match.group(4))

        # Add {entity} of type {Item/ContainerItem/Character} to {entity}
        # add_match = re.match(
        #     r"Add\s\{(.+?)\}\sof\stype\s\{(Item|ContainerItem|Character)\}\sto\s\{(.+?)\}", command, re.DOTALL)
        # if add_match:
        #     return AddNodeOperation(add_match.group(1), add_match.group(2), add_match.group(3), "")
        
        add_match = re.match(
             r"Add\s\{(.+?)\}\sof\stype\s\{(Item|ContainerItem|Character|Room)\}\sto\s\{(.+?)\}", command, re.DOTALL)
       
        if add_match:
            return AddNodeOperation(add_match.group(1), add_match.group(2), add_match.group(3), "")

        raise ValueError(f"Unknown command format \"{command}\"")


class MoveNodeOperation(GraphOperation):
    def __init__(self, node_name: str, container_node_name: str):
        super().__init__()
        self.node_name = node_name
        self.container_node_name = container_node_name

    def __str__(self) -> str:
        return f"Move {self.node_name} to {self.container_node_name}"
    
    def is_valid(self, world: World) -> Tuple[bool, Union[List[Any], str]]:
        try:
            # will raise error if node not found'
            container_node = world.find_node(self.container_node_name)
            # will raise error if node not found
            node = world.find_node(self.node_name)
            #print("IS VALID MOVE NODE FIX")
            #print(self)
            #print(node, type(node), container_node, type(container_node))
            if node == container_node:
                return False, 'Cannot move node to itself.'
            if isinstance(node, Room):
                return False, 'Cannot move room node during runtime.'
            elif isinstance(node, Character):
                if not isinstance(container_node, Room):
                    return False, 'Character can only move to a room.'
                if node in container_node.characters:
                    return False, f'Character {node.name} already in room {container_node.name}.'
            elif isinstance(node, Item):
                if not isinstance(container_node, Character) and not isinstance(container_node, Room) and not isinstance(container_node, ContainerItem):
                    return False, 'Item can only be placed in a character, room, or container.'
                if isinstance(container_node, Character):
                    if node in container_node.inventory:
                        return False, 'Item already in character inventory.'
                elif isinstance(container_node, Room):
                    if node in container_node.items:
                        return False, 'Item already in room.'
                else:  # container
                    if node in container_node.items:
                        return False, 'Item already in container.'
                    if container_node.capacity > 0 and len(container_node.items) >= container_node.capacity:
                        return False, 'Container is full.'
                    ancestor_node: Union[Node, None] = container_node.container
                    while ancestor_node is not None:
                        if ancestor_node == node:
                            return False, 'Cannot move node into its children.'
                        ancestor_node = ancestor_node.container
        except Exception as e:
            return False, str(e)
        return True, [node, container_node]

    def apply(self, world: World) -> None:
        is_valid, results = self.is_valid(world)
        if is_valid:
            assert isinstance(results, list)
            node, container_node = results
            world.move_node(node, container_node)
        else:
            assert isinstance(results, str), "Bug: results should be a string"
            raise AssertionError("Unable to move node, "+results)


class SetNodeAttributeOperation(GraphOperation):
    def __init__(self, node_name: str, attribute: str, value: str):
        super().__init__()
        self.node_name = node_name
        self.attribute = remove_extra_spaces(attribute.lower())
        self.value = remove_extra_spaces(value)

    def __str__(self) -> str:
        return f"Set {self.node_name}.{self.attribute} to {self.value}"

    def is_valid(self, world: World) -> Tuple[bool, Union[List[Any], str]]:
        try:
            # will raise error if node not found
            node = world.find_node(self.node_name)
            if self.attribute not in Node.additional_attribute_list:
                return False, f'Attribute {self.attribute} not registered.'
            cls = type(node)
            expected_type, _, belonging_class, _, _ = cls.additional_attribute_list[
                self.attribute]
            #print("IS VALID SET ATTRIBUTE")
            #print(Node.additional_attribute_list)
            #print(Node.additional_attribute_list[self.attribute])
            #print(node, belonging_class)
            if not isinstance(node, belonging_class):
                return False, f'Attribute {self.attribute} is not applicable to node {node}.'
            if self.value.lower() == 'none' or self.value.lower() == 'null':
                return True, [node, None]
            else:
                # TODO: also check if value is valid
                if isinstance(expected_type, type):
                    if expected_type == str:
                        return True, [node, self.value]
                    elif expected_type == float:
                        try:
                            return True, [node, float(self.value)]
                        except ValueError:
                            return False, f"Invalid float value: {self.value}"
                    elif expected_type == int:
                        try:
                            return True, [node, int(self.value)]
                        except ValueError:
                            return False, f"Invalid integer value: {self.value}"
                    elif expected_type == bool:
                        #print(self.value, self.value.lower())
                        if self.value.lower() in ['true', '1']:
                            return True, [node, True]
                        elif self.value.lower() in ['false', '0']:
                            return True, [node, False]
                        else:
                            return False, f"Invalid boolean value: {self.value}"
                    elif issubclass(expected_type, Node):
                        is_match, match_type, node_id = Node.is_node_repr(
                            self.value)
                        if not is_match:
                            try:
                                # find node directly. will raise error if node not found
                                field_node = world.find_node(self.value)
                                return True, [node, field_node]
                            except Exception as e:
                                pass
                            return False, f"Invalid node representation: {self.value}"
                        assert match_type is not None, "Bug: match_type should not be None"
                        if not issubclass(match_type, expected_type):
                            return False, f"Invalid node type: {self.value}"
                        # will raise error if node not found
                        field_node = world.find_node(node_id)
                        return True, [node, field_node]
                    elif issubclass(expected_type, list):
                        try:
                            value_parsed: Any = json.loads(self.value)
                            if not isinstance(value_parsed, list):
                                return False, f"Invalid list value: {self.value}"
                            value_list:  List[Any] = value_parsed
                            return True, [node, value_list]
                        except json.decoder.JSONDecodeError:
                            return False, f"Invalid list value: {self.value}"
                    elif issubclass(expected_type, dict):
                        try:
                            value_parsed: Any = json.loads(self.value)
                            if not isinstance(value_parsed, dict):
                                return False, f"Invalid dict value: {self.value}"
                            value_dict:  Dict[Any, Any] = value_parsed
                            return True, [node, value_dict]
                        except json.decoder.JSONDecodeError:
                            return False, f"Invalid dict value: {self.value}"
                    elif issubclass(expected_type, tuple):
                        try:
                            value_parsed: Any = json.loads(self.value)
                            if not isinstance(value_parsed, list):
                                return False, f"Invalid tuple value: {self.value}"
                            value_list:  List[Any] = value_parsed
                            value_tuple: Tuple[Any, ...] = tuple(value_list)
                            return True, [node, value_tuple]
                        except json.decoder.JSONDecodeError:
                            return False, f"Invalid tuple value: {self.value}"
                    elif issubclass(expected_type, set):
                        try:
                            value_parsed: Any = json.loads(self.value)
                            if not isinstance(value_parsed, list):
                                return False, f"Invalid set value: {self.value}"
                            value_list:  List[Any] = value_parsed
                            value_set: Set[Any] = set(value_list)
                            return True, [node, value_set]
                        except json.decoder.JSONDecodeError:
                            return False, f"Invalid set value: {self.value}"
                    else:
                        return False, f"Invalid attribute type: {expected_type}"
                else:
                    return False, f"Bug: expected_type is not a type."
        except Exception as e:
            return False, str(e)

    def apply(self, world: World) -> None:
        #print("checking is valid attribute fix")
        is_valid, results = self.is_valid(world)
        if is_valid:
            assert isinstance(results, list), "Bug: results should be a list"
            assert len(results) == 2, "Bug: results should have length 2"
            assert isinstance(
                results[0], Node), "Bug: results[0] should be a Node"
            node = results[0]
            value: Any = results[1]
            node.set_attribute(self.attribute, value)
        else:
            assert isinstance(results, str), "Bug: results should be a string"
            raise AssertionError("Unable to set attributes, "+results)


class DeleteNodeOperation(GraphOperation):
    def __init__(self, node_name: str):
        super().__init__()
        self.node_name = node_name

    def __str__(self) -> str:
        return f"Delete {self.node_name}"

    def is_valid(self, world: World) -> Tuple[bool, Union[List[Any], str]]:
        #print(self.node_name)
        try:
            node = world.find_node(self.node_name)
            if node == world.player:
                return False, 'Cannot delete player node.'
            if isinstance(node, Room):
                return False, 'Cannot delete room node.'
        except Exception as e:
            return False, str(e)
        return True, [node]

    def apply(self, world: World) -> None:
        #print("APPLYING DELETE OPERATION")
        #print(self)
        is_valid, results = self.is_valid(world)
        #print(is_valid, results)
        if is_valid:
            assert isinstance(results, list)
            assert isinstance(results[0], Node)
            node = results[0]
            world.remove_node(node)
        else:
            assert isinstance(results, str)
            raise AssertionError("Unable to delete node, "+results)


class AddNodeOperation(GraphOperation):
    def __init__(self, node_name: str, type: str, container_name: str, description: str):
        super().__init__()
        self.node_name = node_name
        self.container_name = container_name
        self.type = remove_extra_spaces(type.lower())
        self.description = description

    def __str__(self) -> str:
        return f"Add {self.node_name} of type {self.type} to {self.container_name} with description {self.description}"

    def is_valid(self, world: World) -> Tuple[bool, Union[List[Any], str]]:
        assert self.type in ['item', 'containeritem',
                             'character'], "Type should be Item, ContainerItem, or Character. Other types cannot be added during gameplay."
        node_type = Item if self.type == 'item' else ContainerItem if self.type == 'containeritem' else Character
        node = node_type(self.node_name, self.description)
        #print("VALID CHECK")
        #print(self, type(self))
        #print(node, node_type, self.container_name)
        try:
            # will raise error if node not found
            #print(node, self.container_name)
            if self.container_name == 'environment':
                return True, [node, (np.random.randint(0, 100), np.random.randint(0, 100))]
            container = world.find_node(self.container_name)
            if isinstance(node, Character):
                if not isinstance(container, Room):
                    return False, 'Character must be added to a room.'
            else:  # Item
                if not isinstance(container, (Room, Character, ContainerItem)):
                    return False, 'Item must be added to a room, character, or a container item.'
                if isinstance(container, ContainerItem):
                    if container.capacity > 0 and len(container.items) >= container.capacity:
                        return False, 'Container is full.'
        except Exception as e:
            return False, str(e)
        return True, [node, container]

    def apply(self, world: World) -> None:
        is_valid, results = self.is_valid(world)
        #print("CONTAINER")
        #print("NODE")
        #for node in world.nodes:
            #print(node)
        #print("ROOM")
        #for node in world.rooms:
            #print(node)
        #print("CHAR")
        #for node in world.characters:
            #print(node)
        if is_valid:
            assert isinstance(results, list)
            node, container = results
            world.add_node(node, container)
            #print("FINISHED ADDING NODE")
        else:
            assert isinstance(results, str)
            raise AssertionError("Unable to add node, "+results)


class DisplayMessageOperation(GraphOperation):
    def __init__(self, message: str):
        super().__init__()
        self.message = message

    def __str__(self) -> str:
        return f"Display {self.message}"

    def is_valid(self, world: World) -> Tuple[bool, str]:
        #print("IS VALID DISPLAY")
        #print(self.message)
        if not self.message:
            return False, 'Message cannot be None.'
        try:
            result = self._replace_placeholders(self.message, world)
        except Exception as e:
            return False, str(e)
        result = result.replace('\\n', '\n')
        return True, result

    def apply(self, world: World) -> None:
        #print("APPLYING DISPLAY OPERATION")
        is_valid, result = self.is_valid(world)
        #print(is_valid, result)
        # Replace {node.attribute} with the actual value
        if is_valid:
            print(result)
        else:
            raise AssertionError("Unable to display message, "+result)


class DisplayStreamingMessageOperation(GraphOperation):
    def __init__(self, prompt: str):
        super().__init__()
        self.llm = ChatGPT()
        self.prompt = prompt

    def __str__(self) -> str:
        return f"DisplayLlmResponseTo {self.prompt}"

    def is_valid(self, world: World) -> Tuple[bool, str]:
        if not self.prompt:
            return False, 'Prompt cannot be None.'
        if not self.llm:
            return False, 'LLM cannot be None.'
        try:
            result = self._replace_placeholders(self.prompt, world)
        except Exception as e:
            return False, str(e)
        result = result.replace('\\n', '\n')
        return True, result

    def apply(self, world: World) -> None:
        is_valid, processed_prompt = self.is_valid(world)
        if is_valid:
            try:
                self.llm.print_response_stream(processed_prompt)
            except Exception as e:  # e.g. internet connection error
                raise RuntimeError(
                    "Unable to display streaming message, "+str(e))
        else:
            raise AssertionError(
                "Unable to display streaming message, "+processed_prompt)


if __name__ == '__main__':
    import unittest
    from unittest.mock import patch, MagicMock

    from world import World
    from nodes import Room, Item, ContainerItem, Character, Player
    # from game import Game
    import logging
    import sys
    from copy import deepcopy

    class TestOperation(unittest.TestCase):
        def setUp(self) -> None:
            super().setUp()
            self.world = World()
            self.room1 = Room('room1', 'room1')
            self.room2 = Room('room2', 'room2')
            self.item1 = Item('item1', 'item1')
            self.book = Item('book', 'book')
            self.pen = Item('pen', 'pen')
            self.table = ContainerItem('table', 'table')
            self.container1 = ContainerItem('container1', 'container1')
            self.container2 = ContainerItem('container2', 'container2')
            self.player = Player('player', 'player')
            self.world.add_node(self.room1, (0, 0))
            self.world.add_node(self.room2, (0, 1))
            self.world.add_node(self.item1, self.room1)
            self.world.add_node(self.player, self.room1)
            self.world.add_node(self.container1, self.room2)
            self.world.add_node(self.container2, self.room2)
            self.world.add_node(self.table, self.room1)
            self.world.add_node(self.pen, self.room1)
            self.world.add_node(self.book, self.table)
            self.log = logging.getLogger("SomeTest.testSomething")
        
        @patch('builtins.print')
        def test_replace_placeholders(self, mock_print: MagicMock) -> None:
            Item.register_new_attribute('message', str, None)
            self.book.set_attribute('message', 'Machine Learning')
            self.table.set_attribute('message', 'The table is good for reading.')
            operations = GraphOperationFactory.create_operations( # type: ignore
                r'Display You got the leaflet! It says:\n {object1.message} and {object2.message}', arguments={'object1': 'book', 'object2': 'table'})
            self.assertEqual(len(operations), 1)
            operation = operations[0]
            is_valid, _ = operation.is_valid(self.world)
            self.assertTrue(is_valid)
            operation.apply(self.world)
            mock_print.assert_called_with('You got the leaflet! It says:\n Machine Learning and The table is good for reading.')

            operations = GraphOperationFactory.create_operations(
                r'Move {enum(obj)} to {inventory}', self.world, arguments={'enum(obj)': 'book;pen'})
            self.log.debug(operations[0])
            self.assertEqual(len(operations), 2)
            is_valid, _ = operations[0].is_valid(self.world)
            self.assertTrue(is_valid)
            operations[0].apply(self.world)
            self.assertIn(self.book, self.player.inventory)
            self.assertNotIn(self.pen, self.player.inventory)
            is_valid, _ = operations[1].is_valid(self.world)
            self.assertTrue(is_valid)
            operations[1].apply(self.world)
            self.assertIn(self.pen, self.player.inventory)
            


        def test_move_node_operation(self):
            operation = MoveNodeOperation('room1', 'room2')
            is_valid, message = operation.is_valid(self.world)
            self.log.debug(message)
            self.assertFalse(is_valid)
            self.assertRaises(AssertionError, operation.apply, self.world)

            operation = MoveNodeOperation('player', 'room1')
            is_valid, message = operation.is_valid(self.world)
            self.log.debug(message)
            self.assertFalse(is_valid)
            self.assertRaises(AssertionError, operation.apply, self.world)

            operation = MoveNodeOperation('player', 'room2')
            is_valid, message = operation.is_valid(self.world)
            self.assertTrue(is_valid)
            operation.apply(self.world)

            new_item = Item('new_item', 'new_item')
            operation = MoveNodeOperation('new_item', 'player')
            is_valid, message = operation.is_valid(self.world)
            self.log.debug(message)
            self.assertFalse(is_valid)
            self.assertRaises(AssertionError, operation.apply, self.world)

            self.world.add_node(new_item, self.room1)
            is_valid, message = operation.is_valid(self.world)
            self.assertTrue(is_valid)
            operation.apply(self.world)

            # Test building from string
            operation = GraphOperationFactory._create_operation( # type: ignore
                'Move {container2} to {container1}')
            is_valid, message = operation.is_valid(self.world)
            self.assertTrue(is_valid)
            operation.apply(self.world)

            # make a copy of the world to test if the world is not modified
            world_backup = deepcopy(self.world)

            operation = GraphOperationFactory._create_operation( # type: ignore
                'Move {container1} to {container1}')
            is_valid, message = operation.is_valid(self.world)
            self.assertFalse(is_valid)
            self.log.debug(message)
            self.assertRaises(AssertionError, operation.apply, self.world)

            operation = GraphOperationFactory._create_operation( # type: ignore
                'Move {container1} to {container2}')
            is_valid, message = operation.is_valid(self.world)
            self.assertFalse(is_valid)
            self.log.debug(message)
            self.assertRaises(AssertionError, operation.apply, self.world)

            self.assertEqual(self.world, world_backup)

            operation = GraphOperationFactory._create_operation( # type: ignore
                'Move {container2} to {environment}', self.world)
            is_valid, message = operation.is_valid(self.world)
            self.assertTrue(is_valid)
            operation.apply(self.world)
            player_room = self.player.container
            assert isinstance(player_room, Room)
            self.assertIn(self.container2, player_room.items)
            self.assertNotIn(self.container2, self.container1.items)

            operation = GraphOperationFactory._create_operation( # type: ignore
                'Move {container2} to {inventory}', self.world)
            is_valid, message = operation.is_valid(self.world)
            self.assertTrue(is_valid)
            operation.apply(self.world)
            self.assertIn(self.container2, self.player.inventory)

        def test_set_node_attribute(self):
            operation = GraphOperationFactory._create_operation( # type: ignore
                'Set {player.is_open} to {True}')
            is_valid, _ = operation.is_valid(self.world)
            self.assertFalse(is_valid)
            self.assertRaises(AssertionError, operation.apply, self.world)

            Character.register_new_attribute('dialog', str, None)
            operation = GraphOperationFactory._create_operation( # type: ignore
                'Set {player.dialog} to {Hello}')
            is_valid, _ = operation.is_valid(self.world)
            self.assertTrue(is_valid)
            operation.apply(self.world)
            self.assertEqual(self.player.get_attribute('dialog'), 'Hello')

            operation = GraphOperationFactory._create_operation( # type: ignore
                'Set {player.dialog} to {None}')
            is_valid, _ = operation.is_valid(self.world)
            self.assertTrue(is_valid)
            operation.apply(self.world)
            self.assertEqual(self.player.get_attribute('dialog'), None)

            operation = GraphOperationFactory._create_operation( # type: ignore
                'Set {container1.is_destroyed} to {True}')
            is_valid, _ = operation.is_valid(self.world)
            self.assertFalse(is_valid)
            self.assertRaises(AssertionError, operation.apply, self.world)

            ContainerItem.register_new_attribute('is_destroyed', bool, False)

            operations = GraphOperationFactory.create_operations(
                'Set {container1;container2.is_destroyed} to {True}')
            self.assertEqual(len(operations), 2)
            operation = operations[0]
            is_valid, _ = operation.is_valid(self.world)
            self.log.debug(_)
            self.assertTrue(is_valid)
            operation.apply(self.world)
            self.assertEqual(self.container1.get_attribute('is_destroyed'), True)
            operation = operations[1]
            is_valid, _ = operation.is_valid(self.world)
            self.log.debug(_)
            self.assertTrue(is_valid)
            operation.apply(self.world)
            self.assertEqual(self.container2.get_attribute('is_destroyed'), True)

        @patch('builtins.print')
        def test_display_message(self, mock_print: MagicMock):
            Item.register_new_attribute('message', str, None)
            self.item1.set_attribute('message', 'item1')
            operation = GraphOperationFactory._create_operation( # type: ignore
                r'Display You got the leaflet! It says:\n {item1.message}')
            is_valid, _ = operation.is_valid(self.world)
            self.assertTrue(is_valid)
            operation.apply(self.world)
            mock_print.assert_called_with(
                'You got the leaflet! It says:\n item1')

            operation = GraphOperationFactory._create_operation( # type: ignore
                r'Display You got the leaflet! It says:\n {iteddsdsadsam1.message}')
            is_valid, _ = operation.is_valid(self.world)
            self.assertFalse(is_valid)

            operation = GraphOperationFactory._create_operation( # type: ignore
                r'Display You got the leaflet! It says:\n {item1.mefddsfdssage}')
            is_valid, _ = operation.is_valid(self.world)
            self.assertFalse(is_valid)

        def test_delete_node(self):
            operation = GraphOperationFactory._create_operation( # type: ignore
                r'Delete {player}')
            is_valid, _ = operation.is_valid(self.world)
            self.assertFalse(is_valid)
            self.assertRaises(AssertionError, operation.apply, self.world)

            operation = GraphOperationFactory._create_operation( # type: ignore
                r'Delete {room1}')
            is_valid, _ = operation.is_valid(self.world)
            self.assertFalse(is_valid)
            self.assertRaises(AssertionError, operation.apply, self.world)
 
            operation = GraphOperationFactory._create_operation( # type: ignore
                r'Delete {item1}')
            is_valid, _ = operation.is_valid(self.world)
            self.assertTrue(is_valid)
            operation.apply(self.world)
            self.assertNotIn(self.item1, self.world.nodes)

            operation = GraphOperationFactory._create_operation( # type: ignore
                r'Delete {item1}')
            is_valid, _ = operation.is_valid(self.world)
            self.assertFalse(is_valid)
            self.assertRaises(AssertionError, operation.apply, self.world)

            operation = GraphOperationFactory._create_operation( # type: ignore
                r'Delete {container1}')
            is_valid, _ = operation.is_valid(self.world)
            self.assertTrue(is_valid)
            operation.apply(self.world)
            self.assertNotIn(self.container1, self.world.nodes)

            operation = GraphOperationFactory._create_operation( # type: ignore
                r'Delete {container1}')
            is_valid, _ = operation.is_valid(self.world)
            self.assertFalse(is_valid)
            self.assertRaises(AssertionError, operation.apply, self.world)

        def test_add_node(self):
            operation = GraphOperationFactory._create_operation( # type: ignore
                r'Add {money} of type {Item} to {player} with description {100 dollars}')
            is_valid, _ = operation.is_valid(self.world)
            self.assertTrue(is_valid)
            operation.apply(self.world)
            self.assertTrue(self.world.find_node(
                'money') in self.player.inventory)
            self.assertEqual(self.world.find_node(
                'money').description, '100 dollars')
 
            operation = GraphOperationFactory._create_operation( # type: ignore
                r'Add {sword} of type {Item} to {player} with description {A sword}')
            is_valid, _ = operation.is_valid(self.world)
            self.assertTrue(is_valid)
            operation.apply(self.world)
            self.assertTrue(self.world.find_node(
                'sword') in self.player.inventory)
            self.assertEqual(self.world.find_node(
                'sword').description, 'A sword')
            self.assertEqual(self.world.find_node(
                'sword').container, self.player)

            operation = GraphOperationFactory._create_operation( # type: ignore
                r'Add {sword} of type {Item} to {dasnkjdasnjk} with description {A sword}')
            is_valid, _ = operation.is_valid(self.world)
            self.assertFalse(is_valid)
            self.assertRaises(AssertionError, operation.apply, self.world)

        def test_composite_commands(self):
            expected : List[GraphOperation] = [
                SetNodeAttributeOperation('object1', 'is_open', 'True'),
                MoveNodeOperation('item3', 'inventory'),
                MoveNodeOperation('item4', 'inventory'),
                DeleteNodeOperation('item1'),
                DeleteNodeOperation('item2'),
                DisplayMessageOperation('Hello'),
                DisplayMessageOperation(r'{player.inventory}')
            ]
            commands = "Set {object1.is_open} to {True}; Move {item3; item4} to {inventory} ; Delete {item1; item2}; Display Hello; Display {player.inventory}"
            operations = GraphOperationFactory.create_operations(commands)
            self.assertEqual(operations, expected)

    logging.basicConfig(stream=sys.stderr)
    logging.getLogger("SomeTest.testSomething").setLevel(logging.DEBUG)
    unittest.main()
