# 3D Laser Escape Game

A first-person 3D game where you must navigate through a room filled with deadly laser beams to reach the exit.

## Screenshot

```
┌─────────────────────────────────┐
│  Time: 00:12              [HUD] │
│                                 │
│   ══════════════════════════    │
│        Red rotating lasers      │
│   ══════════════════════════    │
│                                 │
│      ╔═══════════════╗          │
│      ║  GREEN  EXIT  ║  ← goal  │
│      ╚═══════════════╝          │
│                  +              │  ← crosshair
└─────────────────────────────────┘
```

## Requirements

- Python 3.8 or later
- Pygame 2.x
- PyOpenGL 3.x
- NumPy

## Installation

```bash
pip install -r requirements.txt
```

> On some Linux systems you may also need:
> ```bash
> sudo apt-get install python3-opengl freeglut3-dev
> ```

## Running the Game

```bash
python laser_escape_3d.py
```

## Controls

| Key / Input | Action |
|---|---|
| **W** / ↑ | Move forward |
| **S** / ↓ | Move backward |
| **A** / ← | Strafe left |
| **D** / → | Strafe right |
| **Mouse** | Look around (first-person) |
| **ESC** | Quit the game |
| **R** | Restart (after game over or win) |

## Gameplay Objectives

1. You start at the **back** of the room (south end).
2. Navigate all the way to the **green glowing exit** at the far (north) end.
3. Avoid touching **any** laser beam — one touch means Game Over.
4. Try to reach the exit as quickly as possible; your elapsed time is shown in the top-left corner.

## Laser Types

| Colour | Type | Behaviour |
|---|---|---|
| Red | Rotating | Rotates in the horizontal plane — duck, time your crossing |
| Blue | Vertical | Moves up and down — find the gap |
| Orange | Stationary | Fixed barriers with a gap in the centre |
| Red (far zone) | Sweeping | Fan-sweeps left/right from a fixed pivot |
| Orange (final zone) | Fast rotating | Multiple fast layers — the toughest section |

## Tips

- Move carefully and observe each laser's pattern before crossing.
- The room is divided into roughly five zones of increasing difficulty.
- Use the crosshair to judge your position relative to laser beams.
- Press **R** immediately after hitting a laser to restart quickly.

## File Structure

```
laser_escape_3d.py   # Main game – all logic, rendering, collision detection
requirements.txt     # Python dependencies
README.md            # This file
```
