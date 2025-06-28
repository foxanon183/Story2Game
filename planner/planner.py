
import json
from planner.util import *
from planner.prompt import *
from collections import defaultdict
import nltk
import torch 
import copy
from nltk.corpus import propbank
#from gpt_interface_alpaca import *
import tqdm
import copy
import argparse
import random
import glob
import sys
import requests
sys.path.append("..")
from llm.chatgpt import ChatGPT
chatgpt_model = 'gpt-3.5-turbo'

chatgpt = ChatGPT() # I sent the API key on Slack. create a file called openai_key.txt in the llm folder and put the key in it.
def chatgpt_call(prompt):
    return chatgpt.get_response(prompt)


TOKENIZER_INCLUDE_SOS = True    #ture for alpaca false for gpt-neox

import os
os.environ['TRANSFORMERS_CACHE'] = '/coc/flash5/aye42/transformers_cache/'

def print_no_buffer(*message, end='\n'):
    """If distributed is initialized print only on rank 0."""
    if torch.distributed.is_initialized():
        if torch.distributed.get_rank() == 0:
            print(*message, flush=True, end=end)
    else:
        print(*message, flush=True, end=end)

class gptPlanner:
    def __init__(self,gpt):
        '''
        param:
            all_objs/rooms: all_objects in Lighting/all rooms in Lighting
        '''
        self.quest_summary = ""
        self.main_quest_line = []
        self.gpt = gpt
        self.text = ""
        self.context_= ""
        self.explored = []
        self.knowledge_graph = []
        self.reasoning_graph = []
        self.banned_preconditions_map = defaultdict(list)
        self.ends = []
        self.open_conflict = []
        self.reusable_solutions = defaultdict(list)
        self.solution_difficulty = defaultdict(list)
    

    def get_syntax_prompting(self,sentence):
        result = self.gpt.gpt_call(prompt_get_syntax.replace('{$text1$}',sentence),10,1,temperature=0.5, top_p=0.1, top_k=1)[0].split('.')[0].strip()
        return result,sentence

    def try_expand_syntax(self, syntax):
        ret =  {'item':True,'location':True,'who':False,'how':False,'why':False,'negation':False}
        syntax,org_sentence = syntax
        result_location = self.gpt.gpt_call(prompt_syntax_location.replace('{$text1$}',syntax),10,1,temperature=0.5, top_p=0.1, top_k=10)[0].split('.')[0].strip()
        if result_location=="":
            result_location = syntax
        else:
            result_location = syntax+' '+result_location
        ret['location']=True 
        result_how = self.gpt.gpt_call(prompt_syntax_through_doing.replace('{$text1$}',org_sentence.replace('.','')),10,1,temperature=0.5, top_p=0.1, top_k=10)[0].split('.')[0].strip()
        if 'through ' in result_how and 'ing' in result_how and 'something' not in result_how:
            ret['how']=True 

        return ret

    def find_character_names(self,sentence):
        '''
        return the principal character's name
        '''
        
        npcs = self.gpt.gpt_call(extract_character_name_prompt.replace('{$text3$}',sentence),10,10,temperature=0.7)
        npcs = [s.split('</s>')[0].split('\n')[0] for s in npcs]
        npcs = most_common(npcs).split(',')
        npcs = [npc.strip().lower() for npc in npcs if npc.strip().lower() not in ['none','nobody','no one','nothing']]

        if 'adventurer' in npcs:
            npcs[npcs.index("adventurer")],npcs[0]=npcs[0],npcs[npcs.index("adventurer")]
        else:
            npcs = ['adventurer']+npcs

        return "adventurer",npcs
    
    def is_frequent_item_in_environment(self,item,environment):
        '''
        return true if the item is frequent in the environment
        '''
        if environment==[]:
            return False
        if item[:4]=='has ':
            item = item[4:].strip()
        environment = environment[0][1]
        if environment[:3]=="at ":
            environment = environment[3:].strip()
        prompt = get_prompt(default_item_in_environment_prompt,environment,item)
        result = self.gpt.gpt_call(prompt,1,10,temperature=0.9, top_p=0.1, top_k=2)
        result = most_common(result)
        # print_no_buffer("infering if",item,"is default in",environment,"result:",result)
        if result in [' yes','yes','Yes',' Yes','YES',' YES']:
            return True
        else:
            return False
        
    def backtrack(self,target,character,is_initial=True):
        '''
        backtrack, return the logic chain (context) that explains why a target event happen
        param target: target event
        already_contains_item_state: the number of item state contraints in all sub causal chains, used to terminate recursion.
        '''
        #print_no_buffer(target,character,'.')
        ids = []
        new_targets = []
        logic_chain = ""  #"To John was arrested. (John was arrested at his house. because  John's wife saw him taking drugs) , the person need to has police, which is solved by was arrested at his house."
        visited = []
        already_contains_item_state = 0
        target_ = target.replace('.','')
        self.banned_preconditions_map[(target_,character)] = []
        if (target_,character) not in self.banned_preconditions_map[(target_,character)]:
            self.banned_preconditions_map[(target_,character)].append((target_,character))
        preconditions = []
        for entry in self.knowledge_graph:
            if entry[2]==target and entry[3]==character:
                preconditions.append(entry[1])
        preconditions = list(set(preconditions))
        if is_initial:
            self.explored = [target_,target]
        for entry in self.knowledge_graph:
            if entry[1] in preconditions and entry[0][0] not in self.explored and entry[3]==character:
                self.explored.append(entry[0][0])
                logic_chain_next, pending_number_item_state = self.backtrack(entry[0][0],"adventurer",is_initial=False)
                already_contains_item_state += pending_number_item_state
                logic_chain+=logic_chain_next
                self.banned_preconditions_map[(target_,character)].extend(self.banned_preconditions_map[(entry[0][0].replace('.',''),entry[3])])
                self.banned_preconditions_map[(target_,character)].append((entry[1][0],entry[3]))
                self.banned_preconditions_map[(target_,character)] = list(set(self.banned_preconditions_map[(target_,character)]))
                if 'which is satisfied automatically.'!=entry[2] and entry[2]==target:
                    for entry_ in self.knowledge_graph:
                        if entry_[0][0]==entry[0][0] and entry_[3]==entry[3]:
                            logic_chain+='\nTo '+entry_[0][0]+' ('+entry_[0][1]+'), '+entry_[3]+' need to '+entry_[1][0]+', which is solved by '+entry_[2]+'.'
                    if entry[1][1]=='item state':
                        already_contains_item_state += 1


        return logic_chain, already_contains_item_state

        
    def forward_traverse(self,end):
        '''
        Used for coverting a DAG to a plan in text
        param end: end node of the plan (end[0] is the input to the pipeline)
        '''
        edges = [end]
        ids = []
        while len(edges)>0:
            #print_no_buffer(edges)
            edge = edges.pop(0)
            for id,node in enumerate(self.knowledge_graph):
                if id not in ids and edge==node[0][0]:
                    edges.append(node[3]+' '+node[2] if node[3]!=node[2].split(' ')[0].strip() else node[2])
                    ids.append(id)
        formated_output = '\n'.join(['To '+self.knowledge_graph[id][0][0]+' ('+self.knowledge_graph[id][0][1]+'), '+self.knowledge_graph[id][3]+' need to '+self.knowledge_graph[id][1][0]+', which is solved by '+self.knowledge_graph[id][2] for id in ids])
        return formated_output  

    def forward_fix_banned_preconditions(self,merge_point,banned_preconditions):
        '''
        forward check for cycle when a new branch is merged to an existing branch.
        update banned_precondition along its path. If a cycle is detect (a precondition that is banned show up in the existing branch), 
        break the cycle by discarding everything after the actions that requires that precondition (inclusively) and mark preconditions 
        of those actions on the edge as opening conflict
        param merge_point: a precondition where two branchs merge
        param banned_preconditions: banned_preconditions given by the new branch
        '''
        ids = []
        for id,node in enumerate(self.knowledge_graph):
            if id not in ids and merge_point[0]==node[1][0] and merge_point[1]==node[3]:
                ids.append(id)   #actions that require the first common precondition of the two branchs
        pending = []
        for id in ids:
            action = self.knowledge_graph[id][2].replace('.','')   
            character = self.knowledge_graph[id][3]
            self.banned_preconditions_map[(action,character)].extend(banned_preconditions)
            self.banned_preconditions_map[(action,character)] = list(set(self.banned_preconditions_map[(action,character)]))
            for node in self.knowledge_graph:
                if node[3]!=character:
                    continue
                if action==node[0][0].replace('.',''):
                    precondition = (node[1][0],node[3])
                    if precondition in self.banned_preconditions_map[(action,character)]:
                        for idx,entry in enumerate(self.knowledge_graph):
                            if entry[2].replace('.','')==action:
                                print_no_buffer("----forward_fix_banned_preconditions: roll back to:",[copy.deepcopy(entry[0]),copy.deepcopy(entry[1])])
                                self.open_conflict.append((copy.deepcopy(entry[0][0]),copy.deepcopy(entry[0][1]),copy.deepcopy(entry[1][0]),copy.deepcopy(entry[1][1])),copy.deepcopy(entry[3]))
                                self.knowledge_graph[idx][0] = ("Dummy Sink","Dummy Sink")
                                self.knowledge_graph[idx][1] = ("Dummy Sink","Dummy Sink")
                                self.knowledge_graph[idx][2] = "XXXXXXXXXX"
                    else:
                        pending.append((precondition,list(set(self.banned_preconditions_map[(action,node[3])]+[precondition]))))
        for next_precondition,next_banned_precondition in pending:
            #print_no_buffer(next_precondition)
            self.forward_fix_banned_preconditions(next_precondition,next_banned_precondition)

    
    def get_facts_and_check_ownership(self, sentence, obj, location):
        '''
        return a name of a person who owns the object
        '''
        
        facts_generation = 'There is '+self.gpt.gpt_call(get_prompt(fact_about_object_prompt,"","",sentence.replace('.','')+' '+location+'.',obj), 8, 1, top_p=0.6, top_k=4)[0].split('\n')[0]
        # print_no_buffer("facts about object: ",facts_generation)
        ownership = self.gpt.gpt_call(get_prompt(ownership_prompt,"","",facts_generation.split('.')[0]+'.',obj), 8, 1, top_p=0.6, top_k=4)[0].split('\n')[0].replace('.','').strip()
        return facts_generation,ownership


    def get_slots_gpt(self,sentence,context_,last_precondition_type, num_item_state_in_the_plan=0):
        '''
        filling slots (preconditions) given the action. We considered four type of preconditions "item needed", "reason"(why?), "location"(where?), "interaction with other person".
        param sentence: string. the action
        param context_: string. context that explains why the action is take
        '''
        sentence_ = str(sentence)
        syntax = self.get_syntax_prompting(sentence.replace('.',''))
        print_no_buffer("syntax:",syntax)
        #if syntax[0].count("somebody")>1 or syntax[0].count("someone")>1:
        character,characters = self.find_character_names(sentence)
        #else:
        ##    character,characters = "adventurer",['adventurer']
        characters = [ch.strip() for ch in characters]
        print_no_buffer('*****debug context*****')
        print_no_buffer("Character:",character, characters)
        print_no_buffer(sentence)
        print_no_buffer(context_)
        print_no_buffer('fill slot.. ',sentence)
        slot_flag = self.try_expand_syntax(syntax)
        #slot_flag['how']=False
        if len(sentence.split(' '))<4:
            sentence = ' '.join(sentence.split(' ')).replace('.','')+' '+self.gpt.gpt_call(context_+get_prompt(enrich_context_prompt,"",' '.join(sentence.split(' ')).replace('.',''),' '.join(sentence.split(' '))), 13, 1, top_p=0.9, top_k=40)[0].split('\n')[0].strip()
            print_no_buffer("Expand Sentence:",sentence)
        slot = {}
        slot['item needed'] = []
        slot['reason'] = []
        slot['interaction with other person'] = []
        slot['location'] = []
        slot['how']=[]
        map_from_slot_flag_key_to_precondition_type_key = {'how':'how','location':'location','item':'item needed','who':'interaction with other person','why':'reason'}
        for key in slot_flag:
            for entry in self.knowledge_graph:
                if key in map_from_slot_flag_key_to_precondition_type_key and entry[0][0]==sentence_ and entry[1][1]==map_from_slot_flag_key_to_precondition_type_key[key]:
                    slot_flag[key]=False
        if slot_flag['how']==True:
            
            how_result = self.gpt.gpt_call(get_prompt(how_to_get_to_goal_prompt,"","",' '.join(sentence.split(' ')).replace('.','')), 8, 15, temperature=0.9)
            how_result = post_process(how_result,remove_first_word=False,mode="gen_actions",to_avoid = sentence,action=sentence, must_have='adventurer', prefix="",separator='.',freq_threshold=15,simi_threshold=0.75,cutoff_frequency=2)
            if len(how_result)>0:    
                slot['how'] =  [(character,how_result[0])]

        if last_precondition_type == 'location':
            for key in slot_flag:
                slot_flag[key]=False
        print_no_buffer(slot_flag)
        if slot_flag['location']==True:
            slot['location'] = []
            for trial in range(4):
                sentence = str(sentence_)
                
                infered_location = self.gpt.gpt_call(get_prompt(parallel_precondition_location_prompt,"",characters[0].strip(),
                                            ' '+' '.join(sentence.strip().replace('.','').split(' ')[1:])), 8, 15, temperature=0.9,repetition_penalty=1.05)
                infered_location = post_process(infered_location,remove_first_word=False,mode="gen_preconditions", prefix="at",freq_threshold=8,simi_threshold=0.75,cutoff_frequency=2)
                location = infered_location
                
                if location!=[]:
                    for person in characters:
                        if person not in [l[0] for l in slot['location']]:
                            slot['location'].append((person,location[0]))
                if len(slot['location'])==len(characters):
                    break
        if slot_flag['item']==True:
            #obj_generated = self.infer_with_constrained_beam_search(context_+ get_prompt(parallel_precondition_item_prompt,
            #        "","",' '+' '.join(sentence.strip().replace('.','').split(' ')[1:]),character), gen_length=7, trie=self.all_objs_trie, temperature=0.75, repeatition_penalty=1.02)[0]
            cnt = 0
            while cnt<3:
                prefix = ' '+', '.join([s[4:] for s in slot['item needed']]) if len(slot['item needed'])>0 else ''
                if len(slot['location'])>0:
                    prompt = get_prompt(parallel_precondition_item_prompt,"",prefix,
                                                ' '+' '.join((sentence.replace('.','')+' '+slot['location'][0][1]).strip().split(' ')[1:]))
                else:
                    prompt = get_prompt(parallel_precondition_item_prompt,"",prefix,
                                                ' '+' '.join(sentence.strip().replace('.','').split(' ')[1:]))
                while True:
                    to_avoid = []
                    if sentence_ in self.solution_difficulty:
                        to_avoid = [precondition[0].replace('has','') for precondition in self.solution_difficulty[sentence_]]
                        print("to avoid items for generate item needed precondition:",to_avoid)
                    obj_generated = self.gpt.gpt_call(prompt, 8, 10, temperature=0.8,repetition_penalty=1.1)
                    obj_generated = post_process(obj_generated,separator=',', remove_first_word=False,mode="gen_preconditions", 
                                                 prefix="",freq_threshold=3,simi_threshold=0.85,cutoff_frequency=1, to_avoid = to_avoid)
                    if all([len(obj.split(' '))<5 for obj in obj_generated]):
                        break 
                    else:
                        print_no_buffer("regenerate item needed",obj_generated)
                if obj_generated==[]:
                    break
                else:
                    obj_generated = obj_generated[0].replace('.','').strip()
                if obj_generated in ['nothing','none','None','no','No','NO','None of them','none of them','Nothing','']:
                    break
                slot['item needed'].append('has'+obj_generated if obj_generated[0]==' ' else 'has '+obj_generated)
                cnt+=1

            slot['item needed'] = [("adventurer",item) for item in slot['item needed'] if ' no ' not in item]
            
        if slot_flag['who']==True:
            for i in range(3):
                if slot_flag['location']==True and slot['location']!=[]:
                    who_slot = self.gpt.gpt_call(context_+get_prompt(parallel_precondition_second_character_prompt,"","",' '.join(sentence.strip().replace('.','').split(' ')).split('.')[0]+'.'), 13, 15, top_p=0.5, top_k=40)
                else:
                    who_slot = self.gpt.gpt_call(context_+get_prompt(parallel_precondition_second_character_prompt,"","",' '.join(sentence.strip().replace('.','').split(' '))), 13, 15, top_p=0.5, top_k=40)
                slot['interaction with other person']=post_process(who_slot,prefix="",separator=';',must_not_contain = ')',
                                                        remove_first_word=False,mode="gen_actions",to_avoid = ' '.join(sentence.strip().replace('.','').split(' ')),lookup={},simi_threshold=0.95,freq_threshold=15)
                if slot['interaction with other person']!=[]:
                    slot['interaction with other person'] = [(character,interaction) for interaction in slot['interaction with other person'] if len(interaction)>0]
                    break
        if slot_flag['why']==True:
            reason = self.gpt.gpt_call(context_+get_prompt(parallel_reason_prompt,"","",' '.join(sentence.strip().replace('.','').split(' ')).replace('.','')), 8, 15, temperature=0.9)
            slot['reason']=post_process(reason,remove_first_word=False,mode="gen_actions",to_avoid = sentence,action=sentence, must_not_contain = 'of ',
                                        must_have='.', prefix="",separator='.',freq_threshold=15,simi_threshold=0.6)
            if len(slot['reason'])>0:
                slot['reason'] = [slot['reason'][0]] if all([k not in slot['reason'][0] for k in [' is ',' was ']]) else []
            if len(slot['reason'])>0:
                self.reasoning_graph.append([sentence_.strip().replace('.',''),slot['reason'][0]])
                slot['reason'] = [(character,slot['reason'][0])]
            #yield reason[0].strip(),"To "+end+", the person need to "+reason[0]+", which is solved by "+reason[0]+".\n",already_satisfied_preconditions
        if len(slot['location'])>0:
            return slot_flag, slot, sentence.replace('.','')+' '+slot['location'][0][1]+'.', character
        return slot_flag, slot, sentence, character

    def gpt_planner_get_open_conflict(self,end,lookup={},initial_state=[],iter=0):
        '''
        See the documentation at the beginning of this cell
        data struction:
            knowledge_graph: list[list[tuple(action, elaboration of action), tuple(precondtion, type of precondition), solution, character name]] 
            banned_preconditions_map: map{tuple(string,string)->list[tuple(string)]} [tuple(action,character):list[tuple(banned precondtions,character)]]
            knowledge_graph: list [tuple(action, elaboration of action), tuple(precondtion, type of precondition), solution, character name]
            self.open_conflict: list[list[action, elaboration of action, precondtion, type of precondition, character name]] 
            reasoning_graph: list[list[event, reason]]
            reusable_solutions: map{string->list[string]} [precondition: list of buffered candidate solutions]
        param end: the goal sentence
        param lookup: not used yet
        initial_state: list of string. Each item in initial_state is a clause that is satisfied for every characters by default. Example like "has money", "has car". It is used to end the recursion.
        '''
        self.open_conflict=[]
        end_ = str(end)
        character = "adventurer"

        #backtrack to produce context_ that help explain why current action is taken, also maintain banned_preconditions_map
        backtrack_result, num_item_state_in_the_plan = self.backtrack(end_.strip(),character)
        context_  = context_hint.replace('{$text1$}','\n'.join(['\n'.join([event[0]+' because '+event[1] for event in self.reasoning_graph if ('want' in event or 'need' in event)]),backtrack_result]))
        context_ = context_.replace('{$text2$}',self.quest_summary).replace('{$text3$}','\n'.join(self.main_quest_line))
        #print_no_buffer("context: ",context_,end_)
        last_precondition_type = None
        last_action_item_needed = None
        last_action = None
        last_precondition = ''
        for entry in self.knowledge_graph:
            if end==entry[2]:
                last_precondition_type = entry[1][1]
                last_precondition = entry[1][0]
                last_action = entry[0][0]
        for entry in self.knowledge_graph: 
            if last_action==entry[0][0] and entry[1][1]=='item needed':
                last_action_item_needed = entry[1][0]

        #Fill slots (candidate preconditions)
        slot_flag, slots_filtered, end, character = self.get_slots_gpt(end,context_,last_precondition_type, num_item_state_in_the_plan=num_item_state_in_the_plan)

        if last_precondition_type=='item state' and last_action_item_needed:
            slots_filtered['item needed'].append((character,last_action_item_needed))
        #initialize already_satisfied_preconditions
        already_satisfied_preconditions = [(str(entry),1,character) for entry in initial_state]
        for entry in self.knowledge_graph:
            # we don't want the same character to perform the same action twice in a plan as this is a greedy planner
            already_satisfied_preconditions.extend([(entry[0][0],0,entry[3]),(entry[0][1],0,entry[3]),(entry[1][0],1,entry[3]),(entry[2],0,entry[3])])  
        already_satisfied_preconditions = list(set(already_satisfied_preconditions))
        print_no_buffer("iteration goal: %s"%end)

        #what preconditions are not allowed to appear for currect node. banned_preconditions_map is maintained by backtrack
        banned_preconditions = self.banned_preconditions_map[(end_.replace('.',''),character)]
        print_no_buffer('banned_preconditions: ',banned_preconditions)
        
        print_no_buffer("Elaborating:",end)
        print_no_buffer(slots_filtered)
        candidate_preconditions = []
        for key in slots_filtered:
            candidate_preconditions.extend([(precondition,key) for precondition in slots_filtered[key]])
        if len(candidate_preconditions)==0:
            "No action is selected"," finished"
        print_no_buffer("-----candidate_preconditions:")
        print_no_buffer(candidate_preconditions)

        #find open preconditions. Part I
        #detect conflict
        self.no_conflict_flag = True
        fact_about_object = ''
        ownership_of_object = ''
        if last_precondition_type=='item needed' and len(slots_filtered['location'])>0:
            fact_about_object,ownership_of_object = self.get_facts_and_check_ownership(end_,last_precondition.replace('has ',''),slots_filtered['location'][0][1])
        for (precondition,precondition_type) in copy.deepcopy(candidate_preconditions):
            self.no_conflict_flag = True
            if precondition_type=='negation':
                self.no_conflict_flag = False
            for banned_precondition in banned_preconditions:
                #print_no_buffer("debug banned precondition:",banned_precondition,precondition)
                if banned_precondition[-1]!=precondition[0]:
                    continue
                similarity = cos_simi(precondition[1],banned_precondition[0])
                if precondition_type=='item needed' or precondition_type=='location':
                    if banned_precondition[0].split(' ')[0]!=precondition[1].split(' ')[0]:
                        continue
                    if similarity>0.75:
                        if last_precondition_type=='item needed' and cos_simi(precondition[1],last_precondition)>0.9:
                            #We recover some actions where the item belongs to the character because we want actions like "John get a book from the shelf at John's home" in our plan
                            #this helps to boost diversity.
                            #if ownership_of_object==character:
                            if True:  #in a text game we don't care if the item belongs to the character, namely, the character can take an item if the item is there
                                print_no_buffer("**recovered a deletion based on facts")
                                print_no_buffer(end_,ownership_of_object,fact_about_object,precondition,last_precondition)
                                if (precondition,precondition_type) in candidate_preconditions:
                                    candidate_preconditions.remove((precondition,precondition_type))
                                for entry_precondition in candidate_preconditions:
                                    if entry_precondition[1]=='item state':
                                        candidate_preconditions.remove(entry_precondition)
                                break
                        print_no_buffer("delete banned precondition 1: ",precondition,banned_precondition[0],similarity)
                        self.no_conflict_flag = False
                        break
                else:
                    if precondition_type == 'interaction with other person' and similarity>0.8:
                        if (precondition,precondition_type) in candidate_preconditions:
                            candidate_preconditions.remove((precondition,precondition_type))
                    elif similarity>0.8:
                        print_no_buffer("delete banned precondition 2: ",precondition,banned_precondition[0],similarity)
                        self.no_conflict_flag = False
                        break
            if self.no_conflict_flag==False and 'want' not in precondition[1] and 'need' not in precondition[1]:
                #if action is banned, we delect this action (entire node), gather its precondtions, find another way to satisfy the precondtion
                candidate_preconditions = []
                #delete previous action, collect entry from knowledge graph that starts with this action and collect entries whose solution is this action, add unsolved precondition caused by the deletion to the pending Q.
                index_to_remove = [idx for idx,entry in enumerate(self.knowledge_graph) if entry[0][0]==end_]
                temp = copy.deepcopy(self.knowledge_graph)
                self.knowledge_graph = [copy.deepcopy(temp[i]) for i in range(len(temp)) if i not in index_to_remove]
                self.reasoning_graph = [reason for reason in self.reasoning_graph if (end_.strip().replace('.','')!=reason[0] and end_.strip().replace('.','')!=reason[1])]
                index_to_pend_and_remove = [idx for idx,entry in enumerate(self.knowledge_graph) if entry[2]==end_]
                new_precondition_unsolved = [(self.knowledge_graph[i][0][0],self.knowledge_graph[i][0][1],self.knowledge_graph[i][1][0],self.knowledge_graph[i][1][1],
                                            self.knowledge_graph[i][3]) for i in index_to_pend_and_remove]
                self.open_conflict.extend(new_precondition_unsolved) 
                for i in range(len(new_precondition_unsolved)):
                    print_no_buffer("remove similar solution from reusable_solutions",new_precondition_unsolved[i][2],end_[5:].strip().replace('.',''))
                    to_remove_action = end_.strip().replace('.','')
                    if 'has ' in new_precondition_unsolved[i][2] or 'at ' in new_precondition_unsolved[i][2]:
                        to_remove_action = ' '.join(to_remove_action.split(' ')[1:])
                    self.reusable_solutions[(new_precondition_unsolved[i][2].strip(),new_precondition_unsolved[i][4])] = [solution for solution in self.reusable_solutions[(new_precondition_unsolved[i][2].strip(),new_precondition_unsolved[i][4])] if cos_simi(solution, to_remove_action)<0.75]
                temp = copy.deepcopy(self.knowledge_graph)
                if precondition_type!='negation':
                    self.knowledge_graph = [copy.deepcopy(temp[i]) for i in range(len(temp)) if i not in index_to_pend_and_remove]
                else:
                    print_no_buffer("add negation",precondition)
                    self.knowledge_graph.append([(end_,end),(precondition,'negation'),'which is satisfied automatically.',character])

                print_no_buffer("add unsolved precondition: ",new_precondition_unsolved)
                break
            
        #print_no_buffer("-----already_satisfied_preconditions:")
        #print_no_buffer(already_satisfied_preconditions)
        #for game project, if an item is normal to appear in the environment, we just assume it is there
        '''
        print_no_buffer("check if item is in the environment by default")
        temp_candidate_preconditions = []
        for precondition,precondition_type in candidate_preconditions:
            if precondition_type!='item needed':
                temp_candidate_preconditions.append((precondition,precondition_type))
            else:
                if self.is_frequent_item_in_environment(precondition[1],slots_filtered['location']):
                    self.knowledge_graph.append([(end_,end),(precondition[1],precondition_type),'which is satisfied automatically.',character])
                else:
                    temp_candidate_preconditions.append((precondition,precondition_type))
        candidate_preconditions = copy.deepcopy(temp_candidate_preconditions)
        '''
        


        for precondition,precondition_type in candidate_preconditions:
            no_match_flag = True
            to_merge_node = None
            for already_satisfied_precondition in already_satisfied_preconditions:
                if already_satisfied_precondition[-1]!=precondition[0]:
                    continue
                similarity = cos_simi(precondition[1],already_satisfied_precondition[0])
                #merge duplicate precondition
                if 'has '==precondition[1][:4] or 'at '==precondition[1][:3]:
                    if similarity>0.9:
                        print_no_buffer("merge duplicate precondition 1: ",precondition[1],already_satisfied_precondition[0],similarity)
                        no_match_flag = False
                        to_merge_node = copy.deepcopy(already_satisfied_precondition)
                        break
                else:
                    if similarity>0.8:
                        print_no_buffer("merge duplicate precondition 2: ",precondition[1],already_satisfied_precondition[0],similarity)
                        no_match_flag = False
                        to_merge_node = copy.deepcopy(already_satisfied_precondition)
                        break
            if no_match_flag and 'want' not in precondition[1] and ('need' not in precondition[1] or precondition_type=='item state'):
                self.open_conflict.append((end_,end,precondition[1],precondition_type,precondition[0]))
            else:
                #fix conflict caused by merging
                #forward_fix_banned_preconditions(precondition[1],list(set(banned_preconditions+[(precondition[1],precondition[0])])))
                if to_merge_node:
                    self.knowledge_graph.append([(end_,end),(to_merge_node[0],precondition_type),'which is satisfied automatically.',precondition[0]])
                else:
                    self.knowledge_graph.append([(end_,end),(precondition[1],precondition_type),'which is satisfied automatically.',precondition[0]])
                #yield "","","",True

        
        if fact_about_object!='' and len(candidate_preconditions)>0:
            self.knowledge_graph.append([(end_,end),(fact_about_object,'fact_about_object'),'which is satisfied automatically.',character])
        '''if len(candidate_preconditions)>0 and (last_precondition_type=='item needed' or last_precondition_type=='location'):
            double_negation = get_double_negation(end_)[0]
            self.knowledge_graph.append([(end_,end),(double_negation,'fact_about_object'),'which is satisfied automatically.',character])'''
        self.open_conflict = list(set(self.open_conflict))
        print_no_buffer("open conflict:",self.open_conflict)
        self.context_ = context_

        #self.knowledge_graph = [entry for entry in self.knowledge_graph if entry[1][1]!='negation' or cos_simi(entry[0][0],end_)<0.7]

        #find next actions (solutions) to take given open preconditions
        #actions for "item needed" are buffered and will be reused if the action is delected for causing a conflict
    def gpt_planner_get_actions(self,lookup={},iter=0):
        '''
        See the documentation at the beginning of this cell
        data struction:
            knowledge_graph: list[list[tuple(action, elaboration of action), tuple(precondtion, type of precondition), solution, character name]] 
            banned_preconditions_map: map{tuple(string,string)->list[tuple(string)]} [tuple(action,character):list[tuple(banned precondtions,character)]]
            knowledge_graph: list [tuple(action, elaboration of action), tuple(precondtion, type of precondition), solution, character name]
            self.open_conflict: list[list[action, elaboration of action, precondtion, type of precondition, character name]] 
            reasoning_graph: list[list[event, reason]]
            reusable_solutions: map{string->list[string]} [precondition: list of buffered candidate solutions]
        param end: the goal sentence
        param lookup: not used yet
        initial_state: list of string. Each item in initial_state is a clause that is satisfied for every characters by default. Example like "has money", "has car". It is used to end the recursion.
        '''
        
        while len(self.open_conflict)!=0:
            original_sentence, expanded_sentence,selected_precondition,selected_precondition_type, character_  = self.open_conflict[0]
            self.open_conflict.pop(0)
            if character_!="adventurer":
                self.knowledge_graph.append([(original_sentence,expanded_sentence),(selected_precondition,selected_precondition_type),'which is satisfied automatically.',character_])
                continue
            print_no_buffer("selected_precondition for (%s):"%original_sentence)
            print_no_buffer(selected_precondition+' to '+' '.join(original_sentence.split(' ')[1:]))
            candidate_actions_filtered = []
            #print_no_buffer(reusable_solutions,(selected_precondition.strip(), character_))
            print_no_buffer("buffered solution for "+character_+" "+selected_precondition+":",self.reusable_solutions[(selected_precondition.strip(), character_)])
            if len(self.reusable_solutions[(selected_precondition.strip(), character_)])>0:
                if selected_precondition_type=='interaction with other person':
                    continue
                candidate_actions_filtered = copy.deepcopy(self.reusable_solutions[(selected_precondition.strip(), character_)])
            else:
                satisfy_flag=False
                print_no_buffer("-----candidate_actions:")
                while satisfy_flag==False:
                    if selected_precondition_type=='item needed' or selected_precondition_type=='location' or selected_precondition_type=='item state':
                        if selected_precondition_type=='item needed':
                            print_no_buffer(get_prompt(action_prompt_obtain_item,' '.join(expanded_sentence.split(' ')[0:]).strip(),character_,preprocess(selected_precondition+'?')))
                            gpt_generated_actions = self.gpt.gpt_call(self.context_+get_prompt(action_prompt_obtain_item,' '.join(expanded_sentence.split(' ')[0:]).strip(),character_,preprocess(selected_precondition+'?')),
                                                                    30, 20, temperature=0.9,repetition_penalty=1.0)
                            candidate_actions = post_process(gpt_generated_actions,'.',match_lemma_threshold=0.8,
                                            mode="gen_actions",must_have='', to_avoid = ' '.join(original_sentence.split(' ')[1:]),action=preprocess(selected_precondition), simi_threshold=0.9,freq_threshold=3,exclude_go_to=not 'at ' in selected_precondition, cutoff_frequency=1)
                            
                        if selected_precondition_type=='location':
                            candidate_actions = [character_+' walked to get to '+selected_precondition.replace('at ','')+'.']
                            
                        if selected_precondition_type=='item state':
                            gpt_generated_actions = self.gpt.gpt_call(get_prompt(object_state_to_action_prompt,"",character_,original_sentence,selected_precondition),12, 5, temperature=0.75)
                            candidate_actions = post_process(gpt_generated_actions,'.',
                                            mode="gen_actions",must_have='', to_avoid = ' '.join(original_sentence.split(' ')[1:]),action=selected_precondition, simi_threshold=0.9,freq_threshold=3,exclude_go_to=not 'at ' in selected_precondition, cutoff_frequency=1)
                        
                    else:
                        candidate_actions = [selected_precondition]
            
                    if len(candidate_actions)==0:
                        continue
                
                    candidate_actions_filtered = []
                    print_no_buffer("debug candidate_actions:",candidate_actions,selected_precondition)
                    for candidate_action in candidate_actions:
                        if character_.lower().strip() != candidate_action.strip().split(' ')[0].lower().strip():
                            candidate_action = character_+' '+candidate_action.strip()
                        if selected_precondition[0:3]=='has': 
                            candidate_actions_filtered.append(fix_missing_object(candidate_action,selected_precondition[4:]))
                        elif selected_precondition[0:2]=='at':
                            candidate_actions_filtered.append(fix_missing_object(candidate_action,selected_precondition[3:]))
                        else:
                            candidate_actions_filtered.append(candidate_action)

                    candidate_actions_filtered = choose_best_action_by_perplexity(selected_precondition,candidate_actions_filtered,expanded_sentence,character_)[1]
                    
                    if len(candidate_actions_filtered)==0:
                        continue
                    else:
                        satisfy_flag = True
                        break

                self.reusable_solutions[(selected_precondition.strip(), character_)] = copy.deepcopy(candidate_actions_filtered)

            print_no_buffer("candidate_actions_filtered:",candidate_actions_filtered)
            #selected_action = choose_best_action_by_perplexity(selected_precondition,candidate_actions_filtered).strip()
            selected_action = candidate_actions_filtered[0] #choose_best_action_by_perplexity(selected_precondition,actions,parent_action,character)[0]
            selected_action = selected_action.strip()
            print_no_buffer("selected_action for (%s):"%selected_precondition)
            if selected_precondition_type=='interaction with other person':
                character_ = self.find_character_names(selected_action)[0]
            elif character_.lower()!=selected_action.split(' ')[0].lower():
                selected_action = character_+' '+selected_action
            selected_action = selected_action.replace('.','')
            print_no_buffer(selected_action)
            if selected_precondition_type=='item needed':
                annotated_sentence = self.gpt.gpt_call(extract_entities_prompt.replace('{$text1$}',selected_action),30, 1, temperature=0.9)[0].split('\n')[0].strip()
                annotated_sentence = annotated_sentence.replace('</s>','').replace('<s>','').replace('\n','')
                start_of_entity = -1
                annotated_sentence_enhanced = ""
                cnt_entity_types = {'object':1,'room':1,'npc':1}
                for i in range(len(annotated_sentence)):
                    if annotated_sentence[i]=='[':
                        start_of_entity=i+1
                    elif annotated_sentence[i]==']':
                        prefix = ""
                        entity = annotated_sentence[start_of_entity:i].strip().lower() # example: the adventurer
                        if 'adventurer' not in entity:
                            # remove a, the, A, The
                            for to_replace  in ['a ','the ','A ','The ']:
                                if entity[:len(to_replace)]==to_replace:
                                    entity = entity[len(to_replace):]
                            for _ in range(5):
                                prefix = self.gpt.gpt_call(get_prompt(find_entity_type_prompt,entity,'',''), 1, 10, top_p=0.5, top_k=40)
                                prefix = post_process(prefix, cutoff_frequency=8)
                                if len(prefix)==0:
                                    continue
                                else:
                                    prefix = prefix[0].strip()
                                if prefix in cnt_entity_types:
                                    break
                            if not prefix in cnt_entity_types:
                                prefix = 'object'  # default
                            annotated_sentence_enhanced = annotated_sentence_enhanced+'{'+prefix+str(cnt_entity_types[prefix])+'}'
                            cnt_entity_types[prefix]+=1
                        start_of_entity = -1
                    elif start_of_entity==-1:
                        annotated_sentence_enhanced = annotated_sentence_enhanced+annotated_sentence[i]
                print("annotated_sentence_enhanced:",annotated_sentence_enhanced)
                for _ in range(4):
                    chatgpt_generated_action_template = chatgpt_call(action_generation_unit_test_prompt.replace('$text1$',annotated_sentence_enhanced)).split('\n\n')[0]
                    print("chatgpt_generated_action_template:",chatgpt_generated_action_template)
                    effects = [line for line in chatgpt_generated_action_template.split('\n') if 'effect' in line]
                    # detect Move {object1} to {inventory}
                    if len(effects)>0:
                        break
                if not ' to {inventory}' in effects[0]:
                    print("Confliction: No effect that moves necessary item is detected for ",selected_action)
                    self.solution_difficulty[original_sentence].append([selected_precondition, selected_precondition_type, selected_action, character_])
                    if original_sentence[-1]=='.':
                        original_sentence = original_sentence[:-1]
                    yield original_sentence, character_,selected_precondition_type,False
            if self.no_conflict_flag == True:
                self.knowledge_graph.append([(original_sentence,expanded_sentence),(selected_precondition,selected_precondition_type),selected_action+'.',character_])
                if original_sentence in self.next_action_location_constraints and original_sentence in self.cur_action_open_precondition_constraints and selected_precondition==self.cur_action_open_precondition_constraints[original_sentence][2]:
                    self.knowledge_graph.append([(selected_action+'.',selected_action+' '+self.next_action_location_constraints[original_sentence]+'.'),
                                                (self.next_action_location_constraints[original_sentence],"location"),
                                                character_+' walked to get to '+self.next_action_location_constraints[original_sentence].replace('at ','')+'.',character_])
                yield selected_action, character_,selected_precondition_type,self.no_conflict_flag

    def interactively_modify_preconditions(self,end):
        inds = []
        for i,entry in enumerate(self.knowledge_graph):
            if entry[1]==end:
                inds.append(i)
        print("*******************************")
        print("Current Action:")
        print(self.knowledge_graph[i][1],self.knowledge_graph[i][2])
        print("Precondtions:")
        for i in inds:
            print(i,":",self.knowledge_graph[i][4],self.knowledge_graph[i][3])

        ####################################################
        # Your code for interactively change precondtions
        #

        #TODO:Your code for interactively change precondtions
        #
        #####################################################

    def reward_events_gen(self,end,admissible_actions):
        '''
        param: end: the end of the story. The final goal
        param: admissible_actions: dict[string,list[string]]. A dict that maps location name (e.g. 'at castle') to a list of 
            actions that can be performed in that location (given everything that has happened in the plan, e.g. ['pick up sword','drop sword']).
            Note that keys in admissible_actions must cover all locations that show up in the plan generated by the pipeline function despite that the test case
            in __main__ only test limited locations.
        function: remove inadmissible actions and rebuild plan using admissible_actions. The location will of the regenerated action will be the same as the action 
            being removed. (e.g. old action: {action: get swords, location: at castle} -> new action: {action: pick up swords, location: at castle}) Also, every proceeding
            actions of the new action (pick up swords) will be generated and there is no guarentee that every proceeding actions of the new action will be admissible.
        '''
        self.admissible_actions = admissible_actions
        self.revise_plan_according_to_admissible_actions(end,admissible_actions)


    def revise_plan_according_to_admissible_actions(self,end,admissible_actions):
        admissible_actions_location=[]
        next_actions = []
        location = None
        last_action_index = []
        for idx,entry in enumerate(self.knowledge_graph):
            if entry[2]==end:
                last_action_index.append(idx)
                
            if entry[0][0]==end:
                if entry[1][1]=="location":
                    location = entry[1][0]
                    if entry[1][0] in admissible_actions:
                        admissible_actions_location = admissible_actions[entry[1][0]]
                else:
                    next_actions.append(entry[2])

        if admissible_actions_location!=[] and end not in admissible_actions_location:
            print_no_buffer("***removing inadmissible action",end,admissible_actions_location)
            for idx in last_action_index:
                self.next_action_location_constraints[self.knowledge_graph[idx][0][0]] = location
                self.cur_action_open_precondition_constraints[self.knowledge_graph[idx][0][0]] = (self.knowledge_graph[idx][0][0],self.knowledge_graph[idx][0][1],
                                                                                                   self.knowledge_graph[idx][1][0],self.knowledge_graph[idx][1][1],self.knowledge_graph[idx][3])
                end_to_regenerate = str(self.knowledge_graph[idx][0][0])
                self.knowledge_graph[idx][0] = ("Dummy Sink","Dummy Sink")
                self.knowledge_graph[idx][1] = ("Dummy Sink","Dummy Sink")
                self.knowledge_graph[idx][2] = "XXXXXXXXXX"
                self.ends = [end_to_regenerate]
                self.iterative_gpt_planner_from_existing_plan(end_to_regenerate)
        else:
            for next_action in next_actions:
                self.revise_plan_according_to_admissible_actions(next_action,admissible_actions)


            

    def iterative_gpt_planner(self,iterations=10,initial_state=['has silver','has money']):
        '''
        See the documentation at the beginning of this cell
        param end: the goal sentence
        param iterations: how many iterations until we cut the recursion
        initial_state: list of string. Each item in initial_state is a clause that is satisfied for every characters by default. Example like "has money", "has car". It is used to end the recursion.
        '''
        self.reusable_solutions = defaultdict(list)
        self.text = ""
        self.initial_state = initial_state
        self.banned_preconditions_map = defaultdict(list)
        
        self.knowledge_graph = []
        self.next_action_location_constraints = {}
        self.cur_action_open_precondition_constraints = defaultdict(list)
        self.reasoning_graph = []
        for i,quest_object in enumerate(self.main_quest_line):
            if i > 1:
                self.knowledge_graph.append([(quest_object,quest_object),(self.main_quest_line[i - 1],"how"),self.main_quest_line[i - 1],"adventurer"])
        text = ''
        knowledge_graph = []
        for quest_object in self.main_quest_line:
            self.ends = [quest_object]
            self.banned_preconditions_map[quest_object]=[]
            text,knowledge_graph = self.iterative_gpt_planner_from_existing_plan(quest_object,iterations=iterations,initial_state=initial_state)
        return text,knowledge_graph

    def iterative_gpt_planner_from_existing_plan(self,end,iterations=10,initial_state=['has silver','has money']):
        '''
        See the documentation at the beginning of this cell
        param end: the goal sentence
        param iterations: how many iterations until we cut the recursion
        initial_state: list of string. Each item in initial_state is a clause that is satisfied for every characters by default. Example like "has money", "has car". It is used to end the recursion.
        '''
        end_ = str(end)
        terminate = False
        for iter in range(iterations):
            #print_no_buffer("knowledge graph:")
            #print_no_buffer(self.knowledge_graph)
            new_ends = []
            time_out = 0
            while len(self.ends)!=0:
                print_no_buffer('****edges: ',self.ends)
                end = self.ends.pop(0)
                if end in self.cur_action_open_precondition_constraints:
                    if self.cur_action_open_precondition_constraints[end] not in self.open_conflict:
                        self.open_conflict.append(self.cur_action_open_precondition_constraints[end])
                else:       
                    self.gpt_planner_get_open_conflict(end,initial_state=initial_state,iter=iter)
                planner = self.gpt_planner_get_actions(iter=iter)
                out = list(planner)
                if len(out)==0:
                    continue
                for o in out:
                    # o: selected_action, character_,selected_precondition_type,self.no_conflict_flag
                    if o[-1]==False:
                        if time_out<=5:
                            if o[2]=='interaction with other person':
                                self.ends.insert(0,(o[0]+'.').strip())
                            else:
                                if  o[1]+' ' not in o[0]:
                                    self.ends.insert(0,(o[1]+" "+o[0]+'.').strip())
                                else:
                                    self.ends.insert(0,(o[0]+'.').strip())
                            time_out+=1
                            print_no_buffer("----------------try to fix cycle: %i--------------"%time_out)
                        else:
                            self.knowledge_graph = [node for node in self.knowledge_graph if node[0][0]!=end]
                            time_out=0
                    elif len(o[0])>0:
                        new_ends.append(o)
            self.ends = []
            print_no_buffer("--------Iteration %i--------"%iter)
            for action,character,action_type,self.no_conflict_flag in new_ends:
                if len(action)!=0:
                    if action_type=='interaction with other person':
                        self.ends.append((action+'.').strip())
                    else:
                        if  character+' ' not in action:
                            self.ends.append((character+" "+action+'.').strip())
                        else:
                            self.ends.append((action+'.').strip())
            self.ends = list(set(self.ends))
            print_no_buffer(self.ends)
            if len(self.ends)==0:
                break
            if terminate:
                break
        self.text = self.forward_traverse(end_)
        print_no_buffer("banned precondition map:")
        print_no_buffer(self.banned_preconditions_map)
        print_no_buffer("full text:")
        print_no_buffer(self.text)
        # print_no_buffer("\n\nfinal text:")
        # [print_no_buffer(s) for s in self.text.split('\n') if 'automatic' not in s]
        return self.text.split('\n'),copy.deepcopy(self.knowledge_graph)

#Start: 

    def pipeline(self,title, main_quest_line=[],quest_summary="",iterations=5,initial_state=['has money','has gold','has silver'], path='../result'):
        self.context_= ""
        self.main_quest_line = main_quest_line
        self.quest_summary = quest_summary
        self.explored = []
        # return game logics, game map, a plot graph (knowledge graph)
        plan,graph = self.iterative_gpt_planner(iterations=iterations,initial_state=initial_state)
        print_no_buffer(plan)
        print_no_buffer(graph)
        game_logics,map = visualize_plan(graph,title=title.replace('.','').replace(' ','_').strip(),end=self.main_quest_line[-1], path=path)
        return game_logics,map,graph
            

if __name__=="__main__":
    #from gpt_interface import GPTInterfaceNeox20B
    #from gpt_interface_alpaca import GPTInterfaceAlpaca
    #gpt = GPTInterfaceAlpaca()
    from llm.chatgpt import ChatGPT
    gpt = ChatGPT("gpt-4o-mini", temperature = 0)
    plan_generator = None
    for file in glob.glob('./skeleton/*.json'):
        print(file)
        if plan_generator is not None:
            del plan_generator
        plan_generator = gptPlanner(gpt)
        with open(file, 'r', encoding='utf8') as f:
            config = json.load(f)
        title = config['title']
        test_main_quest_line = config['subquest']
        quest_summary = config['description']
        plan_generator.pipeline(title, test_main_quest_line,quest_summary)
    
#     title = "The Curse of the Werewolf"
#     test_main_quest_line = ['adventurer investigate the first werewolf attack.', 'adventurer speak with the village elders.', 
#                             'adventurer find the werewolf den.', 'adventurer gather ingredients for a cure.',
#                             'adventure meet with a wise woman in the forest', 'adventurer investigate the abandoned mansion',
#                             'adventure confront the werewolf pack leader', 'adventure escort villagers to safety',
#                             'adventure destroy the cursed artifact', 'adventurer stop the curse from spreading to other villages']
#     quest_summary = '''The Curse of the Werewolf: A village is plagued by a curse that turns people into werewolves. You must find the source of the curse and lift it before it spreads to other villages.
# Investigate the first werewolf attack: Your quest begins by investigating the first werewolf attack in the village. Talk to witnesses, gather clues, and try to piece together what happened.'''
#     
    # title = config['title']
    # test_main_quest_line = config['subquest']
    # quest_summary = config['description']
    # plan_generator.pipeline(title, test_main_quest_line,quest_summary)

    
    #test_main_quest_line = ["adventurer find the entrance to the dungeon by searching for clues and speaking to locals who may have information.",
    #                        "adventurer navigate through the dungeon's maze-like corridors",
    #                        "adventurer solve puzzles and riddles that guard the entrance to the artifact's chamber.",
    #                        "adventurer fight off monsters that guard the artifact, including giant spiders, undead warriors, and powerful elemental beings.",
    #                        "adventurer Retrieve the artifact.",
    #                        "adventurer Escape the dungeon before it collapses."]
    ##quest_summary = '''the Lost Artifact: You must venture deep into a dangerous dungeon to retrieve a powerful artifact that was lost centuries ago. Beware of traps, puzzles, and monsters that guard the artifact.'''
    #plan_generator.pipeline(test_main_quest_line,quest_summary)
    #
    #test_main_quest_line = ["adventurer gather information about the dragon's location and behavior.","adventurer acquire the necessary equipment",
    #                        "adventurer assemble a team.","adventurer plan your attack.", "adventurer track the dragon", "adventurer fight the dragon",
    #                        "adventurer slay the dragon","adventurer claim the dragon's treasure"]
    #quest_summary = '''The Dragon Hunt: A fierce dragon has been terrorizing nearby villages, burning crops and stealing livestock. You must hunt down the dragon and slay it to save the villages.'''
    #plan_generator.pipeline(test_main_quest_line,quest_summary)


    exit()
