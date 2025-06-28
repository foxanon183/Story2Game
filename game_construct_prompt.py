
from utils import read_prompt, format_prompt, log
from llm.llm import LLM
from typing import List, Tuple, Union, Dict, Iterable
import json
from logic_template import ActionTemplate
from functools import cache
from condition import ComplexCondition, ConditionField, Condition
from operation import GraphOperation, GraphOperationFactory
from nodes import Node
from type import NodeType
from typing import Type, Any
from action import Action
from game import Game
from utils import *

ACTION_GENERATION_PROMPT = read_prompt("prompts/action_generation_prompt/story_generation.txt")
ACTION_GENERATION_PROMPT_FAILED = read_prompt("prompts/action_generation_prompt/failed_v1.txt")
ACTION_GENERATION_PROMPT_FAILED_EXAMPLE = read_prompt("prompts/action_generation_prompt/failed_example_v1.txt")
NEW_ACTION_GENERATION_PROMPT = read_prompt('prompts/action_generation_prompt/new_action.txt')
CHECK_EXISTING_ACTION_PROMPT = read_prompt('prompts/novel_action_prompt/check_existing_action.txt')
CHECK_FUTURE_EVENTS_ACTION_PROMPT = read_prompt('prompts/novel_action_prompt/check_future_actions.txt')
MEASURE_COHERENCE_ACTION_PROMPT = read_prompt('prompts/novel_action_prompt/measure_coherence_action.txt')
# DESCRIBE_ENVIRONMENT_PROMPT = read_prompt("prompts/describe_environment_prompt/v1.txt")
EXPAND_SENTENCE_PROMPT = read_prompt("prompts/expand_sentence_prompt/v1.txt")
FIX_GRAMMAR_PROMPT = read_prompt("prompts/fix_grammar_prompt/v1.txt")
GET_NPC_PROMPT = read_prompt("prompts/get_npc_prompt/v1.txt")

FIX_PRECONDITION_PROMPT = read_prompt("prompts/fix_precondition_prompt/v2.txt")
FIX_PRECONDITION_PROMPT_FAILED = read_prompt("prompts/fix_precondition_prompt/failed_v2.txt")
FIX_PRECONDITION_PROMPT_FAILED_EXAMPLE = read_prompt("prompts/fix_precondition_prompt/failed_example_v2.txt")

QUERY_ATTRIBUTE_PROMPT = read_prompt("prompts/query_attribute_prompt/v1.txt")
VERB_ATTRIBUTE_PROMPT = read_prompt("prompts/query_attribute_prompt/verb.txt")

def _get_action_template_prompt(input:str, previous_attempts: Iterable[Tuple[str, str]]=[]) -> str:
    """
    Generate action generation prompt.

    Args:
        input (str): The input sentence, e.g. "adventurer crafts sword with iron, wood".
        previous_attempts (List[Tuple[str, str]], optional): A list of tuples of the form (llm_raw_output, error_message_from_game_engine). Defaults to [].

    Returns:
        str: Action generation prompt.
    """
    if previous_attempts:
        previous_attempts_formatted_list: List[str] = []
        for output, error in previous_attempts:
            previous_attempts_formatted_list.append(format_prompt(ACTION_GENERATION_PROMPT_FAILED_EXAMPLE, input=input, output=output, error=error))
        previous_attempts_formatted = '\n\n'.join(previous_attempts_formatted_list)
        previous_attempts_prompt = format_prompt(ACTION_GENERATION_PROMPT_FAILED, failed_examples=previous_attempts_formatted)
        #print("RIGHT PROMPT")
        return format_prompt(ACTION_GENERATION_PROMPT, input=input, previous_attempts=previous_attempts_prompt)
    else:
        return format_prompt(ACTION_GENERATION_PROMPT, input=input)
    
def _get_fix_precondition_prompt(preconditions: str, individual_field_info: Dict[str, Tuple[bool, str]], previous_attempts: Iterable[Tuple[str, str]]=[]) -> str:
    current_game_state_formatted = '\n'.join([f'{i}: {"satisfied" if individual_field_info[i][0] else "not satisfied"}.' for i in individual_field_info]) if individual_field_info else 'None'
    info = [individual_field_info[i][1] for i in individual_field_info if not individual_field_info[i][0]]
    info_formatted = '\n'.join(info) if info else 'None.'
    if previous_attempts:
        previous_attempts_formatted_list: List[str] = []
        for output, error in previous_attempts:
            previous_attempts_formatted_list.append(format_prompt(FIX_PRECONDITION_PROMPT_FAILED_EXAMPLE, preconditions=preconditions, current_game_state=current_game_state_formatted, info=info_formatted, output=output, error=error))
        previous_attempts_formatted = '\n\n'.join(previous_attempts_formatted_list)
        previous_attempts_prompt = format_prompt(FIX_PRECONDITION_PROMPT_FAILED, failed_examples=previous_attempts_formatted)
        return format_prompt(FIX_PRECONDITION_PROMPT, preconditions=preconditions, current_game_state=current_game_state_formatted, info=info_formatted, previous_attempts=previous_attempts_prompt)
    else:
        return format_prompt(FIX_PRECONDITION_PROMPT, preconditions=preconditions, current_game_state=current_game_state_formatted, info=info_formatted)
    
def fix_precondition(llm: LLM, preconditions: str, individual_field_info: Dict[str, Tuple[bool, str]], previous_attempts: Iterable[Tuple[str, str]]=[]) -> Tuple[str, str, List[GraphOperation]]:
    prompt = _get_fix_precondition_prompt(preconditions, individual_field_info, previous_attempts=previous_attempts)
    llm_raw_output = llm.get_response(prompt).strip()
    llm_raw_outputs = llm_raw_output.split('\n')
    reasoning, fixes_string = llm_raw_outputs[0], llm_raw_outputs[1]
    #print("FIX PRECONDITION LLM PROMPT AND OUTPUT", preconditions, individual_field_info, reasoning, "\n", fixes_string)
    #print("FIXING PRECONDITION")
    #print(llm_raw_output)
    #print("split")
    #print(llm_raw_outputs)
    #print(preconditions)
    #print(reasoning)
    #print(fixes_string)
    assert reasoning.startswith('Reasoning:'), f'LLM output is not in the correct format: {llm_raw_output}'
    reasoning = reasoning[len('Reasoning:'):].strip()
    assert fixes_string.startswith('Answer:'), f'LLM output is not in the correct format: {llm_raw_output}'
    fixes_string = fixes_string[len('Answer:'):].strip()
    fixes_parsed = json.loads(fixes_string)
    #print("THIS FUNCTION")
    fixes = GraphOperationFactory.create_operations(';'.join(fixes_parsed))
    return llm_raw_output,  reasoning, fixes

def check_future_events(llm: LLM, action: Action, new_attribute: str):
    input = action.name + "; " + action.conditions.get_canonical_form() + "; " + new_attribute
    #print(input)
    prompt = format_prompt(CHECK_FUTURE_EVENTS_ACTION_PROMPT, input=input)
    llm_raw_output = llm.get_response(prompt).strip()
    #print(llm_raw_output)
    output = json.loads(llm_raw_output)['output']
    is_necessary, new_attribute = output['isNecessary'], output['new_action_precondition']
    return is_necessary, new_attribute

def get_verbs(llm: LLM, base_form: str) -> Tuple[str]:
    verbs = format_prompt(VERB_ATTRIBUTE_PROMPT, base_form)
    return verbs

def populate_attribute(llm:LLM, node:Node) -> Tuple[str, Dict[str, Any]]:
    node_name = node.name
    node_type = node.__class__.__name__
    node_serialized = node.serialize(serialization_type='flat')
    unpopulated_attributes_to_type = {key: Node.additional_attribute_list[key][0] for key, value in node_serialized.items() if value is None}
    if not unpopulated_attributes_to_type:
        return '', {}
    candidate_attributes_formatted = '\n'.join([f'{key}: {value.__name__}' for key, value in unpopulated_attributes_to_type.items()])
    prompt = format_prompt(QUERY_ATTRIBUTE_PROMPT, name=node_name, type=node_type, candidate_attributes=candidate_attributes_formatted)
    llm_raw_output = llm.get_response(prompt).strip()
    output_parsed : Dict[str, Any] = json.loads(llm_raw_output)
    return llm_raw_output, output_parsed

def fix_grammar(llm: LLM, input:str) -> str:
    """
    Fix grammar mistakes in the input sentence.

    Args:
        llm (LLM): The language model.
        input (str): The input sentence, e.g. "adventurer kill a dragon at dragon's canyon".

    Returns:
        str: The fixed sentence.
    """
    prompt = format_prompt(FIX_GRAMMAR_PROMPT, input=input)
    return llm.get_response(prompt).strip()

def expand_sentence(llm: LLM, sentence:str, objects:List[str]) -> Tuple[str, List[str]]:
    """
    Expand sentence with "with" and objects.

    Args:
        llm (LLM): The language model.
        sentence (str): The input sentence, e.g. "adventurer crafts sword".
        objects (List[str]): A list of objects, e.g. ["iron", "wood"].

    Returns:
        Tuple[str, List[str]]: The expanded sentence and the objects that are used to expand the sentence.
    """
    prompt = format_prompt(EXPAND_SENTENCE_PROMPT, sentence=sentence, objects=', '.join(objects))
    raw = llm.get_response(prompt) # {"sentence": "The bandit attacks the king with knife.", "relevant_objects": ["knife"]}
    # Assume the LLM would not violate the format of the output.
    dic = json.loads(raw)
    return dic["sentence"], dic["relevant_objects"]

def get_npc(llm: LLM, sentence:str, constraints:str) -> str:
    """
    Get npc that fits the profile.

    Args:
        llm (LLM): The language model.
        sentence (str): The input sentence, e.g. "adventurer drink holy water at church.".
        constraints (str): The constraints, e.g. "is_npc=True, is_alive==True".

    Returns:
        str: The npc that fits the profile.
    """
    prompt = format_prompt(GET_NPC_PROMPT, sentence=sentence, constraints=constraints)
    return llm.get_response(prompt).strip()

def analyze_action(game: Game, llm: LLM, input:str, previous_attempts: List[Tuple[str, str]]=[]) -> Tuple[str, str, Dict[str, Union[str, List[str]]],  List[Tuple[str, NodeType, type]], ActionTemplate]:
    """
    Generate action generation prompt.

    Args:
        llm (LLM): The language model.
        input (str): The input sentence, e.g. "adventurer crafts sword with iron, wood".
        previous_attempts (List[Tuple[str, str]], optional): A list of tuples of the form (llm_raw_output, error_message_from_game_engine). Defaults to [].

    Returns:
        Tuple[str, str, Dict[str, Union[str, List[str]]],  List[Tuple[str, NodeType, type]], ActionTemplate]: A tuple of the form (llm_raw_output, base, {"placeholder1":"node_name", "placeholder2":["node_names"]}, [(attribute_name, belonging_class, attribute_type)], action_template).
    """
    #print("call _analyze")
    return _analyze_action(game, llm, input, tuple(previous_attempts)) 

def parse_output(game: Game, llm_raw_output: str):
    json_loaded = json.loads(llm_raw_output)
    if 'output' in json_loaded.keys():
        # If output is in the llm output, assume the format is {"input": "", "output": {"player": "", ...}}
        output = json_loaded['output']
    else:
        # Otherwise, assume the format is {"player": "", ...}
        output = json_loaded
    annotated = output['annotated_form']
    annotated = annotated.replace("[", "")
    annotated = annotated.replace("]", "")
    base = output['base_form'].strip()
    base = base.replace("[", "")
    base = base.replace("]", "")
    args = {}
    for i in range(len(output['rooms'])):
        args["rooms" + str(i)] = output['rooms'][i]
    for i in range(len(output['characters'])):
        args["characters" + str(i)] = output['characters'][i]
    for i in range(len(output['items'])):
        args["items" + str(i)] = output['items'][i]
    preconditions = ""
    for i in range(len(output['fundamental_preconditions'])):
        preconditions += output['fundamental_preconditions'][i].replace("[", "").replace("]", "")
        if i < len(output['fundamental_preconditions']) - 1:
            preconditions += " and "
    if len(output['fundamental_preconditions']) > 0 and len(output['additional_preconditions']) > 0:
        preconditions += " and "
    for i in range(len(output['additional_preconditions'])):
        preconditions += output['additional_preconditions'][i].replace("[", "").replace("]", "")
        if i < len(output['additional_preconditions']) - 1:
            preconditions += " and "
    
    effects = ""
    for i in range(len(output['effects'])):
        if "Display" in output['effects'][i]:
            pass
        else:
            effects += output['effects'][i]
    effects += "; "
    if "display" in output:
        effects += "Display " + output['display']
    effects = effects.replace("[", "")
    effects = effects.replace("]", "")


    #output_list.append(output)
    #items = output["items"]
    #attributes = output["attributes"]
    #preconditions = output["preconditions"]
    #complete_sentences = output["complete_sentence"]
    #for precondition in preconditions:
    #    prompt = format_prompt(NEW_ACTION_GENERATION_PROMPT, input=precondition + " Note: Do not include any preconditions this time.")
    #    llm_raw_output = llm.get_response(prompt).strip()
    #    output = json.loads(llm_raw_output)['output']
    #    output_list.append(output)

    llm_raw_output = ("Annotated Form: " + annotated + "\nBase Form: " + base + "\nArguments: " + str(args) + "\nPreconditions: " + preconditions + "\nEffects: " + effects)
    argument_type_preconditions: List[str] = []
    for placeholder in args:
        if 'item' in placeholder:
            argument_type_preconditions.append(f'{{{placeholder}.is_item==True}}')
        elif 'container' in placeholder:
            argument_type_preconditions.append(f'{{{placeholder}.is_container==True}}')
        elif 'room' in placeholder:
            argument_type_preconditions.append(f'{{{placeholder}.is_room==True}}')
        elif 'character' in placeholder:
            argument_type_preconditions.append(f'{{{placeholder}.is_character==True}}')
        elif 'player' in placeholder:
            argument_type_preconditions.append(f'{{{placeholder}.is_player==True}}')
    #print("GETTING ATTRIBUTES")
    #print(preconditions, argument_type_preconditions)
    preconditions = ComplexCondition.add_precondition_to_expression(preconditions, argument_type_preconditions)
    attributes = ComplexCondition.get_required_node_attributes(game, preconditions)
    #print(attributes, preconditions)
    #print("CURRENT RAW:", llm_raw_output)
    #print("CURRENT BASE:", base)
    #print("CURRENT ANNOTATED:", annotated)
    #print("CURRENT ARGS:", args)
    #print("CURRENT ATTRIBUTES:", attributes)
    #print("CURRENT EFFECTS:", effects)
    #print("CURRENT PRECONDITIONS:", preconditions)
    type_action = replace_placeholders(base, args)
    return llm_raw_output, base, args, attributes, effects, ActionTemplate(name=base, operations=effects, precondition=preconditions)

def generate_new_preconditions(game: Game, llm: LLM, input:str, previous_attempts: Iterable[Tuple[str, str]]=[]) -> Tuple[str, str, Dict[str, Union[str, List[str]]], List[Tuple[str, NodeType, type]], ActionTemplate]:
    """
    Generate new preconditions for novel actions.

    Args:
        input (str): The input sentence, e.g. "adventurer crafts sword with iron, wood".
        previous_attempts (List[Tuple[str, str]], optional): A list of tuples of the form (llm_raw_output, error_message_from_game_engine). Defaults to [].

    Returns:
        str: Action generation prompt.
    """

    #print("NEW ACTION")
    prompt = format_prompt(NEW_ACTION_GENERATION_PROMPT, input=input)
    llm_raw_output = llm.get_response(prompt).strip()
    output = json.loads(llm_raw_output)['output']
    subject = output['subject']
    preceding_events = []
    for i in range(len(output['preceding_events'])):
        preceding_events.append(output['preceding_events'][i])

    attribute_effects = []
    for i in range(len(output['attribute_effects'])):
        attribute_effects.append(output['attribute_effects'][i])
    add_attributes= ComplexCondition.add_precondition_to_expression("", attribute_effects)
    add_attributes = ComplexCondition.get_required_node_attributes(game, add_attributes)
    #print("PROMPT")
    #print(prompt)
    #print("llm_raw_output")
    #print(llm_raw_output)
    llm_raw_output, base, args, attributes, effects, action_template = parse_output(game, llm_raw_output)
    #print("EXTENDING ADDITIONAL ATTRIBUTES")
    #print(attributes, add_attributes)
    attributes.extend(add_attributes)
    return llm_raw_output, base, args, attributes, add_attributes, subject, preceding_events, effects, action_template

def check_if_existing_action(llm: LLM, user_input: str, valid_actions: List[str]) -> str:
    #print("CHECKING IF EXISTING")
    #print(user_input + "; " + str(valid_actions))
    prompt = format_prompt(CHECK_EXISTING_ACTION_PROMPT, input=user_input + "; " + str(valid_actions))
    llm_raw_output = llm.get_response(prompt).strip()
    #print(prompt)
    #print("RAW OUTPUT")
    #print(llm_raw_output)
    output = json.loads(llm_raw_output)['output']

    isMatch, output = output['isMatch'], output['output_str']
    print(isMatch, output)
    return isMatch, output

#@cache
def _analyze_action(game: Game, llm: LLM, input:str, previous_attempts: Tuple[Tuple[str, str], ...]=()) -> Tuple[str, str, Dict[str, Union[str, List[str]]], List[Tuple[str, NodeType, type]], ActionTemplate]:
    #print("ANALYZE_ACTION")
    prompt = _get_action_template_prompt(input, previous_attempts)
    #print(prompt)
    llm_raw_output = llm.get_response(prompt).strip()
    # llm_raw_outputs = llm_raw_output.split('\n')
    #print("ANALYZE ACTION RAW LLM PROMPT AND OUTPUT", prompt, "\n", llm_raw_output)
    llm_raw_output, base, args, attributes, effects, action_template = parse_output(game, llm_raw_output)
    return llm_raw_output, base, args, attributes, action_template

def measure_coherence(llm: LLM, input_action: str, generated_data: str):
    prompt = format_prompt(MEASURE_COHERENCE_ACTION_PROMPT, user_input = input_action, generated_data = generated_data)
    llm_measurement_output = llm.get_response(prompt).strip()
    #print("MEASURING COHERENCE W/ LLM")
    #print(prompt)
    #print(llm_measurement_output)
    output = json.loads(str(llm_measurement_output))['output']
    #print("OUTPUT")
    #print(output)
    return output

if __name__ == '__main__':
    from world import World
    from nodes import Room, Item, Player
    from game import Game

    # Uncomment different sections
    
    # Test fix condition
    # # read = ActionTemplate('read {enum(item)}', 'Display You read {enum(item)}', precondition='{enum(item).is_book==True}')
    # # world = World()
    # # room1 = Room('room 1')
    # # book = Item('book')
    # # player = Player('player')
    # # world.add_node(room1, (0,0))
    # # world.add_node(player, room1)
    # # world.add_node(book, room1)
    # # game = Game(world, [read], [])
    # # action = read.build_action(game, arguments={'enum(item)':'book'})
    # # Item.register_new_attribute('is_book', bool, None)
    # # book.set_attribute('is_book', False)
    # # from llm.chatgpt import ChatGPT
    # # llm = ChatGPT()
    # # _, reasoning, fixes = fix_precondition(llm, action.conditions.get_canonical_form(), action.conditions.get_individual_field_info(game))
    # # print(reasoning)
    # # for fix in fixes:
    # #     print(fix)

    # Test populate attributes
    from llm.chatgpt import ChatGPT
    llm = ChatGPT()
    
    plastic_bag = Item('Plastic bag')

    Item.register_new_attribute('is_empty', bool)
    Item.register_new_attribute('battery_level', int)

    llm_raw_output, output_parsed = populate_attribute(llm, plastic_bag)
    log('main', llm_raw_output)
    print(output_parsed)

    # Test analyze action
    # # from llm.chatgpt import ChatGPT
    # # llm = ChatGPT()
    # # action = analyze_action(llm, "adventurer escorts princess to castle")
    # # print(action)
    # # action = analyze_action(llm, "adventurer escorts princess to castle")
    # # print(action)
    # # action = analyze_action(llm, "adventurer throws stone at dragon")
    # # print(action)
    # # action = analyze_action(llm, "adventurer escorts princess to castle")
    # # print(action)
    # # expanded = expand_sentence(ChatGPT(), "adventurer find treasure", ["torch", "sword", "shield", "armor", "potion", "gold", "map", "magnifier"])
    # # print(expanded)