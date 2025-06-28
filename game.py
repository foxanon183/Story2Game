from __future__ import annotations 

from utils import *
from typing import Dict, List, Union, Any, Set, Iterable
from type import GameState
from nodes import Character

from world import World

import pickle

from action import Action
from logic_template import ActionTemplate, EventTemplate
from event import Event
from result import ActionResult, EventResult, Result

class Game:
    def __init__(self, world: World, action_templates:Iterable[ActionTemplate], events: Iterable[Event|EventTemplate]) -> None:
        self.world = world # the world that the game is played in
        self.time = 0
        self.action_templates = {action_template.name: action_template for action_template in action_templates} # all the actions templates that can be matched
        self.actions = {} # all the playable actions that can be taken in the game
        self.action_history: List[ActionResult] = [] # all the actions that agents have taken (currently only the player), including both successful and failed actions.
        self.successful_action_history: List[ActionResult] = [] # all the actions that agents have taken (currently only the player), including only successful actions.
        events = [event.build_event() if isinstance(event, EventTemplate) else event for event in events]
        self.events = {event.name: event for event in events} # events that can happen in the game, corresponding to game_logic.
        self.unhappened_events: Set[Event] = set(self.events.values()) # events that have not happened yet
        self.happened_events: Set[Event] = set() # events that have happened
        self.happened_actions: Set[Action] = set() # actions that have happened
        self.event_history: List[EventResult] = []
        self.history: List[Result] = [] # all the results that have happened in the game, including actions and events.
        self.game_state = GameState.UNFINISHED # the state of the game
        self.total_reward = 0 # the total reward that the player has accumulated
        self.observations: List[str] = [] # observations that the player has seen
        self.info: Dict[str, Any] = {} # additional information about the game
        self.commands: List[str] = [] # The list of Ideal commands to take

    def add_action_template(self, action: ActionTemplate) -> None:
        '''
        Add an action to the game.
        '''
        self.action_templates[action.name] = action

    def remove_action(self, action: ActionTemplate) -> None:
        return_val = "Key not found"
        to_pop = ""
        for i in self.action_templates.keys():
            if i == action.name:
                return_val = self.action_templates.pop(i, "Key not found")
                to_pop = action.name
                break

        return_val = self.action_templates.pop(to_pop, "Key not found")
        return return_val

    def add_event(self, event: Union[Event, EventTemplate]) -> None:
        '''
        Add an event to the game.
        '''
        if isinstance(event, EventTemplate):
            event = event.build_event()
        self.events[event.name] = event
        self.unhappened_events.add(event)

    def has_event_happened(self, event: Union[str, Event]) -> bool:
        # TODO: The checking may be more rigorous.
        if isinstance(event, Event):
            event_name = event.name
        else:
            event_name = remove_extra_spaces(event.lower())
        if event_name not in self.events:
            raise ValueError(f'Event {event_name} is not defined.')
        event_history = [event_result.event.name for event_result in self.event_history]
        return event_name in event_history

    
    def has_action_happened(self, action: str, initiator:str='') -> bool:
        action = remove_extra_spaces(action.lower()) # 'give book to adventurer'
        initiator = remove_extra_spaces(initiator.lower()) # 'player'
        # Validate if the initiator is valid.
        if not initiator:
            player = self.world.player
            if not player:
                raise ValueError('Player is not in the world.')
            initiator_node = player
        else:
            try:
                initiator_node = self.world.find_node(initiator)
                #assert isinstance(initiator_node, Character), f'{initiator} is not a character.'
            except Exception as e:
                raise ValueError(str(e))
        # Validate if the action is valid.
        action_instance = self.get_action(action)
        if not action_instance:
            return False
        # Validate if the action has happened.
        successful_action_history = [action_result.action for action_result in self.successful_action_history]
        return action_instance in successful_action_history

    def is_finished(self) -> bool:
        '''
        Check if the game is finished.
        '''
        return self.game_state != GameState.UNFINISHED
    
    def _update_game_state(self, result: Result) -> None:
        '''
        Update the game history.
        '''
        #print("UPDATE GAME HISTORY")
        #print(self.happened_actions)
        if isinstance(result, EventResult):
            self.event_history.append(result)
            self.unhappened_events.remove(result.event)
            self.happened_events.add(result.event)
        elif isinstance(result, ActionResult):
            self.action_history.append(result)
            if result.success:
                self.happened_actions.add(result.action.input_name)
                self.successful_action_history.append(result)
        else:
            raise NotImplementedError(f'Cannot update game history for result {result}.')
        self.history.append(result)
        self.total_reward += result.reward
        self.observations.append(result.observation)
        self.info = result.info
        if len(self.unhappened_events) == 0 and len(self.events) > 0:
            self.game_state = GameState.WON # All events have happened. The story is finished.
        elif result.done:
            if result.next_state:
                self.game_state = result.next_state
        self.time += result.time_elapsed
    
    def _trigger_possible_events_from_action(self, action_result:ActionResult) -> None:
        '''
        Trigger possible events from an action.
        '''
        if not action_result.success:
            return
        unhappened_events = list(self.unhappened_events)
        for event in unhappened_events:
            can_be_triggered, _ = event.can_be_triggered(self, action_result)
            if can_be_triggered:
                event_result = event.trigger(self, action_result)
                self._update_game_state(event_result)
                print_warning(event_result.observation)
                print('-'*50)

    def get_action(self, command:str) -> Union[Action, None]:
        '''
        Get an action from a command.
        '''
        assert self.world.player, 'Player is not in the world.'
        #print("GETTING ACTION")
        #print("SELF.ACTION_TEMPLATES", self.action_templates)
        for action_name in self.action_templates:
            action_template = self.action_templates[action_name]
            # THE ACTION TEMPLATE IS INCORRECT LEADING .match METHOD TO FAIL and include room0 instead of forest and includes the item at forest instead of the actual item
            #print(action_name)
            #print("ACTION TEMPLATE AND COMMAND")
            #print(action_template)
            #print("COMMANDSTART")
            #print(command)
            #print("COMMANDEND")
            is_match, arguments = action_template.match(command)
            #print("IS MATCH AND ARGUMENTS", is_match, arguments)
            if is_match:
                action = action_template.build_action(self, arguments=arguments)
                command = re.sub(r"[\[\](){}]", "", command)
                self.actions[command] = action
                return action
        return None

    def execute_command(self, command:str) -> bool:
        '''
        Execute a command by first parsing it into an action and then executing the action.
        '''
        assert self.world.player, 'Player is not in the world.'
        general_commands = ['look', 'inventory', 'go']
        action = None
        if command in self.actions:
            action = self.actions[command]
        if not action:
            action = self.get_action(command)
        #print("EXECUTING USER COMMAND")
        if not action:
            print_warning(f'Cannot parse command {command}. Do you want to create a new action? Enter Yes if so.')
            affirm = input('Enter a command: ')
            if affirm == "Yes":
                return True
            print('-'*50)
            return False
        else:
            #print(action)
            #print(action.name, action.description, action.conditions, action.operations, action.flags)
            action_result = action.execute(self)
            self.happened_events.add(command)
            self._update_game_state(action_result)
            #print_warning(action_result.observation)
            print('-'*50)
            self._trigger_possible_events_from_action(action_result)
            return False
    
    # TODO: Serialize and deserialize the game.
    def save_game(game: Game, filename: str) -> None:
        """
        Saves the game object to a file using pickle.

        Args:
            game (Game): The game object to save.
            filename (str): The path to the file where the game should be saved.
        """
        with open("./games/" + filename, 'wb') as f:
            pickle.dump(game, f)

    def load_game(filename: str) -> Game:
        """
        Loads a game object from a file.

        Args:
            filename (str): The path to the file from which to load the game.

        Returns:
            Game: The loaded game object.
        """
        with open("./games/" + filename, 'rb') as f:
            return pickle.load(f)
    
if __name__ == "__main__":
    from nodes import Room, Item, Player
    import unittest

    class TestGame(unittest.TestCase):

        def setUp(self) -> None:
            super().setUp()
            go = ActionTemplate('go to {room1}', 'Move {player} to {room1}')
            get = ActionTemplate('get {item1}', 'Move {item1} to {inventory}')
            detonate = ActionTemplate('detoNate {item1}', 'Delete {item1}', precondition='{item1.is_explosive==True}')
            defuse = ActionTemplate('defuse {item1}', 'Delete {item1}', precondition='{item1.is_explosive==True} and {has bomb defusal tool}')
            world = World()
            Item.register_new_attribute('is_explosive', bool, False)
            library = Room('School Library')
            cafe = Room('School Cafeteria')
            lab = Room('Chemistry Lab')
            bomb_defusal_tool = Item('Bomb Defusal Tool')
            bomb = Item('Bomb')
            bomb.set_attribute('is_explosive', True)
            student = Player('Student', goal='safely defuse the bomb')
            world.add_node(library, (0, 0))
            world.add_node(cafe, (0, 1))
            world.add_node(lab, (0,2))
            world.add_node(student, library)
            world.add_node(bomb_defusal_tool, cafe)
            world.add_node(bomb, lab)
            grab_tool = EventTemplate('Student obtains the bomb defusal tool.', triggering_action='get bomb defusal tool', reward=10)
            arrive_at_lab = EventTemplate('Student arrives at the chemistry lab.', precondition='{ at     chemisTry lab }', reward=10)
            detonate_bomb = EventTemplate('The bomb explodes. The student is dead.', triggering_action='detonate bomb', next_state='lost', reward=-100)
            defuse_bomb = EventTemplate('The student defuses the bomb.', triggering_action='defuse bomb', next_state='won', reward=100)
            self.simple_game = Game(world, [go, get, detonate, defuse], [grab_tool, arrive_at_lab, detonate_bomb, defuse_bomb])

        def test_simple_game_win(self):
            quest = ['go to school cafeteria', 'get bomb defusal tool', 'go to chemistry lab', 'defuse bomb']
            for command in quest:
                self.simple_game.execute_command(command)

            result = self.simple_game.game_state
            self.assertEqual(result, GameState.WON)
            self.assertEqual(self.simple_game.total_reward, 120)
        
        def test_simple_game_lose(self):
            quest = ['go to school cafeteria', 'go to chemistry lab', 'detonate bomb']
            for command in quest:
                self.simple_game.execute_command(command)
            result = self.simple_game.game_state
            self.assertEqual(result, GameState.LOST)
            self.assertEqual(self.simple_game.total_reward, -90)

    unittest.main()