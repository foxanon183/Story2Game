import sys
import json


sys.path.append("..")
from llm.chatgpt import ChatGPT

llm = ChatGPT()

# to get the input title and description, you can use the following prompt on chatgpt
'''Generate 20 quests of an adventure game. Please give description of the quest in no more than 50 words'''
'''
Output:

The Lost Artifact: The player is tasked with finding a valuable artifact that has been missing for centuries, rumored to be hidden in a treacherous mountain range.

Cursed Kingdom: The land is under a curse, and the player must seek out a way to lift it by collecting three rare ingredients and performing a ritual.

Guardian's Trial: To prove their worth, the player must undergo a series of challenging trials set by ancient guardians to gain access to a hidden realm.

Elixir of Immortality: The player embarks on a journey to discover the ingredients for an elixir that grants eternal life, but must navigate through dangerous realms to obtain them.

Realm of Dreams: The player is transported into a dream world where they must solve riddles, face their fears, and overcome obstacles to find a way back to reality.

Pirate's Treasure: A map leads the player to a fabled pirate's treasure buried on a remote island, but they're not the only ones searching for it.

Curse of the Werewolf: The player becomes afflicted with a curse and must find a cure before the next full moon to prevent a terrible transformation.

Sorcerer's Apprentice: The player becomes an apprentice to a powerful but eccentric sorcerer, and their first task is to retrieve a rare magical creature for a crucial experiment.

Whispers in the Forest: Mysterious whispers lead the player deep into an enchanted forest, where they uncover a hidden civilization and its forgotten secrets.

Time Rift Anomaly: A series of time rifts have opened, causing historical figures and events to mix. The player must restore the timeline and close the rifts.

Aerial Huntress: The player becomes an apprentice to a legendary aerial huntress, learning to tame and ride mythical creatures while protecting the realm from airborne threats.

Mechanical Uprising: Rogue automatons threaten to overrun the land. The player must uncover their creator's hidden lair and deactivate the production facility.

The Oracle's Prophecy: Guided by an oracle's prophecy, the player embarks on a quest to retrieve a set of enchanted crystals needed to prevent an impending catastrophe.

Song of the Sea: The player must assemble a group of skilled sailors and navigate a treacherous sea filled with monsters and mysteries to find a legendary island of untold riches.

Cursed Canvas: An artist's masterpiece has come to life, and creatures from the painting are wreaking havoc. The player must enter the artwork to restore order.

Mystic Masquerade: The player gains entry to an exclusive masquerade ball where attendees are hiding magical secrets. Unmask the truth behind a series of mysterious disappearances.

Plague Doctor's Cure: A deadly plague is spreading across the realm. The player must assist a reclusive plague doctor in creating a cure using rare ingredients from dangerous lands.

Labyrinth of Illusions: Trapped in a shifting labyrinth filled with illusions, the player must solve puzzles and outwit the labyrinth's keeper to escape.

Guardian's Heirloom: The player is the last descendant of an ancient guardian lineage and must retrieve a powerful family heirloom stolen by a rival clan.

Echoes of the Ancients: Ancient ruins hold the secrets to a long-forgotten civilization. The player must decipher inscriptions, restore artifacts, and unveil the history of the lost society.'''

# convert the above output to a list of titles and descriptions
inputs = [
    {'title': 'The Lost Artifact', 'description': 'The player is tasked with finding a valuable artifact that has been missing for centuries, rumored to be hidden in a treacherous mountain range.'},
    {'title': 'Cursed Kingdom', 'description': 'The land is under a curse, and the player must seek out a way to lift it by collecting three rare ingredients and performing a ritual.'},
    {'title': 'Guardian\'s Trial', 'description': 'To prove their worth, the player must undergo a series of challenging trials set by ancient guardians to gain access to a hidden realm.'},
    {'title': 'Elixir of Immortality', 'description': 'The player embarks on a journey to discover the ingredients for an elixir that grants eternal life, but must navigate through dangerous realms to obtain them.'},
    {'title': 'Realm of Dreams', 'description': 'The player is transported into a dream world where they must solve riddles, face their fears, and overcome obstacles to find a way back to reality.'},
    {'title': 'Pirate\'s Treasure', 'description': 'A map leads the player to a fabled pirate\'s treasure buried on a remote island, but they\'re not the only ones searching for it.'},
    {'title': 'Curse of the Werewolf', 'description': 'The player becomes afflicted with a curse and must find a cure before the next full moon to prevent a terrible transformation.'},
    {'title': 'Sorcerer\'s Apprentice', 'description': 'The player becomes an apprentice to a powerful but eccentric sorcerer, and their first task is to retrieve a rare magical creature for a crucial experiment.'},
    {'title': 'Whispers in the Forest', 'description': 'Mysterious whispers lead the player deep into an enchanted forest, where they uncover a hidden civilization and its forgotten secrets.'},
    {'title': 'Time Rift Anomaly', 'description': 'A series of time rifts have opened, causing historical figures and events to mix. The player must restore the timeline and close the rifts.'},
    {'title': 'Aerial Huntress', 'description': 'The player becomes an apprentice to a legendary aerial huntress, learning to tame and ride mythical creatures while protecting the realm from airborne threats.'},
    {'title': 'Mechanical Uprising', 'description': 'Rogue automatons threaten to overrun the land. The player must uncover their creator\'s hidden lair and deactivate the production facility.'},
    {'title': 'The Oracle\'s Prophecy', 'description': 'Guided by an oracle\'s prophecy, the player embarks on a quest to retrieve a set of enchanted crystals needed to prevent an impending catastrophe.'},
    {'title': 'Song of the Sea', 'description': 'The player must assemble a group of skilled sailors and navigate a treacherous sea filled with monsters and mysteries to find a legendary island of untold riches.'},
    {'title': 'Cursed Canvas', 'description': 'An artist\'s masterpiece has come to life, and creatures from the painting are wreaking havoc. The player must enter the artwork to restore order.'},
    {'title': 'Mystic Masquerade', 'description': 'The player gains entry to an exclusive masquerade ball where attendees are hiding magical secrets. Unmask the truth behind a series of mysterious disappearances.'},
    {'title': 'Plague Doctor\'s Cure', 'description': 'A deadly plague is spreading across the realm. The player must assist a reclusive plague doctor in creating a cure using rare ingredients from dangerous lands.'},
    {'title': 'Labyrinth of Illusions', 'description': 'Trapped in a shifting labyrinth filled with illusions, the player must solve puzzles and outwit the labyrinth\'s keeper to escape.'},
    {'title': 'Guardian\'s Heirloom', 'description': 'The player is the last descendant of an ancient guardian lineage and must retrieve a powerful family heirloom stolen by a rival clan.'},
    {'title': 'Echoes of the Ancients', 'description': 'Ancient ruins hold the secrets to a long-forgotten civilization. The player must decipher inscriptions, restore artifacts, and unveil the history of the lost society.'}
]

prompt = '''You are a professional adventural game script writter. Given the title and quest description of a quest, write sub-quests of that quest (each quest should have no more than 6 sub-quests and each sub-quest should be within 10 words)
Title: {$text1$}
Quest Description: {$text2$}
Sub-Quests:
'''
outputs = []
for input in inputs:
    print("Title: ", input['title'])
    print("Description: ", input['description'])
    out = llm.get_response(prompt.replace("{$text1$}",input['title']).replace("{$text2$}",input['description'])).strip()
    out = [' '.join(s.split(' ')[1:]) for s in out.split('\n')]
    print("Sub-Quests: ", out)
    # write the outputs to a json file
    with open(f"./skeleton/{input['title'].replace(' ','_')}.json", 'w', encoding='utf8') as outfile:
        json.dump({'title':input['title'],'description':input['description'],'subquest':out}, outfile, indent=4, ensure_ascii=False)

