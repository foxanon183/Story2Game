# Story2Game

This repository contains the code accompanying our submission to AIIDE 2025.

## Overview

This code implements the core system described in our paper. It includes:

- [✓] The story-to-game transformation pipeline (found in Game Builder.ipynb). A sample story has already been provided and generated.
- [✓] All full-length prompts mentioned in the Appendix (refer to list below to find each one)
- [✓] Sample input story files (found in /planner/skeleton)

For the full-length prompts (all located in the /prompts/ folder):

- /action_generation_prompt/: Refer to story_generation.txt and new_action.txt for story action generation at initialization and dynamic action generation respectively.
- /novel_action_prompt/: Refer to check_existing_action.txt for LLM prompting to check if user inputted actions match current actions in the game. Refer to check_future_actions.txt for novel attribute effect reconciliation. Refer to three_verbs.txt for the LLM prompting used when determining novel actions during evaluation. 
