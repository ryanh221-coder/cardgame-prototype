from __future__ import annotations

import math
import random
import sys
from dataclasses import dataclass, field
from typing import Callable

import pygame


WIDTH = 1280
HEIGHT = 720
FPS = 60
TITLE = "She Draws Near - Ritualist Prototype"

BG_COLOR = (20, 24, 32)
PANEL_COLOR = (33, 40, 52)
PANEL_ALT = (44, 53, 69)
TEXT_COLOR = (235, 239, 244)
MUTED_TEXT = (176, 184, 196)
ACCENT = (100, 180, 255)
RED = (210, 92, 92)
GREEN = (92, 190, 120)
YELLOW = (232, 196, 92)
PURPLE = (174, 118, 255)
BLOOD_RED = (190, 60, 72)
BONE_WHITE = (219, 212, 196)
CARD_BG = (245, 241, 232)
CARD_BORDER = (80, 72, 64)
CARD_TEXT = (25, 25, 25)
BLOCK_BLUE = (110, 168, 255)

BATTLE = "battle"
REWARD = "reward"
DEFEAT = "defeat"


@dataclass
class Card:
    name: str
    energy_cost: int
    description: str
    color: tuple[int, int, int]
    effect: Callable[["GameState"], str]
    component_costs: dict[str, int] = field(default_factory=dict)
    exhausts: bool = False
    temporary: bool = False


@dataclass
class Intent:
    label: str
    amount: int
    kind: str


@dataclass
class Enemy:
    name: str
    hp: int
    max_hp: int
    block: int
    hexed: bool
    component_yield: dict[str, int]
    intents: list[Intent]
    intent_index: int = 0
    acted_this_turn: bool = False

    def current_intent(self) -> Intent:
        return self.intents[self.intent_index]

    def advance_intent(self) -> None:
        self.intent_index = (self.intent_index + 1) % len(self.intents)
        self.acted_this_turn = False


@dataclass
class ActiveEffect:
    name: str
    turns_left: int
    data: dict[str, int]


class Button:
    def __init__(self, rect: pygame.Rect, text: str):
        self.rect = rect
        self.text = text

    def draw(self, surface: pygame.Surface, font: pygame.font.Font, hovered: bool) -> None:
        color = ACCENT if hovered else PANEL_ALT
        pygame.draw.rect(surface, color, self.rect, border_radius=12)
        pygame.draw.rect(surface, TEXT_COLOR, self.rect, 2, border_radius=12)
        label = font.render(self.text, True, TEXT_COLOR)
        surface.blit(label, label.get_rect(center=self.rect.center))


class GameState:
    def __init__(self) -> None:
        self.rng = random.Random()
        self.reset_run()

    def reset_run(self) -> None:
        self.player_max_hp = 42
        self.player_hp = self.player_max_hp
        self.player_block = 0
        self.wards = 0
        self.energy = 3
        self.turn_number = 1
        self.message = "The dead still whisper. Prepare the rite."
        self.screen_mode = BATTLE
        self.run_won = False

        self.soul = 0
        self.blood = 0
        self.bone = 0

        self.next_fight_strength = 0
        self.current_strength = 0
        self.pending_damage_bonus_percent = 0

        self.active_effects: list[ActiveEffect] = []
        self.exile_pile: list[Card] = []
        self.discard_pile: list[Card] = []
        self.hand: list[Card] = []
        self.draw_pile = self.build_ritualist_deck()
        self.reward_buttons: list[tuple[Button, str]] = []
        self.pending_reward_enemy_name = ""
        self.reward_preview_yield: dict[str, int] = {}
        self.last_battle_card_reward = make_spirit_barrage()

        self.enemy_queue = [make_grave_cultist(), make_ossuary_hound()]
        self.enemy = self.enemy_queue.pop(0)
        self.start_player_turn(initial=True)

    def build_ritualist_deck(self) -> list[Card]:
        deck = [
            make_curse(),
            make_curse(),
            make_soul_siphon(),
            make_soul_siphon(),
            make_blood_divination(),
            make_blood_divination(),
            make_bone_ward(),
            make_bone_ward(),
            make_cursed_ground(),
            make_essence_transfer(),
        ]
        self.rng.shuffle(deck)
        return deck

    def component_value(self, name: str) -> int:
        return {"Soul": self.soul, "Blood": self.blood, "Bone": self.bone}[name]

    def change_component(self, name: str, amount: int) -> None:
        if name == "Soul":
            self.soul = max(0, self.soul + amount)
        elif name == "Blood":
            self.blood = max(0, self.blood + amount)
        elif name == "Bone":
            self.bone = max(0, self.bone + amount)

    def can_pay_card(self, card: Card) -> tuple[bool, str]:
        if card.energy_cost > self.energy:
            return False, "Not enough energy."
        for component_name, amount in card.component_costs.items():
            if self.component_value(component_name) < amount:
                return False, f"Not enough {component_name.lower()}."
        return True, ""

    def pay_card_costs(self, card: Card) -> None:
        self.energy -= card.energy_cost
        for component_name, amount in card.component_costs.items():
            self.change_component(component_name, -amount)

    def draw_cards(self, amount: int) -> None:
        for _ in range(amount):
            if not self.draw_pile and self.discard_pile:
                self.draw_pile = self.discard_pile[:]
                self.discard_pile.clear()
                self.rng.shuffle(self.draw_pile)
            if not self.draw_pile:
                return
            self.hand.append(self.draw_pile.pop())

    def draw_bonus_cards(self, amount: int) -> int:
        before = len(self.hand)
        self.draw_cards(amount)
        return len(self.hand) - before

    def start_player_turn(self, initial: bool = False) -> None:
        self.player_block = 0
        self.energy = 3
        self.current_strength = self.next_fight_strength
        self.next_fight_strength = 0
        self.enemy.acted_this_turn = False
        self.hand.clear()
        self.draw_cards(5)
        if not initial:
            self.turn_number += 1
        self.message = f"Turn {self.turn_number}. The rite continues."

    def end_turn(self) -> None:
        if self.screen_mode != BATTLE:
            return

        while self.hand:
            card = self.hand.pop()
            if card.temporary:
                self.exile_pile.append(card)
            else:
                self.discard_pile.append(card)

        enemy_message = self.enemy_take_turn()
        self.resolve_end_of_turn_effects()
        self.check_battle_end()
        if self.screen_mode == BATTLE:
            self.enemy.advance_intent()
            self.start_player_turn()
            self.message = enemy_message

    def enemy_take_turn(self) -> str:
        intent = self.enemy.current_intent()
        self.apply_hex_on_enemy_action()
        if intent.kind == "attack":
            damage_taken = self.damage_player(intent.amount)
            self.enemy.acted_this_turn = True
            return f"{self.enemy.name} attacks for {intent.amount}. You take {damage_taken}."
        if intent.kind == "block":
            self.enemy.block += intent.amount
            self.enemy.acted_this_turn = True
            return f"{self.enemy.name} gains {intent.amount} block."
        if intent.kind == "buff":
            self.enemy.intents[0].amount += intent.amount
            self.enemy.acted_this_turn = True
            return f"{self.enemy.name} prepares a deadlier rite."
        return "The enemy watches in silence."

    def apply_hex_on_enemy_action(self) -> None:
        if self.enemy.hexed and not self.enemy.acted_this_turn:
            self.enemy.hp -= 1
            self.enemy.acted_this_turn = True
            if self.enemy.hp < 0:
                self.enemy.hp = 0

    def damage_player(self, amount: int) -> int:
        damage_remaining = amount
        if self.player_block > 0:
            blocked = min(self.player_block, damage_remaining)
            self.player_block -= blocked
            damage_remaining -= blocked
        while damage_remaining > 0 and self.wards > 0:
            if damage_remaining >= 3:
                damage_remaining -= 3
                self.wards -= 1
            else:
                break
        self.player_hp -= damage_remaining
        return damage_remaining

    def deal_damage_to_enemy(self, base_amount: int, source: str = "card") -> int:
        amount = base_amount + self.current_strength
        if self.pending_damage_bonus_percent > 0:
            amount += math.floor(amount * self.pending_damage_bonus_percent / 100)
            self.pending_damage_bonus_percent = 0

        blocked = min(self.enemy.block, amount)
        self.enemy.block -= blocked
        damage = amount - blocked
        self.enemy.hp -= damage

        if damage > 0:
            self.trigger_cursed_ground()
        return damage

    def trigger_cursed_ground(self) -> None:
        effect = self.find_active_effect("Cursed Ground")
        if effect is None:
            return
        if self.enemy.name == "Lantern Wraith":
            return
        bonus = effect.data.get("bonus_damage", 0)
        self.enemy.hp -= effect.data.get("base_damage", 0) + bonus

    def gain_ward(self, amount: int) -> None:
        self.wards += amount

    def find_active_effect(self, name: str) -> ActiveEffect | None:
        for effect in self.active_effects:
            if effect.name == name:
                return effect
        return None

    def play_card(self, hand_index: int) -> None:
        if self.screen_mode != BATTLE:
            return
        if hand_index < 0 or hand_index >= len(self.hand):
            return

        card = self.hand[hand_index]
        can_pay, reason = self.can_pay_card(card)
        if not can_pay:
            self.message = reason
            return

        self.pay_card_costs(card)
        result = card.effect(self)
        played = self.hand.pop(hand_index)
        if played.exhausts or played.temporary:
            self.exile_pile.append(played)
        else:
            self.discard_pile.append(played)
        self.message = result
        self.resolve_immediate_cleanup()
        self.check_battle_end()

    def resolve_immediate_cleanup(self) -> None:
        if self.enemy.hp < 0:
            self.enemy.hp = 0
        if self.player_hp < 0:
            self.player_hp = 0

    def resolve_end_of_turn_effects(self) -> None:
        remaining: list[ActiveEffect] = []
        for effect in self.active_effects:
            effect.turns_left -= 1
            if effect.turns_left > 0:
                remaining.append(effect)
        self.active_effects = remaining

    def check_battle_end(self) -> None:
        if self.player_hp <= 0:
            self.player_hp = 0
            self.screen_mode = DEFEAT
            self.message = "Defeat. Press R to begin the rite anew."
            return
        if self.enemy.hp <= 0:
            self.enemy.hp = 0
            self.prepare_reward_screen()

    def prepare_reward_screen(self) -> None:
        self.screen_mode = REWARD
        self.pending_reward_enemy_name = self.enemy.name
        self.reward_preview_yield = dict(self.enemy.component_yield)
        self.reward_buttons = [
            (Button(pygame.Rect(120, 470, 320, 88), "Commune with Soul"), "soul"),
            (Button(pygame.Rect(480, 470, 320, 88), "Consecrate Blood"), "blood"),
            (Button(pygame.Rect(840, 470, 320, 88), "bone"), "bone"),
        ]
        self.message = "The remains tremble. She draws near. Choose one ritual."

    def apply_reward_choice(self, reward_key: str) -> None:
        for component_name, amount in self.reward_preview_yield.items():
            self.change_component(component_name, amount)

        reward_message = []
        if reward_key == "soul":
            self.discard_pile.append(self.last_battle_card_reward)
            reward_message.append(f"You commune with the dead and gain {self.last_battle_card_reward.name}.")
        elif reward_key == "blood":
            self.player_max_hp += 2
            self.player_hp = min(self.player_max_hp, self.player_hp + 2)
            self.next_fight_strength += 1
            reward_message.append("Blood is consecrated. Gain +2 max HP and 1 Strength next fight.")
        elif reward_key == "bone":
            self.wards += 2
            reward_message.append("Bone is consecrated. Gain 2 Wards.")

        yield_text = ", ".join(f"{key} +{value}" for key, value in self.reward_preview_yield.items())
        reward_message.append(f"From the corpse: {yield_text}.")

        if self.enemy_queue:
            self.enemy = self.enemy_queue.pop(0)
            self.active_effects.clear()
            self.enemy.block = 0
            self.enemy.hexed = False
            self.current_strength = 0
            self.turn_number += 1
            self.draw_pile += self.discard_pile
            self.discard_pile.clear()
            self.rng.shuffle(self.draw_pile)
            self.hand.clear()
            self.screen_mode = BATTLE
            self.message = " ".join(reward_message)
            self.start_player_turn(initial=True)
        else:
            self.run_won = True
            self.screen_mode = REWARD
            self.reward_buttons = []
            self.message = " ".join(reward_message) + " The path falls silent. Press R to begin another run."


# Card factory functions

def make_blood_divination() -> Card:
    def effect(game: GameState) -> str:
        game.change_component("Blood", 1)
        if not game.draw_pile:
            return "Blood Divination grants 1 Blood, but the future is empty."
        peek = game.draw_pile[-3:]
        chosen = peek[-1]
        game.hand.append(chosen)
        game.draw_pile.remove(chosen)
        top_choice = peek[0] if len(peek) > 1 else None
        if top_choice is not None and top_choice in game.draw_pile:
            game.draw_pile.remove(top_choice)
            game.draw_pile.append(top_choice)
        exile_choice = None
        for card in reversed(peek):
            if card is not chosen and card is not top_choice:
                exile_choice = card
                break
        if exile_choice is not None and exile_choice in game.draw_pile:
            game.draw_pile.remove(exile_choice)
            game.exile_pile.append(exile_choice)
        return "Blood Divination grants 1 Blood and reshapes the next turns."

    return Card(
        "Blood Divination",
        1,
        "Gain 1 Blood. Take 1 of the top 3 to hand, 1 back on top, and exile 1.",
        BLOOD_RED,
        effect,
    )


def make_soul_siphon() -> Card:
    def effect(game: GameState) -> str:
        damage = game.deal_damage_to_enemy(5)
        game.change_component("Soul", 1)
        drawn = 0
        if game.enemy.hexed:
            drawn = game.draw_bonus_cards(1)
        return f"Soul Siphon deals {damage}, grants 1 Soul, and draws {drawn}."

    return Card(
        "Soul Siphon",
        1,
        "Deal 5 damage. Gain 1 Soul. If the target is Hexed, draw 1.",
        PURPLE,
        effect,
    )


def make_curse() -> Card:
    def effect(game: GameState) -> str:
        if game.enemy.hexed:
            damage = game.deal_damage_to_enemy(10)
            return f"Curse lashes an already Hexed foe for {damage}."
        damage = game.deal_damage_to_enemy(4)
        game.enemy.hexed = True
        return f"Curse deals {damage} and Hexes the enemy."

    return Card(
        "Curse",
        1,
        "Deal 4 damage and Hex an enemy. If already Hexed, deal 10 instead.",
        PURPLE,
        effect,
    )


def make_bone_ward() -> Card:
    def effect(game: GameState) -> str:
        game.gain_ward(4)
        return "Bone Ward raises 4 Wards."

    return Card(
        "Bone Ward",
        0,
        "Spend 2 Bone or 3 Energy to gain 4 Ward.",
        BONE_WHITE,
        effect,
        component_costs={"Bone": 2},
    )


def make_cursed_ground() -> Card:
    def effect(game: GameState) -> str:
        game.active_effects = [eff for eff in game.active_effects if eff.name != "Cursed Ground"]
        game.active_effects.append(ActiveEffect("Cursed Ground", 3, {"base_damage": 2, "bonus_damage": 0}))
        return "Cursed Ground spreads beneath the battlefield for 3 turns."

    return Card(
        "Cursed Ground",
        2,
        "For 3 turns, your damaging rites trigger 2 extra damage to grounded enemies.",
        GREEN,
        effect,
        exhausts=True,
    )


def make_essence_transfer() -> Card:
    def effect(game: GameState) -> str:
        damage = game.deal_damage_to_enemy(8)
        heal = damage // 2
        game.player_hp = min(game.player_max_hp, game.player_hp + heal)
        soul_gain = 0
        if game.enemy.hexed:
            game.change_component("Soul", 1)
            soul_gain = 1
        return f"Essence Transfer deals {damage}, heals {heal}, and grants {soul_gain} Soul."

    return Card(
        "Essence Transfer",
        2,
        "Deal 8 damage. Heal half the unblocked damage dealt. If Hexed, gain 1 Soul.",
        ACCENT,
        effect,
    )


def make_spirit_barrage() -> Card:
    def effect(game: GameState) -> str:
        damage = game.deal_damage_to_enemy(4)
        return f"Spirit Barrage deals {damage}."

    return Card(
        "Spirit Barrage",
        1,
        "Deal 4 damage. A future version will sustain itself with Soul.",
        YELLOW,
        effect,
    )


# Enemy factory functions

def make_grave_cultist() -> Enemy:
    return Enemy(
        name="Grave Cultist",
        hp=32,
        max_hp=32,
        block=0,
        hexed=False,
        component_yield={"Soul": 2, "Blood": 1},
        intents=[
            Intent("Needle Rite 7", 7, "attack"),
            Intent("Chant of Ash +6 Block", 6, "block"),
            Intent("Bleed Offering 4", 4, "attack"),
        ],
    )


def make_ossuary_hound() -> Enemy:
    return Enemy(
        name="Ossuary Hound",
        hp=28,
        max_hp=28,
        block=0,
        hexed=False,
        component_yield={"Bone": 2, "Blood": 1},
        intents=[
            Intent("Bite 6", 6, "attack"),
            Intent("Brace +5 Block", 5, "block"),
            Intent("Lunge 9", 9, "attack"),
        ],
    )


# Drawing helpers

def draw_text(surface: pygame.Surface, font: pygame.font.Font, text: str, color: tuple[int, int, int], x: int, y: int) -> None:
    rendered = font.render(text, True, color)
    surface.blit(rendered, (x, y))


def draw_centered_text(surface: pygame.Surface, font: pygame.font.Font, text: str, color: tuple[int, int, int], rect: pygame.Rect) -> None:
    rendered = font.render(text, True, color)
    surface.blit(rendered, rendered.get_rect(center=rect.center))


def wrap_text(text: str, max_chars: int) -> list[str]:
    words = text.split()
    lines: list[str] = []
    current = ""
    for word in words:
        proposed = word if not current else f"{current} {word}"
        if len(proposed) <= max_chars:
            current = proposed
        else:
            lines.append(current)
            current = word
    if current:
        lines.append(current)
    return lines


def card_rect_for_index(index: int, total: int) -> pygame.Rect:
    card_width = 175
    card_height = 245
    spacing = 18
    total_width = total * card_width + max(0, total - 1) * spacing
    start_x = (WIDTH - total_width) // 2
    x = start_x + index * (card_width + spacing)
    y = HEIGHT - card_height - 26
    return pygame.Rect(x, y, card_width, card_height)


def card_cost_label(card: Card) -> str:
    costs = []
    if card.energy_cost > 0:
        costs.append(str(card.energy_cost))
    for component_name, amount in card.component_costs.items():
        costs.append(f"{amount}{component_name[0]}")
    return " / ".join(costs) if costs else "0"


def draw_card(surface: pygame.Surface, fonts: dict[str, pygame.font.Font], card: Card, rect: pygame.Rect, hovered: bool, playable: bool) -> None:
    shadow_rect = rect.move(0, 6)
    pygame.draw.rect(surface, (10, 12, 16), shadow_rect, border_radius=16)

    card_color = card.color if playable else (180, 180, 180)
    body_color = CARD_BG if playable else (220, 220, 220)
    visible_rect = rect.move(0, -10) if hovered and playable else rect

    pygame.draw.rect(surface, body_color, visible_rect, border_radius=16)
    pygame.draw.rect(surface, CARD_BORDER, visible_rect, 3, border_radius=16)

    header = pygame.Rect(visible_rect.x, visible_rect.y, visible_rect.width, 50)
    pygame.draw.rect(surface, card_color, header, border_top_left_radius=16, border_top_right_radius=16)
    pygame.draw.line(surface, CARD_BORDER, (visible_rect.x, visible_rect.y + 50), (visible_rect.right, visible_rect.y + 50), 2)

    cost_circle = pygame.Rect(visible_rect.x + 10, visible_rect.y + 10, 48, 34)
    pygame.draw.ellipse(surface, PANEL_COLOR, cost_circle)
    pygame.draw.ellipse(surface, TEXT_COLOR, cost_circle, 2)
    draw_centered_text(surface, fonts["small"], card_cost_label(card), TEXT_COLOR, cost_circle)

    draw_text(surface, fonts["medium"], card.name, CARD_TEXT, visible_rect.x + 66, visible_rect.y + 12)

    body_y = visible_rect.y + 72
    for line in wrap_text(card.description, 19):
        draw_text(surface, fonts["small"], line, CARD_TEXT, visible_rect.x + 14, body_y)
        body_y += 24


def draw_battlefield(screen: pygame.Surface, state: GameState, fonts: dict[str, pygame.font.Font], end_turn_button: Button, mouse_pos: tuple[int, int]) -> list[pygame.Rect]:
    screen.fill(BG_COLOR)

    header_rect = pygame.Rect(24, 18, WIDTH - 48, 132)
    pygame.draw.rect(screen, PANEL_COLOR, header_rect, border_radius=18)
    pygame.draw.rect(screen, TEXT_COLOR, header_rect, 2, border_radius=18)

    draw_text(screen, fonts["large"], f"Ritualist HP: {state.player_hp}/{state.player_max_hp}", TEXT_COLOR, 42, 34)
    draw_text(screen, fonts["medium"], f"Block: {state.player_block}", BLOCK_BLUE, 44, 76)
    draw_text(screen, fonts["medium"], f"Wards: {state.wards}", BONE_WHITE, 44, 108)

    draw_text(screen, fonts["large"], f"{state.enemy.name}: {state.enemy.hp}/{state.enemy.max_hp}", TEXT_COLOR, 760, 34)
    draw_text(screen, fonts["medium"], f"Block: {state.enemy.block}", BLOCK_BLUE, 762, 76)
    draw_text(screen, fonts["medium"], f"Hexed: {'Yes' if state.enemy.hexed else 'No'}", PURPLE, 762, 108)

    center_panel = pygame.Rect(220, 162, 840, 232)
    pygame.draw.rect(screen, PANEL_COLOR, center_panel, border_radius=18)
    pygame.draw.rect(screen, TEXT_COLOR, center_panel, 2, border_radius=18)

    draw_text(screen, fonts["large"], "She Draws Near", TEXT_COLOR, 500, 182)
    draw_text(screen, fonts["medium"], f"Turn: {state.turn_number}", TEXT_COLOR, 258, 238)
    draw_text(screen, fonts["medium"], f"Energy: {state.energy}/3", YELLOW, 258, 274)
    draw_text(screen, fonts["medium"], f"Soul: {state.soul}", PURPLE, 258, 310)
    draw_text(screen, fonts["medium"], f"Blood: {state.blood}", BLOOD_RED, 258, 346)
    draw_text(screen, fonts["medium"], f"Bone: {state.bone}", BONE_WHITE, 430, 346)

    intent_rect = pygame.Rect(730, 230, 270, 110)
    pygame.draw.rect(screen, PANEL_ALT, intent_rect, border_radius=14)
    pygame.draw.rect(screen, TEXT_COLOR, intent_rect, 2, border_radius=14)
    draw_text(screen, fonts["small"], "Enemy Intent", MUTED_TEXT, intent_rect.x + 18, intent_rect.y + 14)
    draw_text(screen, fonts["medium"], state.enemy.current_intent().label, ACCENT, intent_rect.x + 18, intent_rect.y + 42)

    active_text = "None"
    if state.active_effects:
        active_text = ", ".join(f"{eff.name} ({eff.turns_left})" for eff in state.active_effects)
    draw_text(screen, fonts["small"], f"Active Rites: {active_text}", TEXT_COLOR, 258, 382)

    msg_rect = pygame.Rect(60, 418, WIDTH - 120, 72)
    pygame.draw.rect(screen, PANEL_COLOR, msg_rect, border_radius=16)
    pygame.draw.rect(screen, TEXT_COLOR, msg_rect, 2, border_radius=16)
    draw_text(screen, fonts["small"], state.message, TEXT_COLOR, msg_rect.x + 16, msg_rect.y + 24)

    end_turn_button.draw(screen, fonts["medium"], end_turn_button.rect.collidepoint(mouse_pos))

    card_rects: list[pygame.Rect] = []
    for index, card in enumerate(state.hand):
        rect = card_rect_for_index(index, len(state.hand))
        hovered = rect.collidepoint(mouse_pos)
        playable = state.can_pay_card(card)[0]
        draw_card(screen, fonts, card, rect, hovered, playable)
        card_rects.append(rect)

    return card_rects


def draw_reward_screen(screen: pygame.Surface, state: GameState, fonts: dict[str, pygame.font.Font], mouse_pos: tuple[int, int]) -> None:
    screen.fill(BG_COLOR)
    panel = pygame.Rect(90, 70, WIDTH - 180, HEIGHT - 140)
    pygame.draw.rect(screen, PANEL_COLOR, panel, border_radius=20)
    pygame.draw.rect(screen, TEXT_COLOR, panel, 2, border_radius=20)

    title = "The remains tremble. She draws near." if not state.run_won else "The dead are silent for now."
    draw_text(screen, fonts["large"], title, TEXT_COLOR, 132, 114)
    draw_text(screen, fonts["medium"], f"Defeated: {state.pending_reward_enemy_name}", MUTED_TEXT, 132, 164)

    if state.reward_preview_yield:
        yield_text = "  ".join(f"{key} +{value}" for key, value in state.reward_preview_yield.items())
        draw_text(screen, fonts["medium"], f"Corpse Yield: {yield_text}", ACCENT, 132, 208)

    lore_lines = [
        "Choose how the Ritualist uses the dead before Death claims them.",
        "Your choice grants its ritual reward in addition to the corpse yield.",
    ]
    for idx, line in enumerate(lore_lines):
        draw_text(screen, fonts["small"], line, TEXT_COLOR, 132, 260 + idx * 34)

    if state.reward_buttons:
        descriptions = {
            "soul": "Gain a new card: Spirit Barrage.",
            "blood": "Gain +2 max HP and 1 Strength for the next fight.",
            "bone": "Gain 2 Wards immediately.",
        }
        for button, key in state.reward_buttons:
            button.draw(screen, fonts["medium"], button.rect.collidepoint(mouse_pos))
            draw_text(screen, fonts["small"], descriptions[key], TEXT_COLOR, button.rect.x, button.rect.y + 100)
    else:
        draw_text(screen, fonts["medium"], state.message, TEXT_COLOR, 132, 430)
        draw_text(screen, fonts["medium"], "Press R to begin another run.", ACCENT, 132, 484)


def draw_defeat_screen(screen: pygame.Surface, state: GameState, fonts: dict[str, pygame.font.Font]) -> None:
    screen.fill(BG_COLOR)
    rect = pygame.Rect(280, 180, 720, 220)
    pygame.draw.rect(screen, PANEL_COLOR, rect, border_radius=18)
    pygame.draw.rect(screen, TEXT_COLOR, rect, 2, border_radius=18)
    draw_centered_text(screen, fonts["large"], "Defeat", RED, pygame.Rect(rect.x, rect.y + 26, rect.width, 40))
    draw_centered_text(screen, fonts["medium"], state.message, TEXT_COLOR, pygame.Rect(rect.x + 20, rect.y + 94, rect.width - 40, 40))
    draw_centered_text(screen, fonts["medium"], "Press R to restart", ACCENT, pygame.Rect(rect.x, rect.y + 152, rect.width, 40))


def main() -> None:
    pygame.init()
    screen = pygame.display.set_mode((WIDTH, HEIGHT))
    pygame.display.set_caption(TITLE)
    clock = pygame.time.Clock()

    fonts = {
        "small": pygame.font.SysFont(None, 28),
        "medium": pygame.font.SysFont(None, 34),
        "large": pygame.font.SysFont(None, 46),
    }

    end_turn_button = Button(pygame.Rect(WIDTH - 220, 514, 170, 52), "End Turn")
    state = GameState()

    while True:
        mouse_pos = pygame.mouse.get_pos()
        card_rects: list[pygame.Rect] = []

        if state.screen_mode == BATTLE:
            card_rects = draw_battlefield(screen, state, fonts, end_turn_button, mouse_pos)
        elif state.screen_mode == REWARD:
            draw_reward_screen(screen, state, fonts, mouse_pos)
        else:
            draw_defeat_screen(screen, state, fonts)

        for event in pygame.event.get():
            if event.type == pygame.QUIT:
                pygame.quit()
                sys.exit()
            if event.type == pygame.KEYDOWN and event.key == pygame.K_r:
                state.reset_run()
            if event.type == pygame.MOUSEBUTTONDOWN and event.button == 1:
                if state.screen_mode == BATTLE:
                    if end_turn_button.rect.collidepoint(event.pos):
                        state.end_turn()
                    else:
                        for index, rect in enumerate(card_rects):
                            if rect.collidepoint(event.pos):
                                state.play_card(index)
                                break
                elif state.screen_mode == REWARD and state.reward_buttons:
                    for button, key in state.reward_buttons:
                        if button.rect.collidepoint(event.pos):
                            state.apply_reward_choice(key)
                            break

        pygame.display.flip()
        clock.tick(FPS)


if __name__ == "__main__":
    main()
