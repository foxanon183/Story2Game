from typing import Tuple, Literal
from enum import Enum

# Coordinate type
Coordinate = Tuple[int, int]

# Direction type
Direction = Literal["north", "south", "east", "west", "inside", "outside"]

SerializationType = Literal["flat", "nested", "storage", "comparison"]

NodeType = Literal["Item", "Room", "Character", "Player", "ContainerItem"]

OperatorString = Literal["==", "!=", "<", ">", "<=", ">="]


class GameState(Enum):
    UNFINISHED = 0
    WON = 1
    LOST = 2