from type import GameState

class GameAgent:
    def __init__(self, game, game_logics):
        """Initializes agent with game instance and game logistics

        Args:
            game_logics (dict): The game logics containing ordered actions
        """

        self.game = game
        self.game_logics = game_logics
        self.actions = self.game_logics['game_logics'].keys()

    def play(self):
        '''
        Plays through the game by executing each action in game_logics sequentially
        '''

        for action in self.actions:
            result = self.game_execute_command(action)
            print(result)

            if result.success:
                print(f"Success: {result.observation}")
            else:
                print(f"Failed: {result.observation}")

            if self.game.game_state != GameState.UNFINISHED:
                print("Game Over")
                if self.game.game_state == GameState.WON:
                    print("You Win")
                else:
                    print("You lose")
                break

        print("\nGame Agent has finished executing all actions.")


# if __name__ == "__main__":
#     game_agent = GameAgent(adventureGame, game_logics)
#     game_agent.play