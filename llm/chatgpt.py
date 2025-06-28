import sys
sys.path.append("..")
from .llm import LLM
import time
import os
from openai import OpenAI
from typing import Dict, List
current_dir:str= os.path.dirname(os.path.abspath(__file__))
api_key=open(os.path.join(current_dir, 'openai_key.txt'), 'r').read().strip()
print(api_key)
client = OpenAI(
  api_key=open(os.path.join(
    current_dir, 'openai_key.txt'), 'r').read().strip(),  
)
#openai.api_key = open(os.path.join(
#    current_dir, 'openai_key.txt'), 'r').read().strip()
from utils import format_prompt

# TODO: Use Langchain
class ChatGPT(LLM):
    def __init__(self, model:str='gpt-3.5-turbo', delay_time:float=0.01, max_response_length:int=512, temperature:float=0.7, stateful:bool=False):
        self.messages:List[Dict[str,str]]= []
        self.model = model
        self.delay_time = delay_time
        self.max_response_length = max_response_length
        self.temperature = temperature
        self.stateful = stateful

    def get_response(self, prompt:str, **kwargs:str) -> str:
        prompt = format_prompt(prompt, **kwargs)
        if self.stateful:
            messages = self.messages
        else:
            messages = []
        model = self.model
        #print("MODEL IS: " + model)
        max_response_length = self.max_response_length
        temperature = self.temperature
        # ASK QUESTION
        messages.append({'role': 'user', 'content': prompt})
        # messages.append({'role': 'system', 'content': instruction})
        flag = True
        while flag:
            try:
                response = client.chat.completions.create(
                    model=model,
                    messages=messages,
                    max_tokens=max_response_length,
                    temperature=temperature,
                )
                flag = False
            except:
                if len(messages) == 1:
                    raise ValueError('OpenAI API is not working. Maybe the message is too long, the API key is invalid, or your internet connection is down.')
                messages = messages[1:]
        answer = response.choices[0].message.content # type: ignore
        assert isinstance(answer, str)
        messages.append({'role': 'assistant', 'content': answer})
        return answer
    
    def print_response_stream(self, prompt:str, **kwargs:str):
        prompt = format_prompt(prompt, **kwargs)
        if self.stateful:
            messages = self.messages
        else:
            messages = []
        model = self.model
        delay_time = self.delay_time
        max_response_length = self.max_response_length
        temperature = self.temperature
        # ASK QUESTION
        messages.append({'role': 'user', 'content': prompt})
        # messages.append({'role': 'system', 'content': instruction})
        flag = True
        while flag:
            try:
                response = openai.ChatCompletion.create(  # type: ignore
                    # CHATPG GPT API REQQUEST
                    model=model,
                    messages=messages,
                    max_tokens=max_response_length,
                    temperature=temperature,
                    stream=True,  # this time, we set stream=True
                )
                flag = False
            except Exception:
                if len(messages) == 1:
                    raise ValueError('OpenAI API is not working. Maybe the message is too long, the API key is invalid, or your internet connection is down.')
                messages = messages[1:]
        partial_answers:List[str] = []
        for event in response:  # type: ignore
            # RETRIEVE THE TEXT FROM THE RESPONSE
            event_text = event['choices'][0]['delta']  # EVENT DELTA RESPONSE  # type: ignore
            partial_answer = event_text.get('content', '')  # RETRIEVE CONTENT  # type: ignore
            assert isinstance(partial_answer, str), "Bug: partial answer is not a string"
            partial_answers.append(partial_answer)  # APPEND TO ANSWERS 

            # STREAM THE ANSWER
            print(partial_answer, end='', flush=True)  # Print the response
            time.sleep(delay_time)
        answer = ''.join(partial_answers)
        messages.append({'role': 'assistant', 'content': answer})
        print('')
        return answer

if __name__ == '__main__':
    llm = ChatGPT()
    while True:
        prompt = input()
        answer = llm.print_response_stream(prompt)

