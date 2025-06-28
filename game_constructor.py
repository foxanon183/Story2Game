from llm.chatgpt import ChatGPT

from utils import *

from typing import Dict, List, Union, Tuple

from copy import deepcopy

import json
from nodes import Node, Room, Character, Item, Player

from world import World


import traceback
import re
import copy
import random
from string import Formatter

from game import *
from collections import defaultdict
import nltk
import copy
import re

from game_construct_prompt import *


nltk.download('wordnet')
lemmatizer = nltk.stem.WordNetLemmatizer()
lemmatizer.lemmatize("werewolf")

chatgpt_model = 'gpt-3.5-turbo'

chatgpt = ChatGPT(chatgpt_model) # I sent the API key on Slack. create a file called openai_key.txt in the llm folder and put the key in it.

# MOVE_PATTERN = r'^Move \{[a-z1-9 \(\)]+\} to \{[a-z1-9. \(\)]+\}$'
# ADD_PATTERN = r'^Add \{[a-z1-9 \(\)]+\}$'
# DELETE_PATTERN = r'^Delete \{[a-z1-9 \(\)]+\}$'
# DISPLAY_PATTERN = r'^Display \{[a-z1-9._ \(\)]+\}$'
# SET_ATTRIBUTES_PATTERN = r'^Set \{[a-z1-9._ \(\)]+\} to \{(True|False|AnyValue)\}$'

class GameEngine:
    def __init__(self, map:Dict, game_logics:Dict):
        self.map = map
        self.game_logics = game_logics
        self.world = World(configurations={"map_size":(1,len(self.map))})
        go = ActionTemplate('go to {room1}', 'Move {player} to {room1}; Display You have now entered {room1}; Display {player.observation}')
        self.game = Game(self.world, [go], [])
        self.action_state = defaultdict(lambda : False)
        self.action_template = defaultdict(int)
        self.action_general_constraints = defaultdict(list)
        self.action_game_related_constraints = defaultdict(list)
        self.action_effects = defaultdict(list)
        self.keywords_to_game_logic_action_map = []
        self.obtainable_item_to_game_logic_action_map = defaultdict(list)
        self.locations = [] # list of Room
        self.items = [] # list of Item
        self.npcs = [] # list of Character
        self.locations_ptrs = {} # dict of Room
        self.items_ptrs = {} # dict of Item
        self.npcs_ptrs = {} # dict of Character
        self.num_of_actions = 0
        self.pos_cnt = 0

        # TODO: descriptions for nodes should be provided or generated
        for location in self.map:
            # originally location starts with 'at _____'
            print("add node:",location[3:])
            self.locations.append(Room(location[3:], "You are "+location))
            self.locations_ptrs[location[3:]]=self.locations[-1]
            print('location on map',(0, self.pos_cnt))
            self.world.add_node(self.locations[-1], (0, self.pos_cnt))
            self.pos_cnt += 1     #TODO: this version doesn't care about how rooms are arraged
            for entity in self.map[location]:
                if entity['type']=='npc':
                    npc_name = get_lemma(entity['content'][4:]) # originally npc starts with 'has _____' in the map dict
                    print("add node:",npc_name)
                    self.npcs.append(Character(npc_name,"A "+entity['content'][4:]))
                    self.npcs_ptrs[npc_name]=self.npcs[-1]
                    self.world.add_node(self.npcs[-1],self.locations[-1])
                elif entity['type']=='item':
                    item_name = get_lemma(entity['content'][4:]) # originally item starts with 'has _____' in the map dict
                    print("add node:",item_name)
                    self.items.append(Item(item_name,"A "+entity['content'][4:]))
                    self.items_ptrs[item_name]=self.items[-1]
                    self.world.add_node(self.items[-1],self.locations[-1])

        # TODO: Player goal and description should be provided or generated
        self.player = Player("Player", description="You are the player.", goal="")
        #self.items.append(Item("money","A "+"money"))
        #self.items_ptrs["money"]=self.items[-1]

        self.world.add_node(self.player, self.locations[0])
        self.world.add_node(self.items[-1],self.player)

        print(self.items_ptrs)
        print(self.npcs_ptrs)
        print(self.locations_ptrs)

    def save(self, world_file_name, engine_file_name, indent=4) -> None:
        # save game world
        self.world.save(world_file_name, indent=indent)

        # save game engine
        game_engine_data = {}
        for key in self.__dict__.keys():
            if key in ['world', 'locations', 'items', 'npcs', 'locations_ptrs', 'items_ptrs', 'npcs_ptrs', 'player']:
                continue
            else:
                game_engine_data[key] = copy.deepcopy(getattr(self, key))

        with open(engine_file_name, 'w', encoding = 'utf8') as f:
            f.write(json.dumps(game_engine_data, ensure_ascii=False, indent = indent))

    def load(self, world_file_name, engine_file_name) -> None:
        # load
        self.world = World.load(world_file_name)
        replay_game_engine_data = json.load(open(engine_file_name, 'r', encoding = 'utf8'))
        for key in replay_game_engine_data:
            setattr(self, key, replay_game_engine_data[key])

    def register_action(self, action_template:str) -> bool:
        # gives an action a unique id, returns True if the action is successfully registered
        if self.action_template[action_template]>0:
            return False
        self.num_of_actions += 1
        self.action_template[action_template] = self.num_of_actions
        return True

    def add_game_related_constraint(self, action_template, constraint):
        pass
        #TODO: not very important for now

    def add_action_effect(self, action_template:str, effect:str) -> None:
        assert self.action_template[action_template]>=1 # action_template must be registered and has an id
        if re.match(ADD_PATTERN,effect) or re.match(MOVE_PATTERN,effect) or re.match(DELETE_PATTERN,effect) or re.match(DISPLAY_PATTERN,effect) or re.match(SET_ATTRIBUTES_PATTERN,effect):
            self.action_effects[action_template].append(effect.strip())

    def apply_action(self,action_template:str, parameters, parametric_fields_attributes,replay_game_engine:Union['GameEngine', None]=None) -> None:
        '''
        Execute an action, apply the effects to the game world
        replay_game_engine does not apply the effects, but just checks the conditions and adds the action to the action list.
        TODO: this function needs refactoring. use the Action class. Also remove the replay_game_engine parameter in the future. Modifications to replay_game_engine should be done in (Reference 1) (Search comment "Reference 1")
        '''
        assert self.action_template[action_template]>=1
        move_action = []
        set_action = []
        add_action = []
        display_action = []
        delete_action = []

        self.action_general_constraints[action_template] = copy.deepcopy(parametric_fields_attributes)


        '''
        Preprocessing：parametric_fields_attributes keys are replaced by the corresponding entity names
        '''
        # Example: parameters {'enum(object)': 'book;sign'}
        # Example: parametric_fields_attributes {'enum(object)': {'is_enum_object': 'True', 'is_readable': 'AnyValue', 'message': 'AnyValue'}}
        temp_parametric_fields_attributes = {}
        for param in parameters:
            parameters[param] = parameters[param].split(';')
            #print(parametric_fields_attributes)
            attr_list = parametric_fields_attributes[param]
            for entity in parameters[param]:
                temp_parametric_fields_attributes[entity] = copy.deepcopy(attr_list)
        parametric_fields_attributes = temp_parametric_fields_attributes

        # Example after processing:
        # parameters {'enum(object)': ['book', 'sign']}
        # parametric_fields_attributes {'book': {'is_enum_object': 'True', 'is_readable': 'AnyValue', 'message': 'AnyValue'}, 'sign': {'is_enum_object': 'True', 'is_readable': 'AnyValue', 'message': 'AnyValue'}}

        '''
        Register attributes to the World
        TODO: is_enum_object and is_object should be merged, same for is_enum_npc and is_npc
        '''
        for entity in parametric_fields_attributes:
            if "is_enum_object" in parametric_fields_attributes[entity] or "is_object" in parametric_fields_attributes[entity]:
                for attribute in parametric_fields_attributes[entity]:
                    Item.register_new_attribute(attribute, str, 'AnyValue')
            elif "is_enum_npc" in parametric_fields_attributes[entity] or "is_npc" in parametric_fields_attributes[entity]:
                for attribute in parametric_fields_attributes[entity]:
                    Character.register_new_attribute(attribute, str, 'AnyValue')
            elif "is_enum_room" in parametric_fields_attributes[entity] or "is_room" in parametric_fields_attributes[entity]:
                for attribute in parametric_fields_attributes[entity]:
                    Room.register_new_attribute(attribute, str, 'AnyValue')

        '''
        The following code checks the conditions of the action and raises an exception if the conditions are not met.
        TODO: Use the Condition class.
        '''
        # parameter_alias is a dictionary that maps the names in the parameters to the real names of the entities in the game world. usually should be the same.
        parameter_alias = {}
        #print(parameters)
        #print(parametric_fields_attributes)
        for entity in parameters:
            if 'npc' in entity:
                for t in parameters[entity]:
                    alias = get_alias(self.npcs_ptrs.keys(), t) # alias is the real name of the npc.
                    if edit_distance(alias,get_lemma(t))>0:
                        # This section of the code should be executed sparingly!
                        # We have added npcs in the constructor of the game engine.
                        # The same npc should not be added twice.
                        # It seems that the only case where this section of the code is executed is when something from 'game_logic' is not added.
                        # Any other case, if happens, should be considered a bug (e.g. case issues causing edit distance to be larger than 0).
                        # TODO: Check if we can remove this section of the code, and add npcs and items from 'game_logic' in the constructor of the game engine.
                        alias = get_lemma(t)
                        self.npcs.append(Character(alias,"A "+t))
                        self.npcs_ptrs[alias]=self.npcs[-1]
                        print("add node:",alias)
                        self.world.add_node(self.npcs[-1],self.player.container)
                        if replay_game_engine:
                            replay_game_engine.npcs.append(Character(alias,"A "+t))
                            replay_game_engine.npcs_ptrs[alias]=replay_game_engine.npcs[-1]
                            replay_game_engine.world.add_node(replay_game_engine.npcs[-1],replay_game_engine.world.find_node(replay_game_engine.player.container.name))
                    for attr in parametric_fields_attributes[t]:
                        # check initial attibutes before the action
                        # TODO: this check should be done using the Action class and the Condition class
                        if parametric_fields_attributes[t][attr]!='AnyValue' and self.npcs_ptrs[alias].get_attribute(attr)!='AnyValue' and parametric_fields_attributes[t][attr]!= self.npcs_ptrs[alias].get_attribute(attr):
                            raise Exception("Failed in adding a new action which requires a npc with attributes different from its current value")
                        print("set attribute:",alias,t,attr,parametric_fields_attributes[t][attr])
                        self.npcs_ptrs[alias].set_attribute(attr, parametric_fields_attributes[t][attr])
                        # if replay_game_engine:
                        #     SetNodeAttributeOperation(alias,attr,parametric_fields_attributes[t][attr]).apply(replay_game_engine.world)
                    parameter_alias[t] = alias
            if 'object' in entity:
                for t in parameters[entity]:
                    alias = get_alias(self.items_ptrs.keys(), t)
                    if edit_distance(alias,get_lemma(t))>0:
                        alias = get_lemma(t)
                        self.items.append(Item(alias,"A "+t))
                        self.items_ptrs[alias]=self.items[-1]
                        print("add node:",alias)
                        self.world.add_node(self.items[-1],self.player.container)
                        if replay_game_engine:
                            replay_game_engine.items.append(Item(alias,"A "+t))
                            replay_game_engine.items_ptrs[alias]=replay_game_engine.items[-1]
                            replay_game_engine.world.add_node(replay_game_engine.items[-1],replay_game_engine.world.find_node(replay_game_engine.player.container.name))
                    for attr in parametric_fields_attributes[t]:
                        # initial attibutes before the action
                        if parametric_fields_attributes[t][attr]!='AnyValue' and self.items_ptrs[alias].get_attribute(attr)!='AnyValue' and parametric_fields_attributes[t][attr]!= self.items_ptrs[alias].get_attribute(attr):
                            raise Exception("Failed in adding a new action which requires a item with attributes different from its current value")
                        print("set attribute:",alias,t,attr,parametric_fields_attributes[t][attr])
                        # SetNodeAttributeOperation(alias,attr,parametric_fields_attributes[t][attr]).apply(self.world)
                        # if replay_game_engine:
                        #     SetNodeAttributeOperation(alias,attr,parametric_fields_attributes[t][attr]).apply(replay_game_engine.world)
                        self.items_ptrs[alias].set_attribute(attr, parametric_fields_attributes[t][attr])

                    parameter_alias[t] = alias
            if 'room' in entity:
                for t in parameters[entity]:
                    alias = sorted([i for i in self.locations_ptrs.keys()],key = lambda x:edit_distance(get_lemma(t), x))[0]
                    if edit_distance(alias,get_lemma(t))>0:
                        raise Exception("Location not found error: Try to access a location that doesn't exist")
                    for attr in parametric_fields_attributes[t]:
                        # initial attibutes before the action
                        if parametric_fields_attributes[t][attr]!='AnyValue' and self.locations_ptrs[alias].get_attribute(attr)!='AnyValue' and parametric_fields_attributes[t][attr]!= self.locations_ptrs[alias].get_attribute(attr):
                            raise Exception("Failed in adding a new action which requires a room with attributes different from its current value")
                        print("set attribute:",alias,t,attr,parametric_fields_attributes[t][attr])
                        # SetNodeAttributeOperation(alias,attr,parametric_fields_attributes[t][attr]).apply(self.world)
                        # if replay_game_engine:
                        #     SetNodeAttributeOperation(alias,attr,parametric_fields_attributes[t][attr]).apply(replay_game_engine.world)
                        self.locations_ptrs[alias].set_attribute(attr, parametric_fields_attributes[t][attr])
                    parameter_alias[t] = alias
        print("alias",parameter_alias)

        '''
        The following code is used to apply the action to the game engine.
        TODO: Refactor this code to use the Action class.
        '''
        print("action_template:", action_template, "effect:", "; ".join(self.action_effects[action_template]))
        parameters_ = {k:', '.join([parameter_alias[s] for s in parameters[k]]) for k in parameters}
        action = ActionTemplate(action_template, "; ".join(self.action_effects[action_template]))
        self.game.actions[action.name] = action
        print(f"add event: Adventurer {action_template.format(**parameters_)}. triggering_action={action_template.format(**parameters_)}.")
        event = Event(f"Adventurer {action_template.format(**parameters_)}.", triggering_action=f"{action_template.format(**parameters_)}.", reward=1)
        self.game.events[event.name]=event
        self.game.unhappened_events.add(event)
        self.game.execute_command(f"{action_template.format(**parameters_)}")
        # for effect in self.action_effects[action_template]:
        #     print("Apply:",effect)
        #     if re.match(MOVE_PATTERN,effect):
        #         param = re.findall(r'\{[a-z1-9 \(\)]+\}', effect)
        #         assert len(param)==2
        #         print(param)
        #         param_object, param_to = param[0][1:-1],param[1][1:-1] # Example: ('object1', 'room1')
        #         if param_object not in parameters:
        #             raise Exception("%s not defined. Valid parameters: %s"%(param_object,', '.join([k for k in parameters.keys()])))
        #         if param_to=='inventory':
        #             param_to = 'Player'
        #         elif param_to== "environment":
        #             param_to = self.player.container.name
        #         elif '.inventory' in param[1]:
        #             param_to= param_to.replace('.inventory','')
        #         elif param_to in parameters:
        #             param_to = parameters[param_to]
        #             if isinstance(param_to, list):
        #                 param_to = param_to[0]
        #         for t in parameters[param_object]:
        #             print("Moving",parameter_alias[t],param_to)
        #             can_proceed_flag = False
        #             temp = self.world.find_node(parameter_alias[t]) # we use this to check the container of the entity
        #             while temp:
        #                 if temp==self.player.container:
        #                     can_proceed_flag = True
        #                     break
        #                 else:
        #                     temp = temp.container
        #             if can_proceed_flag==False:
        #                 raise Exception("Execution Error: in %s. You are not allowed to move an entity if the entity is in a different room"%s)

        #             MoveNodeOperation(parameter_alias[t], param_to).apply(self.world)
        #     elif re.match(ADD_PATTERN,effect):
        #         param = re.findall(r'\{[a-z1-9 \(\)]+\}', effect)
        #         assert len(param)==1
        #         param_object = param[0][1:-1]
        #         if param_object not in parameters:
        #             raise Exception("%s not defined. Valid parameters: %s"%(param_object,', '.join([k for k in parameters.keys()])))
        #         for t in parameters[param_object]:
        #             print("Added",parameter_alias[t])
        #             AddNodeOperation(parameter_alias[t], 'item', self.player.container.name, "A "+t).apply(self.world)
        #     elif re.match(DELETE_PATTERN,effect):
        #         param = re.findall(r'\{[a-z1-9 \(\)]+\}', effect)
        #         assert len(param)==1
        #         param_object = param[0][1:-1]
        #         if param_object not in parameters:
        #             raise Exception("%s not defined. Valid parameters: %s"%(param_object,', '.join([k for k in parameters.keys()])))
        #         for t in parameters[param_object]:
        #             print("Deleted",parameter_alias[t])
        #             DeleteNodeOperation(parameter_alias[t]).apply(self.world)
        #     elif re.match(SET_ATTRIBUTES_PATTERN ,effect):
        #         param = re.findall(r'\{[a-zA-Z1-9._ \(\)]+\}', effect)
        #         assert len(param)==2
        #         attribute, value = param[0][1:-1], param[1][1:-1]
        #         assert '.' in attribute
        #         assert value in ['True','False','AnyValue']
        #         param_object = attribute.split('.')[0]
        #         attribute_name = attribute.split('.')[1]
        #         if param_object not in parameters:
        #             raise Exception("%s not defined. Valid parameters: %s"%(param_object,', '.join([k for k in parameters.keys()])))
        #         for t in parameters[param_object]:
        #             print("Set Attribute",parameter_alias[t],attribute_name, value)
        #             SetNodeAttributeOperation(parameter_alias[t], attribute_name, value).apply(self.world)
        #     elif re.match(DISPLAY_PATTERN ,effect):
        #         param = re.findall(r'\{[a-zA-Z1-9._ \(\)]+\}', effect)
        #         assert len(param)==1
        #         attribute = param[0][1:-1]
        #         param_object = attribute.split('.')[0]
        #         if param_object not in parameters and param_object not in ['inventory','environment']:
        #             raise Exception("%s not defined. Valid parameters: %s"%(param_object,', '.join([k for k in parameters.keys()]+['inventory','environment'])))
        #         print("Displaying Message--- Detial:",effect)
        #         DisplayMessageOperation(f"{effect}")
        #     else:
        #         if "Display " in effect:
        #             raise Exception("Unexpected effect format for Display: \"%s\". Expect one of %s"%(effect,', '.join(['Display {'+k+'.message}' for k in parameters.keys()]+['Display {inventory}','Display {environment}'])))
        #         elif "Add " in effect:
        #             raise Exception("Unexpected effect format for Add: \"%s\". Expected format is Add {XXX}"%(effect))
        #         elif "Delete " in effect:
        #             raise Exception("Unexpected effect format for Delete: \"%s\". Expected format is Delete {XXX}"%(effect))
        #         elif "Move " in effect:
        #             raise Exception("Unexpected effect format for Move: \"%s\". Expected format is Move {XXX} to {XXX}")
        #         elif "Set " in effect:
        #             raise Exception("Unexpected effect format for Set: \"%s\". Expected format is Set {XXX.some_attribute} to {True/False}")
        #         else:
        #             raise Exception("%s is not an allowed action"%(effect))

    # TODO: This function may not be needed. Refactor using the Condition class
    # TODO: Preconditions are checked in two places. location, item needed, and attribute needed are checked here. field attribute values are checked in apply_action. Should be unified.

    def check_if_disired_effects_were_applied(self,action):
        # TODO: return false if not met. Do not raise exception
        for disired_effect in self.game_logics[action]['results']:
            if disired_effect[:4]=='has ':
                if self.game.world.find_node(get_lemma(disired_effect[4:])).container.name != 'Player':
                    raise Exception("Wrong effect error: %s should move object %s to inventory  %s"%(action,disired_effect[4:], self.game.world.find_node(get_lemma(disired_effect[4:])).container.name))
            else:
                # TODO: check if other effects are applied
                pass
        return True



# def fix_grammar(sentence) -> str:
#     return chatgpt_call(fix_grammar_prompt.replace('{$text1$}',sentence)).split('\n')[0].split('.')[0].split('(')[0]

# def extract_entities(sentence) -> str:
#     '''
#     Input: The adventurer kill a dragon at dragon's canyon.
#     Output: [The adventurer] kill [a dragon] at [dragon's canyon]
#     '''
#     return chatgpt_call(extract_entities_prompt.replace('{$text1$}',sentence)).split('\n')[0].split('.')[0].split('(')[0]

# def fix_grammar_and_annotate_entities(sentence, all_objects, all_rooms, all_npcs) -> Tuple[str, str]:
#     '''
#     Input: adventurer kill a dragon at dragon's canyon.
#     Output: [npc: the adventurer] killed [npc: a dragon] at [room: dragon's canyon]
#     TODO: Concatenating characters not efficient.
#     '''
#     sentence_fixed_grammar = fix_grammar(sentence)
#     annotated_sentence = extract_entities(sentence_fixed_grammar) # example: [The adventurer] killed [a dragon] at [dragon's canyon].

#     start_of_entity = -1
#     annotated_sentence_enhanced = ""
#     for i in range(len(annotated_sentence)):
#         if annotated_sentence[i]=='[':
#             start_of_entity=i+1
#         elif annotated_sentence[i]==']':
#             prefix = ""
#             entity = annotated_sentence[start_of_entity:i].strip().lower() # example: the adventurer

#             # remove a, the, A, The
#             for to_replace  in ['a ','the ','A ','The ']:
#                 if entity[:len(to_replace)]==to_replace:
#                     entity = entity[len(to_replace):]
#             if entity in all_objects:
#                 prefix = 'object: '
#             elif entity in all_rooms:
#                 prefix = 'room: '
#             elif entity in all_npcs:
#                 prefix = 'npc: '
#             annotated_sentence_enhanced = annotated_sentence_enhanced+'['+prefix+entity+']'
#             start_of_entity = -1
#         elif start_of_entity==-1:
#             annotated_sentence_enhanced = annotated_sentence_enhanced+annotated_sentence[i]


#     print("original sentence:",sentence)
#     print("fixed grammar:",sentence_fixed_grammar)
#     print("annotate_sentence:",annotated_sentence_enhanced)
#     return sentence_fixed_grammar, annotated_sentence_enhanced

# def expand_sentence_with_with(sentence, objects) -> str:
#     '''
#     Example
#     Sentence: adventurer craft sword.
#     Objects: iron, wood, anvil
#     Output: adventurer craft sword with iron, wood
#     '''
#     if objects==[]:
#         return sentence
#     else:
#         result= chatgpt_call(expand_sentence_with_with_prompt.replace('{$text1$}',sentence).replace('{$text2$}',', '.join(objects))).split('\n')[0].split('.')[0].split('(')[0].lower()
#         print(result)
#         if result.strip() not in ["no","No"] and 'adventurer' in result: # TODO: Player may not be adventurer
#             return result
#         else:
#             return sentence
        
# def identify_action_template_given_the_sentence(sentence) -> str:
#     '''
#     Input: crafted [object: shield] with [object: iron], [object: nail] and [object: wood].
#     Output: crafted {object1} with {enum(object)}
#     '''
#     prompt = action_template_extraction_prompt.replace("{$text2$}",' '.join(sentence.split(' ')[1:]))
#     return chatgpt_call(prompt).split('\n')[0]

# def get_npc_that_fits_the_profile(sentence,attributes) -> str:
#     '''
#     Sentence: adventurer buy armor at market place.
#     attributes: is_npc=True, is_vendor==True, is_alive==True
#     Output: armor vendor
#     '''
#     prompt = get_npc_that_fits_the_profile_prompt.replace('{$text1$}',sentence).replace('{$text2$}',', '.join([k+'='+attributes[k] for k in attributes]))
#     infered_npc = chatgpt_call(prompt).split('\n\n')[0]
#     #print(infered_npc)
#     # TODO: infered_npc may be empty, or there may be multiple NPCs
#     return infered_npc

# def parse_enum_objects_npcs(sentence_fragment,type="object") -> List[str]:
#     '''
#     Sentence fragment: wood, nail and steel.
#     Output: ['wood', 'nail', 'steel']
#     '''
#     if type=="object":
#         prompt = find_enum_object_prompt.replace('{$text1$}',sentence_fragment)
#     else:
#         prompt = find_enum_npc_prompt.replace('{$text1$}',sentence_fragment)
#     result = chatgpt_call(prompt).split('\n')[0].split('(')[0].replace(' and ',', ').split(',')
#     result = [s.strip() for s in result if s.strip()!='']
#     return result

# def parsing_parameters(sentence, template) -> Dict[str,str]:
#     '''
#     Find parameter of action.
#     sentence = adventurer craft sword with iron, wood and anvil.
#     template = adventurer craft {object1} with {enum(object)}.
#     Output: {'object1':'sword', 'enum(object)':'iron;wood;anvil'}
#     '''
#     fieldnames_in_template = [name for _, name, _, _ in Formatter().parse(template) if name]
#     print(fieldnames_in_template)
#     p = str(template)
#     for fieldname in fieldnames_in_template:
#         p = p.replace('{'+fieldname+'}','(.*)')
#     print("matching pattern:",sentence,p)
#     p = re.compile(p)
#     result = p.search(sentence)
#     # The following result type check should be implemented for good code style. However, since the null pointer exception in result.group is checked when adding action, having this code would break the game. 
#     # if result is None:
#     #     raise ValueError(f"Cannot parse \"{sentence}\" with \"{template}\"")
#     parameters = {}
#     for i,fieldname in enumerate(fieldnames_in_template):
#         if fieldname=='enum(npc)':
#             parameters[fieldname] = ';'.join(parse_enum_objects_npcs(result.group(i+1),type='npc'))
#         elif fieldname=='enum(object)':
#             parameters[fieldname] = ';'.join(parse_enum_objects_npcs(result.group(i+1),type='object'))
#         elif fieldname[:5]=='enum(':
#             raise ValueError('enum object can only be enum(object) or enum(npc).')
#         else:
#             parameters[fieldname] = result.group(i+1).replace('.','')
#     print("parameters",parameters)
#     return parameters

# def get_action_template_and_rules(sentence,previous_attept_info = "") -> Tuple[str,str,str]:
#     '''
#     TODO: Check doc
#     Input: adventure drink [object: the magic water] with [object: a bottle]
#     Output: action_template, action_rule, attempt_info
#     action_template = 'drink {object1} with {object2}'
#     action_rule = 'attributes check: {object1.is_drinkable==True}; {object2.is_container==True} effect: Delete {object1}; Display {object1.message}'
#     attempt_info = 
#     '//action template for "drink with"
#     drink {object1} with {object2}:
#     attributes check: {object1.is_drinkable==True}; {object2.is_container==True}
#     effect: Delete {object1}; Display {object1.message}'
#     '''
#     # TODO: Player may not be adventurer. Also, this is too hacky.
#     for keyword in ['The adventurer','the adventurer','A adventurer', 'a adventurer', 'Adventurer', 'An adventurer', 'an adventurer']:
#         if keyword in sentence:
#             sentence = sentence.replace(keyword,'adventurer')
#     sucess = False
#     template = identify_action_template_given_the_sentence(sentence) # Example: crafted {object1} with {enum(object)}
#     print(template)
#     state = 0
#     preprocessed = ""
#     for i in range(len(template)):
#         if template[i]=='{':
#             state = 1
#         elif template[i]=='}':
#             state = 0
#         else:
#             if state==0:
#                 preprocessed = preprocessed+template[i]
#     preprocessed = ' '.join([i for i in preprocessed.split(' ') if i!='']) # Example: crafted with
#     prompt = action_generation_prompt.replace("{$text1$}",preprocessed).replace("{$text2$}",template).replace("{$text3$}",'\n//'+sentence).replace("{$text4$}",previous_attept_info)
#     if previous_attept_info!="":
#         print(prompt)
#     action_rule = chatgpt_call(prompt).split('\n\n')[0]
#     print(action_rule)
#     return template,action_rule,prompt.split('\n\n')[-1]+action_rule

def try_adding_action(game_engine:GameEngine, original_sentence, sentence,sentence_expanded,room,template,rule,replay_game_engine=None) -> GameEngine:
    '''
    Try applying the action to the game engine.
    Return the new game engine if the action is successful, otherwise an exception is raised. 
    The original game engine is not modified.
    replay_game_engine should not to be modified, but when there are nodes in game_logic that are not added, they will be added to replay_game_engine.
    TODO: If check_if_disired_effects_were_applied is refactored, this function must be refactored as well.
    TODO: remove dependency on replay_game_engine. Modifications on replay_game_engine should be completely done at (Reference 1) (search comment "Reference 1").
    '''
    parameters = parsing_parameters(sentence, template) #find all parameters in the sentence  # Example: {'object1':'sword', 'enum(object)':'iron;wood;anvil'}
    # for each parameter in action, find their attributes
    parametric_fields_attributes = {} # The requirements for an action. Example: {'object1':{'is_object':'True','is_weapon':'True'}}
    for key in parameters:
        p = re.compile("\{%s\.([a-z,A-Z,_]+)"%key.replace('(','\(').replace(')','\)'))
        result = p.findall(rule)
        parametric_fields_attributes[key] = {}
        if key[:6]=='object':
            parametric_fields_attributes[key]['is_object']='True'
        elif key[:3]=='npc':
            parametric_fields_attributes[key]['is_npc']='True'
        elif key[:4]=='room':
            parametric_fields_attributes[key]['is_room']='True'
        elif key=='enum(npc)':
            parametric_fields_attributes[key]['is_enum_npc']='True'
        elif key=='enum(object)':
            parametric_fields_attributes[key]['is_enum_object']='True'
        for attr in result:
            p = re.compile("\{%s\.%s==[a-z,A-Z]+"%(key,attr))
            initial_state_of_attributes = list(set(p.findall(rule.split('\n')[0])))
            if len(initial_state_of_attributes)==0:
                parametric_fields_attributes[key][attr]='AnyValue'
            elif len(initial_state_of_attributes)==1:
                parametric_fields_attributes[key][attr]=initial_state_of_attributes[0].split('=')[-1]
            else:
                raise ValueError('parametric_fields_attributes cannot be True and False at the same time.')
    print("parametric_fields_attributes",parametric_fields_attributes)

    # non parametric fields. Some objects/npcs may be hidden/implicitly defined, 
    # this makes generation too slow, so removed from the this version
    '''
    non_parametric_fields = list(set([name for _, name, _, _ in Formatter().parse(rule) if name and '.' not in name and name not in fieldnames_in_template]))
    print(non_parametric_fields)
    non_parametric_fields_attributes = {}
    for field in non_parametric_fields:
        p = re.compile("\{%s\.([a-z,A-Z,_]+)"%field)
        result = p.findall(rule)
        non_parametric_fields_attributes[field] = {}
        if field[:6]=='object':
            non_parametric_fields_attributes[field]['is_object']='True'
        elif field[:3]=='npc':
            non_parametric_fields_attributes[field]['is_npc']='True'
        elif field[:4]=='room':
            non_parametric_fields_attributes[field]['is_room']='True'
        for attr in result:
            p = re.compile("\{%s\.%s==[a-z,A-Z]+"%(field,attr))
            initial_state_of_attributes = list(set(p.findall(rule.split('\n')[0])))
            if len(initial_state_of_attributes)==0:
                non_parametric_fields_attributes[field][attr]='AnyValue'
            elif len(initial_state_of_attributes)==1:
                non_parametric_fields_attributes[field][attr]=initial_state_of_attributes[0].split('=')[-1]
            else:
                raise ValueError('non_parametric_fields_attributes cannot be True and False at the same time.')
        if 'is_npc' in non_parametric_fields_attributes[field] and non_parametric_fields_attributes[field]['is_npc']=='True':
            non_parametric_fields_attributes[get_npc_that_fits_the_profile(sentence_expanded,non_parametric_fields_attributes[field])]=copy.deepcopy(non_parametric_fields_attributes[field])
            del non_parametric_fields_attributes[field]


    print("non_parametric_fields_attributes",non_parametric_fields_attributes)
    '''
    
    # parse the effects
    effects = [effect.strip() for effect in rule.split('\n')[-1][len('effect: '):].split(';')]
    print("effects:",effects)

    #input example for game_engine
    #template = 'gathered {enum(object)} for {object1} with {object2}'
    #parameters = {'enum(object)': 'ingredients', 'object1': 'a cure', 'object2': 'a basket'}
    #parametric_fields_attributes = {'enum(object)': {'is_enum_object': 'True'}, 'object1': {'is_object': 'True', 'is_cure': 'True', 'is_complete': 'AnyValue'}, 'object2': {'is_object': 'True', 'is_container': 'True'}}
    #effects = ['Move {enum(object)} to {object2}', 'Set {object1.is_complete} to {True}']

    game_engine_copy = copy.deepcopy(game_engine)     
    assert game_engine_copy.world.player is not None
    #since we omit the walk to action in the walk through
    # omit location requirement
    # TODO: SHOULD BE REMOVED IN THE FUTURE
    if game_engine_copy.world.find_node(game_engine_copy.game_logics[original_sentence]['location'][0][3:]) != game_engine_copy.world.player.container: 
        MoveNodeOperation(game_engine_copy.world, 'Player', game_engine_copy.game_logics[original_sentence]['location'][0][3:]).apply() # TODO: player may not be called player
    
    game_engine_copy.check_if_precondtions_have_been_met(original_sentence)
    if game_engine_copy.register_action(template)==True:
        print("register new action")
        for effect in effects:
            game_engine_copy.add_action_effect(template,effect)
    else:
        print("use existing action")
    game_engine_copy.apply_action(template, parameters, parametric_fields_attributes,replay_game_engine)
    game_engine_copy.check_if_disired_effects_were_applied(original_sentence)
    return game_engine_copy


if __name__ == '__main__':
        
    game =  {'game_logics': {'adventurer speak with the village elders.': {'item needed': [], 'location': ['at village hall'], 'preceeding_events': [], 'description': [], 'results': []}, 'adventurer read books.': {'item needed': [], 'location': ['at library'], 'preceeding_events': [], 'description': ['There is a book at the library.'], 'results': ['has book']}, 'adventurer find maps.': {'item needed': ['has books'], 'location': ['at library'], 'preceeding_events': [], 'description': ['There is a map at the library.'], 'results': ['has map']}, 'adventurer take torch.': {'item needed': ['has money'], 'location': ['at general store'], 'preceeding_events': [], 'description': ['There is a torch for sale at the general'], 'results': ['has torch']}, 'adventurer find the werewolf den.': {'item needed': ['has maps', 'has torch'], 'location': ['at forest'], 'preceeding_events': ['adventurer speak with the village elders.'], 'description': [], 'results': []}, 'adventurer take basket.': {'item needed': [], 'location': ['at forest'], 'preceeding_events': [], 'description': ['There is a basket in the forest.'], 'results': ['has basket']}, 'adventurer gather ingredients for a cure.': {'item needed': ['has basket'], 'location': ['at forest'], 'preceeding_events': ['adventurer find the werewolf den.'], 'description': [], 'results': []}, 'adventure meet with a wise woman in the forest': {'item needed': [], 'location': ['at forest'], 'preceeding_events': ['adventurer gather ingredients for a cure.'], 'description': [], 'results': []}, 'adventurer purchase flashlight.': {'item needed': ['has money'], 'location': ['at store'], 'preceeding_events': [], 'description': ['There is a flashlight for sale at the store'], 'results': ['has flashlight']}, 'adventurer investigate the abandoned mansion': {'item needed': ['has flashlight'], 'location': ['at abandoned mansion'], 'preceeding_events': ['adventure meet with a wise woman in the forest'], 'description': [], 'results': []}, 'adventurer purchase lockpicking tool.': {'item needed': ['has money'], 'location': ['at general store'], 'preceeding_events': [], 'description': ['There is a lockpicking tool for sale at'], 'results': ['has lockpicking tool']}, 'adventurer steal key.': {'item needed': ['has lockpicking tool'], 'location': ['at thieves den'], 'preceeding_events': [], 'description': ['There is a key at thieves den.'], 'results': ['has key']}, 'adventurer take sword.': {'item needed': ['has key'], 'location': ['at weapon depot'], 'preceeding_events': [], 'description': ['There is a sword at a weapon depot.'], 'results': ['has sword']}, 'adventure confront the werewolf pack leader': {'item needed': ['has sword'], 'location': ['at werewolf den'], 'preceeding_events': ['adventurer investigate the abandoned mansion'], 'description': [], 'results': []}, 'adventurer loot weapons.': {'item needed': [], 'location': ['at dungeon'], 'preceeding_events': [], 'description': ['There is a loot of weapons at the d'], 'results': ['has weapons']}, 'adventurer find armor.': {'item needed': ['has money'], 'location': ['at armor shop'], 'preceeding_events': [], 'description': ['There is armor for sale at an armor'], 'results': ['has armor']}, 'adventure escort villagers to safety': {'item needed': ['has weapons', 'has armor'], 'location': ['at village'], 'preceeding_events': ['adventure confront the werewolf pack leader'], 'description': [], 'results': []}, 'adventure destroy the cursed artifact': {'item needed': [], 'location': ['at abandoned mansion'], 'preceeding_events': ['adventure escort villagers to safety'], 'description': [], 'results': []}, 'adventurer stop the curse from spreading to other villages': {'item needed': [], 'location': ['at forest'], 'preceeding_events': ['adventure destroy the cursed artifact'], 'description': [], 'results': []}}, 'map': {'at village hall': [{'type': 'npc', 'content': 'has village elders'}], 'at forest': [{'type': 'npc', 'content': 'has werewolf'}, {'type': 'npc', 'content': 'has farmers'}, {'type': 'npc', 'content': 'has herbalist'}, {'type': 'npc', 'content': 'has witch'}, {'type': 'item', 'content': 'has basket'}, {'type': 'npc', 'content': 'has wise woman'}], 'at general store': [{'type': 'item', 'content': 'has torch'}, {'type': 'item', 'content': 'has lockpicking tool'}, {'type': 'npc', 'content': 'has merchant'}], 'at library': [{'type': 'item', 'content': 'has maps'}, {'type': 'item', 'content': 'has books'}], 'at abandoned mansion': [], 'at store': [{'type': 'item', 'content': 'has flashlight'}, {'type': 'npc', 'content': 'has merchant'}], 'at werewolf den': [{'type': 'npc', 'content': 'has werewolf pack leader'}], 'at weapon depot': [{'type': 'item', 'content': 'has sword'}], 'at thieves den': [{'type': 'item', 'content': 'has key'}], 'at village': [{'type': 'npc', 'content': 'has villagers'}], 'at armor shop': [{'type': 'item', 'content': 'has armor'}], 'at dungeon': [{'type': 'item', 'content': 'has weapons'}]}}

    action_mapping = {key:expand_sentence_with_with(key,game['game_logics'][key]['item needed']) for key in game['game_logics']}

    '''
    The following code reads game logics, map, and generates the story. It also looks for all objects and rooms in the game.
    '''
    game_logics = game['game_logics']
    # the following code changes the actions game_logics to the expanded version. 
    # e.g. adventure confront the werewolf pack leader is changed to adventure confront the werewolf pack leader with sword
    # game['game_logics']['preceeding_events'] is also updated to reflect the changes.
    # Other fields in game['game_logics'] are not changed in this process. Maybe the code should be refactored to make it clearer?
    game_logics = {action_mapping[key]:{k:[t if t not in action_mapping else action_mapping[t] for t in game_logics[key][k]] for k in game_logics[key]} for key in game['game_logics']}
    map = game['map']
    print(game_logics)

    story  = [key for key in game_logics] # every key is an action, which reflects the progress of the story. TODO: Are we sure the story is ordered?
    story_expanded = [key.replace('.','')+' '+game_logics[key]['location'][0]+'.' for key in story] # Add location info. Example: ['adventure confront the werewolf pack leader with sword at werewolf den.']
    rooms = ['at '+s.split(' at ')[-1].replace('.','') for s in story_expanded] # Extract room info. Example: ['werewolf den']

    #initialize game engine
    #action_template = 'gathered {enum(object)} for {object1} with {object2}'
    #parameters = {'enum(object)': 'ingredients', 'object1': 'a cure', 'object2': 'a basket'}
    #parametric_fields_attributes = {'enum(object)': {'is_enum_object': 'True'}, 'object1': {'is_object': 'True', 'is_cure': 'True', 'is_complete': 'AnyValue'}, 'object2': {'is_object': 'True', 'is_container': 'True'}}
    #effects = ['Move {enum(object)} to {object2}', 'Set {object1.is_complete} to {True}']
    game['game_logics']=game_logics
    #initialize game environment 
    #
    game_engine = GameEngine(map, game_logics) # The game engine the computer will interact with and evaluate on during game generation. The actions are executed, so we can know is the game is actually playable or not.
    replay_game_engine = GameEngine(map, game_logics) # The game engine that the player will interact with. It is a copy of game_engine, and has all the information about the admissible actions. but the actions are not executed.
    #
    ###################################################################################################################################

    # for index in range(3):
    for index in range(len(story)):
        print("################## %i of %i action in the story ####################\n"%(index,len(story)))
        # sentence already has the "with" clause. sentence_expanded also has the location info.
        # Example: sentence: adventure confront the werewolf pack leader with sword.
        # Example: sentence_expanded: adventure confront the werewolf pack leader with sword at werewolf den.
        sentence,sentence_expanded,room = story[index], story_expanded[index], rooms[index]
        print("sentence:",sentence)
        print("sentence_expanded:",sentence_expanded)
        print("room:",room)
        sucess = False
        cnt = 0

        #move money to adventurer's inventory since planner assumes several precondition to be true to end the recursion
        # TODO: We may remove this in the future.
        #try:
        #    game_engine.world.find_node("money")
        #except Exception:
        #    game_engine.items.append(Item("money","A "+"money"))
        #    game_engine.items_ptrs["money"]=game_engine.items[-1]
        #    game_engine.world.add_node(game_engine.items[-1],game_engine.player)
        #if game_engine.world.find_node("money").container!=game_engine.player:
        #    raise Exception("money is not in player's inventory")
        #    # MoveNodeOperation(game_engine.world, 'money', 'Player').apply()


        # add the action to the game, and check if the action is actually runnable
        previous_attempt_info = ""
        try:
            print("attempt %i"%cnt,sentence_expanded)
            sentence_fixed_grammar, annotated_sentence = fix_grammar_and_annotate_entities(sentence if sentence[-1]=='.' else sentence+'.', all_objects=all_objects, all_rooms = all_rooms, all_npcs=all_npcs)
            template,action_rule,attempt_info = get_action_template_and_rules(annotated_sentence,previous_attempt_info)
            previous_attempt_info = previous_attempt_info+'\n\n//The following is a wrong example that fail to execute. You should avoid generating the same content in your next trial. Refers to the error message below for more detail\n'+attempt_info
            print("debug #############\n",attempt_info,'#################')
            # interact with game engine and check if the action is actually runnable
            replay_game_engine_copy = copy.deepcopy(replay_game_engine)
            game_engine = try_adding_action(game_engine, sentence, sentence_fixed_grammar,sentence_expanded,room,template,action_rule,replay_game_engine_copy)
            sucess = True   
        except Exception as e:
            sucess = False
            if "'NoneType' object has no attribute 'group'" in str(e): # TODO: Handle exceptions locally.
                previous_attempt_info = '\n\n'.join(previous_attempt_info.split('\n\n')[:-1]) #  TODO: Just remove the last attempt info? Is it a good idea.
            else:
                previous_attempt_info = previous_attempt_info+'\n\nError: '+str(e) 
            print(e,traceback.format_exc())
        print(sucess)
        while not sucess:
            if cnt>7:
                raise ValueError('Adding action: max number of attempt exeeded.')
            if cnt%2==0 and cnt!=0:
                previous_attempt_info = ""
            print("###############\nattemp %i failed, try adding action again!"%cnt)

            # TODO: The following code is the same as above, should be refactored.
            try:
                cnt+=1
                print("attempt %i"%cnt,sentence_expanded)
                sentence_fixed_grammar, annotated_sentence = fix_grammar_and_annotate_entities(sentence if sentence[-1]=='.' else sentence+'.', all_objects=all_objects, all_rooms = all_rooms, all_npcs=all_npcs)
                
                template,action_rule,attempt_info = get_action_template_and_rules(annotated_sentence,previous_attempt_info+('\n\nYour last attempt failed to execute. Revise it based on the error message....' if previous_attempt_info!="" else ""))
                print("debug #############\n",attempt_info,'#################')
                previous_attempt_info = previous_attempt_info+'\n\n//The following is a wrong example that fail to execute. You should avoid generating the same content in your next trial. Refers to the error message below for more detail\n'+attempt_info
                
                # interact with game engine and check if the action is actually runnable
                replay_game_engine_copy = copy.deepcopy(replay_game_engine)
                game_engine = try_adding_action(game_engine, sentence ,sentence_fixed_grammar,sentence_expanded,room,template,action_rule,replay_game_engine_copy)
                sucess = True
            except Exception as e:
                sucess = False
                print(e,'\n',traceback.format_exc())
                if "'NoneType' object has no attribute 'group'" in str(e):
                    previous_attempt_info = '\n\n'.join(previous_attempt_info.split('\n\n')[:-1])
                else:
                    previous_attempt_info = previous_attempt_info+'\n\nError: '+str(e)
        
        # We have successfully added the action to the game engine. We have also ensured that the desired effect is achieved in try_adding_action.
        # replay_game_engine is the game engine that has all the information of the actions, but the actions are not actually executed. 
        # a real player will play the game with replay_game_engine.
        # Now that the system has successfully added the action to the game engine and replay_game_engine_copy, 
        # we are sure that replay_game_engine_copy is runnable. 
        # Now Copy the current state of replay_game_engine_copy to replay_game_engine.
        replay_game_engine = copy.deepcopy(replay_game_engine_copy) 
        # succeed mark objective as done.
        # This field is used when checking action preconditions.
        game_engine.action_state[sentence]=True
        # find primary parameter in the sentence. e.g. find a cave with torch and map -- primary parameter is cave template is find {object}
        if 'with' not in sentence:
            primary_parameter = parsing_parameters(sentence_fixed_grammar.split(' with ')[0].strip(),template.split(' with ')[0].strip()) # TODO: What about phrases like "play with the dog"?
        else:
            primary_parameter = parsing_parameters(sentence_fixed_grammar.strip(),template.strip())
        # get parameter alias. Eg: a name in parameter to a name that is actually used in the game. Usually the two are the same.
        primary_parameter = [get_alias(list(game_engine.items_ptrs)+list(game_engine.npcs_ptrs)+list(game_engine.locations_ptrs), primary_parameter[k]) for k in primary_parameter]
        #print({"sentence_fixed_grammar":sentence_fixed_grammar,"primary_parameter":primary_parameter,'template':template,'keywords':copy.deepcopy(primary_parameter), \
        #                                                 'target_action_in_game_logic': sentence})
        # store keywords, action pairs
        game_engine.keywords_to_game_logic_action_map.append({'template':template,'keywords':primary_parameter, \
                                                        'target_action_in_game_logic': sentence})
        for disired_effect in game_engine.game_logics[sentence]['results']:
            if disired_effect[:4]=='has ':
                game_engine.obtainable_item_to_game_logic_action_map[get_alias(game_engine.items_ptrs.keys(),disired_effect[4:])].append(sentence)

    # finishing construct replay game engine from game engine (Reference 1)
    game_engine.action_template = sorted(list(game_engine.action_template), key=lambda x: 0 if ' with ' in x else 1)
    replay_game_engine.action_template = copy.deepcopy(game_engine.action_template)
    replay_game_engine.action_effects = copy.deepcopy(game_engine.action_effects)
    replay_game_engine.action_general_constraints = copy.deepcopy(game_engine.action_general_constraints)
    replay_game_engine.keywords_to_game_logic_action_map = copy.deepcopy(game_engine.keywords_to_game_logic_action_map)
    replay_game_engine.obtainable_item_to_game_logic_action_map = copy.deepcopy(game_engine.obtainable_item_to_game_logic_action_map)