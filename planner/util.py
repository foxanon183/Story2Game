import marisa_trie
from typing import Dict, List
import torch
import json
import nltk
import graphviz
from planner.prompt import *
from collections import defaultdict
from planner.gpt_interface_alpaca import get_semantic_similarity, get_score
import os

from transformers import AutoTokenizer, AutoModel#for embeddings
from sklearn.metrics.pairwise import cosine_similarity#for similarity


nltk.download('punkt')
nltk.download('stopwords')
nltk.download('propbank')
nltk.download('corpus')
from nltk.corpus import propbank

nltk.download('omw-1.4')
nltk.download('wordnet')
nltk.download('averaged_perceptron_tagger')


lemmatizer = nltk.stem.WordNetLemmatizer()

CUDA_AVAILABLE = torch.cuda.is_available()
#calculate similarity
def cos_simi(text1,text2):
    return get_semantic_similarity(text1,text2)

def score(text):
  #encode sentence
  return get_score(text)

class MarisaTrie(object):
    def __init__(
        self,
        sequences: List[List[int]] = [],
        cache_fist_branch=False,
        max_token_id=256001,
        name="",#for saving
    ):
        '''
        Usage: trie = MarisaTrie([tokenizer.encode(s) for s in [':Hello',':Hello World',":Hello everyone"]])
        '''
        if os.path.exists(os.path.join(LIGHT_DIR, "data", "env", "%s.json"%name)) and os.path.exists(os.path.join(LIGHT_DIR, "data", "env", "%s.marisa"%name)):
            self.load(name)
        else:
            self.int2char = [chr(i) for i in range(min(max_token_id, 55000))] + (
                [chr(i) for i in range(65000, max_token_id + 10000)]
                if max_token_id >= 55000
                else []
            )
            self.char2int = {self.int2char[i]: i for i in range(max_token_id)}

            self.cache_fist_branch = cache_fist_branch
            self.zero_iter = []
            self.first_iter = []
            if self.cache_fist_branch:
                self.zero_iter = list({sequence[0] for sequence in sequences})
                assert len(self.zero_iter) == 1
                self.first_iter = list({sequence[1] for sequence in sequences})

            self.trie = marisa_trie.Trie(
                "".join([self.int2char[i] for i in sequence]) for sequence in sequences
            )
            self.save(name)

    def save(self,file_name):
        json_path=os.path.join(LIGHT_DIR, "data", "env", "%s.json"%file_name)
        with open(json_path, 'w') as f:
            json.dump({"int2char":self.int2char,"char2int":self.char2int,"cache_fist_branch":self.cache_fist_branch,"zero_iter":self.zero_iter,"first_iter":self.first_iter}, f)
        trie_path = os.path.join(LIGHT_DIR, "data", "env", "%s.marisa"%file_name)
        self.trie.save(trie_path)

    def load(self,file_name):
        json_path=os.path.join(LIGHT_DIR, "data", "env", "%s.json"%file_name)
        with open(json_path, 'r') as f:
            data = json.load(f)
        self.int2char = data["int2char"]
        self.char2int = data["char2int"]
        self.cache_fist_branch = data["cache_fist_branch"]
        trie_path = os.path.join(LIGHT_DIR, "data", "env", "%s.marisa"%file_name)
        self.trie = marisa_trie.Trie()
        self.trie.load(trie_path)


    def get(self, prefix_sequence: List[int]):
        if self.cache_fist_branch and len(prefix_sequence) == 0:
            return self.zero_iter
        elif (
            self.cache_fist_branch
            and len(prefix_sequence) == 1
            and self.zero_iter == prefix_sequence
        ):
            return self.first_iter
        else:
            key = "".join([self.int2char[i] for i in prefix_sequence])
            return list(
                {
                    self.char2int[e[len(key)]]
                    for e in self.trie.keys(key)
                    if len(e) > len(key)
                }
            )

    def __iter__(self):
        for sequence in self.trie.iterkeys():
            yield [self.char2int[e] for e in sequence]

    def __len__(self):
        return len(self.trie)

    def __getitem__(self, value):
        return self.get(value)

def get_prompt(prompt,text1="",text2="", text3="", text4="", text5=""):
    '''
    generate prompt with templates
    '''
    if "{$text1$}" in prompt:
        prompt = prompt.replace("{$text1$}",text1)
    if "{$text2$}" in prompt:
        prompt = prompt.replace("{$text2$}",text2)
    if "{$text3$}" in prompt:
        prompt = prompt.replace("{$text3$}",text3)
    if "{$text4$}" in prompt:
        prompt = prompt.replace("{$text4$}",text4)
    if "{$text5$}" in prompt:
        prompt = prompt.replace("{$text5$}",text5)
    return prompt


def preprocess(candidate_preconditions):
  '''
  preprocess before generating actions for preconditions
  '''
  if isinstance(candidate_preconditions,str):
    if "has done" in candidate_preconditions:
      candidate_preconditions = candidate_preconditions.replace("has done ","")
    if "has " in candidate_preconditions:
      candidate_preconditions = candidate_preconditions.replace("has ","get ")
    if "at " in candidate_preconditions:
      candidate_preconditions = candidate_preconditions.replace("at ","get to ")
    return candidate_preconditions
  else:
    ret = []
    for precondition in candidate_preconditions:
      if "has done" in precondition:
        precondition = precondition.replace("has done ","")
      if "has " in precondition:
        precondition = precondition.replace("has ","get ")
      if "at " in precondition:
        precondition = precondition.replace("at ","get to ")
      ret.append(precondition)
    return ret


def lemmarization(word):
    return lemmatizer.lemmatize(word)

def most_common(lst):
    return max(set(lst), key=lst.count)

def match_lemma(precondition1,precondition2,threshold=0.6):
    word_lemma1 = [lemmarization(word) for word in precondition1.split(' ')]
    word_lemma2 = [lemmarization(word) for word in precondition2.split(' ')]
    
    u=len(set(word_lemma1).union(set(word_lemma2)))
    i = len(word_lemma1)+len(word_lemma2)-u
    if i/u>threshold:
        return True
    else:
        return False

def get_verb(sentence):
  doc = NLP(sentence)
  for token in doc:
    if token.pos_ == 'VERB':
      return token.text, token.lemma_
  return "",""

def choose_best_precondition_by_perplexity(action,preconditions):
    '''
    return the best precondition for certain action according to perplexity
    param action: action
    param preconditions: candidate preconditions for the action
    '''
    true_false_prompt = '''Determine if the statement is true or false
    statement: One need to {$precondition$} to {$action$}
    answer: true'''
    scores = [score(true_false_prompt.replace("{$precondition$}",precondition).replace("{$action$}",action)) for precondition in preconditions]
    print(scores)
    return preconditions[scores.index(min(scores))]

def choose_best_action_by_purpose(purpose,actions):
    '''
    return the best precondition for certain action according to perplexity
    param action: action
    param preconditions: candidate preconditions for the action
    '''
    true_false_prompt = '''Determine if the statement is true or false
    statement: One can {$action$} to {$purpose$}
    answer: true'''
    scores = [score(true_false_prompt.replace("{$action$}",action).replace("{$purpose$}",purpose)) for action in actions]
    print(scores)
    return actions[scores.index(min(scores))]


def choose_precondition_by_frequency(preconditions, freq_threshold=2,cutoff_frequency=0,mode="gen_preconditions", action="",match_lemma_threshold=0.66, use_majority_vote = True, majority_vote_threshold=0.5):
    '''
    choose most common preconditions from candidates, a candidate precondition is considered as valid once its frequency pass this threshold
    When none of candidate preconditions pass the threshold, the most frequent one will be returned if its frequency exeed cutoff_frequency.
    when action is given, return the best suit precondition given the action.
    param preconditions: candidate preconditions
    param freq_threshold: a candidate precondition is considered as valid once its frequency pass this threshold
    param cutoff_frequency: When none of candidate preconditions pass the threshold, the most frequent one will be returned if its frequency exeed cutoff_frequency.
    param action: when action is given, return the best suit precondition given the action.
    param match_lemma_threshold: between 0 and 1, a higher value indicate less tolerance in fuzzy matching
    param use_majority_vote: if True, return the majority vote result (More than 50% of votes)
    '''
    pool = {}
    for precondition in preconditions:
        pool[precondition] = 0
    for precondition in preconditions:
        for key in pool.keys():
            if match_lemma(precondition,key,threshold=match_lemma_threshold):
                pool[key]+=1
    most_common_freq = 0
    most_common_precondition = None
    ret = []
    pool = dict(sorted(pool.items(),key=lambda x:x[1],reverse=True))
    print(pool)
    for key in pool.keys():  
        if use_majority_vote and pool[key]>=len(preconditions)*majority_vote_threshold and pool[key]>cutoff_frequency:
            return [key]  
        if pool[key]>=most_common_freq:
            most_common_precondition = key
            most_common_freq = pool[key]
        if pool[key]>=freq_threshold:
            ret.append(key)
    if most_common_precondition not in ret and most_common_freq>cutoff_frequency:
        ret.append(most_common_precondition)
    if mode == "gen_preconditions" and action!="" and ret!=[]:
        ret=[choose_best_precondition_by_perplexity(action, ret)]
    elif mode=='gen_action' and action!="" and ret!=[]:
        ret=[choose_best_action_by_purpose(action, ret)]
    return ret

def post_process(generated_sentences,separator=';',prefix='', mode="gen_preconditions", must_have='',must_not_contain = '', to_avoid = [],action="",remove_first_word=False,exclude_go_to=False,
                 lookup={},simi_threshold=0.8,freq_threshold=20,cutoff_frequency=0,match_lemma_threshold=0.66, use_majority_vote = True, majority_vote_threshold=0.5):
    '''
    all-in-one postprocess function for postprocessing outputs of GPT-J.
    param generated_sentences: original GPT-J output
    param seperator: a string for the delimiter
    param prefix: added as the prefix to the postprocess results
    param mode: string, if "gen_actions", filter all candidates that are similar to to_avoid
    param must_have: string, filter out candidates that doesn't contain it
    param to_avoid: string, must be non-empty if mode is "gen_actions"
    param action: for choose_best_precondition_by_perplexity
    remove_first_word: whether or not to remove the first word, usually the name of the protagonist
    param lookup: not used
    '''
    if type(to_avoid)==str:
        to_avoid = [to_avoid]
    candidates = []
    if must_have!='':
        generated_sentences = [s for s in generated_sentences if must_have in s]
    generated_sentences = [s if s[-4:]!='</s>' else s[:-4] for s in generated_sentences]
    #print(generated_sentences)
    for result in generated_sentences:
        result = result.split('\n')[0]
        if separator in result:
            result = [(s.strip()).strip() for s in result.split(separator)[:-1]]
        else:
            result = [(s.strip()).strip() for s in result.split(separator)]
        #print("result:",result)
        if mode=="gen_actions" or "gen_preconditions" and len(to_avoid)>0:
          for action_ in result:
            similarity_score = max([cos_simi(t,action_.split('.')[0]) for t in to_avoid])
            if similarity_score<simi_threshold and len(action_.replace('.','').strip().split(' '))>1:
                if ' is ' not in action_ and ' was ' not in action_:
                    candidates.append(action_)
        else:
          candidates.extend(result)
    candidates = [candidate.strip() for candidate in candidates]
    if candidates.count('')>len(candidates)/3:
        return []
    candidates = [candidate for candidate in candidates if len(candidate)>0]   #get rid of empty string
    
    if must_not_contain!='':
        candidates = [candidate for candidate in candidates if must_not_contain not in candidate]
    if len(candidates)==0:
        return candidates
    #print("candidates",candidates)
    for i in range(len(candidates)):
        if candidates[i].split(' ')[0] in ['a','an','the'] or remove_first_word:
            candidates[i] = ' '.join(candidates[i].split(' ')[1:])
    if exclude_go_to:
        candidates = [candidate for candidate in candidates if 'go to' not in candidate and 'goes to' not in candidate]
    if mode=="gen_item":
        temp = copy.deepcopy(candidates)
        for i,item in enumerate(temp):
            for item2 in temp:
                if len(item)<len(item2) and item in item2:
                    candidates.append(item2)
    candidates = choose_precondition_by_frequency(candidates, freq_threshold=freq_threshold, cutoff_frequency =cutoff_frequency, mode=mode,
                                                  action=action, match_lemma_threshold=match_lemma_threshold, use_majority_vote=use_majority_vote, majority_vote_threshold=majority_vote_threshold)
    if mode=="gen_item":
        candidates = [candidate for candidate in candidates if candidate not in ['nothing','something']]
    return [prefix+' '+candidate for candidate in candidates]


def choose_best_action_by_perplexity(effect,actions,parent_action,character):
    scores = [[action,score(action)] for action in actions]
    scores = sorted(scores,key=lambda x:x[1],reverse=True)
    return scores[0][0], [t[0] for t in scores]

def fix_missing_object(sentence,item):
    '''
    replace any pronom with specific object
    '''
    tokens = nltk.word_tokenize(sentence)
    tagged = nltk.pos_tag(tokens)
    ret = ''
    for word in tagged:
        new_word = word[0]
        if word[1]=='PRP':
            new_word = item
        ret+=new_word+' '
    return ret.strip()

def check_contains_upper(s):
    cnt = 0
    for c in s:
        if not c.isalpha():
            continue
        if cnt==0:
            if (not c.isalpha()) or c != c.upper():
                return False
        else:
            if c.isalpha() and c==c.upper():
                return False
        cnt+=1
    return True 


class node:
    def __init__(self,val,node_type='None'):
        self.val = val
        self.node_type = node_type
    def __str__(self):
        return self.val[0]+self.val[1]

class DAG:
    def __init__(self):
        self.id_cnt = 0
        self.nodes = {}
        self.edges = {}
        self.edges_backward = {}
        self.text = ""
        self.visited = []
        self.topological_order = []
        self.location_map = {}
        self.map_content_to_id = {}
        self.precondition_node_identifier = ['how','reason','item needed','item state','location','interaction with other person','fact_about_object','negation']

    def add_node(self,content, secondary_content=None, node_type = None):
        if content not in self.map_content_to_id:
            self.nodes[self.id_cnt] = node(content, node_type=node_type)
            self.edges[self.id_cnt] = []
            self.edges_backward[self.id_cnt] = []
            self.map_content_to_id[content] = self.id_cnt
            if secondary_content:
                self.nodes[self.map_content_to_id[content]].val=str(content+'\n'+secondary_content)
            self.id_cnt+=1
            return self.id_cnt
        else:
            if secondary_content:
                self.nodes[self.map_content_to_id[content]].val=str(content+'\n'+secondary_content)
            return self.map_content_to_id[content]

    def add_edge(self,content1,content2):
        id1 = self.map_content_to_id[content1]
        id2 = self.map_content_to_id[content2]
        if id2 not in self.edges[id1]:
            self.edges[id1].append(id2)
            self.edges_backward[id2].append(id1)

    def topological_sort(self,cur):
        print("Node val:",self.nodes[cur].val,len(self.nodes[cur].val.split('\n')))
        print(cur)
        self.visited.append(cur)
        heuristics = {'fact_about_object':0,'negation':1,'reason':2,'how':3,'item needed':4,'item state':5,'location':6,'interaction with other person':7,'event':8}
        self.edges_backward[cur] = sorted(self.edges_backward[cur],key=lambda x:heuristics[self.nodes[x].node_type])

        for next in self.edges_backward[cur]:
            if next not in self.visited:
                self.topological_sort(next)
        self.topological_order.append(cur)

    def format_print(self):
        print(self.edges)
        print('----------------Plan-----------------')
        '''
        position = ''
        lines = self.text.split('\n')
        after_fixing_location_lines = []
        for i,line in enumerate(lines):
            if ' to get to ' in line:
                position = line.split(' to get to ')[1].split(';')[0].replace('.',"").strip()
                print("set position to ",position)
            if 'Precondition location;' in line:
                temp = line.split(';')[2]
                if ' at ' in temp:
                    required_position = temp.split(' at ')[1].replace(' satisfied.',"").strip()
                elif ' from ' in temp:
                    required_position = temp.split(' from ')[1].replace(' satisfied.',"").strip()
                elif ' on ' in temp:
                    required_position = temp.split(' on ')[1].replace(' satisfied.',"").strip()
                else:
                    required_position = position
                if cos_simi(required_position,position)<0.6:
                    print('************fix location************\n',position,required_position)
                    after_fixing_location_lines.append("Event:John went to get to %s.; John went to get to %s."%(required_position,required_position))
                    position = required_position
            after_fixing_location_lines.append(line)
        self.text = '\n'.join(after_fixing_location_lines)
        '''
        print(self.text)
        return '----------------Plan-----------------'+'\n'+self.text



def visualize_plan(graph,title, path='../result',end=None):
    graph = [g for g in graph if g[0][0]!='Dummy Sink']
    print(graph)
    dag = DAG()
    events_and_preconditions = defaultdict(lambda: defaultdict(list))
    preconditions_with_solutions = {}
    preconditions = []
    shorten_key_mapping = {}
    events = {}
    dot = graphviz.Digraph(comment='myplan')
    start_event = graph[0][0][0].replace('.','')
    cnt_automatic_satisfied_node = 0
    game_logics = {}
    solution_map = {}
    map = {}
    visible_actions = []
    if end:
        queue = [end]
        while len(queue)>0:
            action = queue.pop(0)
            visible_actions.append(action)
            for entry in graph:
                if entry[0][0]==action and entry[2] not in visible_actions:
                    queue.append(entry[2])

    for line in graph:
        (event,expansion),(precondition,precondition_type),solution,character = line[0],line[1],line[2],line[3]
        if event not in visible_actions:
            continue
        if precondition_type in ['item needed','location']:
            precondition_type_ = precondition_type
        elif precondition_type=="fact_about_object":
            precondition_type_ = "description"
        else:
            precondition_type_ = 'preceeding_events'
        if event not in game_logics:
            game_logics[event]={'item needed':[],'location':[],'preceeding_events':[],"description":[]}
        if precondition not in game_logics[event][precondition_type_]:
            game_logics[event][precondition_type_].append(precondition)
        if precondition_type_=='item needed':
            solution_map[solution]=precondition
        if event in solution_map and precondition_type_=='location':
            if precondition not in map:
                map[precondition]=[]
            if {"type":"item","content":solution_map[event]} not in map[precondition]:
                map[precondition].append({"type":"item","content":solution_map[event]})
        if precondition_type_=='location' and character!="adventurer":
            if precondition not in map:
                map[precondition]=[]
            if {"type":"npc","content":'has '+character} not in map[precondition]:
                map[precondition].append({"type":"npc","content":'has '+character})
        if precondition_type_=='location':
            if precondition not in map:
                map[precondition]=[]

        dag.add_node('Event:'+event, expansion, node_type='event')
        if solution!="which is satisfied automatically.":
            dag.add_node('Event:'+solution, node_type='event')
        dag.add_node(precondition_type+'\n'+'character: '+character+'\n'+precondition, node_type=precondition_type)
        dag.add_edge(precondition_type+'\n'+'character: '+character+'\n'+precondition, 'Event:'+event)
        if solution!="which is satisfied automatically.":
            dag.add_edge('Event:'+solution, precondition_type+'\n'+'character: '+character+'\n'+precondition)
        
    for node_name in dag.map_content_to_id.keys():
        dot.node(str(dag.map_content_to_id[node_name]), dag.nodes[dag.map_content_to_id[node_name]].val)
    for node_name in dag.map_content_to_id.keys():
        out_edges = dag.edges[dag.map_content_to_id[node_name]]
        for neighbor in out_edges:
            dot.edge(str(dag.map_content_to_id[node_name]),str(neighbor))
    #dot.render(path+'/%s.gv'%title, view=False) 

    #preprocess
    for node in dag.edges_backward.keys():
        next_nodes_type = [dag.nodes[x].node_type for x in dag.edges_backward[node]]
        interaction_nodes = []
        for i,node_type in enumerate(next_nodes_type):
            if node_type=='interaction with other person':
                interaction_nodes.append(dag.edges_backward[node][i])
        if len(interaction_nodes)==2:
            print("marge for generating sequencial plan:",dag.nodes[interaction_nodes[0]].val,dag.nodes[interaction_nodes[1]].val)
            dag.edges_backward[interaction_nodes[0]].extend(dag.edges_backward[interaction_nodes[1]])
            dag.edges_backward[interaction_nodes[0]] = list(set(dag.edges_backward[interaction_nodes[0]]))
            for n in dag.edges_backward.keys():
                dag.edges_backward[n] = [o if o!=interaction_nodes[1] else interaction_nodes[0] for o in dag.edges_backward[n]]

    dag.topological_sort(dag.map_content_to_id['Event:'+end])
    story = [dag.nodes[i].val.split('\n')[0].replace("Event:","") for i in dag.topological_order if "Event:" in dag.nodes[i].val.split('\n')[0]]
    with open(path+'/%s_walk_through.txt'%title, 'w') as f:
        f.write('\n'.join(story))
    print(story)

    story = [s for s in story if s in game_logics]
    game_logics = {k:v for k,v in sorted(game_logics.items(), key=lambda x: story.index(x[0]))}
    print(game_logics)
    with open(path+'/%s_game.txt'%title, 'w') as f:
        f.write(str({'game_logics':game_logics,'map':map}))

    return game_logics,map

if __name__ == '__main__':
    #print(cos_simi("a dog","a cute dog"))

    '''
    test_graph = [[('adventurer kill bandits.', 'adventurer kill bandits at bandit lair.'), ('at bandit lair', 'location'), 'which is satisfied automatically.', 'bandits'], [('adventurer kill bandits.', 'adventurer kill bandits at bandit lair.'), ('at bandit lair', 'location'), 'adventurer walked to get to bandit lair .', 'adventurer'], [('adventurer kill bandits.', 'adventurer kill bandits at bandit lair.'), ('has sword', 'item needed'), 'adventurer get sword.', 'adventurer'], [('adventurer get sword.', 'adventurer get sword at black smiths shop.'), ('There is a sword for sale at black smith', 'fact_about_object'), 'which is satisfied automatically.', 'adventurer'], [('adventurer get sword.', 'adventurer get sword at black smiths shop.'), ('at black smiths shop', 'location'), 'adventurer walked to get to black smiths shop .', 'adventurer']]
    visualize_plan(test_graph,"adventurer kill bandits",end='adventurer kill bandits.')
    test_graph = [[('adventurer kill bandits.', 'adventurer kill bandits at bandit lair.'), ('at bandit lair', 'location'), 'adventurer walked to get to bandit lair .', 'adventurer'], [('adventurer kill bandits.', 'adventurer kill bandits at bandit lair.'), ('at bandit lair', 'location'), 'which is satisfied automatically.', 'bandits'], [('adventurer get sword.', 'adventurer get sword at black smiths shop.'), ('There is a sword at black smiths shop', 'fact_about_object'), 'which is satisfied automatically.', 'adventurer'], [('adventurer get sword.', 'adventurer get sword at black smiths shop.'), ('at black smiths shop', 'location'), 'adventurer walked to get to black smiths shop .', 'adventurer'], [('adventurer kill bandits.', 'adventurer kill bandits at bandit lair.'), ('has sword', 'item needed'), 'adventurer pick up sword.', 'adventurer'], [('adventurer pick up sword.', 'adventurer pick up sword at black smiths shop.'), ('at black smiths shop', 'location'), 'adventurer walked to get to black smiths shop.', 'adventurer']]
    visualize_plan(test_graph,"adventurer kill bandits fix inadmissible actions",end='adventurer kill bandits.')
    '''

    
    test_graph = [[('adventurer find the werewolf den.', 'adventurer find the werewolf den.'), ('adventurer speak with the village elders.', 'how'), 'adventurer speak with the village elders.', 'adventurer'], [('adventurer gather ingredients for a cure.', 'adventurer gather ingredients for a cure.'), ('adventurer find the werewolf den.', 'how'), 'adventurer find the werewolf den.', 'adventurer'], [('adventure meet with a wise woman in the forest', 'adventure meet with a wise woman in the forest'), ('adventurer gather ingredients for a cure.', 'how'), 'adventurer gather ingredients for a cure.', 'adventurer'], [('adventurer investigate the abandoned mansion', 'adventurer investigate the abandoned mansion'), ('adventure meet with a wise woman in the forest', 'how'), 'adventure meet with a wise woman in the forest', 'adventurer'], [('adventure confront the werewolf pack leader', 'adventure confront the werewolf pack leader'), ('adventurer investigate the abandoned mansion', 'how'), 'adventurer investigate the abandoned mansion', 'adventurer'], [('adventure escort villagers to safety', 'adventure escort villagers to safety'), ('adventure confront the werewolf pack leader', 'how'), 'adventure confront the werewolf pack leader', 'adventurer'], [('adventure destroy the cursed artifact', 'adventure destroy the cursed artifact'), ('adventure escort villagers to safety', 'how'), 'adventure escort villagers to safety', 'adventurer'], [('adventurer stop the curse from spreading to other villages', 'adventurer stop the curse from spreading to other villages'), ('adventure destroy the cursed artifact', 'how'), 'adventure destroy the cursed artifact', 'adventurer'], [('adventurer investigate the first werewolf attack.', 'adventurer investigate the first werewolf attack at village.'), ('at village', 'location'), 'adventurer walked to get to village .', 'adventurer'], [('adventurer speak with the village elders.', 'adventurer speak with the village elders at village hall.'), ('at village hall', 'location'), 'which is satisfied automatically.', 'village elders'], [('adventurer speak with the village elders.', 'adventurer speak with the village elders at village hall.'), ('at village hall', 'location'), 'adventurer walked to get to village hall .', 'adventurer'], [('adventurer find the werewolf den.', 'adventurer find the werewolf den at forest.'), ('at forest', 'location'), 'adventurer walked to get to forest .', 'adventurer'], [('adventurer find the werewolf den.', 'adventurer find the werewolf den at forest.'), ('has maps', 'item needed'), 'adventurer find maps.', 'adventurer'], [('adventurer find the werewolf den.', 'adventurer find the werewolf den at forest.'), ('at forest', 'location'), 'which is satisfied automatically.', 'werewolf'], [('adventurer find the werewolf den.', 'adventurer find the werewolf den at forest.'), ('has torch', 'item needed'), 'adventurer take torch.', 'adventurer'], [('adventurer take torch.', 'adventurer take torch at general store.'), ('has money', 'item needed'), 'which is satisfied automatically.', 'adventurer'], [('adventurer take torch.', 'adventurer take torch at general store.'), ('There is a torch for sale at the general', 'fact_about_object'), 'which is satisfied automatically.', 'adventurer'], [('adventurer take torch.', 'adventurer take torch at general store.'), ('at general store', 'location'), 'adventurer walked to get to general store .', 'adventurer'], [('adventurer find maps.', 'adventurer find maps at library.'), ('There is a map at the library.', 'fact_about_object'), 'which is satisfied automatically.', 'adventurer'], [('adventurer find maps.', 'adventurer find maps at library.'), ('has books', 'item needed'), 'adventurer read books.', 'adventurer'], [('adventurer find maps.', 'adventurer find maps at library.'), ('at library', 'location'), 'adventurer walked to get to library .', 'adventurer'], [('adventurer read books.', 'adventurer read books at library.'), ('at library', 'location'), 'which is satisfied automatically.', 'adventurer'], [('adventurer read books.', 'adventurer read books at library.'), ('There is a book at the library.', 'fact_about_object'), 'which is satisfied automatically.', 'adventurer'], [('adventurer gather ingredients for a cure.', 'adventurer gather ingredients for a cure at forest.'), ('at forest', 'location'), 'which is satisfied automatically.', 'adventurer'], [('adventurer gather ingredients for a cure.', 'adventurer gather ingredients for a cure at forest.'), ('at forest', 'location'), 'which is satisfied automatically.', 'farmers'], [('adventurer gather ingredients for a cure.', 'adventurer gather ingredients for a cure at forest.'), ('has basket', 'item needed'), 'adventurer take basket.', 'adventurer'], [('adventurer gather ingredients for a cure.', 'adventurer gather ingredients for a cure at forest.'), ('at forest', 'location'), 'which is satisfied automatically.', 'herbalist'], [('adventurer gather ingredients for a cure.', 'adventurer gather ingredients for a cure at forest.'), ('at forest', 'location'), 'which is satisfied automatically.', 'witch'], [('adventurer take basket.', 'adventurer take basket at forest.'), ('at forest', 'location'), 'which is satisfied automatically.', 'adventurer'], [('adventurer take basket.', 'adventurer take basket at forest.'), ('There is a basket in the forest.', 'fact_about_object'), 'which is satisfied automatically.', 'adventurer'], [('adventure meet with a wise woman in the forest', 'adventure meet with a wise woman in the forest at forest.'), ('at forest', 'location'), 'which is satisfied automatically.', 'adventurer'], [('adventure meet with a wise woman in the forest', 'adventure meet with a wise woman in the forest at forest.'), ('at forest', 'location'), 'which is satisfied automatically.', 'wise woman'], [('adventurer investigate the abandoned mansion', 'adventurer investigate the abandoned mansion at abandoned mansion.'), ('at abandoned mansion', 'location'), 'adventurer walked to get to abandoned mansion .', 'adventurer'], [('adventurer investigate the abandoned mansion', 'adventurer investigate the abandoned mansion at abandoned mansion.'), ('has flashlight', 'item needed'), 'adventurer purchase flashlight.', 'adventurer'], [('adventurer purchase flashlight.', 'adventurer purchase flashlight at store.'), ('has money', 'item needed'), 'which is satisfied automatically.', 'adventurer'], [('adventurer purchase flashlight.', 'adventurer purchase flashlight at store.'), ('There is a flashlight for sale at the store', 'fact_about_object'), 'which is satisfied automatically.', 'adventurer'], [('adventurer purchase flashlight.', 'adventurer purchase flashlight at store.'), ('at store', 'location'), 'adventurer walked to get to store .', 'adventurer'], [('adventurer purchase flashlight.', 'adventurer purchase flashlight at store.'), ('at store', 'location'), 'which is satisfied automatically.', 'merchant'], [('adventure confront the werewolf pack leader', 'adventure confront the werewolf pack leader at werewolf den.'), ('at werewolf den', 'location'), 'adventurer walked to get to werewolf den .', 'adventurer'], [('adventure confront the werewolf pack leader', 'adventure confront the werewolf pack leader at werewolf den.'), ('has sword', 'item needed'), 'adventurer take sword.', 'adventurer'], [('adventure confront the werewolf pack leader', 'adventure confront the werewolf pack leader at werewolf den.'), ('at werewolf den', 'location'), 'which is satisfied automatically.', 'werewolf pack leader'], [('adventurer take sword.', 'adventurer take sword at weapon depot.'), ('There is a sword at a weapon depot.', 'fact_about_object'), 'which is satisfied automatically.', 'adventurer'], [('adventurer take sword.', 'adventurer take sword at weapon depot.'), ('has key', 'item needed'), 'adventurer steal key.', 'adventurer'], [('adventurer take sword.', 'adventurer take sword at weapon depot.'), ('at weapon depot', 'location'), 'adventurer walked to get to weapon depot .', 'adventurer'], [('adventurer steal key.', 'adventurer steal key at thieves den.'), ('There is a key at thieves den.', 'fact_about_object'), 'which is satisfied automatically.', 'adventurer'], [('adventurer steal key.', 'adventurer steal key at thieves den.'), ('at thieves den', 'location'), 'adventurer walked to get to thieves den .', 'adventurer'], [('adventurer steal key.', 'adventurer steal key at thieves den.'), ('has lockpicking tool', 'item needed'), 'adventurer purchase lockpicking tool.', 'adventurer'], [('adventurer purchase lockpicking tool.', 'adventurer purchase lockpicking tool at general store.'), ('has money', 'item needed'), 'which is satisfied automatically.', 'adventurer'], [('adventurer purchase lockpicking tool.', 'adventurer purchase lockpicking tool at general store.'), ('at general store', 'location'), 'which is satisfied automatically.', 'adventurer'], [('adventurer purchase lockpicking tool.', 'adventurer purchase lockpicking tool at general store.'), ('There is a lockpicking tool for sale at', 'fact_about_object'), 'which is satisfied automatically.', 'adventurer'], [('adventurer purchase lockpicking tool.', 'adventurer purchase lockpicking tool at general store.'), ('at general store', 'location'), 'which is satisfied automatically.', 'merchant'], [('adventure escort villagers to safety', 'adventure escort villagers to safety at village.'), ('at village', 'location'), 'which is satisfied automatically.', 'adventurer'], [('adventure escort villagers to safety', 'adventure escort villagers to safety at village.'), ('at village', 'location'), 'which is satisfied automatically.', 'villagers'], [('adventure escort villagers to safety', 'adventure escort villagers to safety at village.'), ('has weapons', 'item needed'), 'adventurer loot weapons.', 'adventurer'], [('adventure escort villagers to safety', 'adventure escort villagers to safety at village.'), ('has armor', 'item needed'), 'adventurer find armor OR adventurer acquire armor OR adventurer earn armor OR adventurer gain armor OR adventure.', 'adventurer'], [('adventurer find armor OR adventurer acquire armor OR adventurer earn armor OR adventurer gain armor OR adventure.', 'adventurer find armor OR adventurer acquire armor OR adventurer earn armor OR adventurer gain armor OR adventure at armor shop.'), ('has money', 'item needed'), 'which is satisfied automatically.', 'adventurer'], [('adventurer find armor OR adventurer acquire armor OR adventurer earn armor OR adventurer gain armor OR adventure.', 'adventurer find armor OR adventurer acquire armor OR adventurer earn armor OR adventurer gain armor OR adventure at armor shop.'), ('There is armor for sale at an armor', 'fact_about_object'), 'which is satisfied automatically.', 'adventurer'], [('adventurer find armor OR adventurer acquire armor OR adventurer earn armor OR adventurer gain armor OR adventure.', 'adventurer find armor OR adventurer acquire armor OR adventurer earn armor OR adventurer gain armor OR adventure at armor shop.'), ('at armor shop', 'location'), 'adventurer walked to get to armor shop .', 'adventurer'], [('adventurer loot weapons.', 'adventurer loot weapons at dungeon.'), ('There is a loot of weapons at the d', 'fact_about_object'), 'which is satisfied automatically.', 'adventurer'], [('adventurer loot weapons.', 'adventurer loot weapons at dungeon.'), ('at dungeon', 'location'), 'adventurer walked to get to dungeon .', 'adventurer'], [('adventure destroy the cursed artifact', 'adventure destroy the cursed artifact at abandoned mansion.'), ('at abandoned mansion', 'location'), 'which is satisfied automatically.', 'adventurer'], [('adventurer stop the curse from spreading to other villages', 'adventurer stop the curse from spreading to other villages at forest.'), ('at forest', 'location'), 'which is satisfied automatically.', 'adventurer']]
    visualize_plan(test_graph,"The Curse of the Werewolf",end='adventurer stop the curse from spreading to other villages')
    '''
    name = "all_admissible_action_trie"
    if os.path.exists(os.path.join(LIGHT_DIR, "data", "env", "%s.json"%name)) and os.path.exists(os.path.join(LIGHT_DIR, "data", "env", "%s.marisa"%name)):
        test_trie = MarisaTrie([],name=name)
        print(test_trie.get([-1,443, 908, 921, 411, 15937, 403, 8367, 886, 373, 278, 380, 7121]))  #expect []
        print(test_trie.get([-1,443, 908, 921, 411, 15937, 403, 8367, 886, 373, 278, 380]))  #expect [7121]
    '''
    
