from __future__ import annotations

import random
import sys
from dataclasses import dataclass
from typing import Callable

import pygame


WIDTH = 1280
HEIGHT = 720
FPS = 60
TITLE = "Card Game Prototype"

BG_COLOR = (20, 24, 32)
PANEL_COLOR = (33, 40, 52)
PANEL_ALT = (44, 53, 69)
TEXT_COLOR = (235, 239, 244)
MUTED_TEXT = (176, 184, 196)
ACCENT = (100, 180, 255)
RED = (210, 92, 92)
GREEN = (92, 190, 120)
YELLOW = (232, 196, 92)
CARD_BG = (245, 241, 232)
CARD_BORDER = (80, 72, 64)
CARD_TEXT = (25, 25, 25)
BLOCK_BLUE = (110, 168, 255)


@dataclass(frozen=True)
class Card:
    name: str
    cost: int
    description: str
    color: tuple[int, int, int]
    effect: Callable[["GameState"], str]


@dataclass
class Intent:
    label: str
    amount: int
    kind: str


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
        self.font_name = None
        self.reset_run()

    def reset_run(self) -> None:
        self.player_max_hp = 40
        self.enemy_max_hp = 38
        self.player_hp = self.player_max_hp
        self.enemy_hp = self.enemy_max_hp
        self.player_block = 0
        self.enemy_block = 0
        self.energy = 3
        self.turn_number = 1
        self.message = "Play cards, then end your turn."
        self.game_over = False
        self.victory = False

        self.draw_pile = self.build_starter_deck()
        self.discard_pile: list[Card] = []
        self.hand: list[Card] = []
        self.current_intent = self.roll_enemy_intent()
        self.start_player_turn(initial=True)

    def build_starter_deck(self) -> list[Card]:
        deck = [
            make_strike(),
            make_strike(),
            make_strike(),
            make_strike(),
            make_defend(),
            make_defend(),
            make_defend(),
            make_defend(),
            make_heavy_blow(),
            make_focus(),
        ]
        self.rng.shuffle(deck)
        return deck

    def draw_cards(self, amount: int) -> None:
        for _ in range(amount):
            if not self.draw_pile and self.discard_pile:
                self.draw_pile = self.discard_pile[:]
                self.discard_pile.clear()
                self.rng.shuffle(self.draw_pile)
            if not self.draw_pile:
                return
            self.hand.append(self.draw_pile.pop())

    def start_player_turn(self, initial: bool = False) -> None:
        self.player_block = 0
        self.enemy_block = max(0, self.enemy_block)
        self.energy = 3
        self.hand.clear()
        self.draw_cards(5)
        if not initial:
            self.turn_number += 1
        self.current_intent = self.roll_enemy_intent()
        if not self.game_over:
            self.message = f"Turn {self.turn_number}. Your move."

    def roll_enemy_intent(self) -> Intent:
        roll = self.rng.random()
        if roll < 0.55:
            amount = self.rng.randint(6, 10)
            return Intent(label=f"Attack {amount}", amount=amount, kind="attack")
        if roll < 0.8:
            amount = self.rng.randint(10, 14)
            return Intent(label=f"Big Attack {amount}", amount=amount, kind="attack")
        amount = self.rng.randint(6, 9)
        return Intent(label=f"Fortify +{amount}", amount=amount, kind="block")

    def play_card(self, hand_index: int) -> None:
        if self.game_over:
            return
        if hand_index < 0 or hand_index >= len(self.hand):
            return
        card = self.hand[hand_index]
        if card.cost > self.energy:
            self.message = f"Not enough energy for {card.name}."
            return

        self.energy -= card.cost
        result = card.effect(self)
        played = self.hand.pop(hand_index)
        self.discard_pile.append(played)
        self.message = result
        self.check_end_state()

    def end_turn(self) -> None:
        if self.game_over:
            return

        while self.hand:
            self.discard_pile.append(self.hand.pop())

        if self.current_intent.kind == "attack":
            damage = max(0, self.current_intent.amount - self.player_block)
            self.player_block = max(0, self.player_block - self.current_intent.amount)
            self.player_hp -= damage
            self.message = f"Enemy attacks for {self.current_intent.amount}. You take {damage}."
        else:
            self.enemy_block += self.current_intent.amount
            self.message = f"Enemy gains {self.current_intent.amount} block."

        self.check_end_state()
        if not self.game_over:
            self.start_player_turn()

    def deal_damage_to_enemy(self, amount: int) -> int:
        blocked = min(self.enemy_block, amount)
        self.enemy_block -= blocked
        damage = amount - blocked
        self.enemy_hp -= damage
        return damage

    def gain_player_block(self, amount: int) -> None:
        self.player_block += amount

    def draw_bonus_cards(self, amount: int) -> int:
        before = len(self.hand)
        self.draw_cards(amount)
        return len(self.hand) - before

    def check_end_state(self) -> None:
        if self.enemy_hp <= 0:
            self.enemy_hp = 0
            self.game_over = True
            self.victory = True
            self.message = "Victory. The enemy is defeated. Press R to restart."
        elif self.player_hp <= 0:
            self.player_hp = 0
            self.game_over = True
            self.victory = False
            self.message = "Defeat. Press R to restart."


def make_strike() -> Card:
    def effect(game: GameState) -> str:
        damage = game.deal_damage_to_enemy(6)
        return f"Strike hits for {damage}."

    return Card("Strike", 1, "Deal 6 damage.", RED, effect)


def make_defend() -> Card:
    def effect(game: GameState) -> str:
        game.gain_player_block(5)
        return "Defend grants 5 block."

    return Card("Defend", 1, "Gain 5 block.", BLOCK_BLUE, effect)


def make_heavy_blow() -> Card:
    def effect(game: GameState) -> str:
        damage = game.deal_damage_to_enemy(12)
        return f"Heavy Blow crushes for {damage}."

    return Card("Heavy Blow", 2, "Deal 12 damage.", YELLOW, effect)


def make_focus() -> Card:
    def effect(game: GameState) -> str:
        drawn = game.draw_bonus_cards(2)
        game.gain_player_block(3)
        return f"Focus draws {drawn} and gives 3 block."

    return Card("Focus", 1, "Draw 2 cards. Gain 3 block.", GREEN, effect)


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
    y = HEIGHT - card_height - 28
    return pygame.Rect(x, y, card_width, card_height)


def draw_card(surface: pygame.Surface, font_small: pygame.font.Font, font_medium: pygame.font.Font, font_large: pygame.font.Font, card: Card, rect: pygame.Rect, hovered: bool, playable: bool) -> None:
    shadow_rect = rect.move(0, 6)
    pygame.draw.rect(surface, (10, 12, 16), shadow_rect, border_radius=16)

    card_color = card.color if playable else (180, 180, 180)
    body_color = CARD_BG if playable else (220, 220, 220)
    if hovered and playable:
        rect = rect.move(0, -10)

    pygame.draw.rect(surface, body_color, rect, border_radius=16)
    pygame.draw.rect(surface, CARD_BORDER, rect, 3, border_radius=16)

    header = pygame.Rect(rect.x, rect.y, rect.width, 50)
    pygame.draw.rect(surface, card_color, header, border_top_left_radius=16, border_top_right_radius=16)
    pygame.draw.line(surface, CARD_BORDER, (rect.x, rect.y + 50), (rect.right, rect.y + 50), 2)

    cost_circle = pygame.Rect(rect.x + 10, rect.y + 10, 34, 34)
    pygame.draw.ellipse(surface, PANEL_COLOR, cost_circle)
    pygame.draw.ellipse(surface, TEXT_COLOR, cost_circle, 2)
    draw_centered_text(surface, font_medium, str(card.cost), TEXT_COLOR, cost_circle)

    draw_text(surface, font_medium, card.name, CARD_TEXT, rect.x + 52, rect.y + 14)

    body_y = rect.y + 72
    for line in wrap_text(card.description, 18):
        draw_text(surface, font_small, line, CARD_TEXT, rect.x + 14, body_y)
        body_y += 24


def draw_battlefield(screen: pygame.Surface, state: GameState, fonts: dict[str, pygame.font.Font], end_turn_button: Button, mouse_pos: tuple[int, int]) -> list[pygame.Rect]:
    screen.fill(BG_COLOR)

    header_rect = pygame.Rect(24, 18, WIDTH - 48, 120)
    pygame.draw.rect(screen, PANEL_COLOR, header_rect, border_radius=18)
    pygame.draw.rect(screen, TEXT_COLOR, header_rect, 2, border_radius=18)

    draw_text(screen, fonts["large"], f"Player HP: {state.player_hp}/{state.player_max_hp}", TEXT_COLOR, 42, 36)
    draw_text(screen, fonts["medium"], f"Block: {state.player_block}", BLOCK_BLUE, 44, 80)

    draw_text(screen, fonts["large"], f"Enemy HP: {state.enemy_hp}/{state.enemy_max_hp}", TEXT_COLOR, 770, 36)
    draw_text(screen, fonts["medium"], f"Enemy Block: {state.enemy_block}", BLOCK_BLUE, 772, 80)

    center_panel = pygame.Rect(310, 160, 660, 235)
    pygame.draw.rect(screen, PANEL_COLOR, center_panel, border_radius=18)
    pygame.draw.rect(screen, TEXT_COLOR, center_panel, 2, border_radius=18)

    draw_text(screen, fonts["large"], "Combat Prototype", TEXT_COLOR, 536, 182)
    draw_text(screen, fonts["medium"], f"Turn: {state.turn_number}", TEXT_COLOR, 358, 238)
    draw_text(screen, fonts["medium"], f"Energy: {state.energy}/3", YELLOW, 358, 274)
    draw_text(screen, fonts["medium"], f"Draw: {len(state.draw_pile)}", TEXT_COLOR, 358, 310)
    draw_text(screen, fonts["medium"], f"Discard: {len(state.discard_pile)}", TEXT_COLOR, 358, 346)

    intent_rect = pygame.Rect(720, 230, 200, 86)
    pygame.draw.rect(screen, PANEL_ALT, intent_rect, border_radius=14)
    pygame.draw.rect(screen, TEXT_COLOR, intent_rect, 2, border_radius=14)
    draw_text(screen, fonts["small"], "Enemy Intent", MUTED_TEXT, intent_rect.x + 20, intent_rect.y + 14)
    draw_text(screen, fonts["medium"], state.current_intent.label, ACCENT, intent_rect.x + 20, intent_rect.y + 42)

    msg_rect = pygame.Rect(60, 420, WIDTH - 120, 70)
    pygame.draw.rect(screen, PANEL_COLOR, msg_rect, border_radius=16)
    pygame.draw.rect(screen, TEXT_COLOR, msg_rect, 2, border_radius=16)
    draw_text(screen, fonts["small"], state.message, TEXT_COLOR, msg_rect.x + 16, msg_rect.y + 24)

    end_turn_button.draw(screen, fonts["medium"], end_turn_button.rect.collidepoint(mouse_pos))

    card_rects: list[pygame.Rect] = []
    for index, card in enumerate(state.hand):
        rect = card_rect_for_index(index, len(state.hand))
        hovered = rect.collidepoint(mouse_pos)
        playable = card.cost <= state.energy and not state.game_over
        draw_card(screen, fonts["small"], fonts["medium"], fonts["large"], card, rect, hovered, playable)
        card_rects.append(rect)

    if state.game_over:
        overlay = pygame.Surface((WIDTH, HEIGHT), pygame.SRCALPHA)
        overlay.fill((6, 8, 10, 150))
        screen.blit(overlay, (0, 0))
        result_rect = pygame.Rect(330, 210, 620, 150)
        pygame.draw.rect(screen, PANEL_ALT, result_rect, border_radius=18)
        pygame.draw.rect(screen, TEXT_COLOR, result_rect, 2, border_radius=18)
        title = "Victory" if state.victory else "Defeat"
        title_color = GREEN if state.victory else RED
        draw_centered_text(screen, fonts["large"], title, title_color, pygame.Rect(result_rect.x, result_rect.y + 20, result_rect.width, 40))
        draw_centered_text(screen, fonts["medium"], "Press R to restart", TEXT_COLOR, pygame.Rect(result_rect.x, result_rect.y + 78, result_rect.width, 32))

    return card_rects


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

    end_turn_button = Button(pygame.Rect(WIDTH - 220, 518, 170, 52), "End Turn")
    state = GameState()

    while True:
        mouse_pos = pygame.mouse.get_pos()
        card_rects = draw_battlefield(screen, state, fonts, end_turn_button, mouse_pos)

        for event in pygame.event.get():
            if event.type == pygame.QUIT:
                pygame.quit()
                sys.exit()
            if event.type == pygame.KEYDOWN and event.key == pygame.K_r:
                state.reset_run()
            if event.type == pygame.MOUSEBUTTONDOWN and event.button == 1:
                if end_turn_button.rect.collidepoint(event.pos):
                    state.end_turn()
                else:
                    for index, rect in enumerate(card_rects):
                        if rect.collidepoint(event.pos):
                            state.play_card(index)
                            break

        pygame.display.flip()
        clock.tick(FPS)


if __name__ == "__main__":
    main()
