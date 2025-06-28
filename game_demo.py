from __future__ import annotations 

from utils import *
from type import GameState

from world import World

from logic_template import ActionTemplate, EventTemplate
from event import Event
from nodes import Room, Item, Player
from game import Game

look = ActionTemplate('look', 'Display {player.observation}', 'None')
inventory = ActionTemplate('inventory', 'Display {inventory}')
go = ActionTemplate('go to {room1}', 'Move {player} to {room1}; Display You have now entered {room1}; Display {player.observation}')
get = ActionTemplate('get {item1}', 'Move {item1} to {inventory}; Display You have now obtained {item1}')
read = ActionTemplate('read {enum(item)}', 'Display You read {enum(item)}', precondition='{enum(item).is_book==True}')
detonate = ActionTemplate('detoNate {item1}', 'Delete {item1}; Display This is not the correct way to defuse a domb!', precondition='{item1.is_explosive==True}')
defuse = ActionTemplate('defuse {item1}', 'Delete {item1}; Display Using the bomb defusal tool, you successfully defuse the bomb! You have saved the life of everyone!', precondition='{item1.is_explosive==True} and {has bomb defusal tool}')
flush = ActionTemplate('flush {item1}', 'Set {item1.is_flushed} to {True}; Display You have now flushed the toilet!', precondition='{item1.is_flushable==True}')
world = World()
Item.register_new_attribute('is_explosive', bool, False)
Item.register_new_attribute('is_book', bool, False)
library = Room('School Library', description='A library with nothing inside.')
book1=Item('Book1', description='A book that is very old.')
book2=Item('Book2', description='A book that is very new.')
chair = Item('Chair', description='A chair that is very old.')
book1.set_attribute('is_book', True)
book2.set_attribute('is_book', True)
cafe = Room('School Cafeteria', description='A cafeteria with many tables. There is a bomb defusal tool on one of the tables.')
lab = Room('Chemistry Lab', description='A chemistry lab with many chemicals. There is a bomb on one of the tables.')
restroom = Room('Restroom', description='A restroom with a toilet.')
toilet = Item('Toilet', description='A toilet that is very dirty.')
Item.register_new_attribute('is_flushable', bool, False)    
Item.register_new_attribute('is_flushed', bool, False)
toilet.set_attribute('is_flushable', True)
bomb_defusal_tool = Item('Bomb Defusal Tool', description='A tool that can be used to defuse a bomb.')
bomb = Item('Bomb', description='A bomb that explodes easily.')
bomb.set_attribute('is_explosive', True)
student = Player('Student', goal='safely defuse the bomb')
world.add_node(library, (0, 0))
world.add_node(book1, library)
world.add_node(book2, library)
world.add_node(chair, library)
world.add_node(cafe, (0, 1))
world.add_node(lab, (0,2))
world.add_node(student, library)
world.add_node(bomb_defusal_tool, cafe)
world.add_node(bomb, lab)
world.add_node(restroom, (1, 0))
world.add_node(toilet, restroom)

grab_tool = EventTemplate('Student obtains the bomb defusal tool.', triggering_action='get bomb defusal tool', reward=10)
arrive_at_lab = EventTemplate('Student arrives at the chemistry lab.', precondition='{at     chemisTry lab}', reward=10)
detonate_bomb = EventTemplate('The bomb explodes. The student is dead.', triggering_action='detonate bomb', next_state='lost', reward=-100)
defuse_bomb = EventTemplate('The student defuses the bomb.', triggering_action='defuse bomb', next_state='won', reward=100)

game = Game(world, [go, get, detonate, defuse, look, inventory, read, flush], [grab_tool, arrive_at_lab, detonate_bomb, defuse_bomb])

game.execute_command('look')
while True:
    command = input('Enter a command: ')
    game.execute_command(command)
    if game.game_state != GameState.UNFINISHED:
        print_warning('You win!' if game.game_state == GameState.WON else 'You lose!')
        break
