from utils import format_prompt
from .llm import LLM
from huggingface_hub import hf_hub_download
from langchain.llms import LlamaCpp

class Llama2(LLM):
    def __init__(self) -> None:
        model_name_or_path = "TheBloke/Llama-2-13B-chat-GGML"
        model_basename = "llama-2-13b-chat.ggmlv3.q5_1.bin" # the model is in bin format
        model_path = hf_hub_download(repo_id=model_name_or_path, filename=model_basename)

        n_gpu_layers = 40  # Change this value based on your model and your GPU VRAM pool.
        n_batch = 512  # Should be between 1 and n_ctx, consider the amount of VRAM in your GPU.

        # Loading model,
        self.llm = LlamaCpp(
            model_path=model_path,
            max_tokens=1024,
            n_gpu_layers=n_gpu_layers,
            n_batch=n_batch,
            # callback_manager=callback_manager,
            verbose=True,
            n_ctx=4096, # Context window
            stop = ['Question:', 'Input:', 'USER:', 'User:', 'Human:', 'Person:'], # Dynamic stopping when such token is detected.
            temperature = 0.4,
        ) # type: ignore

    def get_response(self, prompt:str, **kwargs:str) -> str:
        '''
        return the response.
        '''
        prompt = format_prompt(prompt, **kwargs)
        return self.llm.predict(prompt)
    
    def print_response_stream(self, prompt:str, **kwargs:str) -> str:
        '''
        print the response in a stream, and return the response
        '''
        prompt = format_prompt(prompt, **kwargs)
        raise NotImplementedError('print_response_stream() not implemented.')
