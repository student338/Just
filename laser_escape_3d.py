"""
3D Laser Escape Game
====================
Navigate through a room filled with laser beams to reach the exit.
Avoid all lasers - touching one ends the game!

Controls:
  W / Up Arrow    - Move forward
  S / Down Arrow  - Move backward
  A / Left Arrow  - Strafe left
  D / Right Arrow - Strafe right
  Mouse           - Look around (first-person)
  ESC             - Quit game
  R               - Restart (after game over or win)
"""

import sys
import math
import time
import ctypes

import pygame
from pygame.locals import (
    DOUBLEBUF, OPENGL, QUIT, KEYDOWN, K_ESCAPE,
    K_w, K_s, K_a, K_d, K_UP, K_DOWN, K_LEFT, K_RIGHT,
    K_r, MOUSEMOTION,
)
from OpenGL.GL import (
    glBegin, glEnd, glVertex3f, glVertex2f, glColor3f, glColor4f,
    glEnable, glDisable, glBlendFunc, glClearColor, glClear,
    glLoadIdentity, glMatrixMode, glViewport, glOrtho,
    glRotatef, glTranslatef, glLineWidth, glPointSize,
    glShadeModel, glDepthFunc, glDepthMask,
    glGenTextures, glBindTexture, glTexImage2D, glTexParameteri,
    glTexSubImage2D, glDeleteTextures,
    GL_LINES, GL_QUADS, GL_POINTS,
    GL_COLOR_BUFFER_BIT, GL_DEPTH_BUFFER_BIT,
    GL_PROJECTION, GL_MODELVIEW,
    GL_BLEND, GL_SRC_ALPHA, GL_ONE, GL_ONE_MINUS_SRC_ALPHA,
    GL_SMOOTH, GL_LEQUAL, GL_DEPTH_TEST,
    GL_TEXTURE_2D, GL_RGBA, GL_UNSIGNED_BYTE,
    GL_TEXTURE_MIN_FILTER, GL_TEXTURE_MAG_FILTER, GL_LINEAR,
    GL_FALSE, GL_TRUE,
)
from OpenGL.GLU import gluPerspective
import numpy as np

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

WINDOW_WIDTH = 1024
WINDOW_HEIGHT = 768
WINDOW_TITLE = "3D Laser Escape"

# Room dimensions
ROOM_WIDTH = 20.0
ROOM_LENGTH = 40.0
ROOM_HEIGHT = 8.0
HALF_W = ROOM_WIDTH / 2.0
HALF_L = ROOM_LENGTH / 2.0

# Player settings
PLAYER_HEIGHT = 1.7
PLAYER_RADIUS = 0.4
MOVE_SPEED = 5.0       # units per second
MOUSE_SENSITIVITY = 0.15

# Colours (R, G, B)
COL_FLOOR = (0.15, 0.15, 0.20)
COL_CEILING = (0.10, 0.10, 0.15)
COL_WALL = (0.20, 0.18, 0.22)
COL_EXIT = (0.0, 1.0, 0.3)
COL_LASER_RED = (1.0, 0.05, 0.05)
COL_LASER_BLUE = (0.1, 0.4, 1.0)
COL_LASER_ORANGE = (1.0, 0.5, 0.0)

# Game states
STATE_PLAYING = "playing"
STATE_DEAD = "dead"
STATE_WIN = "win"

# Gameplay tuning
TARGET_FPS = 60
MAX_DELTA_TIME = 0.1          # cap dt (seconds) to prevent tunnelling
COLLISION_TOLERANCE_FACTOR = 1.5  # multiplier on PLAYER_RADIUS for laser hit test
EXIT_ZONE_DEPTH = 2.5         # how close to the far wall triggers the win
EXIT_ZONE_WIDTH = 2.0         # half-width of the exit opening

# ---------------------------------------------------------------------------
# Laser definitions
# ---------------------------------------------------------------------------

class Laser:
    """A single laser beam defined by two endpoints that can move over time."""

    def __init__(self, laser_type, color, **kwargs):
        """
        laser_type: 'horizontal_rotate' | 'vertical_move' | 'stationary' | 'sweep'
        color: (r, g, b) tuple
        kwargs: type-specific parameters
        """
        self.laser_type = laser_type
        self.color = color
        self.kwargs = kwargs
        # Precomputed endpoints updated each frame
        self.p1 = np.zeros(3)
        self.p2 = np.zeros(3)

    def update(self, t):
        """Recompute laser endpoints for the current time t (seconds)."""
        k = self.kwargs

        if self.laser_type == "stationary":
            self.p1 = np.array(k["p1"], dtype=float)
            self.p2 = np.array(k["p2"], dtype=float)

        elif self.laser_type == "horizontal_rotate":
            # Laser rotates in the XZ plane around a centre point
            cx, cy, cz = k["center"]
            radius = k["radius"]
            speed = k["speed"]          # radians per second
            angle = t * speed + k.get("phase", 0.0)
            dx = math.cos(angle) * radius
            dz = math.sin(angle) * radius
            self.p1 = np.array([cx - dx, cy, cz - dz])
            self.p2 = np.array([cx + dx, cy, cz + dz])

        elif self.laser_type == "vertical_move":
            # Laser translates vertically between y_min and y_max
            x1, _, z1 = k["p1"]
            x2, _, z2 = k["p2"]
            y_min = k["y_min"]
            y_max = k["y_max"]
            speed = k["speed"]
            y = y_min + (y_max - y_min) * (0.5 + 0.5 * math.sin(t * speed))
            self.p1 = np.array([x1, y, z1])
            self.p2 = np.array([x2, y, z2])

        elif self.laser_type == "sweep":
            # Fan-sweep: one endpoint sweeps left/right while the other is fixed
            fx, fy, fz = k["fixed"]
            sx, sy, sz = k["sweep_center"]
            sweep_range = k["sweep_range"]   # half-width of sweep in X
            speed = k["speed"]
            offset = math.sin(t * speed) * sweep_range
            self.p1 = np.array([fx, fy, fz])
            self.p2 = np.array([sx + offset, sy, sz])


def build_lasers():
    """Return the full list of Laser objects for the game."""
    lasers = []

    # ------------------------------------------------------------------
    # Zone 1  (z ≈ -15 to -10): rotating lasers
    # ------------------------------------------------------------------
    lasers.append(Laser(
        "horizontal_rotate",
        COL_LASER_RED,
        center=(0, 1.5, -12),
        radius=HALF_W * 0.9,
        speed=0.8,
        phase=0.0,
    ))
    lasers.append(Laser(
        "horizontal_rotate",
        COL_LASER_RED,
        center=(0, 3.0, -12),
        radius=HALF_W * 0.9,
        speed=0.8,
        phase=math.pi,          # counter-rotated pair
    ))

    # ------------------------------------------------------------------
    # Zone 2  (z ≈ -8 to -5): vertical-moving barriers
    # ------------------------------------------------------------------
    for x_pos in (-4.0, 0.0, 4.0):
        lasers.append(Laser(
            "vertical_move",
            COL_LASER_BLUE,
            p1=(-HALF_W + 0.5, 0, x_pos - 7),
            p2=(HALF_W - 0.5, 0, x_pos - 7),
            y_min=0.3,
            y_max=4.5,
            speed=1.2 + x_pos * 0.1,
        ))

    # ------------------------------------------------------------------
    # Zone 3  (z ≈ -3 to 0): stationary grid barriers
    # ------------------------------------------------------------------
    for z_off in (-2.5, -1.0):
        lasers.append(Laser(
            "stationary",
            COL_LASER_ORANGE,
            p1=(-HALF_W + 0.5, 0.5, z_off),
            p2=(-2.0, 0.5, z_off),
        ))
        lasers.append(Laser(
            "stationary",
            COL_LASER_ORANGE,
            p1=(2.0, 0.5, z_off),
            p2=(HALF_W - 0.5, 0.5, z_off),
        ))
        lasers.append(Laser(
            "stationary",
            COL_LASER_ORANGE,
            p1=(-HALF_W + 0.5, 3.0, z_off),
            p2=(HALF_W - 0.5, 3.0, z_off),
        ))

    # ------------------------------------------------------------------
    # Zone 4  (z ≈ 5 to 10): sweep lasers
    # ------------------------------------------------------------------
    for y_pos, spd in ((1.0, 1.5), (2.5, -1.8), (4.0, 1.2)):
        lasers.append(Laser(
            "sweep",
            COL_LASER_RED,
            fixed=(0, y_pos, 6),
            sweep_center=(0, y_pos, 12),
            sweep_range=HALF_W * 0.85,
            speed=spd,
        ))

    # ------------------------------------------------------------------
    # Zone 5  (z ≈ 14 to 18): final gauntlet – fast rotators
    # ------------------------------------------------------------------
    for i in range(3):
        lasers.append(Laser(
            "horizontal_rotate",
            COL_LASER_ORANGE,
            center=(0, 1.0 + i * 1.5, 16),
            radius=HALF_W * 0.85,
            speed=1.5 + i * 0.3,
            phase=i * math.pi / 3,
        ))

    return lasers


# ---------------------------------------------------------------------------
# Collision detection helper
# ---------------------------------------------------------------------------

def point_to_segment_dist_sq(p, a, b):
    """Squared distance from point p to line segment a–b (all numpy arrays)."""
    ab = b - a
    ap = p - a
    denom = np.dot(ab, ab)
    if denom < 1e-12:
        return float(np.dot(ap, ap))
    t = max(0.0, min(1.0, np.dot(ap, ab) / denom))
    closest = a + t * ab
    diff = p - closest
    return float(np.dot(diff, diff))


def player_hits_laser(player_pos, laser):
    """Return True if the player bounding sphere overlaps the laser segment."""
    p = np.array(player_pos)
    dist_sq = point_to_segment_dist_sq(p, laser.p1, laser.p2)
    return dist_sq < (PLAYER_RADIUS * COLLISION_TOLERANCE_FACTOR) ** 2


# ---------------------------------------------------------------------------
# Rendering helpers – 3D scene
# ---------------------------------------------------------------------------

def draw_quad(corners, color):
    """Draw a solid coloured quad. corners: list of 4 (x,y,z) tuples."""
    glColor3f(*color)
    glBegin(GL_QUADS)
    for c in corners:
        glVertex3f(*c)
    glEnd()


def draw_room():
    """Draw the 6 faces of the room."""
    hw, hl, h = HALF_W, HALF_L, ROOM_HEIGHT

    # Floor
    draw_quad(
        [(-hw, 0, -hl), (hw, 0, -hl), (hw, 0, hl), (-hw, 0, hl)],
        COL_FLOOR,
    )
    # Ceiling
    draw_quad(
        [(-hw, h, -hl), (-hw, h, hl), (hw, h, hl), (hw, h, -hl)],
        COL_CEILING,
    )
    # Back wall (start end, z = -HALF_L)
    draw_quad(
        [(-hw, 0, -hl), (-hw, h, -hl), (hw, h, -hl), (hw, 0, -hl)],
        COL_WALL,
    )
    # Front wall (exit end, z = +HALF_L)
    draw_quad(
        [(-hw, 0, hl), (hw, 0, hl), (hw, h, hl), (-hw, h, hl)],
        COL_WALL,
    )
    # Left wall
    draw_quad(
        [(-hw, 0, -hl), (-hw, 0, hl), (-hw, h, hl), (-hw, h, -hl)],
        COL_WALL,
    )
    # Right wall
    draw_quad(
        [(hw, 0, -hl), (hw, h, -hl), (hw, h, hl), (hw, 0, hl)],
        COL_WALL,
    )


def draw_grid_floor():
    """Draw a subtle grid on the floor to aid depth perception."""
    glLineWidth(1.0)
    glColor3f(0.25, 0.25, 0.32)
    glBegin(GL_LINES)
    for x in range(int(-HALF_W), int(HALF_W) + 1):
        glVertex3f(x, 0.01, -HALF_L)
        glVertex3f(x, 0.01,  HALF_L)
    for z in range(int(-HALF_L), int(HALF_L) + 1):
        glVertex3f(-HALF_W, 0.01, z)
        glVertex3f( HALF_W, 0.01, z)
    glEnd()


def draw_exit():
    """Draw a glowing green exit portal at the far end of the room."""
    hl = HALF_L
    # Solid green rectangle on the far wall
    glColor3f(*COL_EXIT)
    glBegin(GL_QUADS)
    glVertex3f(-2.0, 0.0, hl - 0.05)
    glVertex3f( 2.0, 0.0, hl - 0.05)
    glVertex3f( 2.0, 3.5, hl - 0.05)
    glVertex3f(-2.0, 3.5, hl - 0.05)
    glEnd()

    # Glow border lines
    glLineWidth(4.0)
    glColor3f(0.5, 1.0, 0.5)
    glBegin(GL_LINES)
    for x in (-2.0, 2.0):
        glVertex3f(x, 0.0, hl - 0.06)
        glVertex3f(x, 3.5, hl - 0.06)
    for y in (0.0, 3.5):
        glVertex3f(-2.0, y, hl - 0.06)
        glVertex3f( 2.0, y, hl - 0.06)
    glEnd()
    glLineWidth(1.0)


def draw_laser(laser):
    """Draw a laser beam with a bright core and a wider semi-transparent glow."""
    p1 = laser.p1
    p2 = laser.p2
    r, g, b = laser.color

    # Bright core line
    glLineWidth(3.0)
    glColor3f(r, g, b)
    glBegin(GL_LINES)
    glVertex3f(*p1)
    glVertex3f(*p2)
    glEnd()

    # Wide glow (additive blend)
    glEnable(GL_BLEND)
    glBlendFunc(GL_SRC_ALPHA, GL_ONE)
    glDepthMask(GL_FALSE)
    glLineWidth(12.0)
    glColor4f(r, g, b, 0.20)
    glBegin(GL_LINES)
    glVertex3f(*p1)
    glVertex3f(*p2)
    glEnd()
    glDepthMask(GL_TRUE)
    glDisable(GL_BLEND)
    glLineWidth(1.0)

    # Endpoint dots for visual clarity
    glPointSize(6.0)
    glColor3f(1.0, 1.0, 1.0)
    glBegin(GL_POINTS)
    glVertex3f(*p1)
    glVertex3f(*p2)
    glEnd()
    glPointSize(1.0)


# ---------------------------------------------------------------------------
# HUD – rendered as a full-screen quad textured with a pygame surface
# ---------------------------------------------------------------------------

class HUDRenderer:
    """Renders 2D HUD text onto an OpenGL texture using pygame drawing."""

    def __init__(self, width, height):
        self.width = width
        self.height = height
        self.surface = pygame.Surface((width, height), pygame.SRCALPHA)
        self.tex_id = int(glGenTextures(1))
        glBindTexture(GL_TEXTURE_2D, self.tex_id)
        glTexParameteri(GL_TEXTURE_2D, GL_TEXTURE_MIN_FILTER, GL_LINEAR)
        glTexParameteri(GL_TEXTURE_2D, GL_TEXTURE_MAG_FILTER, GL_LINEAR)
        # Allocate texture storage
        empty = np.zeros((height, width, 4), dtype=np.uint8)
        glTexImage2D(
            GL_TEXTURE_2D, 0, GL_RGBA, width, height, 0,
            GL_RGBA, GL_UNSIGNED_BYTE, empty.tobytes(),
        )
        glBindTexture(GL_TEXTURE_2D, 0)

    def render(self, elapsed, state):
        """Draw the HUD content and upload to the OpenGL texture, then draw it."""
        self._build_surface(elapsed, state)
        self._upload_texture()
        self._draw_fullscreen_quad()

    def _build_surface(self, elapsed, state):
        """Draw HUD elements onto the pygame surface."""
        w, h = self.width, self.height
        self.surface.fill((0, 0, 0, 0))

        font_big = pygame.font.SysFont("monospace", 40, bold=True)
        font_med = pygame.font.SysFont("monospace", 28, bold=True)
        font_sm  = pygame.font.SysFont("monospace", 22)

        def blit_text(text, pos, color=(255, 255, 255), font=None):
            if font is None:
                font = font_med
            label = font.render(text, True, color)
            self.surface.blit(label, pos)

        if state == STATE_PLAYING:
            mins = int(elapsed) // 60
            secs = int(elapsed) % 60
            blit_text(f"Time: {mins:02d}:{secs:02d}", (10, 10))
            blit_text("Reach the GREEN EXIT!", (10, h - 40),
                      (100, 255, 120), font_sm)
            # Crosshair
            cx, cy = w // 2, h // 2
            pygame.draw.line(self.surface, (200, 200, 200, 200),
                             (cx - 12, cy), (cx + 12, cy), 2)
            pygame.draw.line(self.surface, (200, 200, 200, 200),
                             (cx, cy - 12), (cx, cy + 12), 2)

        elif state == STATE_DEAD:
            red = pygame.Surface((w, h), pygame.SRCALPHA)
            red.fill((180, 0, 0, 80))
            self.surface.blit(red, (0, 0))
            blit_text("LASER HIT!  GAME OVER",
                      (w // 2 - 230, h // 2 - 60),
                      (255, 60, 60), font_big)
            blit_text("Press R to Restart  |  ESC to Quit",
                      (w // 2 - 230, h // 2 + 20),
                      (220, 220, 220), font_med)

        elif state == STATE_WIN:
            green = pygame.Surface((w, h), pygame.SRCALPHA)
            green.fill((0, 140, 0, 70))
            self.surface.blit(green, (0, 0))
            mins = int(elapsed) // 60
            secs = int(elapsed) % 60
            blit_text("YOU ESCAPED!",
                      (w // 2 - 190, h // 2 - 80),
                      (60, 255, 100), font_big)
            blit_text(f"Time: {mins:02d}:{secs:02d}",
                      (w // 2 - 90, h // 2),
                      (200, 255, 200), font_med)
            blit_text("Press R to Play Again  |  ESC to Quit",
                      (w // 2 - 270, h // 2 + 60),
                      (220, 220, 220), font_med)

    def _upload_texture(self):
        """Convert the pygame surface to bytes and upload as an OpenGL texture."""
        # pygame uses BGRA or RGBA; convert to consistent RGBA
        raw = pygame.image.tostring(self.surface, "RGBA", True)
        glBindTexture(GL_TEXTURE_2D, self.tex_id)
        glTexSubImage2D(
            GL_TEXTURE_2D, 0, 0, 0,
            self.width, self.height,
            GL_RGBA, GL_UNSIGNED_BYTE, raw,
        )
        glBindTexture(GL_TEXTURE_2D, 0)

    def _draw_fullscreen_quad(self):
        """Draw a full-screen textured quad in 2D orthographic projection."""
        glMatrixMode(GL_PROJECTION)
        glLoadIdentity()
        glOrtho(0, self.width, 0, self.height, -1, 1)
        glMatrixMode(GL_MODELVIEW)
        glLoadIdentity()

        glDisable(GL_DEPTH_TEST)
        glEnable(GL_BLEND)
        glBlendFunc(GL_SRC_ALPHA, GL_ONE_MINUS_SRC_ALPHA)
        glEnable(GL_TEXTURE_2D)
        glBindTexture(GL_TEXTURE_2D, self.tex_id)
        glColor4f(1, 1, 1, 1)

        glBegin(GL_QUADS)
        glVertex2f(0,          0)
        glVertex2f(self.width, 0)
        glVertex2f(self.width, self.height)
        glVertex2f(0,          self.height)
        glEnd()

        glBindTexture(GL_TEXTURE_2D, 0)
        glDisable(GL_TEXTURE_2D)
        glDisable(GL_BLEND)
        glEnable(GL_DEPTH_TEST)

    def destroy(self):
        glDeleteTextures([self.tex_id])


# ---------------------------------------------------------------------------
# OpenGL setup
# ---------------------------------------------------------------------------

def setup_opengl(width, height):
    """Initialise the OpenGL state for the main 3D rendering."""
    glViewport(0, 0, width, height)
    glMatrixMode(GL_PROJECTION)
    glLoadIdentity()
    gluPerspective(75, width / height, 0.1, 200.0)
    glMatrixMode(GL_MODELVIEW)
    glLoadIdentity()

    glEnable(GL_DEPTH_TEST)
    glDepthFunc(GL_LEQUAL)
    glShadeModel(GL_SMOOTH)
    glClearColor(0.02, 0.02, 0.05, 1.0)


def restore_3d_projection(width, height):
    """Restore the perspective projection after HUD rendering."""
    glViewport(0, 0, width, height)
    glMatrixMode(GL_PROJECTION)
    glLoadIdentity()
    gluPerspective(75, width / height, 0.1, 200.0)
    glMatrixMode(GL_MODELVIEW)


# ---------------------------------------------------------------------------
# Game state
# ---------------------------------------------------------------------------

class GameState:
    """Holds all mutable game state."""

    def __init__(self):
        self.reset()

    def reset(self):
        # Player starts at the back of the room, looking toward the exit (+z)
        self.pos = [0.0, PLAYER_HEIGHT, -HALF_L + 2.0]
        self.yaw = 0.0      # horizontal look angle (degrees)
        self.pitch = 0.0    # vertical look angle (degrees)
        self.state = STATE_PLAYING
        self.start_time = time.time()
        self.elapsed = 0.0
        self.lasers = build_lasers()


# ---------------------------------------------------------------------------
# Input & camera
# ---------------------------------------------------------------------------

def handle_movement(gs, keys, dt):
    """Update player position from keyboard input, clamped to room bounds."""
    yaw_rad = math.radians(gs.yaw)
    forward = np.array([math.sin(yaw_rad), 0.0, math.cos(yaw_rad)])
    right    = np.array([math.cos(yaw_rad), 0.0, -math.sin(yaw_rad)])

    move = np.zeros(3)
    if keys[K_w] or keys[K_UP]:
        move += forward
    if keys[K_s] or keys[K_DOWN]:
        move -= forward
    if keys[K_d] or keys[K_RIGHT]:
        move += right
    if keys[K_a] or keys[K_LEFT]:
        move -= right

    length = float(np.linalg.norm(move))
    if length > 0:
        move = move / length * MOVE_SPEED * dt

    new_x = gs.pos[0] + move[0]
    new_z = gs.pos[2] + move[2]

    # Clamp to room boundaries
    new_x = max(-HALF_W + PLAYER_RADIUS, min(HALF_W - PLAYER_RADIUS, new_x))
    new_z = max(-HALF_L + PLAYER_RADIUS, min(HALF_L - PLAYER_RADIUS, new_z))

    gs.pos[0] = new_x
    gs.pos[2] = new_z


def apply_camera(gs):
    """Apply the first-person camera transform to the ModelView matrix."""
    glRotatef(-gs.pitch, 1, 0, 0)
    glRotatef(-gs.yaw,   0, 1, 0)
    glTranslatef(-gs.pos[0], -gs.pos[1], -gs.pos[2])


# ---------------------------------------------------------------------------
# Main game loop
# ---------------------------------------------------------------------------

def main():
    pygame.init()
    pygame.font.init()

    screen = pygame.display.set_mode(
        (WINDOW_WIDTH, WINDOW_HEIGHT), DOUBLEBUF | OPENGL
    )
    pygame.display.set_caption(WINDOW_TITLE)
    setup_opengl(WINDOW_WIDTH, WINDOW_HEIGHT)

    hud = HUDRenderer(WINDOW_WIDTH, WINDOW_HEIGHT)

    # Lock mouse to window for first-person look
    pygame.event.set_grab(True)
    pygame.mouse.set_visible(False)

    clock = pygame.time.Clock()
    gs = GameState()

    while True:
        dt = min(clock.tick(TARGET_FPS) / 1000.0, MAX_DELTA_TIME)

        # ----------------------------------------------------------------
        # Event handling
        # ----------------------------------------------------------------
        for event in pygame.event.get():
            if event.type == QUIT:
                hud.destroy()
                pygame.quit()
                sys.exit()
            if event.type == KEYDOWN:
                if event.key == K_ESCAPE:
                    hud.destroy()
                    pygame.quit()
                    sys.exit()
                if event.key == K_r and gs.state in (STATE_DEAD, STATE_WIN):
                    gs = GameState()
                    pygame.event.set_grab(True)
                    pygame.mouse.set_visible(False)
            if event.type == MOUSEMOTION and gs.state == STATE_PLAYING:
                dx, dy = event.rel
                gs.yaw   += dx * MOUSE_SENSITIVITY
                gs.pitch  = max(-89.0, min(89.0,
                                           gs.pitch + dy * MOUSE_SENSITIVITY))

        # ----------------------------------------------------------------
        # Update game logic (only while playing)
        # ----------------------------------------------------------------
        if gs.state == STATE_PLAYING:
            gs.elapsed = time.time() - gs.start_time

            keys = pygame.key.get_pressed()
            handle_movement(gs, keys, dt)

            for laser in gs.lasers:
                laser.update(gs.elapsed)

            # Collision check against all lasers
            player_np = np.array(gs.pos)
            for laser in gs.lasers:
                if player_hits_laser(player_np, laser):
                    gs.state = STATE_DEAD
                    pygame.event.set_grab(False)
                    pygame.mouse.set_visible(True)
                    break

            # Win condition: player steps into the exit area
            if gs.pos[2] > HALF_L - EXIT_ZONE_DEPTH and abs(gs.pos[0]) < EXIT_ZONE_WIDTH:
                gs.state = STATE_WIN
                pygame.event.set_grab(False)
                pygame.mouse.set_visible(True)

        # ----------------------------------------------------------------
        # Render 3D scene
        # ----------------------------------------------------------------
        glClear(GL_COLOR_BUFFER_BIT | GL_DEPTH_BUFFER_BIT)
        restore_3d_projection(WINDOW_WIDTH, WINDOW_HEIGHT)
        glLoadIdentity()
        apply_camera(gs)

        draw_room()
        draw_grid_floor()
        draw_exit()

        for laser in gs.lasers:
            draw_laser(laser)

        # ----------------------------------------------------------------
        # Render 2D HUD overlay (uploads to GL texture, draws full-screen quad)
        # ----------------------------------------------------------------
        hud.render(gs.elapsed, gs.state)

        # Restore 3D projection for the next frame
        restore_3d_projection(WINDOW_WIDTH, WINDOW_HEIGHT)

        pygame.display.flip()

    pygame.quit()


if __name__ == "__main__":
    main()
