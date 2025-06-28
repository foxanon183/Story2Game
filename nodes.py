from utils import to_lower_bound_kebab_case

from uuid import uuid4

from typing import Dict, List, Union, Tuple, Any, Set, Callable, Type, Self, cast

from copy import deepcopy

from type import Direction, SerializationType

from utils import remove_extra_spaces

import re, json

# # Create a generic variable that can be 'Node', or any subclass.
# T = TypeVar('T', bound='Node')

class Node:
    additional_attribute_list: Dict[str,
                                    Tuple[type, Any, Type['Node'], bool, bool]] = {}  # (type, default, belonging_class, is_internal, is_restorable)
    mapping: Dict[str, Type['Node']] = {}

    def __init__(self, name: str, description: str = "", id: Union[str, None] = None):
        self.additional_attributes : Dict[str, List[Any]]= {}
        self.name = name
        self.description = description
        self.container : Union['Node', None] = None
        self.original_container : Union['Node', None] = None
        self.id = to_lower_bound_kebab_case(name) + '-' + str(uuid4()) if id is None else id

    def get_children(self) -> Set['Node']:
        raise NotImplementedError("This method should be implemented by subclasses.")
    
    def get_parent(self) -> Union['Node', None]:
        return self.container
    
    def __contains__(self, child: Union['Node', str]) -> bool:
        raise NotImplementedError("This method should be implemented by subclasses.")

    def get_room(self) -> 'Room':
        room:Node = self
        while room.container is not None:
            room = room.container
        assert isinstance(room, Room), "Bug: root node is not a room."
        return room
    
    @classmethod
    def _register_new_attribute(cls, attr: str, attribute_type: type, default:Any=None, is_internal:bool=False, is_restorable:bool=True) -> None:
        #print("REGISTERING NEW ATTRIBUTE", attr, cls)
        # assert default is None or isinstance(default, attribute_type)
        attr = remove_extra_spaces(attr.lower())
        if attr in Node.additional_attribute_list:
            attribute_type_, default_, belonging_class_, is_internal_, is_restorable_ = Node.additional_attribute_list[attr]
            if attribute_type_ == attribute_type and default_ == default and is_internal_ == is_internal and is_restorable_ == is_restorable:
                if cls != belonging_class_:
                    Node.additional_attribute_list[attr] = (attribute_type, default, Node, is_internal, is_restorable)
            else:
                raise AssertionError(f'Attribute {attr} already exists in class {belonging_class_.__name__}')
            return
        if attr in cls.__dict__ and isinstance(getattr(cls, attr, None), property):
            return
        assert len(attr) > 0, "Attribute name cannot be empty."
        assert attr[0].isalpha(), "Attribute name must start with a letter."
        assert attr not in cls.__dict__, f"Attribute {attr} already exists in class {cls.__name__}"
        if isinstance(attribute_type, type):
            assert isinstance(default, attribute_type) or default is None
        Node.additional_attribute_list[attr] = (attribute_type, default, cls, is_internal, is_restorable)
        getter: Callable[[Node], type] = lambda self: self.get_attribute(attr)
        setter: Callable[[Node, type], None] = lambda self, value: self.set_attribute(attr, value)
        setattr(cls, attr, property(getter, setter))

    @classmethod
    def register_new_attribute(cls, attr: str, attribute_type: type, default:Any=None, is_internal:bool=False) -> None:
        cls._register_new_attribute(attr, attribute_type, default, is_internal, True)

    @staticmethod
    def reset_additional_attributes() -> None:
            for attr in Node.additional_attribute_list:
                cls = Node.additional_attribute_list[attr][2]
                delattr(cls, attr)
            Node.additional_attribute_list = {}
            Node._register_new_attribute("name", str, "")
            Node._register_new_attribute("description", str, "")
            Node._register_new_attribute("container", Node, None, is_internal=True)
            Node._register_new_attribute("id", str, "")
            Character._register_new_attribute("inventory", set, set(), is_restorable=False)
            Player._register_new_attribute("goal", str, "")
            Room._register_new_attribute("items", set, set(), is_restorable=False)
            Room._register_new_attribute("characters", set, set(), is_restorable=False)
            Room._register_new_attribute("adjacent_rooms", dict, {"east": None, "west": None, "north": None, "south": None}, is_restorable=False)
            Item._register_new_attribute("keywords", list, [])
            ContainerItem._register_new_attribute("capacity", int, 0)
            ContainerItem._register_new_attribute("items", set, set(), is_restorable=False)
            ContainerItem._register_new_attribute("is_locked", bool, False)
            ContainerItem._register_new_attribute("is_open", bool, False)
    
    @classmethod
    def has_attribute(cls, attr: str) -> bool:
        return attr in Node.additional_attribute_list or isinstance(getattr(cls, attr, None), property)

    def get_attribute(self, attr: str) -> Any:
        if attr not in Node.additional_attribute_list:
            #print('not in Node.additional_attribute_list')
            if isinstance(getattr(self.__class__, attr, None), property):
                return getattr(self, attr)
            else:
                raise AssertionError(f"Attribute {attr} not found.")
        _, default, belonging_class, _, _ = Node.additional_attribute_list[attr]
        assert issubclass(self.__class__, belonging_class), f"Attribute {attr} is private to {belonging_class.__name__}"
        # TODO: in the future, missing attributes might be filled by querying a language model.

        if attr not in self.additional_attributes:
            #print('attr not in self.additional_attributes')
            return default
        return self.additional_attributes[attr][-1]

    def set_attribute(self, attr: str, value: Any) -> None:
        if attr not in Node.additional_attribute_list:
            if isinstance(getattr(self.__class__, attr, None), property):
                raise AssertionError(f"Attribute {attr} is read-only.")
            else:
                raise AssertionError(f"Attribute {attr} not found.")
        attribute_type, _, belonging_class, _, is_restorable = Node.additional_attribute_list[attr]
        assert isinstance(
            value, attribute_type) or value is None, f"Attribute {attr} is of type {attribute_type}, got {value} of type {type(value)}." 
        assert issubclass(self.__class__, belonging_class), f"Attribute {attr} is private to {belonging_class.__name__}"
        if is_restorable:
            if attr not in self.additional_attributes:
                self.additional_attributes[attr] = [value]
            else:
                self.additional_attributes[attr].append(value)
        else:
            self.additional_attributes[attr] = [value]

    def restore_initial_state(self) -> None:
        #print("RESTORING INITIAL ATTRIBUTES")
        for attr in self.additional_attributes:
            #print(attr)
            is_restorable = Node.additional_attribute_list[attr][4]
            assert is_restorable or len(self.additional_attributes[attr]) == 1, f"Bug: non restorable attribute {attr} has multiple values."
            self.additional_attributes[attr] = [self.additional_attributes[attr][0]]
    
    def __repr__(self):
        return f"[{self.__class__.__name__}]@({self.id})"
    
    def __str__(self) -> str:
        return f"[{self.__class__.__name__}]@({self.id})"

    def __hash__(self) -> int:
        return hash(self.id)
    
    def __eq__(self, other: Any) -> bool:
        if not isinstance(other, Node):
            return False
        if self.__class__ != other.__class__:
            return False
        if self.id != other.id:
            return False
        return self.serialize(serialization_type='comparison') == other.serialize(serialization_type='comparison')
    
    def _serialize_rec(self, child: Union['Node', List[Any], Tuple[Any], Set[Any], dict[str, Any], int, str, float, bool, None], parent_nodes:List['Node'], serialization_type: SerializationType) -> Any:
        if isinstance(child, Node):
            if serialization_type in ['storage', 'comparison']:
                return repr(child)
            else:
                if child in parent_nodes or serialization_type == 'flat':
                    return child.name
                else:
                    return child._serialize(parent_nodes, serialization_type)
        elif isinstance(child, list) or isinstance(child, tuple) or isinstance(child, set):
            if serialization_type == 'comparison':
                if isinstance(child, list):
                    return [self._serialize_rec(item, parent_nodes, serialization_type) for item in child]
                elif isinstance(child, tuple):
                    return tuple([self._serialize_rec(item, parent_nodes, serialization_type) for item in child])
                else:
                    return set([self._serialize_rec(item, parent_nodes, serialization_type) for item in child])
            elif serialization_type == 'storage':
                return [child.__class__.__name__,[self._serialize_rec(item, parent_nodes, serialization_type) for item in child]]
            else:
                return [self._serialize_rec(item, parent_nodes, serialization_type) for item in child]
        elif isinstance(child, dict):
            return {key: self._serialize_rec(value, parent_nodes, serialization_type) for key, value in child.items()}
        else:
            return deepcopy(child)      

    def _serialize(self, parent_nodes:List['Node'], serialization_type: SerializationType) -> Dict[str, Any]:
        result:Dict[str, Any] = {}
        for attr in Node.additional_attribute_list:
            _, _, belonging_class, is_internal, _ = Node.additional_attribute_list[attr]
            if (not is_internal or serialization_type in ['storage', 'comparison']) and issubclass(self.__class__, belonging_class):
                value = self.get_attribute(attr)
                result[attr] = self._serialize_rec(value, parent_nodes + [self], serialization_type)
        return deepcopy(result) # TODO: deepcopy may not be necessary here, but we need further testing.
    
    @property
    def is_item(self) -> bool:
        return False
    
    @property
    def is_container(self) -> bool:
        return False
    
    @property
    def is_character(self) -> bool:
        return False
    
    @property
    def is_player(self) -> bool:
        return False
    
    @property
    def is_room(self) -> bool:
        return False
    
    @property
    def detail(self) -> str:
        return json.dumps(self.serialize(serialization_type='nested'), indent=4)
    
    def serialize(self, serialization_type: SerializationType = 'storage') -> Dict[str, Any]:
        '''
        This function is used to serialize a node into a dictionary.
        Do not use this method to compare nodes directly. Use the __eq__ method instead.
        '''
        result = self._serialize([], serialization_type)
        if serialization_type == 'storage' or serialization_type == 'comparison':
            result['_type'] = self.__class__.__name__
        return result
    
    def _deserialize_rec(self, child: Union['Node', List[Any], Tuple[Any], Set[Any], dict[str, Any], int, str, float, bool, None], ids_to_nodes:Dict[str, 'Node']) -> Any:
        if isinstance(child, str):
            is_match, match_type, node_id = Node.is_node_repr(child)
            if is_match: # this is a node
                assert match_type is not None
                assert node_id in ids_to_nodes and isinstance(ids_to_nodes[node_id], match_type)
                return ids_to_nodes[node_id]
            else: # this is just a normal string
                return child
        elif isinstance(child, list):
            if len(child) != 2:
                raise ValueError('Only data created by the serialize function with serialization_type="storage" can be deserialized.')
            type_name, child = child
            assert isinstance(type_name, str), f'Expected type_name to be str, got {type_name} of type {type(type_name)}'
            assert isinstance(child, list), f'Expected child to be list, got {child} of type {type(child)}'
            result = [self._deserialize_rec(item, ids_to_nodes) for item in child]
            # cast to the correct type
            if type_name == 'list':
                return result
            elif type_name == 'tuple':
                return tuple(result)
            elif type_name == 'set':
                return set(result)
            else:
                raise ValueError(f'Unknown type name {type_name}.')
        elif isinstance(child, dict):
            return {key: self._deserialize_rec(value, ids_to_nodes) for key, value in child.items()}
        elif isinstance(child, tuple) or isinstance(child, set):
            raise ValueError('Only data created by the serialize function with serialization_type="storage" can be deserialized.')
        else:
            return deepcopy(child)
        
    def deserialize(self, data: Dict[str, Any], ids_to_nodes:Dict[str, 'Node']) -> Self:
        '''
        This function is used to deserialize a node from a serialized representation.
        Only data created by the serialize function with serialization_type="storage" can be deserialized.
        '''
        assert 'id' in data, "Corrupted data. Missing id."
        assert 'name' in data, "Corrupted data. Missing name."
        assert '_type' in data, "Corrupted data. Missing _type."
        assert data['_type'] == self.__class__.__name__, "Wrong class method called for deserialization."
        for attr in data:
            if attr.startswith('_'): # meta attributes
                pass
            elif attr in Node.additional_attribute_list:
                _, _, belonging_class, _, _ = Node.additional_attribute_list[attr]
                if not isinstance(self, belonging_class):
                    print(f"Warning: Attribute {attr} is not registered for class {self.__class__.__name__}")
                    continue
                # set the attribute
                value = data[attr]
                self.set_attribute(attr, self._deserialize_rec(value, ids_to_nodes))
            else:
                # attribute registration is handled in World.deserialize.
                print(f"Warning: Attribute {attr} is not registered for class Node")
        return self

    @staticmethod
    def is_node_repr(s: str) -> Tuple[bool, Union[Type['Node'], None], str]:
        '''
        Check if a string is a node representation.
        Return a tuple (is_match, match_type, node_id).
        '''
        pattern = r'\[(Room|Character|Player|Item|ContainerItem)\]@\((.+)\)'
        match = re.search(pattern, s)
        is_match = match is not None
        match_type = None
        node_id = ''
        if is_match:
            match_type = Node.mapping[match.group(1)]
            node_id = match.group(2)
        return is_match, match_type, node_id


class Item(Node):
    def __init__(self, name: str, description: str = "", id: Union[str, None] = None, keywords: List[str]=[]):
        super().__init__(name, description, id)
        self.keywords = keywords

    @property
    def is_item(self) -> bool:
        return True
    
    def get_children(self) -> Set['Node']:
        return set()
    
    def __contains__(self, child: Union['Node', str]) -> bool:
        return False


class ContainerItem(Item):
    def __init__(self, name: str, description: str = "", id: Union[str, None] = None, capacity: int = 0, is_locked: bool = False, is_open: bool = False):
        super().__init__(name, description, id)
        self.capacity = capacity # 0 means unlimited
        self.is_locked = is_locked
        self.is_open = is_open
        self.items: Set[Item] = set()
    
    @property
    def is_container(self) -> bool:
        return True
    
    def get_children(self) -> Set['Node']:
        return cast(Set['Node'], self.items)
    
    def __contains__(self, child: Union['Node', str]) -> bool:
        if isinstance(child, str):
            return child in [i.id for i in self.items] or child in [i.name for i in self.items]
        else:
            return child in self.items

class Character(Node):    
    def __init__(self, name: str, description: str = "", id: Union[str, None] = None):
        super().__init__(name, description, id)
        self.inventory: Set[Item] = set()

    @property
    def is_character(self) -> bool:
        return True
    
    def get_children(self) -> Set['Node']:
        return cast(Set['Node'], self.inventory)
    
    def __contains__(self, child: Union['Node', str]) -> bool:
        if isinstance(child, str):
            return child in [i.id for i in self.inventory] or child in [i.name for i in self.inventory]
        else:
            return child in self.inventory

class Player(Character):
    def __init__(self, name: str, description: str = "", id: Union[str, None] = None, goal: str = ""):
        super().__init__(name, description, id)
        self.goal = goal

    @property
    def get_super_room(self):
        room: Node = self
        while room.container is not None:
            room = room.container
        assert isinstance(room, Room), "Bug: root node is not a room."
        return room

    
    @property
    def is_player(self) -> bool:
        return True
    
    @property
    def observation(self) -> str:
        room = self.get_room()
        room_name: str = room.name
        room_description: str = room.description
        room_items: Set[Item] = room.items
        room_characters: Set[Character] = room.characters
        player_inventory: Set[Item] = self.inventory
        adjacent_rooms: Dict[Direction,Union[Room,None]] = room.adjacent_rooms

        # summarize all the information into a string.
        observation = f"Room: {room_name}\n"
        observation += f"Description: {room_description}\n"

        if room_items:
            observation += "Items in the room:\n"
            for item in room_items:
                observation += f"  - {item.name}: {item.description}\n"
        else:
            observation += "No items in the room.\n"

        if room_characters - {self}:
            observation += "Characters in the room:\n"
            for character in room_characters:
                if character != self:
                    observation += f"  - {character.name}: {character.description}\n"
        else:
            observation += "No characters in the room.\n"

        if adjacent_rooms:
            observation += "Adjacent rooms:\n"
            for direction, room in adjacent_rooms.items():
                if room:
                    observation += f"  - {direction.capitalize()}: {room.name}\n"
        else:
            observation += "No adjacent rooms.\n"

        if player_inventory:
            observation += "Your inventory:\n"
            for item in player_inventory:
                observation += f"  - {item.name}: {item.description}\n"
        else:
            observation += "Your inventory is empty.\n"

        goal = self.goal
        observation += f"Your goal: {goal}\n"

        return observation
    

class Room(Node):
    def __init__(self, name: str, description: str = "", id: Union[str, None] = None):
        super().__init__(name, description, id)
        self.items: Set[Item] = set()
        self.characters: Set[Character] = set()
        self.adjacent_rooms: Dict[Direction, Union[Room, None]] = {"east": None, "west": None, "north": None, "south": None, "inside": None, "outside": None}

    @property
    def is_room(self) -> bool:
        return True

    def get_children(self) -> Set['Node']:
        return cast(Set['Node'], self.items | self.characters)
    
    def __contains__(self, child: Union['Node', str]) -> bool:
        if isinstance(child, str):
            return child in [i.id for i in self.items] or child in [i.name for i in self.items] or child in [i.id for i in self.characters] or child in [i.name for i in self.characters]
        else:
            return child in self.items or child in self.characters
    
Node.mapping['Item'] = Item
Node.mapping['ContainerItem'] = ContainerItem
Node.mapping['Character'] = Character
Node.mapping['Player'] = Player
Node.mapping['Room'] = Room
Node.reset_additional_attributes() # TODO: In the future, additional_attributes should be moved to World class to support multiple games in one script. Otherwise, the attributes will be shared across games.

if __name__ == '__main__':
    import unittest

    class TestRoom(unittest.TestCase):

        def test_serialization(self):
            room1 = Room("room1", "This is room 1")
            room2 = Room("room2", "This is room 2")
            item1 = Item("item1", "This is item 1")
            container1 = ContainerItem("container1", "This is container 1", capacity=2)
            room1.adjacent_rooms['north'] = room2
            room1.items.add(container1)
            container1.items.add(item1)
            room1_dict = room1.serialize(serialization_type='storage')
            room2_dict = room2.serialize(serialization_type='storage')
            item1_dict = item1.serialize(serialization_type='storage')
            container1_dict = container1.serialize(serialization_type='storage')

            room1_deserialized = Room('', id=room1.id)
            room2_deserialized = Room('', id=room2.id)
            item1_deserialized = Item('', id=item1.id)
            container1_deserialized = ContainerItem('', id=container1.id)
            container1_deserialized_wrong = Item('', id=container1.id)

            ids_to_nodes:Dict[str, Node] = {
                room1.id: room1_deserialized,
                room2.id: room2_deserialized,
                item1.id: item1_deserialized,
                container1.id: container1_deserialized
            }

            room1_deserialized.deserialize(room1_dict, ids_to_nodes)
            room2_deserialized.deserialize(room2_dict, ids_to_nodes)
            item1_deserialized.deserialize(item1_dict, ids_to_nodes)
            container1_deserialized.deserialize(container1_dict, ids_to_nodes)
            for node in [room1_deserialized, room2_deserialized, item1_deserialized, container1_deserialized]:
                self.assertEqual(node.id, ids_to_nodes[node.id].id)
                self.assertEqual(node.name, ids_to_nodes[node.id].name)
                self.assertEqual(node.description, ids_to_nodes[node.id].description)
                self.assertEqual(node.container, ids_to_nodes[node.id].container)
                self.assertEqual(node.additional_attributes.keys(), ids_to_nodes[node.id].additional_attributes.keys())
                for attr in node.additional_attributes:
                    self.assertEqual(node.additional_attributes[attr],ids_to_nodes[node.id].additional_attributes[attr])
            
            self.assertRaises(AssertionError, container1_deserialized_wrong.deserialize, container1_dict, ids_to_nodes)

        def test_attribute_registration(self):
            ContainerItem.register_new_attribute("is_opened", bool, False)
            container1 = ContainerItem("container1", "This is container 1", capacity=2)
            self.assertFalse(container1.get_attribute('is_opened'))
            container1.set_attribute('is_opened', True)
            self.assertTrue(container1.get_attribute('is_opened'))
            item1 = Item("item1", "This is item 1")
            self.assertRaises(AssertionError, item1.get_attribute,'is_opened')
            self.assertRaises(AssertionError, container1.get_attribute,'fsdnkjfnsdjk')
            self.assertRaises(AssertionError, container1.set_attribute,'fsdnkjfnsdjk', 'fsdfd')
            self.assertRaises(AssertionError, container1.set_attribute, 'is_opened', 2)
            Node.reset_additional_attributes()
            self.assertEqual(container1.get_attribute('capacity'), 2)
            self.assertRaises(AssertionError, container1.get_attribute,'is_opened')

    unittest.main()

