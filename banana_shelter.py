#!/usr/bin/env python3
"""
BANANA SHELTER 🍌🏠
Save all the coins from the evil kayaking!

You've built a banana shelter down by the river.
But the evil kayakers keep trying to steal your coins.
Defend them!
"""

import random
import os
import time
import sys

# ── Game State ──────────────────────────────────────────────────
COINS = 0
COINS_TO_WIN = 20
COINS_IN_PLAY = 0  # coins currently being stolen
SHELTER_HEALTH = 100
KAYAKER_HEALTH = 0  # current attacker
KAYAKER_NAME = ""
DAY = 1
GAME_OVER = False
WON = False
INVENTORY = []

# ── Helper ──────────────────────────────────────────────────────
def cls():
    os.system('cls' if os.name == 'nt' else 'clear')

def pause(sec=0.5):
    time.sleep(sec)

def print_slow(text, delay=0.02):
    for ch in text:
        print(ch, end='', flush=True)
        time.sleep(delay)
    print()

# ── Names ───────────────────────────────────────────────────────
KAYAKER_NAMES = [
    "Paddle-Pete", "Kurt Kayak", "Swoosh-Sam", "River-Rat Rick",
    "Canoe-Carl", "Splashy-Susan", "Oar-Wars Oscar", "Whitewater Wendy",
    "The Paddling Phantom", "Sir Paddles-a-Lot", "Captain Kayak",
    "Dr. Splash", "Mega-Paddle Mitch", "The Kayak Krusher"
]

# ── Items ───────────────────────────────────────────────────────
ITEM_DESCS = {
    "🪨 Rock": "A hefty throwing rock. Stuns a kayaker for 1 turn.",
    "🪝 Fishing Hook": "Hooks a coin right out of the water! Grab 2 coins.",
    "🛡️ Banana Shield": "Block incoming damage from evil kayakers.",
    "🍌 Banana Bomb": "Explodes with slippery banana peels. Big damage!",
    "🏐 Beach Ball": "Distract the kayaker for 2 turns.",
    "🪣 Bucket": "Scoop up 3 floating coins at once!",
    "🔦 Flashlight": "Blind the kayaker — they miss a turn.",
    "🦆 Rubber Duck": "The kayaker stops to pet the duck. Free turn!",
}

def random_item():
    return random.choice(list(ITEM_DESCS.keys()))

# ── Intro ───────────────────────────────────────────────────────
def intro():
    cls()
    print(r"""
   ╔══════════════════════════════════════════════╗
   ║           🍌 BANANA SHELTER 🏠              ║
   ║      Down by the River                      ║
   ╚══════════════════════════════════════════════╝
    """)
    print_slow("You built yourself a cozy banana shelter down by the river...")
    pause(1)
    print_slow("You've been saving shiny coins for a rainy day.")
    pause(1)
    print_slow("But the EVIL KAYAKERS have spotted your treasure!")
    pause(1)
    print_slow("They paddle by every day, trying to steal your coins.")
    pause(1)
    print_slow(f"Collect {COINS_TO_WIN} coins to secure your future!")
    pause(1)
    print_slow("Defend your banana shelter at all costs!")
    pause(1.5)

# ── Scavenge ────────────────────────────────────────────────────
def scavenge_phase():
    global COINS, INVENTORY
    cls()
    print("\n  🌅 Morning by the river...\n")
    print_slow("You scavenge along the riverbank for supplies...")
    pause(0.5)

    # Always find at least 1 coin
    found_coins = random.randint(1, 3)
    COINS += found_coins
    print(f"\n  🪙 Found {found_coins} coin{'s' if found_coins > 1 else ''}! (Total: {COINS})")

    # Random item find
    if random.random() < 0.6:
        item = random_item()
        INVENTORY.append(item)
        print(f"  🎒 Found a {item}!")
        print(f"     {ITEM_DESCS[item]}")

    pause(1.5)

# ── Kayaker Attack ──────────────────────────────────────────────
def spawn_kayaker():
    global KAYAKER_HEALTH, KAYAKER_NAME
    KAYAKER_NAME = random.choice(KAYAKER_NAMES)
    # Kayaker gets stronger as days progress
    KAYAKER_HEALTH = 20 + DAY * 5
    return KAYAKER_HEALTH

def kayaker_attack_phase():
    global COINS, SHELTER_HEALTH, KAYAKER_HEALTH, COINS_IN_PLAY, GAME_OVER, DAY

    spawn_kayaker()
    coins_stolen_this_round = 0
    KAYAKER_HEALTH = 20 + DAY * 5
    COINS_IN_PLAY = min(COINS, random.randint(2, 5 + DAY))

    cls()
    print(f"\n  ⚠️  DAY {DAY} — EVIL KAYAKER APPROACHES!")
    print(f"\n  🛶 {KAYAKER_NAME} paddles furiously toward your banana shelter!")
    print(f"  💀 Kayaker Health: {KAYAKER_HEALTH}")
    print(f"  🪙 Coins at risk: {COINS_IN_PLAY}")
    print(f"  🏠 Shelter HP: {SHELTER_HEALTH}")
    print(f"  🪙 Your coins: {COINS}")
    print(f"  🎒 Items: {', '.join(INVENTORY) if INVENTORY else 'None'}")
    pause(1.5)

    while KAYAKER_HEALTH > 0 and not GAME_OVER:
        action = do_action_phase()

        if GAME_OVER:
            break

        # Kayaker fights back
        if KAYAKER_HEALTH > 0 and not GAME_OVER:
            kayaker_retaliate()
            if SHELTER_HEALTH <= 0:
                print_slow("\n  💔 Your banana shelter has been destroyed!")
                GAME_OVER = True
                return

        if SHELTER_HEALTH <= 0:
            break

    if KAYAKER_HEALTH <= 0 and not GAME_OVER:
        defeated_kayaker()

def defeated_kayaker():
    global COINS, DAY
    print_slow(f"\n  🏆 {KAYAKER_NAME} has been defeated! They paddle away in shame!")
    pause(0.5)
    print_slow(f"  🪙 You saved your {COINS_IN_PLAY} coins!")
    DAY += 1

def do_action_phase():
    global COINS, KAYAKER_HEALTH, SHELTER_HEALTH, COINS_IN_PLAY, INVENTORY, GAME_OVER
    print(f"\n  ─── What will you do? ───")
    print(f"    1. 🥊 Punch the kayaker (damage: {5 + DAY})")
    print(f"    2. 🛡️  Repair shelter (+10 HP)")
    print(f"    3. 💰 Hide coins (save {COINS_IN_PLAY // 2})")
    if INVENTORY:
        print(f"    4. 🎒 Use item ({len(INVENTORY)} available)")
    print(f"    5. 🏃 Flee (skip this day, lose {COINS_IN_PLAY // 2} coins)")

    choice = input("\n  > ").strip()

    if choice == "1":
        dmg = 5 + DAY + random.randint(0, 5)
        KAYAKER_HEALTH -= dmg
        print(f"\n  👊 WHAM! You punch {KAYAKER_NAME} for {dmg} damage! (Remaining HP: {max(0, KAYAKER_HEALTH)})")

    elif choice == "2":
        repair = 10
        SHELTER_HEALTH = min(100, SHELTER_HEALTH + repair)
        print(f"\n  🔨 You patch up the banana shelter! (+{repair} HP, now {SHELTER_HEALTH} HP)")

    elif choice == "3":
        saved = COINS_IN_PLAY // 2
        COINS += saved
        COINS_IN_PLAY -= saved
        print(f"\n  🙈 You hid {saved} coins under a banana peel! Safe for now!")

    elif choice == "4" and INVENTORY:
        use_item()

    elif choice == "5":
        lost = COINS_IN_PLAY // 2
        COINS = max(0, COINS - lost)
        print(f"\n  🏃 You flee! The kayaker steals {lost} coins. (Remaining: {COINS})")
        KAYAKER_HEALTH = 0  # end encounter

    else:
        print("  ❓ Not a valid choice! The kayaker laughs at you.")
        KAYAKER_HEALTH -= 0  # nothing

    pause(1)

def use_item():
    global COINS, KAYAKER_HEALTH, SHELTER_HEALTH, COINS_IN_PLAY, INVENTORY, GAME_OVER

    print(f"\n  Your items:")
    for i, item in enumerate(INVENTORY, 1):
        print(f"    {i}. {item}")
    print(f"    {len(INVENTORY) + 1}. Cancel")

    choice = input("  > ").strip()
    if choice.isdigit():
        idx = int(choice) - 1
        if 0 <= idx < len(INVENTORY):
            item = INVENTORY.pop(idx)
            print(f"\n  🎯 You use the {item}!")
            pause(0.5)

            if item == "🪨 Rock":
                dmg = random.randint(10, 20)
                KAYAKER_HEALTH -= dmg
                print(f"  🎯 BONK! {dmg} damage!")
            elif item == "🪝 Fishing Hook":
                gained = 2
                COINS += gained
                print(f"  🎣 You hook 2 coins from the river!")
            elif item == "🛡️ Banana Shield":
                SHELTER_HEALTH = min(100, SHELTER_HEALTH + 15)
                print(f"  🛡️  Banana shield absorbs the hit! +15 shelter HP ({SHELTER_HEALTH})")
            elif item == "🍌 Banana Bomb":
                dmg = random.randint(20, 35)
                KAYAKER_HEALTH -= dmg
                print(f"  💥🍌 KABOOM! Slippery banana goo deals {dmg} damage!")
            elif item == "🏐 Beach Ball":
                print(f"  🏐 The kayaker is distracted! They miss their turn!")
                return  # skip retaliation
            elif item == "🪣 Bucket":
                scooped = min(3, COINS_IN_PLAY)
                COINS += scooped
                COINS_IN_PLAY -= scooped
                print(f"  🪣 Scooped up {scooped} coins!")
            elif item == "🔦 Flashlight":
                print(f"  🔦 BLINDED! The kayaker flails and misses!")
                return
            elif item == "🦆 Rubber Duck":
                print(f"  🦆 QUACK! The kayaker stops to pet the duck. Free turn!")
                return
        else:
            print("  Canceled.")
    else:
        print("  Canceled.")

def kayaker_retaliate():
    global COINS, SHELTER_HEALTH, COINS_IN_PLAY
    print(f"\n  🛶 {KAYAKER_NAME} strikes back!")
    pause(0.3)

    action = random.choices(
        ["steal", "smash", "splash"],
        weights=[0.5, 0.3, 0.2]
    )[0]

    if action == "steal":
        stolen = min(random.randint(1, 3), COINS_IN_PLAY)
        COINS_IN_PLAY -= stolen
        COINS = max(0, COINS - stolen)
        print(f"  💰 They grab {stolen} coin{'s' if stolen > 1 else ''}! (-{stolen} coins)")
    elif action == "smash":
        dmg = random.randint(5, 12)
        SHELTER_HEALTH -= dmg
        print(f"  🔨 They smash your shelter for {dmg} damage! ({max(0, SHELTER_HEALTH)} HP left)")
    elif action == "splash":
        splashed = min(2, COINS_IN_PLAY)
        COINS_IN_PLAY -= splashed
        print(f"  🌊 The kayaker splashes! {splashed} coin{'s' if splashed > 1 else ''} washed away!")
    pause(1)

# ── Win Check ───────────────────────────────────────────────────
def check_win():
    global WON, GAME_OVER
    if COINS >= COINS_TO_WIN:
        WON = True
        GAME_OVER = True

# ── Main Loop ───────────────────────────────────────────────────
def main():
    global DAY, GAME_OVER, WON
    intro()
    input("\n  Press ENTER to begin your adventure...")

    while not GAME_OVER:
        scavenge_phase()
        check_win()
        if GAME_OVER:
            break
        kayaker_attack_phase()
        check_win()

    cls()
    if WON:
        print(r"""
   ╔══════════════════════════════════════════════╗
   ║         🎉 VICTORY! 🎉                       ║
   ╚══════════════════════════════════════════════╝
        """)
        print_slow(f"You saved {COINS} coins in your banana shelter!")
        pause(0.5)
        print_slow("The evil kayakers have given up and paddled away forever!")
        pause(0.5)
        print_slow("Your banana shelter stands tall by the river.")
        pause(0.5)
        print_slow("You are a legend among banana-shelter-dwellers! 🍌🏆")
    else:
        print(r"""
   ╔══════════════════════════════════════════════╗
   ║         💀 GAME OVER 💀                     ║
   ╚══════════════════════════════════════════════╝
        """)
        print_slow(f"The evil kayakers stole everything you had...")
        print_slow(f"Your banana shelter is in ruins.")

    print(f"\n  🪙 Final coins: {COINS}")
    print(f"  📅 Days survived: {DAY}")
    print(f"  🏠 Shelter condition: {'Destroyed' if SHELTER_HEALTH <= 0 else f'{SHELTER_HEALTH} HP'}")
    print()
    print_slow("Thanks for playing Banana Shelter! 🍌")
    print()

if __name__ == "__main__":
    try:
        main()
    except KeyboardInterrupt:
        print("\n\n  👋 See you by the river!")
        sys.exit(0)
