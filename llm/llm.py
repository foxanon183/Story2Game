class LLM:
    def get_response(self, prompt:str, **kwargs:str) -> str:
        '''
        return the response.
        '''
        raise NotImplementedError('get_response() not implemented.')
    
    def print_response_stream(self, prompt:str, **kwargs:str) -> str:
        '''
        print the response in a stream, and return the response
        '''
        raise NotImplementedError('print_response() not implemented.')

