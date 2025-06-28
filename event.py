from __future__ import annotations 
from typing import List, Tuple, Union
from condition import Condition
from result import ActionResult, EventResult
from typing import TYPE_CHECKING
from utils import remove_extra_spaces, print_warning
from type import GameState
if TYPE_CHECKING:
    from game import Game

class Event:
    def __init__(self, name:str, triggering_action:str='', conditions: Union[Condition, None]=None, desired_effect:str='', description:str='', reward:int=1, next_state:Union[GameState, None]=None) -> None:
        self.name = name = remove_extra_spaces(name)
        self.triggering_action = remove_extra_spaces(triggering_action)
        self.conditions = conditions
        self.desired_effect = remove_extra_spaces(desired_effect)
        self.description = description
        self.reward = reward
        self.next_state = next_state

    def __str__(self) -> str:
        return self.name

    def __eq__(self, __value: object) -> bool:
        if isinstance(__value, Event):
            return self.name == __value.name
        return False
    
    def __hash__(self) -> int:
        return hash(self.name)
    
    def can_be_triggered(self, game: Game, action_result: ActionResult) -> Tuple[bool, List[str]]:
        # action_history = [action_result.action.name for action_result in game.action_history]
        # if self.triggering_action not in action_history:
        #     return False, [f'Action {self.triggering_action} has not been taken.']
        if self.triggering_action:
            dummy_action = game.get_action(self.triggering_action)
            if dummy_action is None:
                return False, [f'Action {self.triggering_action} has not been defined.']
            if dummy_action != action_result.action:
                return False, [f'The action does not match the triggering action. Expected: {dummy_action.name}; Actual: {action_result.action.name}.']
        conditions = self.conditions
        if conditions is not None:
            is_satisfied, messages = conditions.evaluate(game)
            if is_satisfied:
                return True, []
            else:
                return False, messages
        else:
            return True, []
        
    def trigger(self, game: Game, action_result: ActionResult) -> EventResult:
        '''
        Trigger the event.
        TODO: Currently, the only effect is to add something to the player's inventory, as well as returning an EventResult.
        '''
        player = game.world.player
        assert player is not None, 'Player is not in the world.'
        desired_effects = self.desired_effect.split(';')
        objects_that_must_be_in_player_inventory = [remove_extra_spaces(i[4:]) if i.startswith('has ') else remove_extra_spaces(i) for i in desired_effects]
        objects = [game.world.find_node(i, local=True) for i in objects_that_must_be_in_player_inventory if i]
        for obj in objects:
            if obj not in player.inventory:
                print_warning(f'Event {self.name} is triggered, but the desired object {obj.name} is not in the player\'s inventory yet.')
                game.world.move_node(obj, player)
        
        done = True if self.next_state==GameState.WON or self.next_state==GameState.LOST else False
        return EventResult(self, game.time, self.name, self.reward, done, {}, next_state=self.next_state)
