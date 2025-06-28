from typing import Dict, List, Union, Tuple, Any, Set, Type

from type import Coordinate, Direction

from nodes import Node, Room, Character, Item, Player, ContainerItem

from trie import Trie

from pydoc import locate

from utils import is_jsonable, remove_extra_spaces, print_warning

import json, os

import numpy as np


current_file_path = os.path.dirname(os.path.abspath(__file__))
 
class World:
    def __init__(self, configurations: Dict[str, Any] = {}):
        map_size : Tuple[int, int] = configurations.get("map_size", (5, 5))
        self.map: List[List[Union[Room, None]]] = [
            [None for _ in range(map_size[1])] for _ in range(map_size[0])]
        self.room_coordinates: Dict[Room, Coordinate] = {}
        self.nodes = Trie()
        self.characters = Trie()
        self.player: Union[Player, None] = None
        self.rooms = Trie()
        self.items = Trie()
        self.removed_nodes = Trie() # Nodes that are removed from the world are stored here. The purpose is to keep a reference to the nodes.

    def get_num_rooms(self) -> int:
        return len(self.rooms)
    
    def get_adjacent_rooms(self, room: Room) -> Dict[Direction, Union[Room, None]]:      
        return room.adjacent_rooms
    
    def are_rooms_adjacent(self, room1: Room, room2: Room) -> bool:
        return room2 in self.get_adjacent_rooms(room1).values()
    
    def node_exists(self, name: str, room: str='', local:bool=False, strict:bool=False) -> bool:
        candidates = self.find_nodes(name, room, local, strict=strict)
        return len(candidates) > 0

    def find_node(self, name: str, room: str='', local:bool=False, find_removed:bool=False, strict:bool=False, error_message_verbose:bool=False) -> Node:
        '''
        Returns the node with the given name, id, or name prefix.
        If the name is ambiguous or no node is found, raises ValueError.
        local: if we just search in a specific room, or globally.
        '''
        is_node, _, node_id = Node.is_node_repr(name)
        if is_node:
            name = node_id
        candidates = self.find_nodes(name, room, local, find_removed, strict)
        if len(candidates) == 0:
            if not error_message_verbose:
                raise ValueError(f"No node found with name '{name}'.")
            else:
                if local or strict:
                    candidates_elsewhere = self.find_nodes(name, find_removed=find_removed)
                    if len(candidates_elsewhere) == 0:
                        raise ValueError(f"No node found with name '{name}'{'in the current location or elsewhere' if local else ''}. The node does not exist in the world.")
                    else:
                        raise ValueError(f"No node found with name '{name}'{'in the current location' if local else ''}. However, the following node(s) can be found: " + ', '.join([f'"{i.name}" {f"at {i.get_room().name}" if i not in self.removed_nodes else "(this node has been deleted from the world)"}' for i in candidates_elsewhere]))
                else:
                    raise ValueError(f"No node found with name '{name}'.")
        elif len(candidates) == 1:
            return candidates.pop()
        else:
            candidates = [i for i in candidates if remove_extra_spaces(i.name).lower()==remove_extra_spaces(name).lower()]
            if len(candidates) == 1:
                return candidates[0]
            else:
                # Check if there is only one node that in the same room as the player.
                if not local:
                    player = self.player
                    if player is not None:
                        candidates = [i for i in candidates if i.get_room() == player.get_room()]
                        if len(candidates) == 1:
                            return candidates[0]
                raise ValueError(f"Ambiguous name \"{name}\". Which one do you mean: {[i.name for i in candidates]}?")

    def find_nodes(self, name: str, room: str='', local:bool=False, find_removed:bool=False, strict:bool=False) -> Set[Node]:
        '''
        Returns the set of nodes with the given name, id, or name prefix.
        This method will never raise Error, unlike find_node.
        '''
        is_node, _, node_id = Node.is_node_repr(name)
        if is_node:
            name = node_id
        nodes = self.nodes.search(name)
        if find_removed:
            nodes = nodes.union(self.removed_nodes.search(name))
        if strict:
            nodes = [i for i in nodes if remove_extra_spaces(i.name).lower()==remove_extra_spaces(name).lower()]
        if room and not local:
            room = '' # ignore the "room" parameter if search globally.
        if local:
            if not room:
                player = self.player
                assert player is not None, "Player not found. Cannot identify the scope of node search."
                room = player.get_room().id
        if room:
            room_node = self.find_node(room)
            assert isinstance(room_node, Room), f'Node {room} is not a room.'
        else:
            room_node = None
        
        return set([i for i in nodes if not room_node or (isinstance(i, Room) and self.are_rooms_adjacent(i, room_node)) or i.get_room() == room_node])

    def move_node(self, node: Node, to: Node) -> None:  
        assert node in self.nodes, 'Node does not exist.'
        assert to in self.nodes, 'Destination does not exist.' 
        assert not isinstance(node, Room), 'Rooms cannot be moved.'
        assert node != to, 'Cannot move node to itself.'
        if isinstance(node, Character):
            from_room = node.container
            assert isinstance(from_room, Room) and isinstance(to, Room), 'Character can only be moved between rooms.'
            assert node not in to.characters, 'Character already exists in the room.'
            from_room.characters.remove(node)
            to.characters.add(node)
            node.container = to
        elif isinstance(node, Item):
            from_node = node.container
            assert isinstance(from_node, (Room, Character, ContainerItem)) and isinstance(to, (Room, Character, ContainerItem)), 'Item can only be moved here.'
            if isinstance(to, Room):
                assert node not in to.items, 'Item already exists in the room.'
                to.items.add(node)
            elif isinstance(to, Character):
                assert node not in to.inventory, 'Item already exists in the inventory.'
                to.inventory.add(node)
            else: # ContainerItem
                assert node not in to.items, 'Item already exists in the container.'
                assert to.capacity <= 0 or len(to.items) < to.capacity, 'Container is full.'
                # to ensure no cycles form, we need to check to ensure that we are not moving a container into one of its children
                ancestor_node : Union[Node, None] = to.container
                while ancestor_node is not None:
                    assert ancestor_node != node, 'Cannot move container into its children.'
                    ancestor_node = ancestor_node.container
                to.items.add(node)
            if isinstance(from_node, Room):
                from_node.items.remove(node)
            elif isinstance(from_node, Character):
                from_node.inventory.remove(node)
            else: # ContainerItem
                from_node.items.remove(node)
            node.container = to

    def register_new_attribute(self, node_type: Type[Node], attr: str, default:Any=None, is_internal:bool=False) -> None:
        return node_type.register_new_attribute(attr, default, is_internal)

    def get_node_attribute(self, node: Node, attr: str) -> Any:
        return node.get_attribute(attr)

    def set_node_attribute(self, node: Node, attr: str, value: Any) -> None:
        node.set_attribute(attr, value)
    
    def add_room(self, room: Room, coordinate: Coordinate) -> None:
        assert room not in self.nodes, 'Room already exists.'
        assert self.map[coordinate[0]][coordinate[1]] is None, 'Room already exists at the coordinate.'        
        self.map[coordinate[0]][coordinate[1]] = room
        self.room_coordinates[room] = coordinate
        self.nodes.insert(room)
        self.rooms.insert(room)
        room_to_west = self.map[coordinate[0]][coordinate[1] - 1] if coordinate[1] > 0 else None
        room_to_east = self.map[coordinate[0]][coordinate[1] + 1] if coordinate[1] < len(self.map[0]) - 1 else None
        room_to_south = self.map[coordinate[0] + 1][coordinate[1]] if coordinate[0] < len(self.map) - 1 else None
        room_to_north = self.map[coordinate[0] - 1][coordinate[1]] if coordinate[0] > 0 else None
        if room_to_north is not None:
            room_to_north.adjacent_rooms["south"] = room
            room.adjacent_rooms["north"] = room_to_north
        if room_to_south is not None:
            room_to_south.adjacent_rooms["north"] = room
            room.adjacent_rooms["south"] = room_to_south
        if room_to_east is not None:
            room_to_east.adjacent_rooms["west"] = room
            room.adjacent_rooms["east"] = room_to_east
        if room_to_west is not None:
            room_to_west.adjacent_rooms["east"] = room
            room.adjacent_rooms["west"] = room_to_west

    def restore_initial_state(self) -> None:
        '''
        Restore the world to its initial state.
        '''

        # Step 1: Remove node hierarchy by deleting references to children, then reset the node attributes.
        for node in self.nodes:
            #print("REMOVING NODE ATTRIBUTES")
            #print(node)
            if isinstance(node, ContainerItem):
                #print(node.items)
                node.items = set()
            elif isinstance(node, Character):
                #print(node.inventory)
                node.inventory = set()
            elif isinstance(node, Room):
                #print(node.items, node.characters)
                node.items = set()
                node.characters = set()
            node.restore_initial_state()
        
        # Step 2: Recreate node hierarchy by adding references to children.
        for node in self.nodes:
            node.container = node.original_container
            parent_node = node.container
            if parent_node is not None:
                if isinstance(parent_node, Room):
                    if isinstance(node, Item):
                        parent_node.items.add(node)
                    elif isinstance(node, Character):
                        parent_node.characters.add(node)
                    else:
                        raise RuntimeError('Bug! Unsupported node type.')
                elif isinstance(parent_node, Character):
                    if isinstance(node, Item):
                        parent_node.inventory.add(node)
                    else:
                        raise ValueError('Bug! Unsupported node type.')
                elif isinstance(parent_node, ContainerItem):
                    if isinstance(node, Item):
                        parent_node.items.add(node)
                    else:
                        raise ValueError('Bug! Unsupported node type.')
                            
    def add_node(self, node: Node, container: Union[Node, Coordinate]) -> None:
        #print("ADDING NODE, CONTAINER")
        print(node, type(node), container)
        if "inventory" in node:
            return
        assert node not in self.nodes, 'Node already exists.'
        if isinstance(node, Room):
            #print("NODE IS ROOM")
            #print(node, type(node))
            #print(container, type(container), len(container), type(container[0]), type(container[1]))
            assert isinstance(container, tuple) and len(container) == 2 and isinstance(container[0], int) and isinstance(container[1], int), 'Coordinate must be a tuple of two integers.'
            self.add_room(node, container)
        else:
            assert isinstance(container, Node), 'Container must be a node.'
            assert container in self.nodes, 'Container does not exist.'
            if isinstance(node, Item):
                assert isinstance(container, (Room, Character, ContainerItem)), 'Item cannot be added here.'
                if isinstance(container, Room):
                    container.items.add(node)
                elif isinstance(container, Character):
                    container.inventory.add(node)
                else: # ContainerItem
                    assert container.capacity <= 0 or len(container.items) < container.capacity, 'Container is full.'
                    container.items.add(node)
                self.nodes.insert(node)
                self.items.insert(node)
                node.container = container
                node.original_container = container
            elif isinstance(node, Character):
                assert isinstance(container, Room), 'Character must be added to a room.'
                if isinstance(node, Player):
                    assert self.player is None, 'Player already exists.'
                    self.player = node
                self.nodes.insert(node)
                self.characters.insert(node)
                container.characters.add(node)
                node.container = container
                node.original_container = container
            else: 
                raise ValueError('Unknown node type.')
            
    def remove_node(self, node: Node, remove_children:bool=True) -> None:
        assert node in self.nodes, 'Node does not exist.'
        if isinstance(node, Room):
            raise ValueError("Rooms cannot be removed.")
        elif isinstance(node, Item):
            assert isinstance(node.container, (Room, Character, ContainerItem)), "Bug: Item's container is not a node."
            self.nodes.remove(node)
            self.items.remove(node)
            if isinstance(node.container, Room):
                node.container.items.remove(node)
            elif isinstance(node.container, Character):
                node.container.inventory.remove(node)
            else: # ContainerItem
                node.container.items.remove(node)
            if isinstance(node, ContainerItem):
                if remove_children:
                    items = list(node.items) # Need to copy the list because the list will be modified during the iteration
                    for item in items:
                        self.remove_node(item, True)
                else:
                    parent_node: Union[Node, None] = node.container
                    while not isinstance(parent_node, Room):
                        assert parent_node is not None, "Bug: Reached a null node without reaching a room"
                        parent_node = parent_node.container
                    items = list(node.items)
                    for item in items:
                        self.move_node(item, parent_node)
            node.container = None
            self.removed_nodes.insert(node)
        elif isinstance(node, Character):
            assert isinstance(node.container, Room)
            if isinstance(node, Player):
                raise ValueError("The player cannot be removed.")
            self.nodes.remove(node)
            self.characters.remove(node)
            node.container.characters.remove(node)
            if remove_children:
                items = list(node.inventory)
                for item in items:
                    self.remove_node(item, True)
            else:
                parent_room: Room = node.container
                items = list(node.inventory)
                for item in items:
                    self.move_node(item, parent_room)
            node.container = None
            self.removed_nodes.insert(node)

    def get_room_from_name(self, name: str) -> Room:
        room = self.find_node(name)
        assert isinstance(room, Room)
        return room
    
    def get_room_from_coordinate(self, coordinate: Coordinate) -> Union[Room, None]:
        return self.map[coordinate[0]][coordinate[1]]
    
    def serialize(self, is_strict:bool=True) -> Dict[str, Any]:
        '''
        Returns an serialized representation of the world.
        '''
        # map_size = (len(self.map), len(self.map[0]))
        result:Dict[str, Any] = {}
        map: List[List[Union[str, None]]]= [[None if location == None else location.id for location in row] for row in self.map]
        result['map'] = map
        result['characters'] = {node.id:node.serialize('storage') for node in self.characters}
        result['items'] = {node.id:node.serialize('storage') for node in self.items}
        result['rooms'] = {node.id:node.serialize('storage') for node in self.rooms}
        result['player'] = self.player.id if self.player is not None else None
        result['node_attributes'] = {}
        result['removed_nodes'] = {node.id:node.serialize('storage') for node in self.removed_nodes}

        # {name, type, default, belonging_class, is_internal，is_restorable}
        additional_attribute_list: Dict[str,
                                    Tuple[Type[Any], Any, Type[Any], bool, bool]] = Node.additional_attribute_list
        for attr in additional_attribute_list:
            attribute_type, default, belonging_class, is_internal, _ = additional_attribute_list[attr]
            if isinstance(attribute_type, type):
                assert isinstance(default, attribute_type) or default is None
            if attribute_type == set or attribute_type == tuple:
                default = list(default)
            if not is_jsonable(default):
                if is_strict:
                    raise ValueError('The default value of attribute {} is not jsonable.'.format(attr))
                else:
                    print('Warning: the default value of attribute {} is not jsonable.'.format(attr))
                    default = None
            result['node_attributes'][attr] = {'type': attribute_type.__name__,
                                               'default': default,
                                               'belonging_class': belonging_class.__name__,
                                               'is_internal': is_internal
                                        }
        return result

    @staticmethod
    def deserialize(serialized: Dict[str, Any], is_strict:bool=True) -> "World":
        # Implement the deserialization of a dictionary representation to a world object
        character_data = serialized['characters']
        item_data = serialized['items']
        room_data = serialized['rooms']
        player_id:Union[str, None]= serialized['player']
        node_attributes:Dict[str, Dict[str, Any]]= serialized['node_attributes']
        map_size = (len(serialized['map']), len(serialized['map'][0]))
        world = World({'map_size': map_size})
        class_map:Dict[str, Type[Node]] = {'Player': Player, 'Room': Room, 'Character': Character, 'Item': Item, 'ContainerItem': ContainerItem, 'Node': Node}

        # register node attributes
        for attr in node_attributes:
            # print('registering attribute {} for class {}'.format(attr, node_attributes[attr]['belonging_class']))
            attribute_type_str:str = node_attributes[attr]['type']
            default = node_attributes[attr]['default']
            belonging_class:str = node_attributes[attr]['belonging_class']
            is_internal:bool = node_attributes[attr]['is_internal']
            if attribute_type_str == 'set':
                attribute_type = set
                default = set(default)
            elif attribute_type_str == 'tuple':
                attribute_type = tuple
                default = tuple(default)
            elif attribute_type_str in class_map:
                attribute_type = class_map[attribute_type_str]
                if default is not None:
                    if is_strict:
                        raise ValueError('Giving default value to a Node type attribute is currently not supported.')
                    else:
                        print('Warning: Giving default value to a Node type attribute is currently not supported.')
                        default = None
            else:
                # check if it is a built-in type
                if '.' not in attribute_type_str and locate(attribute_type_str):
                    attribute_type = locate(attribute_type_str)
                    assert isinstance(attribute_type, type), 'The type of attribute {} is not supported.'.format(attribute_type_str)
                else:
                    raise ValueError('The type of attribute {} is not supported.'.format(attribute_type_str))
            assert isinstance(default, attribute_type) or default is None, 'The default value of attribute {} is not of type {}.'.format(attr, attribute_type_str)
            assert belonging_class in class_map, "Unknown node class {}.".format(belonging_class)
            class_map[belonging_class].register_new_attribute(attr, attribute_type, default, is_internal)

        # create nodes
        characters:Dict[str, Character] = {id:Character('', id=id) if id != player_id else Player('', id=id) for id in character_data}
        items:Dict[str, Item] = {id:Item('', id=id) if item_data[id]['_type'] != 'ContainerItem' else ContainerItem('', id=id) for id in item_data}
        rooms:Dict[str, Room] = {id:Room('', id=id) for id in room_data}
        nodes:Dict[str, Node] = {**characters, **items, **rooms}


        # populate node attributes by deserialization
        for character_id in characters:
            nodes[character_id].deserialize(character_data[character_id], nodes)

        for item_id in items:
            nodes[item_id].deserialize(item_data[item_id], nodes)

        for room_id in rooms:
            nodes[room_id].deserialize(room_data[room_id], nodes)
        
        # add nodes to world
        for character_id in characters:
             world.nodes.insert(characters[character_id])
             world.characters.insert(characters[character_id])
        player = characters[player_id] if player_id is not None else None
        assert isinstance(player, Player) or player is None, 'Player is not a Player object.'
        world.player = player

        for item_id in items:
            world.nodes.insert(items[item_id])
            world.items.insert(items[item_id])

        for room_id in rooms:
            world.nodes.insert(rooms[room_id])
            world.rooms.insert(rooms[room_id])

        for i in range(map_size[0]):
            for j in range(map_size[1]):
                if serialized['map'][i][j] is not None:
                    room = nodes[serialized['map'][i][j]]
                    assert isinstance(room, Room), 'Map contains non-room node.'
                    world.map[i][j] = room
                    world.room_coordinates[room] = (i, j)
        
        # TODO: Deserialize removed nodes
        return world
    
    def save(self, file_name:str='game.json', dir_name: Union[str,None]=None, is_strict:bool=True, indent:Union[int, None]=None):
        if dir_name is None:
            dir_name = current_file_path
        path = os.path.join(dir_name, file_name)
        with open(path, 'w') as f:
            json.dump(self.serialize(is_strict), f, indent=indent)

    @staticmethod
    def load(file_name:str='game.json', dir_name: str='', is_strict:bool=True) -> "World":
        if dir_name == '':
            dir_name = current_file_path
        path = os.path.join(dir_name, file_name)
        with open(path, 'r') as f:
            return World.deserialize(json.load(f), is_strict)
        
    def __eq__(self, __value: object) -> bool:
        if not isinstance(__value, World):
            return False
        return self.nodes == __value.nodes and self.map == __value.map # Other attributes are not compared because they can be derived from the nodes and map attributes. removed nodes are not compared because they are not part of the world.

if __name__ == '__main__':
    import unittest

    class TestWorld(unittest.TestCase):
        def test_consistenty(self):
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
            world.add_node(room1, (0, 0))
            world.add_node(room2, (0, 1))
            self.assertRaises(AssertionError, world.add_node, room2, (0, 0))
            self.assertRaises(AssertionError, world.add_node, room1, (0, 0))
            self.assertRaises(AssertionError, world.add_room, room3, (0, 0))
            world.add_room(room3, (0, 2))
            self.assertEqual(world.map[0][0],room1)
            self.assertEqual(world.map[0][1],room2)
            self.assertEqual(world.map[0][2],room3)
            self.assertEqual(world.room_coordinates[room1],(0, 0))
            self.assertEqual(world.room_coordinates[room2],(0, 1))
            self.assertEqual(world.room_coordinates[room3],(0, 2))
            self.assertEqual(world.find_node('room1'), room1)
            self.assertEqual(world.find_node(room2.id), room2)
            self.assertEqual(world.find_node('room3'), room3)
            self.assertEqual(room1.adjacent_rooms['east'], room2)
            self.assertEqual(room1.adjacent_rooms['south'], None)
            self.assertEqual(room1.adjacent_rooms['west'], None)
            self.assertEqual(room1.adjacent_rooms['north'], None)
            self.assertRaises(ValueError, world.find_node, 'room4')
            world.add_node(character1, room1)
            self.assertEqual(world.find_node('aaa'), character1)
            self.assertRaises(ValueError, world.find_node, 'room')
            world.add_node(container1, character1)
            world.add_node(item1, container1)
            self.assertRaises(AssertionError, world.add_node, item1, container1)
            world.add_node(item2, container1)
            self.assertRaises(AssertionError, world.add_node, item3, container1)
            self.assertNotIn(item3, container1.items)
            world.move_node(item2, room1)
            self.assertEqual(item2.container, room1)
            self.assertIn(item2, room1.items)
            self.assertNotIn(item2, container1.items)   
            world.move_node(item2, container1)
            self.assertEqual(item2.container, container1)
            self.assertNotIn(item2, room1.items)
            self.assertIn(item2, container1.items)
            self.assertRaises(AssertionError, world.move_node, character2, room1)
            world.add_node(character2, room1)
            self.assertRaises(AssertionError, world.move_node, character2, room1)
            self.assertRaises(AssertionError, world.move_node, character2, container1)
            self.assertIn(character2, room1.characters)
            self.assertNotIn(character2, container1.items)
            world.remove_node(container1, False)
            self.assertNotIn(container1, world.nodes)
            self.assertIn(item2, room1.items)
            self.assertIn(item1, room1.items)
            self.assertEqual(item2.container, room1)
            self.assertEqual(item1.container, room1)
            world.add_node(container1, room2)
            world.move_node(item1, container1)
            world.move_node(item2, container1)
            world.remove_node(container1, True)
            self.assertNotIn(container1, world.nodes)
            self.assertNotIn(item1, world.nodes)
            self.assertNotIn(item2, world.nodes)
            self.assertNotIn(item1, world.items)
            self.assertNotIn(item2, world.items)
            self.assertNotIn(item1, room1.items)
            self.assertNotIn(item2, room1.items)
            self.assertNotIn(item1, container1.items)
            self.assertNotIn(item2, container1.items)
            self.assertIsNone(item1.container)
            self.assertIsNone(item2.container)

            room4 = Room('room4')
            container3 = ContainerItem('container3')
            container4 = ContainerItem('container4')
            world.add_node(room4, (0, 3))
            world.add_node(container3, room4)
            world.add_node(container4, room4)
            world.move_node(container4, container3) # Should be fine
            self.assertEqual(container4.container, container3)
            self.assertEqual(container3.container, room4)
            self.assertIn(container3, room4.items)
            self.assertIn(container4, container3.items)
            self.assertRaises(AssertionError, world.move_node, container3, container4) # This will cause a cycle. They cannot contain each other.


        def test_serialize(self):
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
            character1.set_attribute('dialog_history', ['Hello', 'I am character1'])
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
            character2.set_attribute('dialog_history', character2.get_attribute('dialog_history') + ['I am character2'])

            serialized_json = world.serialize()
            deserialized_world = World.deserialize(serialized_json)
            self.assertEqual(world, deserialized_world)

            Node.reset_additional_attributes()
            
            deserialized_world = World.deserialize(serialized_json)
            self.assertEqual(world, deserialized_world)

    unittest.main()


    