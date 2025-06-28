from __future__ import annotations 
from typing import List, Tuple, Union
from operation import GraphOperation
from condition import Condition, AlwaysTrueCondition
from result import ActionResult
from copy import deepcopy
from nodes import Character
from typing import TYPE_CHECKING
from utils import remove_extra_spaces, print_warning

if TYPE_CHECKING:
    from game import Game

class Action:
    def __init__(self, name:str, initiator: str, operations: List[GraphOperation]=[], conditions: Union[Condition,None] = None, description: str = '', input_name: str = '', flags: List[str] = []):
        self.name = remove_extra_spaces(name.lower())  # E.g. eat apple;orange, get book, go to school, give pen to John
        self.initiator = remove_extra_spaces(initiator.lower()) # E.g. player
        self.description = description # TODO: not used for now
        self.conditions : Condition = conditions if conditions else AlwaysTrueCondition()
        self.operations = operations
        self.input_name = input_name
        self.flags = flags

    def __str__(self) -> str:
        return f'Action({self.initiator},{self.name})'
    
    def __eq__(self, __value: object) -> bool:
        if isinstance(__value, Action):
            return self.name == __value.name and self.initiator == __value.initiator
        return False
    
    def is_initiator_valid(self, game: Game) -> Tuple[bool, Union[Character, None], List[str]]:
        if not self.initiator:
            initiator = game.world.player
            if not initiator:
                return False,None, ['Player is not in the world.']
        else:
            try:
                initiator = game.world.find_node(self.initiator)
                #if not isinstance(initiator, Character):
                #    return False, None, [f'{self.initiator} is not a character.']
            except Exception as e:
                return False, None, [str(e)]
        return True, initiator, []
        
    def is_valid(self, game: Game) -> Tuple[bool, List[str]]:
        # TODO: Check action_general_constraints.
        # TODO: Check if the arguments refer to valid nodes in the world.
        is_initiator_valid, _, initiator_message = self.is_initiator_valid(game)
        is_condition_satisfied, condition_messages = self.conditions.evaluate(game)
        #print("ACTION VALIDATOR")
        #print(is_initiator_valid, is_condition_satisfied)
        #print(initiator_message, condition_messages)
        if not is_initiator_valid or not is_condition_satisfied:
            return False, initiator_message + condition_messages
        operation_checking_results = [op.is_valid(game.world) for op in self.operations]
        #print("ACTION VALIDATION OPERATIONS")
        #print(self.operations)
        #print(operation_checking_results)
        operations_valid =  True
        operation_messages : List[str] = []
        for result, additional_info in operation_checking_results:
            #print(operations_valid, result)
            operations_valid = operations_valid and result
            if not result:
                assert isinstance(additional_info, str), "Bug: additional_info is not a string."
                operation_messages.append(additional_info)
        return operations_valid, operation_messages
    
    def execute(self, game: Game) -> ActionResult:
        is_valid, messages = self.is_valid(game)
        if is_valid:
            #print("GETS HERE?")
            initiator = game.world.find_node(self.initiator)
            #assert isinstance(initiator, Character), "Bug: initiator is not a character."
            world_backup = deepcopy(game.world)
            #print("TRY OP")
            #print("CHECKING PRECEDING EVENTS")
            
            #print(self)
            #print(self.flags)
            #print(game.happened_actions)
            for flag in self.flags:
                if flag not in game.happened_actions:
                    observation = 'Preceding events not completed.'
                    #print_warning(observation)
                    #print(game.happened_actions)
                    return ActionResult(self, game.time, False, observation, 0, False, {})
            try:
                for op in self.operations:
                    #print("APPLYING" + str(op))
                    op.apply(game.world)
                    #print("DONE APLYING")
            except Exception as e:
                game.world = world_backup
                observation = f'Runtime Error (Might be a bug): Action "{self.name}" failed. {str(e)}'
                #print_warning(observation)
                return ActionResult(self, game.time, False, observation, 0, False, {})
            # TODO: The action is successful. Now, we need to check if an action triggers an event in the game logic.
            result = ActionResult(self, game.time, True, f'Action "{self.name}" executed by {initiator.name}.', 0, False, {})
            game._update_game_state(result)
            return result # TODO: add reward; custom messages for action execution
        else:
            observations = [f'Action "{self.name}" failed.']
            observations += messages
            observation = '\n'.join(observations)
            #print("FAILED ACTION", observation)
            result = ActionResult(self, game.time, False, observation, 0, False, {})
            return result
            

