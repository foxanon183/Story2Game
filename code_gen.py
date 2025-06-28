# Code Generation Module
import json
import os

#from logic_template import ActionTemplate
from dotenv import load_dotenv
from openai import OpenAI

load_dotenv()
client = OpenAI()

def call_llm(prompt, model="gpt-4o"):
    '''
    Make a call to whatever LLM we are using
    '''
    print("starting")
    completion = client.chat.completions.create(
        model=model,
        messages=[
            {"role": "system", "content": "You are a helpful assistant."},
            {"role": "user", "content": f"{prompt}"}
        ]
    )

    return completion.choices[0].message

def prompting_controller():
    '''
    Prompt the LLM multiple times until we get the output that we want
    '''
    with open("./code_gen_prompt.txt", "r") as f:
        prompt = f.read()
    
    response = call_llm(prompt)
    print(response)

# def generate_code():
#     '''
#     Generate the code based off of the LLM output
#     '''
#     with open("./ex_code_gen.json", "r") as f:
#         data = json.load(f)

#     my_actions = []
#     for action in data:
#         action = data['output']
#         my_actions.append(ActionTemplate(name=action['base_form'], operations=action["effect"], precondition=action["fundamental_preconditions"], description=action['display']))
    
#     print(my_actions)

if __name__ == "__main__":
    prompting_controller()
