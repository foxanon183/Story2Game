context_hint = '''Quest summary:
{$text2$}

Quest objectives:
{$text3$}

Here is some context for the event that's going to happen.
{$text1$}

'''

prompt_get_syntax = '''This is a syntax analyzer. Infer the correct syntax for the sentence.

Sentence: Mike visited his sister in law at her home.
Syntax: somebody visited somebody at someplace.

Sentence: Sam watched a moive with his girl friend.
Syntax: somebody watched a movie with somebody.

Sentence: Fred takes his sister to the hospital.
Syntax: somebody takes somebody to someplace.

Sentence: John buys food from a grocery.
Syntax: somebody buys something from someplace.

Sentence: Tina was seen drinking at the bar.
Syntax: somebody was seen doing something at someplace.

Sentence: Lee borrows some money from bank.
Syntax: somebody borrows something from someplace.

Sentence: Tim takes the bus to his apartment.
Syntax: somebody takes the bus to someplace.

Sentence: {$text1$}
Syntax:'''


default_item_in_environment_prompt = '''Given a location and an item, determine if the item is a common item at that location?

Example 1:
Location: kitchen
Item: knife
Is knife a common item at kitchen?
Answer: yes

Example 2:
Location: bedroom
Item: axe
Is axe a common item at bedroom?
Answer: no

Example 3:
Location: {$text1$}
Item: {$text2$}
Is {$text2$} a common item at {$text1$}?
Answer:'''



parallel_precondition_item_prompt = '''Below is an instruction that describes a task, paired with an input that provides further context. Write a response that appropriately completes the request.

### Instruction:
You are an RPG game plot writer. Given an task description, generate a list of items that the adventurer need in order to perform the task. if nothing is needed for the task, answer "nothing". Please separate the item names with comma and follow the exact format as in the input output examples below.

Input output examples:
Example 1:
task: adventurer open the door.
item needed: key

Example 2:
task: adventurer slayed the dragon.
item needed: sword, shield

Example 3:
task: adventurer find a book.
item needed: nothing

### Input:

task description: adventurer{$text3$}.

### Response:
item needed:'''


parallel_precondition_action_prompt = '''How to buy something?
Answer: by ordering online;
How to get a good grade in an exam?
Answer: by studying hard
How to go to home?
Answer: by taking a bus;
How to {$text3$}?
Answer: by{$text2$}'''

prompt_syntax_location = '''This is a syntax generator. Use someplace if possible

someplace: somebody visits somebody at someplace.

somebody reads something.

someplace: somebody takes something to someplace.

somebody teaches somebody.

somebody manufactures something at someplace.

someplace: {$text1$}'''

prompt_syntax_through_doing = '''This is a sentence generator. Use "through doing something" if possible

Tina became a chief inspector.
Tina became a chief inspector through solving a major case.

Tim rode a bike.
Tim rode a bike.

John got promoted.
John got promoted through working hard.

Mike reads a book at home.
Mike reads a book at home.

The knight save the girl from the dragon.
The knight save the girl from the dragon through killing the dragon.

Tom teaches Jack after class.
Tom teaches Jack after class.

Fred got an A in the class.
Fred got an A in the class through cheating.

Richard retired from his job at the factory.
Richard retired from his job at the factory.

Ruth made a lot of enermies.
Ruth made a lot of enermies.

Jack get a knife from the drawer.
Jack get a knife from the drawer.

Thomas was kidnapped.
Thomas was kidnapped.

{$text1$}.
{$text1$}'''

prompt_syntax_reason = '''This is a sentence generator. Use for because if possible

John went to the hospital.
John went to the hospital because John is sick.

Tom buys a book.
Tom can buy a book if he want to.

Fred cheats in the exam.
Fred cheats in the exam because he wants to get a better grade.

Ruth met Jack.
Ruth can meet Jack if she want to.

Tim argued with his wife.
Tim argued with his wife because his wife spend money on buying useless things.

Jack walk to Jack's home.
Jack can walk to Jack's home if he want to.

Tina is fired by her boss for playing a game at work.
Tina is fired by her boss because she played a game at work.

Richard drives to his company.
Richard can drives if he want to.

{$text1$}
'''

fact_about_object_prompt = '''Given the sentence, what can be said about the object in the sentence?
Sentence: Tim picked up a bottle of water from the table at home.
What can we tell about the bottle of water?
Answer: There is a bottle of water on the table at Tim's home.

Sentence: Mike read book at the library.
What can we tell about the book?
Answer: There is a book at library.

Sentence: Fred use the microware at kitchen.
What can we tell about the microware?
Answer: There is a microware at Fred's kitchen.

Sentence: Tim bought milk from the grocery store.
What can we tell about milk?
Answer: There is milk for sale at the grocery store.

Sentence: {$text3$}
What can we tell about the {$text4$}?
Answer: There is'''
        
ownership_prompt = '''Given the sentence, determine Who owns the object.
Sentence: There is a bottle of water on the table at John's home.
Who owns the bottle of water?
Answer: John.

Sentence: There is milk for sale at the grocery store.
Who owns the milk?
Answer: grocery store.

Sentence:{$text3$}
Who owns the {$text4$}?
Answer:'''


how_to_get_to_goal_prompt = '''Given the sentence, answer how the adventurer achieves the goal.

Sentence: adventurer open the door.
How does adventurer open the door?
Answer: adventurer use key to open the door

Sentence: adventurer kill dragon.
How does adventurer kill dragon?
adventurer hit dragon

Sentence: adventurer get a new armor.
How does adventurer get a new armor?
Answer: adventurer steal from guards

Sentence: adventurer persuaded the cheif to give money to him.
How does adventurer persuaded the cheif to give money to him?
Answer: adventurer kill goblins

Sentence: {$text3$}.
How does {$text3$}?
Answer: '''


parallel_precondition_action_prompt = '''How to buy something?
Answer: by ordering online;

How to get a good grade in an exam?
Answer: by studying hard

How to go to home?
Answer: by taking a bus;

How to {$text3$}?
Answer: by{$text2$}'''



parallel_precondition_second_character_prompt = '''What happens between the protagonist and another character prior to the event?
Event: Tom bought a second-hand car.
prior to Tom bought a second-hand car, Tom negotiated with a used car dealer;

Event: Tim chats with Smith at a bar.
prior to Tim chatted with Smith at a bar, Tim met Smith at the bar;

Event: Danie had a fight with Tony.
prior to Danie had a fight with Tony, Danie had an argument with Tony;

Event: Fred hugs Tom on the street.
prior to Fred hugged Tom, Fred met Tom on the street;

Event: {$text3$}.
prior to {$text3$},'''


parallel_precondition_location_prompt = '''Infer where does the adventurer need to be to perform certain action or achieve certain goal. Here are some examples.

{$text2$} drink beer.
Where is {$text2$}?
Answer: inn

{$text2$} met the merchant.
Where is {$text2$}?
Answer: marketplace

{$text2$} buy potion.
Where is {$text2$}?
Answer: general store

{$text2$} slaw a dragon.
Where is {$text2$}?
Answer: dragon nest

{$text2$} farmed some barley.
Where is {$text2$}?
Answer: farm

{$text2$} mined some iron.
Where is {$text2$}?
Answer: iron mine

{$text2$} get new shoes from the shoes shop.
Where is {$text2$}?
Answer: shop

{$text2$} took a sword from the sword rack.
Where is {$text2$}?
Answer: weapon depot

{$text2$} crafted a shield.
Where is {$text2$}?
Answer: black smiths shop

adventurer{$text3$}
Where is {$text2$}?
Answer:'''

parallel_effect_prompt = '''How does a person have some food to eat food?
Answer: go to a restaurant; order takeout online；

How does a person study to get good grades in an exam?
Answer: revise to prepare for the exam;

How does a person by taking the bus to go to the museum?
Answer: take the bus;

How does a person at home to party with friends?
Answer: drive home; walk home;

how does a person {$text3$}?
Answer:{$text2$}'''


action_prompt_obtain_item = '''Infer how the adventurer obtains the item. Answer this using the following template "adventurer {verb} {noun}". Here are some examples. Follow the examples to answer the question.

How did {$text2$} get a roasted chicken?
Answer: {$text2$} make roasted chicken

How did {$text2$} get key?
Answer: {$text2$} steal key

How did {$text2$} get sword?
Answer: {$text2$} pick up sword

How did {$text2$} get citron?
Answer: {$text2$} get citron

How did {$text2$} get wagon?
Answer: {$text2$} buy wagon

How did {$text2$} {$text3$}
Answer: {$text2$}'''


action_prompt_obtain_item = '''Below is an instruction that describes a task, paired with an input that provides further context. Write a response that appropriately completes the request.

### Instruction:
You are an RPG game plot writer. Given the name of an item, generate a method for the adventurer to obtain that item. Your output should a simple sentence that follows one of the allowed output formats. The style of your output should mimic the input output examples below.

### Input:
Allowed output formats
adventurer [verb].
adventurer [verb] [norm].
adventurer [verb] [norm] with [norm].
adventurer [verb] with [norm].

Input output examples
Example 1:
item: sword
method: adventurer pick up sword.

Example 2:
item: key
method: adventurer steal key.

Example 3:
item: citron
method: adventurer get citron.

target item: {$text1$}

### Response:
method:'''

action_prompt_go_to_somewhere = '''Context: {$text2$} drink at inn.
How did {$text2$} get to inn?
Answer: {$text2$} rode horse to go to the inn.

Context: {$text2$} defeat dragon at a cleaning in a forest.
How did {$text2$} get to forest?
Answer: {$text2$} rode horse to go to the forest.

Context: {$text2$} find a fairy.
How did {$text2$} get to an island in the middle of a lake?
Answer: {$text2$} take a boat to got to the island.

Context: {$text2$} sold barley the merchant guild.
How did {$text2$} get to the city?
Answer: {$text2$} drive his wagon to get to the city.

Context: {$text1$}
How did {$text2$} {$text3$}
Answer: {$text2$}'''

parallel_reason_prompt = '''Explain what the protagonist has done that causes the event to happen.

Example 1: John went to the hospital because Mike wanted to see a doctor at the hospital.

Example 2: Fred got a zero on the exam because Fred cheated during the exam at school.

Example 3: Tom reads a book because Tom wants to read a book.

Example 4: Tina was fired by her boss because Tina failed to finish her work at the company.

Example 5: Thomas takes the bus to get to the library because Thomas wants to go to the library.

Example 6: Julia broke up with her boyfriend because Julia's boyfriend didn't reply to her message.

Example 7: Tim had an amputation because he was hit by a car badly.

Example 8: {$text3$} because{$text2$}'''

enrich_context_prompt='''Elaborate the given event to include a location where the event takes place.

Original sentence: Tony watched a movie.
Sentence with a location where the event takes place: Tony watched a movie at the cinema.

Original sentence: Tina bought a pancake at the supermarket.
Sentence with a location where the event takes place: Tina bought a pancake from a supermarket.

Original sentence: Mike went hiking.
Sentence with a location where the event takes place: Mike went hiking with his friends at a national park.

Original sentence: Jam was seen drinking at a bar by the bartender.
Sentence with a location where the event takes place: Jam was seen drinking at a bar by the bartender.

Original sentence: {$text3$}
Sentence with a location where the event takes place: {$text2$}'''


extract_character_name_prompt='''Imagine the event described in the given sentences. Find NPCs (characters and creatures) who ainteract with adventurer in the event. Here are some examples:
Example 1:
Sentence: The adventurer walked to the dragon nest.
NPCs interact with adventurer: none

Example 2: 
Sentence: the adventurer talk to the blacksmith.
NPCs interact with adventurer: blacksmith

Example 3:
Sentence: adventurer pick up a sword.
NPCs interact with adventurer: none

Example 4:
Sentence: adventurer entered the merchant's shop.
NPCs interact with adventurer: none

Example 5:
Sentence: adventurer rode a donkey.
NPCs interact with adventurer: donkey

Example 6:
Sentence: {$text3$}
NPCs interact with adventurer:'''

object_state_to_action_prompt = '''Given the sentence, what we tell about the state of the item in the sentence?

Context: Tim picked up a bottle of water from the table.
The bottle needs to be full.
Tim takes water from the tap at the restroom.

Sentence: Millian shot Mike on the street.
The gun needs to be loaded.
Millian loaded the gun on the street.

Sentence: Jonny took a bus to get home.
The bus ticket needs to be validated.
Jonny let the ticket collector validate the ticket.

Sentence: Fred made steak in the kitchen.
The steak needs to be marinated.
Fred marinated the steak in the kitchen.

Sentence: Willson drove his car to Sally's home.
The car needs to be repaired.
Willson repairs his car at a garage.

Sentence: Tony wrote with a typewriter.
The typewriter needs to be turned on.
Tony turned on the typewriter.

Sentence: {$text3$}
{$text4$}
{$text2$}'''

object_state_prompt = '''Given the sentence, what we tell about the state of the item in the sentence?

Sentence: Tim picked up a bottle of water from the table.
What can we tell about the bottle of water other than how Tim obtain it?
nothing.

Sentence: Millian shot Mike.
What can we tell about the gun other than how Millian obtain it?
The gun needs to be loaded.

Sentence: Jonny took a bus to get home.
What can we tell about the bus ticket other than how Jonny obtain it?
nothing.

Sentence: Fred made steak.
What can we tell about the steak other than how Fred obtain it?
The steak needs to be marinated.

Sentence: Willson drove his car to Sally's home.
What can we tell about the car other than how Willson obtain it?
nothing.

Sentence: Tony wrote with a typewriter.
What can we tell about the typewriter other than how Tony obtain it?
The typewriter needs to be turned on.

Sentence: Tom paid his rent.
What can we tell about the money other than how Tom obtain it?
nothing.

Sentence: {$text3$}
What can we tell about the {$text4$} other than how {$text2$} obtain it?
'''
