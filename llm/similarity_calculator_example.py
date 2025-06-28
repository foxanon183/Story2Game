from langchain.prompts.example_selector import SemanticSimilarityExampleSelector
from langchain.vectorstores import Chroma
from langchain.embeddings import OpenAIEmbeddings
from langchain.prompts import FewShotPromptTemplate, PromptTemplate
import os
from typing import Dict, List
current_dir:str= os.path.dirname(os.path.abspath(__file__))

openai_api_key = open(os.path.join(
    current_dir, 'openai_key.txt'), 'r').read().strip()

example_prompt = PromptTemplate(
    input_variables=["word"],
    template="{word}",
)

# Examples of a pretend task of creating antonyms.
examples:List[Dict[str, str]]= [
    {"word":"go to store"},
    {"word":"get store"},
    {"word":"give store"},
    {"word":"take store"},
    {"word":"make store"},
    {"word":"buy store"},
]

example_selector = SemanticSimilarityExampleSelector.from_examples(  # type: ignore
    # The list of examples available to select from.
    examples, 
    # The embedding class used to produce embeddings which are used to measure semantic similarity.
    OpenAIEmbeddings(openai_api_key=openai_api_key), 
    # The VectorStore class that is used to store the embeddings and do a similarity search over.
    Chroma, 
    # The number of examples to produce.
    k=1
)

example_selector.select_examples({"word":"walk to store"}) # type: ignore
