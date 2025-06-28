from __future__ import annotations 
from typing import Dict, Any, Union, TYPE_CHECKING
from type import GameState

if TYPE_CHECKING:
    from action import Action
    from event import Event

class Result:
    def __init__(self, timestamp:int, observation: str, reward: int, done: bool, info: Dict[str, Any], time_elapsed:int=1, next_state:Union[GameState, None]=None):
        self.timestamp = timestamp
        self.observation = observation
        self.reward = reward
        self.done = done
        self.next_state = next_state
        self.info = info
        self.time_elapsed = time_elapsed
        if done:
            assert next_state is not None and next_state != GameState.UNFINISHED, 'EventResult is done but wrong next_state is provided.'

    def __lt__(self, other:Any):
        if isinstance(other, Result):
            return self.timestamp < other.timestamp
        return NotImplemented

    def __le__(self, other:Any):
        if isinstance(other, Result):
            return self.timestamp <= other.timestamp
        return NotImplemented

    def __eq__(self, other:Any):
        if isinstance(other, self.__class__):
            return self.__dict__ == other.__dict__
        return False
    
    def __ne__(self, other:Any):
        if isinstance(other, self.__class__):
            return self.__dict__ != other.__dict__
        return True

    def __gt__(self, other:Any):
        if isinstance(other, Result):
            return self.timestamp > other.timestamp
        return NotImplemented

    def __ge__(self, other:Any):
        if isinstance(other, Result):
            return self.timestamp >= other.timestamp
        return NotImplemented


class ActionResult(Result):
    """
    The result of an action taken by an agent.

    Attributes:
        action (Action): The action taken by the agent.
        timestamp (int): The timestamp of the action.
        success (bool): Whether the action was successful.
        observation (str): The observation resulting from the action.
        reward (int): The reward resulting from the action.
        done (bool): Whether the game is over as a result of the action.
        info (Dict[str, Any]): Additional information about the action result.
    """

    def __init__(self, action:Action, timestamp:int, success: bool, observation: str, reward: int, done: bool, info: Dict[str, Any], time_elapsed:int=1, next_state:Union[GameState, None]=None):
        self.action = action
        self.timestamp = timestamp
        self.success = success
        self.observation = observation
        self.reward = reward
        self.done = done
        self.next_state = next_state
        self.info = info
        self.time_elapsed = time_elapsed
        if done:
            assert next_state is not None and next_state != GameState.UNFINISHED, 'EventResult is done but wrong next_state is provided.'

class EventResult(Result):
    def __init__(self, event:Event, timestamp:int, observation: str, reward: int, done: bool, info: Dict[str, Any], time_elapsed:int=1, next_state:Union[GameState, None]=None):
        self.event = event
        self.timestamp = timestamp
        self.observation = observation
        self.reward = reward
        self.done = done
        self.next_state = next_state
        self.info = info
        self.time_elapsed = time_elapsed
        if done:
            assert next_state is not None and next_state != GameState.UNFINISHED, 'EventResult is done but wrong next_state is provided.'
