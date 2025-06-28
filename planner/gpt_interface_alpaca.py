import socket
import json
import time
#tcp_ip='localhost'
#tcp_port=1101
#s = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
#s.connect((tcp_ip,tcp_port))

def recvall(sock):
    print("HI")
    BUFF_SIZE = 4096 # 4 KiB
    data = b''
    while True:
        #print(data)
        #print(BUFF_SIZE)
        part = sock.recv(BUFF_SIZE)
        data += part
        if len(part)>0 and len(part) < BUFF_SIZE and part[-1]==125:
            # either 0 or end of data
            break
    return data

def get_semantic_similarity(text1,text2):
    d = {}
    d['text1']=text1
    d['text2']=text2 
    d['task']='semantic-similarity'
    data = json.dumps(d).encode('utf-8')
    s.send(data)
    response = recvall(s).decode('utf-8')
    return json.loads(response)['similarity'][0]

def get_score(text):
    d = {}
    d['text']=text
    d['task']='get-score'
    data = json.dumps(d).encode('utf-8')
    s.send(data)
    response = recvall(s).decode('utf-8')
    return json.loads(response)['score']

class tokenizerAPI():
    def __init__(self) -> None:
        self.id = 0
    def tokenize(self,prompt):
        d = {}
        d['prompt']=prompt
        d['task']='tokenize'
        data = json.dumps(d).encode('utf-8')
        s.send(data)
        response = recvall(s).decode('utf-8')
        return json.loads(response)['tokens']
    def detokenize(self,tokens):
        d = {}
        d['tokens']=tokens
        d['task']='detokenize'
        data = json.dumps(d).encode('utf-8')
        s.send(data)
        response = recvall(s).decode('utf-8')
        return json.loads(response)['text']

class gptAPI():
    def __init__(self) -> None:
        self.tokenizer = None
        self.id = 0

class GPTInterfaceAlpaca():
    def __init__(self) -> None:

        self.gpt = gptAPI()
        self.gpt.tokenizer = tokenizerAPI()

    def gpt_call(self,prompt,max_token,num_of_sentences,temperature=0.9, top_p=1.0, top_k=50, repetition_penalty=1.0):
        '''
        GPT-J API:
            returning multiple generated sentence if return_probability is False
            returning list of (samples, probability, tokens, logits) if return_probability is True. 
                samples is the generated sentence in text by default sampling method. (in this colab demo, batch size is 1, so only one sentence is returned)
                probability is a list of probability for each word in samples
                tokens is a list of tokens for each word in samples
                logits: list of numpy vector. posterior probability at each step given the previous tokens. It is probability not logits!!!!
        param context: prompt
        param num_of_sentences: number of sentence to generate
        param top_k (int, optional, defaults to model.config.top_k or 50 if the config does not set any value) — The number of highest probability vocabulary tokens to keep for top-k-filtering.
        param top_p (float, optional, defaults to model.config.top_p or 1.0 if the config does not set any value) — If set to float < 1, only the most probable tokens with probabilities that add up to top_p or higher are kept for generation.
        param temperature:  (float, optional, defaults to model.config.temperature or 1.0 if the config does not set any value) — The value used to module the next token probabilities.
        param max_token: num of tokens to generate
        param return_probability: if set to True, return list of (samples, probability, tokens, logits)
        '''
        #print("prompt:\n",prompt)
        d = {}
        d['prompt']=prompt
        d['task']='text-generation'
        d['maximum_tokens']=max_token
        d['num_return_sequences']=num_of_sentences
        d['top_k']=top_k
        d['top_p']=top_p
        d['temperature']=temperature
        d['return_logits']=False
        d['do_sample']=True
        d['repetition_penalty']=repetition_penalty
        data = json.dumps(d).encode('utf-8')
        s.send(data)
        response = recvall(s).decode('utf-8')
        return json.loads(response)['out']

    def get_next_token_score(self,prompt):
        d = {}
        d['prompt']=prompt
        d['task']='get-next-token-score'
        d['return_logits']=True
        data = json.dumps(d).encode('utf-8')
        s.send(data)
        response = recvall(s).decode('utf-8')
        #print(response)
        return json.loads(response)['scores']


if __name__ == "__main__":
    prompt = '''Below is an instruction that describes a task, paired with an input that provides further context. Write a response that appropriately completes the request.

### Instruction:
You are an RPG game plot writer. Given an task description, generate a list of items that the adventurer need in order to perform the task. if nothing is needed for the task, answer "nothing". Please separate the item names with comma.

### Input:
task description: adventurer investigate the first werewolf attack.

### Response:
item needed:'''
    prompt = '''Guess what items, tools, or materials are needed to perform certain action, if nothing is needed, answer "nothing". Here are some examples:

What items must be pocessed by adventurer before pick up a sword?
Answer: nothing

What items must be pocessed by adventurer before defeat Owen the dark wizard?
Answer: sword, armor

What items must be pocessed by adventurer before use magical item?
Answer: magical item

What items must be pocessed by adventurer before craft a sword?
Answer: iron, hammer, anvil

What items must be pocessed by adventurer before buy flower from marketplace?
Answer: money

What items must be pocessed by adventurer before investigate the first werewolf attack?
Answer:'''
    gpt = GPTInterfaceAlpaca()
    print(gpt.gpt_call(prompt, 5, 1,temperature=0.75))
    print(gpt.gpt_call(prompt, 10, 1,temperature=0.75))
    print(gpt.gpt_call(prompt, 5, 1,temperature=0.9))
    print(gpt.gpt_call(prompt, 10, 1,temperature=0.9))
    print(gpt.gpt_call(prompt, 5, 1,temperature=1.0))
    print(gpt.gpt_call(prompt, 10, 1,temperature=1.0))