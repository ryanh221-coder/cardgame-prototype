# Card Game Prototype

A small, playable turn-based card battler prototype for Windows using Python and Pygame.

## Current prototype

This first slice already includes:
- a deck, hand, draw pile, and discard pile
- energy each turn
- attack and block cards
- a simple enemy intent system
- win and loss states
- restart support

## Run it on Windows

1. Install Python 3.11 or newer
2. Open a terminal in the repo folder
3. Create a virtual environment
4. Install dependencies
5. Run the game

### PowerShell

```powershell
python -m venv .venv
.\.venv\Scripts\Activate.ps1
python -m pip install -r requirements.txt
python src/main.py
```

## Controls

- Left click a card to play it
- Click **End Turn** to let the enemy act
- Press **R** to restart after a win or loss

## Next good steps

- add more cards and card keywords
- add relics and status effects
- add multiple enemies
- add a map and rewards between fights
- move game logic into separate modules
