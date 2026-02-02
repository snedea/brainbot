#!/usr/bin/env python3
"""Create assets for BrainBot Pong reel."""

from PIL import Image, ImageDraw, ImageFont
import math
import os

OUTPUT_DIR = "/home/brainbot/homelab/brainbot/media/pong_reel"

# Colors
DARK_BG = (20, 24, 33)
RAINBOW = [
    (255, 0, 0),      # Red
    (255, 127, 0),    # Orange
    (255, 255, 0),    # Yellow
    (0, 255, 0),      # Green
    (0, 0, 255),      # Blue
    (75, 0, 130),     # Indigo
    (148, 0, 211),    # Violet
]
CYAN = (100, 200, 255)
WHITE = (255, 255, 255)
GRAY = (128, 128, 128)
YELLOW = (255, 200, 50)

def get_font(size):
    """Get a font, fallback to default."""
    try:
        return ImageFont.truetype("/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf", size)
    except:
        return ImageFont.load_default()

def draw_rainbow_paddle(draw, x, y, width, height):
    """Draw a rainbow gradient paddle."""
    segment_height = height / len(RAINBOW)
    for i, color in enumerate(RAINBOW):
        y1 = y + i * segment_height
        y2 = y + (i + 1) * segment_height
        draw.rectangle([x, y1, x + width, y2], fill=color)

def draw_shimmering_circle(draw, cx, cy, radius, frame=0):
    """Draw a shimmering rainbow circle (logo style)."""
    for i in range(360):
        angle = math.radians(i)
        color_idx = (i + frame * 10) % 360
        # Map to rainbow
        rainbow_pos = (color_idx / 360) * len(RAINBOW)
        c1 = RAINBOW[int(rainbow_pos) % len(RAINBOW)]
        c2 = RAINBOW[(int(rainbow_pos) + 1) % len(RAINBOW)]
        t = rainbow_pos - int(rainbow_pos)
        color = tuple(int(c1[j] + t * (c2[j] - c1[j])) for j in range(3))

        x1 = cx + (radius - 5) * math.cos(angle)
        y1 = cy + (radius - 5) * math.sin(angle)
        x2 = cx + radius * math.cos(angle)
        y2 = cy + radius * math.sin(angle)
        draw.line([x1, y1, x2, y2], fill=color, width=3)

# =============================================================================
# LOGO - Rainbow Shimmering Circle with "BB"
# =============================================================================
def create_logo():
    """Create BrainBot logo with rainbow shimmer."""
    size = 512
    img = Image.new('RGBA', (size, size), (0, 0, 0, 0))
    draw = ImageDraw.Draw(img)

    cx, cy = size // 2, size // 2
    radius = 220

    # Draw multiple shimmering rings
    for r in range(radius - 30, radius + 10, 8):
        for i in range(360):
            angle = math.radians(i)
            rainbow_pos = ((i + r) / 360) * len(RAINBOW)
            c1 = RAINBOW[int(rainbow_pos) % len(RAINBOW)]
            c2 = RAINBOW[(int(rainbow_pos) + 1) % len(RAINBOW)]
            t = rainbow_pos - int(rainbow_pos)
            color = tuple(int(c1[j] + t * (c2[j] - c1[j])) for j in range(3))

            x = cx + r * math.cos(angle)
            y = cy + r * math.sin(angle)
            draw.ellipse([x-4, y-4, x+4, y+4], fill=color)

    # Inner dark circle
    draw.ellipse([cx-150, cy-150, cx+150, cy+150], fill=DARK_BG)

    # "BB" text
    font = get_font(120)
    draw.text((cx, cy), "BB", font=font, fill=WHITE, anchor="mm")

    # Small "pong" below
    font_small = get_font(40)
    draw.text((cx, cy + 80), "PONG", font=font_small, fill=GRAY, anchor="mm")

    img.save(f"{OUTPUT_DIR}/logo_brainbot_pong.png")
    print("Created: logo_brainbot_pong.png")

# =============================================================================
# SLIDE 1 - Title Card
# =============================================================================
def create_slide1():
    """Title slide."""
    img = Image.new('RGB', (1920, 1080), DARK_BG)
    draw = ImageDraw.Draw(img)

    # Rainbow paddle left side
    draw_rainbow_paddle(draw, 100, 340, 30, 400)

    # Title
    font_big = get_font(100)
    font_med = get_font(50)

    draw.text((960, 400), "BrainBot", font=font_big, fill=WHITE, anchor="mm")
    draw.text((960, 520), "NETWORKED PONG", font=font_med, fill=CYAN, anchor="mm")
    draw.text((960, 620), "Pi 5 vs MacBook Pro", font=font_med, fill=GRAY, anchor="mm")

    # Cyan paddle right side
    draw.rectangle([1790, 340, 1820, 740], fill=CYAN)

    # Ball in center
    draw.ellipse([940, 700, 980, 740], fill=YELLOW)

    img.save(f"{OUTPUT_DIR}/slide1_title.png")
    print("Created: slide1_title.png")

# =============================================================================
# SLIDE 2 - Architecture Diagram
# =============================================================================
def create_slide2():
    """Architecture diagram."""
    img = Image.new('RGB', (1920, 1080), DARK_BG)
    draw = ImageDraw.Draw(img)

    font_title = get_font(60)
    font_med = get_font(36)
    font_small = get_font(24)

    # Title
    draw.text((960, 60), "Network Architecture", font=font_title, fill=WHITE, anchor="mm")

    # Pi box (left)
    draw.rectangle([100, 200, 550, 600], outline=RAINBOW[0], width=4)
    draw.text((325, 230), "Raspberry Pi 5", font=font_med, fill=RAINBOW[0], anchor="mm")
    draw.text((325, 280), "HOST", font=font_small, fill=GRAY, anchor="mm")

    # Pi details
    details_pi = [
        "Game Physics Engine",
        "Ball Movement",
        "Collision Detection",
        "Score Tracking",
        "Left Paddle AI",
        "5\" LCD Display",
    ]
    for i, text in enumerate(details_pi):
        draw.text((325, 340 + i*40), f"• {text}", font=font_small, fill=WHITE, anchor="mm")

    # Rainbow paddle icon
    draw_rainbow_paddle(draw, 150, 450, 15, 100)

    # MacBook box (right)
    draw.rectangle([1370, 200, 1820, 600], outline=CYAN, width=4)
    draw.text((1595, 230), "MacBook Pro", font=font_med, fill=CYAN, anchor="mm")
    draw.text((1595, 280), "CLIENT", font=font_small, fill=GRAY, anchor="mm")

    # MacBook details
    details_mac = [
        "Receives Game State",
        "Sends Paddle Input",
        "Right Paddle AI",
        "Local Rendering",
        "Network Sync",
        "Terminal Display",
    ]
    for i, text in enumerate(details_mac):
        draw.text((1595, 340 + i*40), f"• {text}", font=font_small, fill=WHITE, anchor="mm")

    # Cyan paddle icon
    draw.rectangle([1750, 450, 1765, 550], fill=CYAN)

    # Network arrows
    # Host -> Client (game state)
    draw.line([550, 350, 1370, 350], fill=YELLOW, width=3)
    draw.polygon([(1370, 350), (1340, 335), (1340, 365)], fill=YELLOW)
    draw.text((960, 320), "Game State (ball, scores, paddles)", font=font_small, fill=YELLOW, anchor="mm")

    # Client -> Host (input)
    draw.line([1370, 450, 550, 450], fill=(100, 255, 100), width=3)
    draw.polygon([(550, 450), (580, 435), (580, 465)], fill=(100, 255, 100))
    draw.text((960, 480), "Paddle Input (y velocity)", font=font_small, fill=(100, 255, 100), anchor="mm")

    # Tailscale cloud
    draw.ellipse([800, 630, 1120, 780], outline=(100, 100, 255), width=3)
    draw.text((960, 700), "Tailscale VPN", font=font_med, fill=(100, 100, 255), anchor="mm")
    draw.text((960, 750), "100.x.x.x ↔ 100.y.y.y", font=font_small, fill=GRAY, anchor="mm")

    # Connection lines to cloud
    draw.line([325, 600, 860, 680], fill=(100, 100, 255), width=2)
    draw.line([1595, 600, 1060, 680], fill=(100, 100, 255), width=2)

    # Port info
    draw.text((960, 850), "HTTP on port 7778", font=font_small, fill=GRAY, anchor="mm")
    draw.text((960, 900), "~60 FPS sync rate", font=font_small, fill=GRAY, anchor="mm")

    img.save(f"{OUTPUT_DIR}/slide2_architecture.png")
    print("Created: slide2_architecture.png")

# =============================================================================
# SLIDE 3 - Data Flow
# =============================================================================
def create_slide3():
    """Data flow slide."""
    img = Image.new('RGB', (1920, 1080), DARK_BG)
    draw = ImageDraw.Draw(img)

    font_title = get_font(60)
    font_med = get_font(32)
    font_small = get_font(24)
    font_code = get_font(20)

    # Title
    draw.text((960, 60), "What Gets Sent Over The Wire", font=font_title, fill=WHITE, anchor="mm")

    # Left box - Game State
    draw.rectangle([100, 150, 900, 700], outline=YELLOW, width=3)
    draw.text((500, 180), "NetworkGameState", font=font_med, fill=YELLOW, anchor="mm")
    draw.text((500, 220), "(Host → Client)", font=font_small, fill=GRAY, anchor="mm")

    state_fields = [
        ("ball_x, ball_y", "Ball position"),
        ("ball_vx, ball_vy", "Ball velocity"),
        ("ball_speed", "Current speed"),
        ("left_y, right_y", "Paddle positions"),
        ("left_score", "Host score"),
        ("right_score", "Client score"),
        ("game_over", "End flag"),
        ("winner", "Winner name"),
        ("rally_count", "Current rally"),
        ("timestamp", "Sync timing"),
        ("frame_number", "Frame counter"),
    ]

    y = 280
    for field, desc in state_fields:
        draw.text((150, y), field, font=font_code, fill=CYAN)
        draw.text((450, y), f"// {desc}", font=font_code, fill=GRAY)
        y += 35

    # Right box - Paddle Input
    draw.rectangle([1020, 150, 1820, 450], outline=(100, 255, 100), width=3)
    draw.text((1420, 180), "PaddleInput", font=font_med, fill=(100, 255, 100), anchor="mm")
    draw.text((1420, 220), "(Client → Host)", font=font_small, fill=GRAY, anchor="mm")

    input_fields = [
        ("y_velocity", "-1 to 1 (up/down)"),
        ("timestamp", "Input timing"),
        ("node_id", "Client identifier"),
    ]

    y = 280
    for field, desc in input_fields:
        draw.text((1070, y), field, font=font_code, fill=CYAN)
        draw.text((1300, y), f"// {desc}", font=font_code, fill=GRAY)
        y += 50

    # Bottom - Key insight
    draw.rectangle([100, 750, 1820, 950], outline=RAINBOW[4], width=2)
    draw.text((960, 800), "Key Insight", font=font_med, fill=RAINBOW[4], anchor="mm")
    draw.text((960, 860), "Host is AUTHORITATIVE - runs all physics, client just renders & sends input", font=font_small, fill=WHITE, anchor="mm")
    draw.text((960, 910), "Simple AI on both sides: paddle.y → ball.y (tracks the ball)", font=font_small, fill=GRAY, anchor="mm")

    img.save(f"{OUTPUT_DIR}/slide3_dataflow.png")
    print("Created: slide3_dataflow.png")

# =============================================================================
# SLIDE 4 - Game Screenshot mockup
# =============================================================================
def create_slide4():
    """Game in action slide."""
    img = Image.new('RGB', (1920, 1080), DARK_BG)
    draw = ImageDraw.Draw(img)

    font_title = get_font(60)
    font_med = get_font(36)
    font_small = get_font(24)

    # Title
    draw.text((960, 50), "Game In Action", font=font_title, fill=WHITE, anchor="mm")

    # Game frame in center (800x480 scaled up)
    game_x, game_y = 360, 150
    game_w, game_h = 1200, 720

    # Game background
    draw.rectangle([game_x, game_y, game_x + game_w, game_y + game_h], fill=(15, 18, 27), outline=GRAY, width=2)

    # Center line
    for y in range(game_y + 20, game_y + game_h - 20, 40):
        draw.rectangle([game_x + game_w//2 - 3, y, game_x + game_w//2 + 3, y + 20], fill=GRAY)

    # Scores
    font_score = get_font(80)
    draw.text((game_x + 300, game_y + 80), "3", font=font_score, fill=(150, 150, 180), anchor="mm")
    draw.text((game_x + game_w - 300, game_y + 80), "2", font=font_score, fill=(150, 150, 180), anchor="mm")

    # Rainbow paddle (left) - BrainBot
    paddle_h = 150
    draw_rainbow_paddle(draw, game_x + 50, game_y + 300, 25, paddle_h)

    # Cyan paddle (right) - MacBook
    draw.rectangle([game_x + game_w - 75, game_y + 250, game_x + game_w - 50, game_y + 250 + paddle_h], fill=CYAN)

    # Ball
    ball_x, ball_y = game_x + 700, game_y + 350
    draw.ellipse([ball_x - 15, ball_y - 15, ball_x + 15, ball_y + 15], fill=YELLOW)

    # Labels below game
    draw.text((game_x + 100, game_y + game_h + 30), "BrainBot (Pi 5)", font=font_small, fill=RAINBOW[0], anchor="mm")
    draw.text((game_x + game_w - 100, game_y + game_h + 30), "MacBook Pro", font=font_small, fill=CYAN, anchor="mm")

    # Rally counter
    draw.text((game_x + game_w//2, game_y + game_h - 40), "Rally: 15", font=font_small, fill=GRAY, anchor="mm")

    # Status
    draw.text((game_x + game_w//2, game_y + 30), "Connected!", font=font_med, fill=(100, 255, 100), anchor="mm")

    img.save(f"{OUTPUT_DIR}/slide4_gameplay.png")
    print("Created: slide4_gameplay.png")

# =============================================================================
# SLIDE 5 - Results / Stats
# =============================================================================
def create_slide5():
    """Results slide."""
    img = Image.new('RGB', (1920, 1080), DARK_BG)
    draw = ImageDraw.Draw(img)

    font_title = get_font(60)
    font_big = get_font(120)
    font_med = get_font(40)
    font_small = get_font(28)

    # Title
    draw.text((960, 80), "First Match Results", font=font_title, fill=WHITE, anchor="mm")

    # Winner announcement
    draw.text((960, 250), "WINNER", font=font_med, fill=YELLOW, anchor="mm")
    draw.text((960, 380), "BrainBot", font=font_big, fill=RAINBOW[0], anchor="mm")

    # Score
    draw.text((960, 520), "5 - 0", font=font_big, fill=WHITE, anchor="mm")

    # Stats boxes
    stats = [
        ("Max Rally", "21"),
        ("Network", "Tailscale P2P"),
        ("Latency", "<10ms local"),
        ("FPS", "~60"),
    ]

    box_width = 350
    start_x = 185
    for i, (label, value) in enumerate(stats):
        x = start_x + i * (box_width + 50)
        draw.rectangle([x, 650, x + box_width, 780], outline=CYAN, width=2)
        draw.text((x + box_width//2, 690), label, font=font_small, fill=GRAY, anchor="mm")
        draw.text((x + box_width//2, 740), value, font=font_med, fill=WHITE, anchor="mm")

    # Footer
    draw.text((960, 900), "Two machines, one game, zero cloud", font=font_med, fill=GRAY, anchor="mm")
    draw.text((960, 970), "github.com/snedea/brainbot", font=font_small, fill=(100, 100, 255), anchor="mm")

    # Rainbow paddle left
    draw_rainbow_paddle(draw, 80, 300, 20, 200)

    # Cyan paddle right
    draw.rectangle([1820, 300, 1840, 500], fill=CYAN)

    img.save(f"{OUTPUT_DIR}/slide5_results.png")
    print("Created: slide5_results.png")

# =============================================================================
# MAIN
# =============================================================================
if __name__ == "__main__":
    os.makedirs(OUTPUT_DIR, exist_ok=True)

    print("Creating BrainBot Pong Reel Assets...")
    print("=" * 50)

    create_logo()
    create_slide1()
    create_slide2()
    create_slide3()
    create_slide4()
    create_slide5()

    print("=" * 50)
    print(f"All assets saved to: {OUTPUT_DIR}")
