import json
from typing import Any, Dict, Tuple, List, Union
import re
import ast
import hashlib
import nltk # type: ignore
from settings import DEBUG

def string_to_ansi_color_code(input_string: str):
    # Create an MD5 hash of the input string
    hash_obj = hashlib.md5(input_string.encode())
    hash_hex = hash_obj.hexdigest()

    # Convert the first 6 characters of the hash to RGB
    red = int(hash_hex[0:2], 16)
    green = int(hash_hex[2:4], 16)
    blue = int(hash_hex[4:6], 16)

    # Compute the luminance
    luminance = 0.2126 * red/255 + 0.7152 * green/255 + 0.0722 * blue/255

    # Adjust the color if it's too dark
    MIN_LUMINANCE = 0.0722
    if luminance < MIN_LUMINANCE:
        scale_factor = MIN_LUMINANCE / luminance
        red = min(255, int(red * scale_factor))
        green = min(255, int(green * scale_factor))
        blue = min(255, int(blue * scale_factor))

    return f"\033[38;2;{red};{green};{blue}m"

def print_colored_string(input_string: str):
    color_code = string_to_ansi_color_code(input_string)
    end_code = "\033[0m"  # Reset to default
    print(f"{color_code}{input_string}{end_code}")

def log(tag: str, message: str) -> None:
    """
    Logs a message.

    Args:
        tag (str): The tag of the message.
        message (str): The message to log.
    """
    if not DEBUG:
        return
    color_code = string_to_ansi_color_code(tag)
    end_code = "\033[0m"  # Reset to default
    print(f"{color_code}{tag}: {message}{end_code}")

def to_lower_bound_kebab_case(s: str) -> str:
    """
    Converts the given string to lower bound kebab case.

    Args:
        s (str): The string to convert.

    Returns:
        str: The converted string.
    """
    return s.lower().strip().replace(" ", "-").replace("_", "-")

def to_lower_bound_snake_case(s: str) -> str:
    """
    Converts the given string to lower bound snake case.

    Args:
        s (str): The string to convert.

    Returns:
        str: The converted string.
    """
    return s.lower().strip().replace("-", "_").replace(" ", "_")

def to_upper_bound_snake_case(s: str) -> str:
    """
    Converts the given string to upper bound snake case.

    Args:
        s (str): The string to convert.

    Returns:
        str: The converted string.
    """
    return s.upper().strip().replace("-", "_").replace(" ", "_")

def replace_placeholders(commands: str, arguments: Union[Dict[str, str], Dict[str, List[str]], Dict[str, Union[str, List[str]]]]) -> str:
    for key, value in arguments.items():
        if isinstance(value, list):
            value = ';'.join(value)
        pattern = r'(?<=[{\s"])(%s)(?=[.\s"}])' % re.escape(key)
        commands = re.sub(pattern, value, commands)
    return commands

def remove_extra_spaces(s:str) -> str:
    s = re.sub(r'\s+', ' ', s)
    return s.strip()

def to_literal(argument:str) -> Tuple[bool, Any]:
    argument = remove_extra_spaces(argument)
    if argument.lower() == 'true':
        return True, True
    elif argument.lower() == 'false':
        return True, False
    elif argument.lower() in ['none', 'null']:
        return True, None
    try:
        return True, ast.literal_eval(argument)
    except (ValueError, SyntaxError):
        return False, argument

class bcolors:
    HEADER = '\033[95m'
    OKBLUE = '\033[94m'
    OKCYAN = '\033[96m'
    OKGREEN = '\033[92m'
    WARNING = '\033[93m'
    FAIL = '\033[91m'
    ENDC = '\033[0m'
    BOLD = '\033[1m'
    UNDERLINE = '\033[4m'
    
def print_debug(s: Any, tag:str='') -> None:
    """
    Prints a debug message.

    Args:
        s (str): The message to print.
        tag (str): The tag of the message.
    """
    if tag:
        print(f"{bcolors.OKBLUE}{tag}: {s}{bcolors.ENDC}")
    else:
        print(f"{bcolors.OKBLUE}{s}{bcolors.ENDC}")
    
def print_warning(s: Any, tag:str='') -> None:
    """
    Prints a warning message.

    Args:
        s (str): The message to print.
        tag (str): The tag of the message.
    """
    if tag:
        print(f"{bcolors.WARNING}{tag}: {s}{bcolors.ENDC}")
    else:
        print(f"{bcolors.WARNING}{s}{bcolors.ENDC}")

def print_success(s: Any, tag:str='') -> None:
    """
    Prints a success message.

    Args:
        s (str): The message to print.
        tag (str): The tag of the message.
    """
    if tag:
        print(f"{bcolors.OKGREEN}{tag}: {s}{bcolors.ENDC}")
    else:
        print(f"{bcolors.OKGREEN}{s}{bcolors.ENDC}")

def print_error(s: Any, tag:str='') -> None:
    """
    Prints an error message.

    Args:
        s (str): The message to print.
        tag (str): The tag of the message.
    """
    if tag:
        print(f"{bcolors.FAIL}{tag}: {s}{bcolors.ENDC}")
    else:
        print(f"{bcolors.FAIL}{s}{bcolors.ENDC}")

def is_jsonable(x: Any):
    try:
        json.dumps(x)
        return True
    except:
        return False
    
def to_third_person_singular(verb:str):
    verb = verb.lower().strip()
    if verb == "be":
        return "is"
    if verb == "have":
        return "has"
    if verb == "do":
        return "does"
    if verb == "go":
        return "goes"
    if verb.endswith(('s', 'x', 'z', 'ch', 'sh')):
        return verb + 'es'
    elif verb[-1] == 'y' and verb[-2] not in "aeiou":
        return verb[:-1] + 'ies'
    else:
        return verb + 's'
    
def format_prompt(s:str, **kwargs:str):
    for k, v in kwargs.items():
        s = s.replace("${" + k + "}$", v.strip())
        s = s.replace("${" + k + "?}$", v.strip())

    # look for all the optional placeholders
    placeholders = re.findall(r'\$\{.*?\?\}\$', s) # ${...?}$
    for placeholder in placeholders:
        s = s.replace(placeholder, "")

    # look for all the required placeholders, and raise an error if any of them is missing
    placeholders = re.findall(r'\$\{.*?\}\$', s) # ${...}$
    if len(placeholders) > 0:
        raise ValueError(f"Missing placeholders: {', '.join(placeholders)}")

    s =  re.sub(r'\n\n+', '\n\n', s) # No two consecutive lines can be empty.
    return s

def parse_output(s:str) -> Dict[str, str]:
    s = s.strip()
    lines = s.split('\n')
    result: Dict[str, str] = {}
    for line in lines:
        if not line.startswith('#'):
            key, value = line[:line.find(':')].strip(), line[line.find(':')+1:].strip()
            # if key in array_items:
            #     value = value.split(';')
            #     value = [i.strip() for i in value]
            key = to_lower_bound_snake_case(key)
            result[key] = value
    return result

def read_prompt(file_path: str) -> str:
    """
    Reads the entire file and trims it.
    1. All trailing whitespaces in every line are removed.
    2. No two consecutive lines can be empty.

    Args:
        file_path (str): The path to the file.

    Returns:
        str: The contents of the file.
    """
    with open(file_path, "r") as f:
        lines = f.readlines()
        lines = [line.rstrip() for line in lines]
        output = '\n'.join(lines)
        output = re.sub(r'\n\n+', '\n\n', output) # No two consecutive lines can be empty.
        return output

def get_lemma(s:str) -> str:
    """
    Returns the lemma (base form) of a noun.

    This function attempts to derive the lemma of a given noun. For example, the plural form 'dogs' 
    is converted to its singular form 'dog'. Similarly, a phrase like 'the village elders' is 
    converted to its base form 'village elder'.

    Args:
    - s (str): A string representing the noun or noun phrase to be lemmatized.

    Returns:
    - str: The lemmatized form of the input noun or noun phrase.

    Examples:
    >>> get_lemma('dogs')
    'dog'
    >>> get_lemma('the village elders')
    'village elder'

    Note:
    The function is a simple illustration and may not handle all edge cases or complexities 
    of the English language.
    """

    _lemmatizer = nltk.stem.WordNetLemmatizer()
    s = s.strip()
    if s[:2]=='a ' or s[:2]=='A ':
        s = s[2:]
    elif s[:3]=='an ' or s[:3]=='An ':
        s = s[3:]
    elif s[:4]=='the ' or s[:4]=='The ':
        s = s[4:]
    is_lower = s.islower()
    is_upper = s.isupper()
    is_title = s.istitle()
    s = s.strip()
    s_splitted = [''] + s.split(' ')
    s_last = s_splitted[-1]
    lemma = _lemmatizer.lemmatize(s_last)
    if is_lower:
        if lemma == s_last:
            lemma = _lemmatizer.lemmatize(s_last.upper()).lower()
        if lemma == s_last:
            lemma = _lemmatizer.lemmatize(s_last.title()).lower()        
    elif is_upper:
        if lemma == s_last:
            lemma = _lemmatizer.lemmatize(s_last.lower()).upper()
        if lemma == s_last:
            lemma = _lemmatizer.lemmatize(s_last.title()).upper()
    elif is_title:
        if lemma == s_last:
            lemma = _lemmatizer.lemmatize(s_last.lower()).title()
        if lemma == s_last:
            lemma = _lemmatizer.lemmatize(s_last.upper()).title()
    return remove_extra_spaces(' '.join(s_splitted[:-1] + [lemma]))

def edit_distance(s1:str, s2:str) -> int:
    m, n = len(s1), len(s2)

    dp = [[0] * (n + 1) for _ in range(m + 1)]

    for i in range(m + 1):
        dp[i][0] = i
    for j in range(n + 1):
        dp[0][j] = j

    for i in range(1, m + 1):
        for j in range(1, n + 1):
            cost = 0 if s1[i-1] == s2[j-1] else 1
            dp[i][j] = min(dp[i-1][j] + 1, dp[i][j-1] + 1, dp[i-1][j-1] + cost)

    return dp[m][n]

def get_closest_string(s:str, options:List[str]) -> str:
    if s in options:
        return s
    min_distance = 100000
    min_distance_string = ""
    for option in options:
        distance = edit_distance(s, option)
        if distance < min_distance:
            min_distance = distance
            min_distance_string = option
    return min_distance_string
