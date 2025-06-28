from type import GameState
import difflib
from game_construct_prompt import expand_sentence, analyze_action, populate_attribute, get_verbs
from game import Game
from world import World
from nodes import Node, Item, Room, Character, Player, ContainerItem
from logic_template import ActionTemplate, EventTemplate
from condition import ComplexCondition
from type import Coordinate
from typing import *
import time

from collections import defaultdict, deque
from llm.chatgpt import ChatGPT

class IdealGameAgent:
    def __init__(self, game, game_logics, game_name):
        """Initializes the agent with the game instance and game logics.

        Args:
            game (Game): The game instance.
            game_logics (dict): The game logics containing ordered ideal actions.
        """
        self.game = game
        self.game_logics = game_logics
        self.game_name = game_name

        commands = []
        for command in self.game.commands:
            commands.append(command.replace("{", "").replace("}", "").replace(".", ""))

        self.ideal_actions = list(dict.fromkeys(commands))  # Ordered list of ideal actions
        
        self.llm = ChatGPT(model='gpt-4o-mini')

        self.custom_map = self.parse_game_map()
        
    def match_with_llm(self, action):

        location = self.llm.get_response(f"""Given an action, return the location of an action. Do NOT say anything else. Only respond with the location of the action
                                        Example
                                        Action: speak with the village elders at village hall
                                        Answer: village hall
                                         
                                        Action: {action}
                                        Answer: """)
        
        print("LLM RESPONSE", action, location)

        return action, location
    
    def parse_game_map(self):
        custom_map = {}
        for room in self.game.world.map[0]:
            if room:
                custom_map[room.name] = {}
                for direction, adj_room in room.adjacent_rooms.items():
                    if adj_room != None:
                        #print(direction, adj_room.name)
                        custom_map[room.name][direction] = adj_room.name
                #print()
        # print(custom_map)
        return custom_map
    
    def find_path_bfs(self, start, end):
        queue = deque([(start, [start])])
        
        while queue:
            current_room, path = queue.popleft()
            
            if current_room == end:
                return path
            
            for direction, next_room in self.custom_map.get(current_room, {}).items():
                if next_room not in path:
                    queue.append((next_room, path + [next_room]))
        
        return None

    def play(self):
        """Plays through the game by executing each ideal action mapped to a generalized action."""

        action_list = {}
        for action in self.ideal_actions:
            # print("Callling match with ", action)
            temp_action, location = self.match_with_llm(action)
            action_list[temp_action] = location

        # print("ACTION LIST", action_list)

        timestamp = time.strftime("%Y%m%d-%H%M%S")
        filename = f"./traces/log_{self.game_name}_{timestamp}.txt"

        log = open(filename, "w")
    
        for action, location in action_list.items():
            try:
                # Go to the location
                
                # Get current location
                player_loc = adventureGame.world.player.get_room().name

                # Call BFS with start and end
                path_to_room = self.find_path_bfs(player_loc, location)

                # Traverse that path
                if len(path_to_room) > 1:
                    for location in path_to_room[1:]:
                        command = "Go to " + location
                        log.write(command)
                        log.write("\n")
                        result = self.game.execute_command(command)
                        if result:
                            log.write(result)
                            log.write("\n")

                # Execute the action
                result = self.game.execute_command(action)

                log.write(action)
                log.write("\n")
                if result:
                    log.write(result)
                    log.wirte("\n")

                print(f"Success: {action} → {result}")
            except Exception as e:
                print(f"error: {str(e)}")

            # Check if the game has ended
            if self.game.game_state != GameState.UNFINISHED:
                print("🏁 Game Over")
                if self.game.game_state == GameState.WON:
                    print("You Win!")
                else:
                    print("You Lose!")
                break

        log.close()

        print("\nIdealGameAgent has finished executing all actions.")

game_input = {
    "game_logics": {
        "adventurer speak with the village elders.": {
            "item needed": [],
            "location": [
                "at village hall"
            ],
            "preceeding_events": [],
            "description": [],
            "results": []
        },
        "adventurer read books.": {
            "item needed": [],
            "location": [
                "at library"
            ],
            "preceeding_events": [],
            "description": [
                "There is a book at the library."
            ],
            "results": [
                "has book"
            ]
        },
        "adventurer find maps.": {
            "item needed": [
                "has books"
            ],
            "location": [
                "at library"
            ],
            "preceeding_events": [],
            "description": [
                "There is a map at the library."
            ],
            "results": [
                "has map"
            ]
        },
        "adventurer take torch.": {
            "item needed": [
                "has money"
            ],
            "location": [
                "at general store"
            ],
            "preceeding_events": [],
            "description": [
                "There is a torch for sale at the general"
            ],
            "results": [
                "has torch"
            ]
        },
        "adventurer gather ingredient for a cure.": {
            "item needed": [
                "has basket"
            ],
            "location": [
                "at forest"
            ],
            "preceeding_events": [
                "adventurer speak with the village elders."
            ],
            "description": [],
            "results": []
        },
        "adventure meet with a wise woman in the forest": {
            "item needed": [],
            "location": [
                "at forest"
            ],
            "preceeding_events": [
                "adventurer gather ingredient for a cure."
            ],
            "description": [],
            "results": []
        }
    },
    "map": {
        "at village hall": [
            {
                "type": "npc",
                "content": "has village elders"
            }
        ],
        "at forest": [
            {
                "type": "npc",
                "content": "has farmers"
            },
            {
                "type": "npc",
                "content": "has herbalist"
            },
            {
                "type": "npc",
                "content": "has witch"
            },
            {
                "type": "npc",
                "content": "has wise woman"
            }
        ],
        "at general store": [
            {
                "type": "item",
                "content": "has torch"
            },
            {
                "type": "item",
                "content": "has lockpicking tool"
            },
            {
                "type": "npc",
                "content": "has merchant"
            }
        ],
        "at library": [
            {
                "type": "item",
                "content": "has maps"
            },
            {
                "type": "item",
                "content": "has books"
            }
        ],
        "at village": [
            {
                "type": "npc",
                "content": "has villagers"
            }
        ],
    }
}

if __name__ == "__main__":
    adventureGame = Game.load_game("test_game.pkl")
    my_agent = IdealGameAgent(adventureGame, game_input, game_name="test_game")
    my_agent.play()


