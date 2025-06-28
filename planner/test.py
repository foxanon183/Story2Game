import requests

url = 'http://localhost:8889/api/llama2_13b_chat'
myobj = {
    "sentence": "What is 2 + 2?"
}

x = requests.post(url, json = myobj)

print(x)
print(x.text)