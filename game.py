import os.path

import pygame
from assets import colors
import copy
import math
import random

pygame.init()

gridwidth = 11
gridheight = 6
size = 64

scwidth, scheight = gridwidth * size, gridheight * size
screen = pygame.display.set_mode((scwidth, scheight), pygame.FULLSCREEN | pygame.SCALED | pygame.DOUBLEBUF)
colselection = colors.BLACK
screencolor = colors.BLACK
screenoptions = [getattr(colors, s) for s in dir(colors) if not s.startswith("__") and not s.endswith("__") and
                 s.startswith('COL')]
screen.fill(screencolor)

grid = pygame.Surface((scwidth, scheight), pygame.HWSURFACE | pygame.SRCALPHA)
grid.fill((0, 0, 0, 0))
for w in range(gridwidth):
    for h in range(gridheight):
        pygame.draw.rect(grid, (*colors.WHITE, 128), (w * size, h * size, size, size), 2, border_radius=4)

win = pygame.Surface((scwidth, scheight), pygame.SRCALPHA)

framerate = 60
clock = pygame.time.Clock()
counter = 0
turntime = 3
turnmod = 0.99
turnmin = 0.1
turns = 0
suddendeath = False
stuns = ('whiff', 'knocked', 'getup')

bar = pygame.image.load("sprites/ui/bar.png").convert_alpha()
arrow = pygame.image.load("sprites/ui/arrow.png").convert_alpha()
lowest = 'p1'
rotate = 0
predictions = []
sdfont = pygame.font.Font(None, 80).render("SUDDEN DEATH", False, colors.RED)
p1winfont = pygame.font.Font(None, 80).render("P1 WINS", False, colors.RED)
p2winfont = pygame.font.Font(None, 80).render("P2 WINS", False, colors.RED)
drawfont = pygame.font.Font(None, 80).render("DRAW", False, colors.BLUE)
font = pygame.font.Font(None)


class Player(pygame.sprite.Sprite):
    moves = [
        {
            'name': "idle",
            'move': True,
            'effect': [0, 0],
            'signature': [0, 0, 0, 0],
        },
        {
            'name': "walk",
            'move': True,
            'effect': [1, 0],
            'signature': [0, 0, 0, 1],
            'altsig': [0, 1, 0, 0],
        },
        {
            'name': "jump",
            'move': True,
            'effect': [0, 1],
            'signature': [1, 0, 0, 0],
        },
        {
            'name': "airdash",
            'move': True,
            'effect': [1, 1],
            'signature': [1, 0, 0, 1],
        },
        {
            'name': "dash",
            'move': True,
            'effect': ([-1, 0], [4, 0]),
            'signature': [0, 1, 0, 1],
        },
        {
            'name': "fall",
            'move': True,
            'effect': [0, 0],
            'signature': [0, 0, 0, 0],
            'air': True,
        },
        {
            'name': "movefall",
            'move': True,
            'effect': [1, 0],
            'signature': [0, 0, 0, 1],
            'altsig': [0, 1, 0, 0],
            'air': True,
        },
        {
            'name': "parry",
            'move': False,
            'effect': [[0, 0]],
            'signature': [0, 0, 1, 0],
            'invincible': True,
            'layer': -2,
        },
        {
            'name': "knocked",
            'move': True,
            'effect': [-1, 0],
            'signature': True,
        },
        {
            'name': "getup",
            'move': True,
            'effect': [0, 0],
            'signature': True,
            'invincible': True | False,
        },
        {
            'name': "recovery",
            'move': True,
            'effect': [0, 0],
            'signature': True,
            'invincible': False,
        },
    ]

    signatures = [s['signature'] for s in moves]
    altsigs = [s['altsig'] for s in moves if 'altsig' in s.keys()]
    whiff = {
        'name': "whiff",
        'move': True,
        'effect': [0, 0],
    }

    def __init__(self, x, y, team, motion, facing='R'):
        super().__init__()
        self.x = x
        self.y = y
        self.team = team
        self.health = 10
        self.super = 10
        self.special = 0
        self.specstart = 0
        self.specmax = 0
        self.specui = pygame.image.load(f"sprites/{type(self).__name__}/special.png")
        self.motion = motion
        self.facing = facing
        self.keycache = []
        self.actionqueue = []
        self.move = type(self).moves[0]
        self.air = False if self.y == gridheight - 1 else True
        self.reverse = False
        self.airmoves = 0
        self.airmax = 2

        self.sprite = None
        self.offset = None
        self.shadow = None
        self.last = [self.x, self.y]
        self.hit = False
        self.aggro = 0

    def getsig(self):
        if len(self.keycache) >= 2:
            signature = list(map(lambda x: 1 if x in self.keycache[-2:] else 0, self.motion))
        elif self.keycache:
            signature = list(map(lambda x: 1 if x == self.keycache[-1] else 0, self.motion))
        else:
            signature = [0, 0, 0, 0]
        while len(signature) > 4 and signature[-1] == 0:
            signature[:] = signature[:-1]

        if self.facing == 'L':
            signature[1], signature[3] = signature[3], signature[1]

        return signature

    def update(self, move=False, key=None):
        if not move:
            if key is not None and key in self.motion:
                self.keycache.append(key)
            return 1

        cls = type(self)

        self.move = None
        self.reverse = False
        if self.actionqueue:
            self.move = self.actionqueue.pop(0)
            if self.move.get('altsig', None):
                self.reverse = True

        else:
            signature = self.getsig() if self.health > 0 else None

            if signature in cls.signatures or signature in cls.altsigs:
                for act in cls.moves:
                    if signature in (act['signature'], (alt := act.get('altsig', None))) and \
                            self.air is act.get('air', False) and \
                            self.super >= act.get('supercost', 0) and \
                            self.special >= act.get('specialcost', 0) and \
                            self.airmoves >= act.get('aircost', 0):
                        self.move = copy.deepcopy(act)
                        self.super -= act.get('supercost', 0)
                        self.special -= act.get('specialcost', 0)
                        self.airmoves -= act.get('aircost', 0)
                        if signature != alt:
                            self.move.pop('altsig', None)
                        else:
                            self.reverse = True
                            self.move.pop('signature')
            if self.move is None:
                self.move = copy.deepcopy(cls.moves[0]) if not self.air else copy.deepcopy(cls.moves[5])

            if isinstance(self.move['effect'], tuple):
                for i, stage in enumerate(self.move['effect'][1:], 2):
                    self.actionqueue.append(self.move.copy())
                    self.actionqueue[-1]['effect'] = stage
                    self.actionqueue[-1]['name'] += str(i)
                    self.actionqueue[-1].pop('super', None)
                    self.actionqueue[-1].pop('special', None)
                    self.actionqueue[-1].pop('supercost', None)
                    self.actionqueue[-1].pop('specialcost', None)
                    self.actionqueue[-1].pop('aircost', None)
                self.move['effect'] = self.move['effect'][0]
                self.move['name'] += '1'

            if nextmove := self.move.get('follow', None):
                self.actionqueue.append(nextmove.copy())
                self.move.pop('follow')
                while nextnextmove := self.actionqueue[-1].get('follow', False):
                    self.actionqueue.append(nextnextmove.copy())
                    self.actionqueue[-2].pop('follow')

            if getup := self.move.get('getup', 0):
                for _ in range(getup):
                    self.actionqueue.append({
                        'name': "getup",
                        'move': True,
                        'effect': [0, 0],
                        'signature': True,
                        'invincible': True,
                    })
            if recovering := self.move.get('recovery', 0):
                for _ in range(recovering):
                    self.actionqueue.append({
                        'name': "recovery",
                        'move': True,
                        'effect': [0, 0],
                        'signature': True,
                        'invincible': False,
                    })

            if not self.move['move'] and not self.move.get('free', False):
                self.actionqueue.append(Player.whiff.copy())

        def determinestr(effect: list, ismove: bool):
            for val in range(len(effect)):
                if ismove:
                    if isinstance(effect[val], str):
                        effect[val] = eval(effect[val]
                                           .replace("x", str(abs(self.x - determinestr.px.x)))
                                           .replace("y", str(self.y - determinestr.px.y)))
                        effect[val] = wbind(effect[val]) if val == 0 else hbind(effect[val])
                else:
                    determinestr(effect[val], True)

        determinestr.px = [s for s in players if s is not self][0]

        determinestr(self.move['effect'], True if self.move['move'] else False)
        if self.actionqueue:
            determinestr(self.actionqueue[0]['effect'], True if self.actionqueue[0]['move'] else False)

        if self.reverse:
            if self.move['move']:
                self.move['effect'][0] *= -1
            else:
                pass

        # print(self.keycache)
        # print(signature)
        # print(self.move)

        self.keycache.clear()

        return 0


class Ruffian(Player):
    moves = [
        {
            'name': "idle",
            'move': True,
            'effect': [0, 0],
            'signature': [0, 0, 0, 0],
        },
        {
            'name': "walk",
            'move': True,
            'effect': [1, 0],
            'signature': [0, 0, 0, 1],
            'altsig': [0, 1, 0, 0],
        },
        {
            'name': "jump",
            'move': True,
            'effect': [0, 1],
            'signature': [1, 0, 0, 0],
        },
        {
            'name': "airdash",
            'move': True,
            'effect': [1, 1],
            'signature': [1, 0, 0, 1],
        },
        {
            'name': "dash",
            'move': True,
            'effect': ([-1, 0], [4, 0]),
            'signature': [0, 1, 0, 1],
        },
        {
            'name': "fall",
            'move': True,
            'effect': [0, 0],
            'signature': [0, 0, 0, 0],
            'air': True,
        },
        {
            'name': "movefall",
            'move': True,
            'effect': [1, 0],
            'signature': [0, 0, 0, 1],
            'altsig': [0, 1, 0, 0],
            'air': True,
        },
        {
            'name': "taunt",
            'move': True,
            'effect': [0, 0],
            'signature': [1, 0, 1, 0],
            'recovery': 2,
            'super': 3,
        },
        {
            'name': "projdodge",
            'move': True,
            'effect': [1, 0],
            'signature': [1, 1, 0, 0],
            'projimmune': True,
            'recovery': 1,
        },
        {
            'name': "roll",
            'move': True,
            'effect': [-1, 0],
            'signature': [0, 1, 1, 0],
            'altsig': [0, 0, 1, 1],
            'dmg': 0,
            'invincible': True,
            'getup': 1,
        },
        {
            'name': "parry",
            'move': False,
            'effect': [[0, 0]],
            'signature': [0, 0, 1, 0],
            'invincible': True,
            'layer': -2,
        },
        {
            'name': "strike_long",
            'move': False,
            'effect': [[1, 0], [2, 0]],
            'signature': [0, 0, 0, 1, 1],
            'knock': [2, 0],
            'priority': -1,
        },
        {
            'name': "strike_close",
            'move': False,
            'effect': [[1, 0], [0, 1], [1, 1]],
            'signature': [0, 0, 0, 0, 1],
            'knock': [1, 1],
            'offset': [0, 1],
        },
        {
            'name': "strike_charge",
            'move': False,
            'effect': ([[0, 0]], [[1, 0], [2, 0], [3, 0]]),
            'signature': [0, 1, 0, 0, 1],
            'targetrecovery': 1,
            'dmg': 4,
            'pierce': 1,
        },
        {
            'name': "strike_grab",
            'move': False,
            'effect': [[1, 0]],
            'signature': [0, 0, 1, 0, 1],
            'dmg': 4,
            'layer': -1,
            'grab': True,
            'throw': [2, 0],
            'targetrecovery': 1,
        },
        {
            'name': "throw",
            'move': True,
            'effect': [0, 0],
            'signature': True,
            'particle': [[32, 0], [[2, 5], [-2, 2]], None, 0.25, 0, None, 8],
        },
        {
            'name': "strike_antiair",
            'move': False,
            'effect': [[-1, 1], [0, 1], [1, 1]],
            'signature': [1, 0, 0, 0, 1],
            'dmg': 3,
            'knock': [0, 2],
            'offset': [1, 1],
        },
        {
            'name': "air_side",
            'move': False,
            'effect': [[1, 0]],
            'signature': [0, 0, 0, 0, 1],
            'knock': [1, 0],
            'air': True,
        },
        {
            'name': "air_down",
            'move': False,
            'effect': [[0, -1]],
            'signature': [0, 0, 1, 0, 1],
            'air': True,
        },
        {
            'name': "jump",
            'move': True,
            'effect': [0, 1],
            'signature': [1, 0, 0, 0],
            'air': True,
            'aircost': 1,
        },
        {
            'name': "airdash",
            'move': True,
            'effect': [1, 1],
            'signature': [1, 0, 0, 1],
            'air': True,
            'aircost': 1,
        },
        {
            'name': "super_run",
            'move': True,
            'effect': [5, 0],
            'signature': [0, 0, 0, 1, 0, 1],
            'supercost': 2,
        },
        {
            'name': "super_evade",
            'move': True,
            'effect': [-2, 0],
            'signature': [0, 1, 0, 0, 0, 1],
            'supercost': 6,
        },
        {
            'name': "super_ray",
            'move': False,
            'effect': ([[x, y] for y in range(0, 2) for x in range(-1, 2)],
                       [[x, y] for y in range(0, 3) for x in range(-2, 3) if abs(x) > 1 or abs(y) > 1]),
            'signature': [0, 0, 0, 0, 1, 1],
            'dmg': 4,
            'knock': [1],
            'invincible': True,
            'free': True,
            'hitcancel': False,
            'supercost': 9,
            'offset': [2, 2],
        },
    ]

    signatures = [s['signature'] for s in moves]
    altsigs = [s['altsig'] for s in moves if 'altsig' in s.keys()]

    def __init__(self, x, y, team, motion, facing='R'):
        super().__init__(x, y, team, motion, facing)
        self.specmax = 3  # freecancel

    def update(self, move=False, key=None):
        specvalid = False
        if self.actionqueue:
            specvalid = True
        super().update(move, key)
        if move and specvalid and self.special >= 3 and sum(self.getsig()):
            self.move = None
            self.actionqueue.clear()
            self.special = 0
            super().update(move, key)


class Wrestler(Player):
    moves = [
        {
            'name': "idle",
            'move': True,
            'effect': [0, 0],
            'signature': [0, 0, 0, 0],
        },
        {
            'name': "walk",
            'move': True,
            'effect': [1, 0],
            'signature': [0, 0, 0, 1],
        },
        {
            'name': "jump",
            'move': True,
            'effect': [0, 1],
            'signature': [1, 0, 0, 0],
        },
        {
            'name': "airdash",
            'move': True,
            'effect': [1, 1],
            'signature': [1, 0, 0, 1],
            'recovery': 1,
            'follow': {
                'name': "crush",
                'move': False,
                'effect': [[0, -1]],
                'signature': True,
                'particle': [[0, 32], None, None, None, None, None, 8],
            },
        },
        {
            'name': "cycle",
            'move': True,
            'effect': ([-1, 0], [1, 0]),
            'signature': [0, 1, 0, 1],
        },
        {
            'name': "fall",
            'move': True,
            'effect': [0, 0],
            'signature': [0, 0, 0, 0],
            'air': True,
        },
        {
            'name': "movefall",
            'move': True,
            'effect': [1, 0],
            'signature': [0, 0, 0, 1],
            'altsig': [0, 1, 0, 0],
            'air': True,
        },
        {
            'name': "walkback",
            'move': True,
            'effect': [-1, 0],
            'signature': [0, 1, 0, 0],
            'follow': {
                'name': "crush",
                'move': False,
                'effect': [[-1, 0], [1, 0]],
                'signature': True,
                'free': True,
                'priority': 1,
            },
        },
        {
            'name': "taunt",
            'move': True,
            'effect': [0, 0],
            'signature': [1, 0, 1, 0],
            'recovery': 2,
            'super': 3,
        },
        {
            'name': "shell",
            'move': True,
            'effect': [0, 0],
            'signature': [1, 1, 0, 0],
            'invincible': True,
            'hitwhiff': False,
            'layer': -2,
        },
        {
            'name': "roll",
            'move': True,
            'effect': [-1, 0],
            'signature': [0, 1, 1, 0],
            'altsig': [0, 0, 1, 1],
            'dmg': 0,
            'invincible': True,
            'getup': 1,
        },
        {
            'name': "parry",
            'move': False,
            'effect': [[0, 0]],
            'signature': [0, 0, 1, 0],
            'invincible': True,
            'layer': -2,
        },
        {
            'name': "strike_straight",
            'move': False,
            'effect': [[1, 0], [2, 0]],
            'signature': [0, 0, 0, 1, 1],
            'dmg': 3,
            'knock': [1, 0],
            'free': True,
            'hitcancel': False,
            'armor': 1,
            'follow': {
                'name': "walk",
                'move': True,
                'effect': [1, 0],
                'signature': [0, 0, 0, 1],
            },
        },
        {
            'name': "strike_shove",
            'move': False,
            'effect': [[1, 0], [1, 1]],
            'signature': [0, 0, 0, 0, 1],
            'knock': [3, 0],
            'offset': [0, 1]
        },
        {
            'name': "strike_stomp",
            'move': False,
            'effect': ([[0, 0]], [[1, 0], [2, 0], [3, 0]]),
            'signature': [0, 1, 0, 0, 1],
            'dmg': 4,
            'knock': [0, 1],
            'armor': 1,
        },
        {
            'name': "strike_slam",
            'move': False,
            'effect': [[1, 0]],
            'signature': [0, 0, 1, 0, 1],
            'dmg': 5,
            'layer': -1,
            'grab': True,
            'knock': [gridwidth, 0],
            'targetrecovery': 1,
            'hitcancel': False,
            'whiffcancel': True,
            'follow': {
                'name': "throw",
                'move': True,
                'effect': [gridwidth, 0],
                'signature': True,
            },
        },
        {
            'name': "strike_grounder",
            'move': False,
            'effect': [[0, 1]],
            'signature': [1, 0, 0, 0, 1],
            'dmg': 4,
            'throw': [[1, -1], [1, 0]],
            'free': True,
            'recovery': 1,
            'targetrecovery': 1,
            'offset': [0, 1],
        },
        {
            'name': "air_toss",
            'move': False,
            'effect': [[1, 0]],
            'signature': [0, 0, 0, 0, 1],
            'air': True,
            'grab': True,
            'throw': [0, 2],
        },
        {
            'name': "air_grounder",
            'move': False,
            'effect': [[1, 0]],
            'signature': [0, 0, 1, 0, 1],
            'air': True,
            'dmg': 6,
            'grab': True,
            'knock': [[0, -gridheight], [gridwidth, 0]],
            'recovery': 2,
            'targetrecovery': 1,
            'whiffcancel': True,
            'follow': {
                'name': "air_smash",
                'move': True,
                'effect': [0, -gridheight],
                'signature': True,
            },
        },
        {
            'name': "jump",
            'move': True,
            'effect': [0, 1],
            'signature': [1, 0, 0, 0],
            'air': True,
            'aircost': 2,
        },
        {
            'name': "airdash",
            'move': True,
            'effect': [1, 1],
            'signature': [1, 0, 0, 1],
            'air': True,
            'aircost': 2,
        },
        {
            'name': "super_backstep",
            'move': True,
            'effect': [-2, 0],
            'signature': [0, 1, 0, 0, 0, 1],
            'supercost': 2,
        },
        {
            'name': "super_drop",
            'move': True,
            'effect': [0, -gridheight],
            'signature': [0, 0, 1, 0, 0, 1],
            'air': True,
            'dmg': 5,
            'knock': [0, 0],
            'supercost': 6,
            'follow': {
                'name': "crush",
                'move': True,
                'effect': [
                    {
                        'pos': [1, 0],
                        'name': "proj_quake",
                        'drive': [2, 0],
                    },
                    {
                        'pos': [-1, 0],
                        'name': "proj_quake",
                        'reversefacing': True,
                        'drive': [2, 0],
                    },
                ],
                'signature': True,
                'projectile': True,
            },
        },
        {
            'name': "super_ASEB",
            'move': False,
            'effect': [[1, 1]],
            'signature': [0, 0, 0, 0, 1, 1],
            'dmg': 100,
            'grab': True,
            'knock': [10],
            'armor': 2,
            'supercost': 9,
            'offset': [0, 1],
        }
    ]

    signatures = [s['signature'] for s in moves]
    altsigs = [s['altsig'] for s in moves if 'altsig' in s.keys()]

    def __init__(self, x, y, team, motion, facing='R'):
        super().__init__(x, y, team, motion, facing)
        self.specmax = 4  # knockboost

    def update(self, move=False, key=None):
        super().update(move, key)
        if move and self.move == Wrestler.moves[0]:
            self.special += 0.5


class Roller(Player):
    moves = [
        {
            'name': "idle",
            'move': True,
            'effect': [0, 0],
            'signature': [0, 0, 0, 0],
        },
        {
            'name': "walk",
            'move': True,
            'effect': [1, 0],
            'signature': [0, 0, 0, 1],
            'altsig': [0, 1, 0, 0],
        },
        {
            'name': "jump",
            'move': True,
            'effect': [0, 1],
            'signature': [1, 0, 0, 0],
        },
        {
            'name': "airdash",
            'move': True,
            'effect': [1, 1],
            'signature': [1, 0, 0, 1],
        },
        {
            'name': "dash",
            'move': True,
            'effect': ([-1, 0], [4, 0]),
            'signature': [0, 1, 0, 1],
        },
        {
            'name': "fall",
            'move': True,
            'effect': [0, 0],
            'signature': [0, 0, 0, 0],
            'air': True,
        },
        {
            'name': "movefall",
            'move': True,
            'effect': [1, 0],
            'signature': [0, 0, 0, 1],
            'altsig': [0, 1, 0, 0],
            'air': True,
        },
        {
            'name': "taunt",
            'move': True,
            'effect': [0, 0],
            'signature': [1, 0, 1, 0],
            'recovery': 2,
            'super': 3,
        },
        {
            'name': "teleport",
            'move': True,
            'effect': [3, 0],
            'signature': [1, 1, 0, 0],
            'teleport': True,
            'projimmune': True,
            'recovery': 1,
        },
        {
            'name': "roll",
            'move': True,
            'effect': [-1, 0],
            'signature': [0, 1, 1, 0],
            'altsig': [0, 0, 1, 1],
            'dmg': 0,
            'invincible': True,
            'getup': 1,
        },
        {
            'name': "parry",
            'move': False,
            'effect': [[0, 0]],
            'signature': [0, 0, 1, 0],
            'invincible': True,
            'layer': -2,
        },
        {
            'name': "strike_dropkick",
            'move': True,
            'effect': [1, 1],
            'signature': [0, 0, 0, 1, 1],
            'getup': 1,
            'follow': {
                'name': "strike_dropkick2",
                'move': False,
                'effect': [[1, 0]],
                'signature': True,
                'dmg': 4,
                'knock': [5, 0],
                'free': True,
                'hitcancel': False,
            },
        },
        {
            'name': "strike_inst",
            'move': False,
            'effect': [[1, 0]],
            'signature': [0, 0, 0, 0, 1],
            'dmg': 1,
            'knock': [1, 0],
            'pierce': 2,
            'priority': 3,
        },
        {
            'name': "strike_tp",
            'move': True,
            'effect': ["x - 1", "y"],
            'signature': [0, 1, 0, 0, 1],
            'teleport': True,
            'follow': {
                'name': "strike_tp2",
                'move': False,
                'effect': [[1, 0]],
                'signature': True,
                'dmg': 4,
                'knock': [2, 0],
                'free': True,
                'priority': -1,
            },
        },
        {
            'name': "strike_swap",
            'move': False,
            'effect': [[1, 0]],
            'signature': [0, 0, 1, 0, 1],
            'dmg': 3,
            'layer': -1,
            'grab': True,
            'knock': [[-1, 0], [2, 0]],
            'hitcancel': False,
            'whiffcancel': True,
            'follow': {
                'name': "strike_swap2",
                'move': True,
                'effect': [1, 0],
                'teleport': True,
            },
        },
        {
            'name': "strike_updraft",
            'move': False,
            'effect': [[0, 1], [0, 2]],
            'signature': [1, 0, 0, 0, 1],
            'knock': [0, 1],
            'offset': [0, 2],
        },
        {
            'name': "air_punch",
            'move': False,
            'effect': [[1, 0]],
            'signature': [0, 0, 0, 0, 1],
            'air': True,
            'dmg': 3,
            'knock': [0, -1],
        },
        {
            'name': "air_roll",
            'move': True,
            'effect': [-1, 0],
            'signature': [0, 1, 1, 0],
            'altsig': [0, 0, 1, 1],
            'air': True,
            'dmg': 0,
            'invincible': True,
            'getup': 1,
        },
        {
            'name': "jump",
            'move': True,
            'effect': [0, 1],
            'signature': [1, 0, 0, 0],
            'air': True,
            'aircost': 1,
        },
        {
            'name': "airdash",
            'move': True,
            'effect': [1, 1],
            'signature': [1, 0, 0, 1],
            'air': True,
            'aircost': 1,
        },
        {
            'name': "air_swim",
            'move': True,
            'effect': [2, 1],
            'signature': [1, 0, 0, 0, 1],
            'air': True,
            'recovery': 1,
        },
        {
            'name': "air_sink",
            'move': True,
            'effect': [2, -1],
            'signature': [0, 0, 1, 0, 1],
            'air': True,
            'recovery': 1,
        },
        {
            'name': "super_release",
            'move': True,
            'effect': [0, 0],
            'signature': [0, 0, 0, 0, 0, 1],
            'special': -6,
            'supercost': 2,
        },
        {
            'name': "super_teleport",
            'move': True,
            'effect': ["x + 1", "y"],
            'signature': [0, 1, 0, 0, 0, 1],
            'teleport': True,
            'supercost': 6,
        },
        {
            'name': "super_burst",
            'move': False,
            'effect': [[x, y] for y in range(-1, 2) for x in range(-1, 2) if x or y],
            'signature': [0, 0, 0, 0, 1, 1],
            'dmg': 1,
            'knock': [10],
            'invincible': True,
            'free': True,
            'special': 6,
            'supercost': 9,
        },
    ]

    signatures = [s['signature'] for s in moves]
    altsigs = [s['altsig'] for s in moves if 'altsig' in s.keys()]

    def __init__(self, x, y, team, motion, facing='R'):
        super().__init__(x, y, team, motion, facing)
        self.specmax = 6  # momentum
        self.airmax = 3

    def update(self, move=False, key=None):
        super().update(move, key)
        if move is True:
            if self.move['name'] in stuns:
                self.special = 0
                return
            if self.special == 0:
                if self.actionqueue and not self.actionqueue[0]['move']:
                    self.actionqueue.clear()
                    self.move = Roller.moves[12].copy()
                    self.actionqueue.append(Player.whiff.copy())
                # elif self.actionqueue and self.actionqueue[0]['name'] in stuns:
                #     self.move = Roller.moves[0].copy()
            if self.move['move'] and self.move['effect'][0] and not self.move.get('teleport', False) and not \
                    (self.move['effect'][0] < 0 and self.x <= 0 or
                     self.move['effect'][0] > 0 and self.x >= gridwidth - 1):
                self.move['effect'][0] += math.copysign(self.special // 3, self.move['effect'][0])
                self.special += 1
            elif not self.actionqueue:
                self.special -= 1


class GunGuy(Player):
    moves = [
        {
            'name': "idle",
            'move': True,
            'effect': [0, 0],
            'signature': [0, 0, 0, 0],
        },
        {
            'name': "walk",
            'move': True,
            'effect': [1, 0],
            'signature': [0, 0, 0, 1],
            'altsig': [0, 1, 0, 0],
        },
        {
            'name': "jump",
            'move': True,
            'effect': [0, 1],
            'signature': [1, 0, 0, 0],
        },
        {
            'name': "airdash",
            'move': True,
            'effect': [1, 1],
            'signature': [1, 0, 0, 1],
        },
        {
            'name': "reload",
            'move': True,
            'effect': [0, 0],
            'signature': [0, 1, 0, 1],
            'special': 1,
        },
        {
            'name': "fall",
            'move': True,
            'effect': [0, 0],
            'signature': [0, 0, 0, 0],
            'air': True,
        },
        {
            'name': "movefall",
            'move': True,
            'effect': [1, 0],
            'signature': [0, 0, 0, 1],
            'altsig': [0, 1, 0, 0],
            'air': True,
        },
        {
            'name': "taunt",
            'move': True,
            'effect': [0, 0],
            'signature': [1, 0, 1, 0],
            'recovery': 2,
            'super': 3,
        },
        {
            'name': "reflect",
            'move': True,
            'effect': [0, 0],
            'signature': [1, 1, 0, 0],
            'projimmune': True,
            'projreflect': True,
            'recovery': 1,
        },
        {
            'name': "roll",
            'move': True,
            'effect': [-1, 0],
            'signature': [0, 1, 1, 0],
            'altsig': [0, 0, 1, 1],
            'dmg': 0,
            'invincible': True,
            'getup': 1,
        },
        {
            'name': "parry",
            'move': False,
            'effect': [[0, 0]],
            'signature': [0, 0, 1, 0],
            'invincible': True,
            'layer': -2,
        },
        {
            'name': "strike_hipfire",
            'move': False,
            'effect': [[1, 0], [2, 0]],
            'signature': [0, 0, 0, 1, 1],
            'knock': [1, 0],
            'special': -2,
        },
        {
            'name': "strike_spin",
            'move': False,
            'effect': [[1, 0], [-1, 0]],
            'signature': [0, 0, 0, 0, 1],
            'dmg': 3,
            'knock': [1],
            'offset': [1, 0],
        },
        {
            'name': "strike_shoot",
            'move': False,
            'effect': ([[0, 0]], [["x", "y - 1"]]),
            'signature': [0, 1, 0, 0, 1],
            'knock': [1],
            'special': -1,
        },
        {
            'name': "strike_dist",
            'move': False,
            'effect': [[1, 0]],
            'signature': [0, 0, 1, 0, 1],
            'dmg': 4,
            'layer': -1,
            'grab': True,
            'knock': [2, 0],
            'whiffcancel': True,
            'targetrecovery': 1,
            'follow': {
                'name': "strike_dist2",
                'move': True,
                'effect': [-1, 0],
                'signature': True,
            },
        },
        {
            'name': "strike_zone",
            'move': True,
            'effect': [
                {
                    'pos': [0, 1],
                    'name': "proj_blast",
                    'drive': [0, 2],
                    'damage': 2,
                    'knock': [0, 1],
                },
                {
                    'pos': [1, 1],
                    'name': "proj_zone",
                    'drive': [2, 0],
                    'damage': 4,
                },
                {
                    'pos': [-1, 1],
                    'name': "proj_zone",
                    'reversefacing': True,
                    'drive': [2, 0],
                    'damage': 4,
                },
            ],
            'signature': [1, 0, 0, 0, 1],
            'projectile': True,
            'special': -3,
        },
        {
            'name': "air_shoot",
            'move': False,
            'effect': ([[0, 0]], [["x", "y - 1"]]),
            'signature': [0, 0, 0, 0, 1],
            'air': True,
            'knock': [1],
            'special': -1,
        },
        {
            'name': "air_hipfire",
            'move': False,
            'effect': [[0, -1], [0, -2]],
            'signature': [0, 0, 1, 0, 1],
            'air': True,
            'special': -2,
            'aircost': 1,
        },
        {
            'name': "jump",
            'move': True,
            'effect': [0, 1],
            'signature': [1, 0, 0, 0],
            'air': True,
            'aircost': 1,
        },
        {
            'name': "airdash",
            'move': True,
            'effect': [1, 1],
            'signature': [1, 0, 0, 1],
            'air': True,
            'aircost': 1,
        },
        {
            'name': "super_quickfire",
            'move': False,
            'effect': ([[0, 0]], [["x", "y - 1"]]),
            'signature': [0, 1, 0, 0, 0, 1],
            'knock': [0, 0],
            'hitcancel': False,
            'special': -1,
            'supercost': 2,
            'follow': {
                'name': "super_quickfire3",
                'move': False,
                'effect': [["x", "y - 1"]],
                'signature': True,
                'dmg': 1,
                'knock': [0, 0],
                'hitcancel': False,
                'special': -1,
                'follow': {
                    'name': "super_quickfire4",
                    'move': False,
                    'effect': [["x", "y - 1"]],
                    'signature': True,
                    'dmg': 1,
                    'knock': [0, 0],
                    'hitcancel': False,
                    'special': -1,
                    'follow': {
                        'name': "super_quickfire5",
                        'move': False,
                        'effect': [["x", "y - 1"]],
                        'signature': True,
                        'dmg': 1,
                        'knock': [0, 0],
                        'hitcancel': False,
                        'special': -1,
                        'follow': {
                            'name': "super_quickfire6",
                            'move': False,
                            'effect': [["x", "y - 1"]],
                            'signature': True,
                            'dmg': 1,
                            'knock': [0, 0],
                            'hitcancel': False,
                            'special': -1,
                            'follow': {
                                'name': "super_quickfire7",
                                'move': False,
                                'effect': [["x", "y - 1"]],
                                'signature': True,
                                'dmg': 2,
                                'knock': [gridwidth, 0],
                                'targetrecoveru': 1,
                                'special': -3,
                            },
                        },
                    },
                },
            },
        },
        {
            'name': "super_reload",
            'move': True,
            'effect': [0, 0],
            'signature': [0, 0, 1, 0, 0, 1],
            'special': 8,
            'supercost': 6,
        },
        {
            'name': "super_deathball",
            'move': True,
            'effect': [
                {
                    'pos': [1, 0],
                    'name': "proj_deathball",
                    'drive': [1, 0],
                    'damage': 10,
                },
                {
                    'pos': [1, 1],
                    'name': "proj_deathball",
                    'damage': 10,
                },
            ],
            'signature': [0, 0, 0, 0, 1, 1],
            'projectile': True,
            'supercost': 9,
        },
    ]

    signatures = [s['signature'] for s in moves]
    altsigs = [s['altsig'] for s in moves if 'altsig' in s.keys()]

    def __init__(self, x, y, team, motion, facing='R'):
        super().__init__(x, y, team, motion, facing)
        self.specstart = 8  # ammo
        self.specmax = 8

    def update(self, move=False, key=None):
        super().update(move, key)
        if move:
            if (spec := self.move.get('special', 0)) < 0:
                if self.special + spec >= 0:
                    self.special += spec
                    self.move['special'] = 0
                else:
                    self.move = copy.deepcopy(GunGuy.moves[4])
                    self.actionqueue.clear()


class Tussler(Player):
    moves = [
        {
            'name': "idle",
            'move': True,
            'effect': [0, 0],
            'signature': [0, 0, 0, 0],
        },
        {
            'name': "walk",
            'move': True,
            'effect': [1, 0],
            'signature': [0, 0, 0, 1],
            'altsig': [0, 1, 0, 0],
        },
        {
            'name': "jump",
            'move': True,
            'effect': [0, 1],
            'signature': [1, 0, 0, 0],
        },
        {
            'name': "airdash",
            'move': True,
            'effect': [1, 1],
            'signature': [1, 0, 0, 1],
        },
        {
            'name': "backstep",
            'move': True,
            'effect': ([-2, 0], [1, 0]),
            'signature': [0, 1, 0, 1],
        },
        {
            'name': "fall",
            'move': True,
            'effect': [0, 0],
            'signature': [0, 0, 0, 0],
            'air': True,
        },
        {
            'name': "movefall",
            'move': True,
            'effect': [1, 0],
            'signature': [0, 0, 0, 1],
            'altsig': [0, 1, 0, 0],
            'air': True,
        },
        {
            'name': "taunt",
            'move': True,
            'effect': [0, 0],
            'signature': [1, 0, 1, 0],
            'recovery': 2,
            'super': 3,
        },
        {
            'name': "catch",
            'move': True,
            'effect': [0, 0],
            'signature': [1, 1, 0, 0],
            'projimmune': True,
            'recovery': 1,
        },
        {
            'name': "roll",
            'move': True,
            'effect': [-1, 0],
            'signature': [0, 1, 1, 0],
            'altsig': [0, 0, 1, 1],
            'dmg': 0,
            'invincible': True,
            'getup': 1,
        },
        {
            'name': "parry",
            'move': False,
            'effect': [[0, 0]],
            'signature': [0, 0, 1, 0],
            'invincible': True,
            'layer': -2,
        },
        {
            'name': "strike_clash",
            'move': False,
            'effect': ([[0, 0]], [[1, 0], [2, 0]]),
            'signature': [0, 0, 0, 1, 1],
            'knock': [1, 1],
            'dmg': 3,
            'free': True,
            'armor': 1,
        },
        {
            'name': "strike_summon",
            'move': False,
            'effect': [[1, 0]],
            'signature': [0, 0, 0, 0, 1],
            'dmg': 1,
            'knock': [1, 0],
            'targetrecovery': 1,
            'free': True,
            'follow': {
                'name': "strike_summon2",
                'move': True,
                'effect': [
                    {
                        'pos': [-1, 0],
                        'name': "proj_pressure",
                        'pierce': 1,
                    },
                ],
                'signature': True,
                'projectile': True,
            },
        },
        {
            'name': "strike_whip",
            'move': False,
            'effect': ([[3, 0]], [[0, 0]]),
            'signature': [0, 1, 0, 0, 1],
            'grab': True,
            'knock': [[-2, 0], [0, 0]],
            'free': True,
            'hitcancel': False,
        },
        {
            'name': "strike_toss",
            'move': False,
            'effect': [[1, 0]],
            'signature': [0, 0, 1, 0, 1],
            'dmg': 3,
            'grab': True,
            'throw': [[-1, 1], [0, 0]],
        },
        {
            'name': "strike_fly",
            'move': False,
            'effect': [[0, 1]],
            'signature': [1, 0, 0, 0, 1],
            'knock': [[0, 1], [0, 0]],
            'hitcancel': False,
            'offset': [0, 1],
            'follow': {
                'name': "jump",
                'move': True,
                'effect': [0, 1],
                'signature': True,
            },
        },
        {
            'name': "air_slice",
            'move': False,
            'effect': [[1, -1], [1, 0], [1, 1]],
            'signature': [0, 0, 0, 0, 1],
            'air': True,
            'knock': [1, 0],
            'offset': [0, 1],
        },
        {
            'name': "air_summon",
            'move': True,
            'effect': [
                {
                    'pos': [1, 0],
                    'name': "proj_diagonal",
                    'drive': [1, -1],
                },
            ],
            'signature': [0, 0, 1, 0, 1],
            'air': True,
            'projectile': True,
            'recovery': 1,
            'aircost': 1,
        },
        {
            'name': "jump",
            'move': True,
            'effect': [0, 1],
            'signature': [1, 0, 0, 0],
            'air': True,
            'aircost': 1,
        },
        {
            'name': "airdash",
            'move': True,
            'effect': [1, 1],
            'signature': [1, 0, 0, 1],
            'air': True,
            'aircost': 1,
        },
        {
            'name': "super_trap",
            'move': True,
            'effect': [
                {
                    'pos': [1, 0],
                    'name': "proj_trap",
                    'drive': [0, 0],
                    'damage': 4,
                    'lifespan': 15,
                },
            ],
            'signature': [0, 0, 0, 1, 0, 1],
            'projectile': True,
            'supercost': 2,
        },
        {
            'name': "super_trap",
            'move': True,
            'effect': [
                {
                    'pos': [1, 0],
                    'name': "proj_trap",
                    'drive': [0, 0],
                    'damage': 4,
                    'lifespan': 15,
                },
            ],
            'signature': [0, 0, 0, 1, 0, 1],
            'air': True,
            'projectile': True,
            'supercost': 2,
        },
        {
            'name': "super_defuse",
            'move': False,
            'effect': [[x, y] for y in range(gridheight) for x in range(gridwidth)],
            'signature': [0, 0, 1, 0, 0, 1],
            'dmg': 0,
            'free': True,
            'projhit': True,
            'supercost': 6,
        },
        {
            'name': "super_vacuum",
            'move': False,
            'effect': [[x, y] for y in range(gridheight) for x in range(gridwidth)],
            'signature': [0, 0, 0, 0, 1, 1],
            'dmg': 0,
            'knock': [-3],
            'recovery': 1,
            'supercost': 3,
            'priority': -1,
        },
    ]

    signatures = [s['signature'] for s in moves]
    altsigs = [s['altsig'] for s in moves if 'altsig' in s.keys()]

    def __init__(self, x, y, team, motion, facing='R'):
        super().__init__(x, y, team, motion, facing)
        self.specstart = 1  # armorboost
        self.specmax = 1

    def update(self, move=False, key=None):
        super().update(move, key)
        if move:
            if self.special and not self.move['move']:
                self.move['armor'] = self.move.get('armor', 0) + 1
                self.special -= 1


class Projectile(pygame.sprite.Sprite):
    def __init__(self, x, y, img, master: Player, facing: str, drive: list[int, int] = None, damage=1, dieonhit=True,
                 interrupt=True, knock=None, lifespan=999, pierce=0, supergain=1):
        super().__init__()
        self.x = x
        self.y = y
        self.img = teamcolor(pygame.image.load(f"sprites/{type(master).__name__}/{img}.png").convert_alpha(),
                             master.team)
        self.master = master
        self.facing = facing
        self.drive = drive if drive is not None else [1, 0]
        self.age = 0
        self.effect = {
            'damage': damage,
            'dieonhit': dieonhit,
            'interrupt': interrupt,
            'knock': knock,
            'lifespan': lifespan,
            'pierce': pierce,
            'supergain': supergain,
        }
        self.last = [self.x, self.y]
        self.firstmove = True

    def update(self):
        if self.firstmove:
            self.firstmove = False
            self.age += 1
            return
        if self.age >= self.effect['lifespan']:
            self.kill()
            return
        self.age += 1

        Projectile.calchit(self)
        drive = self.drive.copy()
        self.last = [self.x, self.y]
        mod = 1 if self.facing == 'R' else -1
        while drive != [0, 0]:
            if self.drive[0]:
                self.x += math.copysign(1, self.drive[0] * mod)
                drive[0] -= 1 if self.drive[0] > 0 else -1
            if self.drive[1]:
                self.y -= math.copysign(1, self.drive[1])
                drive[1] -= 1 if self.drive[1] > 0 else -1

    def hit(self, target: Player):
        target.health -= self.effect['damage'] * (1 if not suddendeath else 100)
        if target.move.get('armor', 0):
            target.move['armor'] -= self.effect.get('pierce', 0)
        pierced = target.move.get('armor', 0) <= 0
        if pierced:
            if kb := self.effect['knock']:
                target.actionqueue.clear()
                target.move = {
                    'name': "knocked",
                    'move': True,
                    'effect': [kb[0] * -1, kb[1]],
                    'signature': True,
                }
            elif self.effect['interrupt']:
                target.actionqueue.clear()
        self.master.super += self.effect['supergain']

        if self.effect['dieonhit']:
            self.kill()

    @staticmethod
    def add(master: Player, spawn: dict):
        pos = spawn.pop('pos')
        mod = 1 if master.facing == 'R' else -1
        name = spawn.pop('name')
        facing = master.facing if not spawn.pop('reversefacing', False) else \
            [s for s in {'L', 'R'} if s != master.facing][0]
        hostile = spawn.pop('hostile', False)

        projectiles.add(Projectile(master.x + pos[0] * mod, master.y - pos[1], name, master if not hostile else None,
                                   facing, **spawn))

    @staticmethod
    def calchit(proj):
        xmod = math.copysign(1, proj.drive[0] * (1 if proj.facing == 'R' else -1))
        ymod = math.copysign(1, proj.drive[1])
        projtiles = [(proj.x + x * xmod, proj.y - y * ymod)
                     for x in range(abs(proj.drive[0]) + 1)
                     for y in range(abs(proj.drive[1]) + 1)]

        for p in [s for s in projectiles if s is not proj and s.master is not proj.master]:
            if (proj.x, proj.y) == (p.x, p.y):
                if proj.effect['damage'] < p.effect['damage']:
                    p.effect['damage'] -= proj.effect['damage']
                    proj.kill()
                    if p.effect['damage'] <= 0:
                        p.kill()
                else:
                    proj.effect['damage'] -= p.effect['damage']
                    p.kill()
                    if proj.effect['damage'] <= 0:
                        proj.kill()
                return

        for p in players:
            if (p.x, p.y) in projtiles and proj.master is not p:
                p.actionqueue.clear()
                if not p.move.get('invincible', False) and not p.move.get('projimmune', False):
                    proj.hit(p)
                if p.move.get('projreflect', False):
                    proj.master = p
                    proj.drive = [s * -1 for s in proj.drive]
                    proj.facing = [s for s in {'L', 'R'} if s != proj.facing][0]


class Particle(object):
    particles = []
    heldparticles = []

    def __init__(self):
        pass

    def add(self, pos=None, vel=None, mass=None, decay=None, gravity=None, color=None, delay=None):
        if pos is None:
            pos = [win.get_width(), win.get_height()]
        pos = list(pos)
        if vel is None:
            vel = [random.randint(0, 20) / 10 - 1, -2]
        if mass is None:
            mass = random.randint(4, 6)
        if decay is None:
            decay = 0.1
        if gravity is None:
            gravity = abs(vel[1] / 20)
        if color is None:
            color = (255, 255, 255)
        if delay is None:
            delay = 0
        if delay == 0:
            self.particles.append({'pos': pos,
                                   'vel': vel,
                                   'mass': mass,
                                   'decay': decay,
                                   'gravity': gravity,
                                   'color': color})
        else:
            self.heldparticles.append({'pos': pos,
                                       'vel': vel,
                                       'mass': mass,
                                       'decay': decay,
                                       'gravity': gravity,
                                       'color': color,
                                       'delay': delay})

    def run(self, shape="circle"):
        for particle in self.particles:
            particle['pos'][0] += particle['vel'][0]
            particle['pos'][1] += particle['vel'][1]
            particle['mass'] -= particle['decay']
            particle['vel'][1] += particle['gravity']

            if shape == "circle":
                pygame.draw.circle(win, particle['color'], [particle['pos'][0], particle['pos'][1]],
                                   particle['mass'])
            if shape == "square":
                pygame.draw.rect(win, particle['color'], [particle['pos'][0] - particle['mass'] / 2,
                                                          particle['pos'][1] - particle['mass'] / 2,
                                                          particle['mass'], particle['mass']])

            if particle['mass'] <= 0 or \
                    not 0 - particle['mass'] / 2 <= particle['pos'][0] <= scwidth + particle['mass'] / 2 or \
                    not 0 - particle['mass'] / 2 <= particle['pos'][1] <= scheight + particle['mass'] / 2:
                self.particles.remove(particle)

        for particle in self.heldparticles:
            if particle['delay'] <= 0:
                del particle['delay']
                self.particles.append(dict(particle))
        self.heldparticles[:] = [particle for particle in self.heldparticles if 'delay' in particle]
        for particle in self.heldparticles:
            particle['delay'] -= 1


def bound(low: int):
    def bound2(high: int):
        def bound3(value: int):
            return max(low, min(high, value))

        return bound3

    return bound2


def moveupdate():
    p1.last = (p1.x, p1.y)
    p2.last = (p2.x, p2.y)

    for p in players:
        px = p1 if p is p2 else p2
        if p.air:
            if not p.move.get('aircost', 0) and (p.x, p.y + 1) != (px.x, px.y):
                p.y += 1
        else:
            p.airmoves += 1
        if p.move['move'] and not p.move.get('projectile', False):
            if p.move['effect'][0] > 0:
                p.aggro += 1
            p.super += p.move.get('super', 0)
            p.special += p.move.get('special', 0)

    if p1.move['move'] and p2.move['move'] and \
            not (p1.move.get('projectile', False) or p2.move.get('projectile', False)):
        p1move = p1.move['effect'].copy()
        p2move = p2.move['effect'].copy()
        p1mod = 1 if p1.facing == 'R' else -1
        p2mod = 1 if p2.facing == 'R' else -1
        favored = math.copysign(bool(sum(p2move) - sum(p1move)), sum(p2move) - sum(p1move))  # -1 p1, 1 p2
        while p1move != [0, 0] or p2move != [0, 0]:
            movex = 0.5 if abs(p1.x - p2.x) <= 1 and p1move[0] > 0 and p2move[0] > 0 and p1move[1] == p2move[1] else 1
            movey = 0.5 if abs(p1.y - p2.y) <= 1 and p1move[1] * p2move[1] < 0 and p1move[0] == -p2move[0] else 1

            if not p1.move.get('teleport', False):
                if p1move[1]:
                    if 0 < p1.y < gridheight - 1 or \
                            (p1.y == 0 and p1move[1] < 0) or (p1.y == gridheight - 1 and p1move[1] > 0):
                        p1.y -= math.copysign(movey, p1move[1])
                    p1move[1] -= 1 if p1move[1] > 0 else -1
                if p1move[0]:
                    if 0 < p1.x < gridwidth - 1 or \
                            (p1.x == 0 and p1move[0] * p1mod > 0) or (p1.x == gridwidth - 1 and p1move[0] * p1mod < 0):
                        p1.x += math.copysign(movex, p1move[0] * p1mod)
                    p1move[0] -= movex if p1move[0] > 0 else -movex
            else:
                if (p2.x, p2.y) != (wbind(p1.x + p1move[0] * p1mod), hbind(p1.y - p1move[1])):
                    p1.x += p1move[0] * p1mod
                    p1.y -= p1move[1]
                    p1move = [0, 0]
                if p2move == [0, 0]:
                    p1move = p2move

            if not p2.move.get('teleport', False):
                if p2move[1]:
                    if 0 < p2.y < gridheight - 1 or \
                            (p2.y == 0 and p2move[1] < 0) or (p2.y == gridheight - 1 and p2move[1] > 0):
                        p2.y -= math.copysign(movey, p2move[1])
                    p2move[1] -= 1 if p2move[1] > 0 else -1
                if p2move[0]:
                    if 0 < p2.x < gridwidth - 1 or \
                            (p2.x == 0 and p2move[0] * p2mod > 0) or (p2.x == gridwidth - 1 and p2move[0] * p2mod < 0):
                        p2.x += math.copysign(movex, p2move[0] * p2mod)
                    p2move[0] -= movex if p2move[0] > 0 else -movex
            else:
                if (p1.x, p1.y) != (wbind(p2.x + p2move[0] * p2mod), hbind(p2.y - p2move[1])):
                    p2.x += p2move[0] * p2mod
                    p2.y -= p2move[1]
                    p2move = [0, 0]
                if p1move == [0, 0]:
                    p2move = p1move

            for proj in projectiles:
                Projectile.calchit(proj)

            if p1.move.get('teleport', False) and p2.move.get('teleport', False):
                break

            if (p1.x, p1.y) == (p2.x, p2.y):
                if p1.move.get('teleport', False) or p2.move.get('teleport', False):
                    continue
                if favored == -1:
                    if p1.x == 1 - movex and p1.move['effect'][0] * p1mod < 0:
                        p1.x += movex
                        break
                    if p1.x == gridwidth - 2 + movex and p1.move['effect'][0] * p1mod > 0:
                        p1.x -= movex
                        break
                    if p1.y == 1 - movey and p1.move['effect'][1] > 0:
                        p1.y += movey
                        break
                    if p1.y == gridheight - 2 + movey and p1.move['effect'][1] < 0:
                        p1.y -= movey
                        break

                    if p1.move['effect'][0]:
                        p2.x += math.copysign(movex, p1.move['effect'][0] * p1mod)
                    if p1.move['effect'][1]:
                        p2.y -= math.copysign(movey, p1.move['effect'][1])
                    p2.health -= p1.move.get('dmg', 1)
                if favored == 1:
                    if p2.x == 1 - movex and p2.move['effect'][0] * p2mod < 0:
                        p2.x += movex
                        break
                    if p2.x == gridwidth - 2 + movex and p2.move['effect'][0] * p2mod > 0:
                        p2.x -= movex
                        break
                    if p2.y == 1 - movey and p2.move['effect'][1] > 0:
                        p2.y += movey
                        break
                    if p2.y == gridheight - 2 + movey and p2.move['effect'][1] < 0:
                        p2.y -= movey
                        break

                    if p2.move['effect'][0]:
                        p1.x += math.copysign(movex, p2.move['effect'][0] * p2mod)
                    if p2.move['effect'][1]:
                        p1.y -= math.copysign(movey, p2.move['effect'][1])
                    p1.health -= p2.move.get('dmg', 1)
                if favored == 0:
                    if p1.move['effect'][0]:
                        p1.x -= math.copysign(movex, p1.move['effect'][0] * p1mod)
                    if p1.move['effect'][1]:
                        p1.y += math.copysign(movey, p1.move['effect'][1])
                    if p2.move['effect'][0]:
                        p2.x -= math.copysign(movex, p2.move['effect'][0] * p2mod)
                    if p2.move['effect'][1]:
                        p2.y += math.copysign(movey, p2.move['effect'][1])
                break

    elif (p1move := p1.move['move'] and not p1.move.get('projectile', False)) or \
            p2.move['move'] and not p2.move.get('projectile', False):
        mover, attacker = (p1, p2) if p1move else (p2, p1)
        move = mover.move['effect'].copy()
        movemod = 1 if mover.facing == 'R' else -1
        if not mover.move.get('teleport', False):
            while move != [0, 0]:
                if move[0]:
                    mover.x += math.copysign(1, move[0] * movemod)
                    move[0] -= 1 if move[0] > 0 else -1
                if move[1]:
                    mover.y -= math.copysign(1, move[1])
                    move[1] -= 1 if move[1] > 0 else -1

                if (mover.x, mover.y) == (attacker.x, attacker.y):
                    if mover.move['effect'][0]:
                        mover.x -= math.copysign(1, mover.move['effect'][0] * movemod)
                    if mover.move['effect'][1]:
                        mover.y += math.copysign(1, mover.move['effect'][1])
                    move = [0, 0]

                for proj in projectiles:
                    Projectile.calchit(proj)
        else:
            if (attacker.x, attacker.y) != (wbind(mover.x + move[0] * movemod), hbind(mover.y - move[0])):
                mover.x += move[0] * movemod
                mover.y -= move[1]

    for mover in players:
        if mover.x < 0:
            mover.x = 0
        if mover.x > gridwidth - 1:
            mover.x = gridwidth - 1
        if mover.y < 0:
            mover.y = 0
        if mover.y > gridheight - 1:
            mover.y = gridheight - 1

        mover.air = False if mover.y == gridheight - 1 else True

        if mover.move.get('supercost', 0) >= 9:
            vec = pygame.math.Vector2(0, -1)
            for _ in range(8):
                vec.rotate_ip(360 / 8)
                particlesys.add([mover.x * size + 32, mover.y * size + 32], [vec.x, vec.y], 6, 0.1, 0, mover.team)

        if mover.move.get('projectile', False):
            spawnlist: list[dict] = copy.deepcopy(mover.move['effect'])
            for spawn in spawnlist:
                Projectile.add(mover, spawn)

    projectiles.update()


def atkupdate():
    p1.hit = p2.hit = False
    for attacker in [s for s in players if not s.move['move']]:
        defender = p1 if attacker is not p1 else p2
        atkmod = 1 if attacker.facing == 'R' else -1
        dmgtiles = [(attacker.x + (s[0] * atkmod), attacker.y - s[1]) for s in attacker.move['effect']]
        if (defender.x, defender.y) in dmgtiles:
            defender.hit = True
        if attacker.move.get('projhit', False):
            for proj in projectiles:
                if (proj.x, proj.y) in dmgtiles:
                    proj.kill()

    if p1.hit and p2.hit:
        if p1.move == p2.move:
            p1.hit = p2.hit = False
        elif prioritydiff := p2.move.get('priority', 0) - p1.move.get('priority', 0):
            if prioritydiff < 0:
                p1.hit = False
            else:
                p2.hit = False
        elif tilediff := len(p1.move['effect']) - len(p2.move['effect']):
            if tilediff < 0:
                p1.hit = False
            else:
                p2.hit = False
        elif p1.air != p2.air:
            if p2.air:
                p1.hit = False
            else:
                p2.hit = False
        else:
            p1.hit = p2.hit = False

        if p1.move.get('armor', 0) > 0:
            p2.hit = True
        if p2.move.get('armor', 0) > 0:
            p1.hit = True

    for p in players:
        px = [s for s in players if s is not p][0]
        if p.hit:
            if p.move.get('armor', 0):
                p.move['armor'] -= px.move.get('pierce', 0)
            pierced = (p.move.get('armor', 0) <= 0) if not px.move.get('grab', False) else True
            if pierced:
                p.actionqueue.clear()

            if p.move.get('invincible', False) if not px.move.get('grab', False) else False:
                p.super += 1
                if not p.move.get('hitwhiff', True):
                    if px.move.get('hitcancel', True):
                        px.actionqueue.clear()
                    else:
                        for i in range(-1, -len(px.actionqueue) - 1, -1):
                            if px.actionqueue[i]['name'] == 'whiff':
                                px.actionqueue[:] = px.actionqueue[:i]
                                break
                return

            if type(px) is Ruffian:
                px.special += 1
            if type(px) is Tussler and not px.move.get('armor'):
                px.special += 1

            p.health -= px.move.get('dmg', 2) * (1 if not suddendeath else 100)
            px.super += px.move.get('super', 1)
            px.special += px.move.get('special', 0)

            p.aggro = px.aggro = 0

            if px.move.get('recovery', 0) or not px.move.get('hitcancel', True):
                for i in range(-1, -len(px.actionqueue) - 1, -1):
                    if px.actionqueue[i]['name'] == 'whiff':
                        px.actionqueue[:] = px.actionqueue[:i]
                        break
            else:
                px.actionqueue.clear()

            knockback: list[list] = None
            if (kb := px.move.get('knock', False)) and pierced:
                knockback = kb.copy()
                if px.__class__ == Wrestler:
                    if isinstance(knockback[0], list):
                        if knockback[0][0]:
                            knockback[0][0] += int(px.special) * math.copysign(1, knockback[0][0])
                            px.special = 0
                    elif knockback[0]:
                        knockback[0] += int(px.special) * math.copysign(1, knockback[0])
                        px.special = 0
            elif (kb := px.move.get('throw', False)) and pierced:
                knockback = kb.copy()
            if knockback and len(knockback) == 1:
                mod = 1 if px.facing == 'R' else -1
                knockback = [math.copysign(bool(p.x - px.x), p.x - px.x) * knockback[0] * mod,
                             math.copysign(bool(px.y - p.y), px.y - p.y) * knockback[0] + (1 if p.air else 0)]

            if knockback and px.__class__ == Wrestler:
                if isinstance(knockback[0], list):
                    if knockback[0][0]:
                        knockback[0][0] += int(px.special) * math.copysign(1, knockback[0][0])
                        px.special = 0
                elif knockback[0]:
                    knockback[0] += int(px.special) * math.copysign(1, knockback[0])
                    px.special = 0

            if knockback:
                if not (0 < p.x < gridwidth - 1):
                    knockback[1] += 2 if p.air else 1

                if isinstance(knockback[0], list):
                    for kb in knockback:
                        p.actionqueue.append({
                            'name': "knocked",
                            'move': True,
                            'effect': [kb[0] * -1, kb[1]],
                            'signature': True,
                            'dmg': 0,
                        })
                else:
                    p.actionqueue.append({
                        'name': "knocked",
                        'move': True,
                        'effect': [knockback[0] * -1, knockback[1]],
                        'signature': True,
                        'dmg': 0,
                    })

            if recovering := px.move.get('targetrecovery', 0):
                for _ in range(recovering):
                    p.actionqueue.append({
                        'name': "getup",
                        'move': True,
                        'effect': [0, 0],
                        'signature': True,
                        'invincible': True,
                    })
            if px.move.get('throw', False):
                px.actionqueue.insert(0, {
                    'name': "throw",
                    'move': True,
                    'effect': [0, 0],
                    'signature': True,
                    'particle': [[32, 0], [[2, 5], [-2, 2]], None, 0.25, 0, None, 8],
                })
        elif not px.move['move']:
            if px.move.get('whiffcancel', False):
                for i in range(len(px.actionqueue)):
                    if px.actionqueue[i]['name'] in stuns:
                        px.actionqueue[:] = px.actionqueue[i:]
                        break


def gameupdate():
    global turns
    p1.update(True)
    p2.update(True)
    turns += 1

    moveupdate()
    atkupdate()

    if p1.x != p2.x:
        if not p1.actionqueue or p1.actionqueue[0]['name'] in stuns:
            if p1.x < p2.x:
                p1.facing = 'R'
            elif p1.x > p2.x:
                p1.facing = 'L'
        if not p2.actionqueue or p2.actionqueue[0]['name'] in stuns:
            if p1.x < p2.x:
                p2.facing = 'L'
            elif p1.x > p2.x:
                p2.facing = 'R'

    for proj in projectiles:
        if not (0 <= proj.x < gridwidth and 0 <= proj.y < gridheight):
            proj.kill()

    if turns % 5 == 0:
        aggressor = p2.aggro - p1.aggro
        p1.aggro = p2.aggro = 0
        if aggressor < 0:
            p1.super += 1
        elif aggressor > 0:
            p2.super += 1

    for p in players:
        p.health = pbind(p.health)
        p.super = pbind(p.super)
        p.special = bind(p.specmax)(p.special)
        p.airmoves = bind(p.airmax)(p.airmoves)

    bottom = 'p1'
    if layerdiff := p2.move.get('layer', 0) - p1.move.get('layer', 0):
        bottom = 'p1' if layerdiff < 0 else 'p2'
    elif p1.hit != p2.hit:
        bottom = 'p1' if p1.hit else 'p2'

    redrawgamewindow(bottom, True)


def teamcolor(surf: pygame.Surface, team: tuple[int, int, int], replace=colors.BLACK, total=False, ip=True):
    if not ip:
        surf = surf.copy()

    r, g, b = team
    for x in range(surf.get_width()):
        for y in range(surf.get_height()):
            *precol, a = surf.get_at((x, y))
            if total or (a != 0 and tuple(precol) == replace):
                surf.set_at((x, y), (r, g, b, a))

    return surf


def redrawgamewindow(bottom='p1', full=False):
    global colselection, screencolor, lowest, rotate
    global predictions

    if full:
        colselection = random.choice([s for s in screenoptions if s != colselection])
        rotate = random.randrange(-1, 1)
    colscalar = (turntime * framerate - counter) / (turntime * framerate)
    screencolor = [min(s * (colscalar + 0.4), s) for s in colselection]
    grid.set_alpha(max(int(colscalar * (255 + 30) - 30), 0))
    win.fill((*colors.BLACK, 0))

    if full:
        p1.sprite, p1.offset = teamcolor(
            pygame.image.load(f"sprites/{type(p1).__name__}/{p1.move['name']}.png").convert_alpha(), p1.team), \
            [p1.move.get('offset', [0, 0])[0], p1.move.get('offset', [0, 0])[1]]
        if p1.facing == 'L':
            p1.sprite = pygame.transform.flip(p1.sprite, True, False)
            p1.offset[0] = p1.sprite.get_width() / size - p1.offset[0] - 1
        if p1.reverse:
            p1.sprite = pygame.transform.flip(p1.sprite, True, False)
        p1.shadow = teamcolor(p1.sprite, colors.BLACK, total=True, ip=False)
        p2.sprite, p2.offset = teamcolor(
            pygame.image.load(f"sprites/{type(p2).__name__}/{p2.move['name']}.png").convert_alpha(), p2.team), \
            [p2.move.get('offset', [0, 0])[0], p2.move.get('offset', [0, 0])[1]]
        if p2.facing == 'L':
            p2.sprite = pygame.transform.flip(p2.sprite, True, False)
            p2.offset[0] = p2.sprite.get_width() / size - p2.offset[0] - 1
        if p2.reverse:
            p2.sprite = pygame.transform.flip(p2.sprite, True, False)
        p2.shadow = teamcolor(p2.sprite, colors.BLACK, total=True, ip=False)

        lowest = bottom

        predictions.clear()
        for p in players:
            if p.actionqueue:
                mod = 1 if p.facing == 'R' else -1
                if p.actionqueue[0].get('projectile', False):
                    for pos in [s['pos'] for s in p.actionqueue[0]['effect']]:
                        predictions.append([(*p.team, size), ((p.x + pos[0] * mod) * size,
                                                              (p.y - pos[1] + p.air) * size, size, size)])
                    continue
                if p.actionqueue[0]['move']:
                    coord = p.actionqueue[0]['effect']
                    predictions.append([(*[(s + p.team[i]) * 2 / 5 for i, s in enumerate(colors.WHITE)], size), (
                        wbind(p.x + coord[0] * mod) * size, hbind(p.y - coord[1] + p.air) * size, size, size)])
                else:
                    for tile in p.actionqueue[0]['effect']:
                        predictions.append([(*p.team, size), ((p.x + tile[0] * mod) * size,
                                                              (p.y - tile[1]) * size, size, size)])

            if particle := p.move.get('particle', False):
                for _ in range(particle[6]):
                    tempparticle: list[list] = copy.deepcopy(particle)
                    for i, val in enumerate(tempparticle):
                        if val is None:
                            continue
                        if i in (0, 1, 5) and isinstance(val, list):
                            for j, subval in enumerate(val):
                                if isinstance(subval, list):
                                    if i != 1:
                                        tempparticle[i][j] = random.randrange(subval[0], subval[1])
                                    else:
                                        tempparticle[i][j] = float(random.randrange(
                                            subval[0] * 100, subval[1] * 100) / 100)
                        else:
                            if isinstance(val, list):
                                tempparticle[i] = random.randrange(val[0], val[1])

                        if i == 0 and isinstance(val, list):
                            mod = 1 if p.facing == 'R' else -1
                            tempparticle[i][0] = p.x * size + 32 + tempparticle[i][0] * mod
                            tempparticle[i][1] += p.y * size + 32
                    particlesys.add(*tempparticle[:-1])
        for p in projectiles:
            coord = p.drive
            mod = 1 if p.facing == 'R' else -1
            predictions.append([(*[(s + p.master.team[i]) * 2 / 5 for i, s in enumerate(colors.WHITE)], size), (
                (p.x + coord[0] * mod) * size, (p.y - coord[1]) * size, size, size)])

    for pred in predictions:
        pygame.draw.rect(win, *pred, border_radius=4)

    particlesys.run()

    lerp = min(1, counter / (turntime * framerate / 4))

    p1pos = [(p1.last[0] * (1 - lerp) + p1.x * lerp) * size - p1.offset[0] * size,
             (p1.last[1] * (1 - lerp) + p1.y * lerp) * size - p1.offset[1] * size]
    p2pos = [(p2.last[0] * (1 - lerp) + p2.x * lerp) * size - p2.offset[0] * size,
             (p2.last[1] * (1 - lerp) + p2.y * lerp) * size - p2.offset[1] * size]
    projpos = {s.img: [(s.last[0] * (1 - lerp) + s.x * lerp) * size,
                       (s.last[1] * (1 - lerp) + s.y * lerp) * size, s.facing] for s in projectiles}

    if lowest == 'p1':
        win.blit(p1.shadow, [s + 2 for s in p1pos])
        win.blit(p1.sprite, p1pos)
        win.blit(p2.shadow, [s + 2 for s in p2pos])
        win.blit(p2.sprite, p2pos)
    else:
        win.blit(p2.shadow, [s + 2 for s in p2pos])
        win.blit(p2.sprite, p2pos)
        win.blit(p1.shadow, [s + 2 for s in p1pos])
        win.blit(p1.sprite, p1pos)
    for img in projpos.keys():
        win.blit(pygame.transform.flip(img, projpos[img][-1] != 'R', False), projpos[img][:-1])

    pygame.draw.polygon(win, colors.RED, ([20, 30], [30, 20],
                                          [30 + p1.health * 16, 20], [20 + p1.health * 16, 30]))
    pygame.draw.polygon(win, colors.BLUE, ([10, 40], [20, 30],
                                           [20 + p1.super * 16, 30], [10 + p1.super * 16, 40]))
    win.blit(bar, (20, 20))
    win.blit(bar, (10, 30))
    pygame.draw.polygon(win, colors.RED, ([scwidth - 20, 30], [scwidth - 30, 20],
                                          [scwidth - 30 - p2.health * 16, 20], [scwidth - 20 - p2.health * 16, 30]))
    pygame.draw.polygon(win, colors.BLUE, ([scwidth - 10, 40], [scwidth - 20, 30],
                                           [scwidth - 20 - p2.super * 16, 30], [scwidth - 10 - p2.super * 16, 40]))
    win.blit(pygame.transform.flip(bar, True, False), (scwidth - 30 - 10 * 16, 20))
    win.blit(pygame.transform.flip(bar, True, False), (scwidth - 20 - 10 * 16, 30))

    if type(p1) == Ruffian:
        for i in range(p1.special):
            pygame.draw.circle(win, colors.DPURPLE, (15 + i * 16 + 10 + 1, 15 + i * 16 + 50), 10)
    elif type(p1) == Wrestler:
        pygame.draw.rect(win, colors.DPURPLE, (30, 50 + size - 16 * p1.special, 22, 16 * p1.special))
    elif type(p1) == Roller:
        for i in range(p1.special):
            pygame.draw.rect(win, colors.DPURPLE, (10 + 32 * bool(i - 3 >= 0), 50 + 22 * (i % 3), 32, 22))
    elif type(p1) == GunGuy:
        vec = pygame.math.Vector2(0, -18)
        for _ in range(p1.special):
            pygame.draw.circle(win, colors.DPURPLE, (42, 82) + vec, 8)
            vec.rotate_ip(-45)
    elif type(p1) == Tussler:
        if p1.special:
            pygame.draw.rect(win, colors.DPURPLE, (10, 50, size, size))
    win.blit(p1.specui, (10, 50))

    if type(p2) == Ruffian:
        for i in range(p2.special):
            pygame.draw.circle(win, colors.DPURPLE, (scwidth - 15 - i * 16 - 10 - 1, 15 + i * 16 + 50), 10)
    elif type(p2) == Wrestler:
        pygame.draw.rect(win, colors.DPURPLE, (scwidth - 53, 50 + size - 16 * p2.special, 22, 16 * p2.special))
    elif type(p2) == Roller:
        for i in range(p2.special):
            pygame.draw.rect(win, colors.DPURPLE, (scwidth - 10 - 32 * (bool(i - 3 >= 0) + 1),
                                                   50 + 22 * (i % 3), 32, 22))
    elif type(p2) == GunGuy:
        vec = pygame.math.Vector2(0, -18)
        for _ in range(p2.special):
            pygame.draw.circle(win, colors.DPURPLE, (scwidth - 42, 82) + vec, 8)
            vec.rotate_ip(45)
    elif type(p2) == Tussler:
        if p2.special:
            pygame.draw.rect(win, colors.DPURPLE, (scwidth - 10 - size, 50, size, size))
    win.blit(pygame.transform.flip(p2.specui, True, False), (scwidth - 10 - p2.specui.get_width(), 50))

    for i in range(p1.airmax):
        if i < p1.airmoves:
            pygame.draw.circle(win, colors.GREEN, (74 + 16, 50 + 16 + i * 34), 16)
        pygame.draw.circle(win, colors.BLACK, (74 + 16, 50 + 16 + i * 34), 16, width=1)
    for i in range(p2.airmax):
        if i < p2.airmoves:
            pygame.draw.circle(win, colors.GREEN, (scwidth - 74 - 16, 50 + 16 + i * 34), 16)
        pygame.draw.circle(win, colors.BLACK, (scwidth - 74 - 16, 50 + 16 + i * 34), 16, width=1)

    if counter // 25 % 2 == 0:
        if p1.health <= 0 and p2.health <= 0:
            win.blit(drawfont, drawfont.get_rect(center=(win.get_width() / 2, 50)))
        elif p1.health <= 0:
            win.blit(p2winfont, p2winfont.get_rect(center=(win.get_width() / 2, 50)))
        elif p2.health <= 0:
            win.blit(p1winfont, p1winfont.get_rect(center=(win.get_width() / 2, 50)))
        elif suddendeath:
            win.blit(sdfont, sdfont.get_rect(center=(win.get_width() / 2, 50)))

    screen.fill(screencolor)
    screen.blit(grid, (0, 0))
    screen.blit(win, (0, 0))
    # newgrid, newwin = pygame.transform.rotate(grid, rotate), pygame.transform.rotate(win, rotate)
    # screen.blit(newgrid, (scwidth // 2 - newgrid.get_width() // 2, scheight // 2 - newgrid.get_height() // 2))
    # screen.blit(newwin, (scwidth // 2 - newwin.get_width() // 2, scheight // 2 - newwin.get_height() // 2))
    pygame.display.flip()


win.blit(font.render("Press space to start", False, colors.WHITE), (5, 5))
screen.blit(win, (0, 0))
pygame.display.flip()
notstarted = 4
starttext = ["None", "Select p2", "Select p1", "Blacklist for p2", "Blacklist for p1",
             "p1 win", "p2 win", "draw", "BLACKLISTED"]
starttext = [font.render(s, False, colors.WHITE) for s in starttext]
chars = [Ruffian, Wrestler, Roller, GunGuy, Tussler]
charpics = [[(teamcolor(pygame.image.load(f"sprites/{s.__name__}/{move['name']}.png"), (255, 255, 255))
              if os.path.isfile(f"sprites/{s.__name__}/{move['name']}.png") else
              teamcolor(pygame.image.load(f"sprites/{s.__name__}/{move['name'] + '1'}.png"), (255, 255, 255)))
             for move in s.moves if isinstance(move['signature'], list)] for s in chars]
chartext = [font.render(s.__name__, False, colors.WHITE) for s in chars]
notableattrs = ['name', 'move', 'air', 'dmg', 'grab', 'knock', 'invincible', 'recovery', 'targetrecovery',
                'aircost', 'free', 'hitcancel', 'whiffcancel', 'armor', 'pierce', 'super', 'special', 'supercost',
                'specialcost', 'priority']
charmoves = [[[font.render(f'{attr}: {move[attr]}', False, colors.WHITE) for
               attr in notableattrs if attr in move] for move in s.moves if isinstance(move['signature'], list)]
             for s in chars]
charoffsets = [[move.get('offset', [0, 0]) for move in s.moves if isinstance(move['signature'], list)] for s in chars]
sigdirs = {
    0: arrow,
    1: pygame.transform.rotate(arrow, 90),
    2: pygame.transform.rotate(arrow, 180),
    3: pygame.transform.rotate(arrow, 270),
    4: pygame.image.load("sprites/ui/attack.png"),
    5: pygame.image.load("sprites/ui/super.png"),
}
charsigs = []
for s in chars:
    charsiglist = []
    for move in s.moves:
        if isinstance(move['signature'], list):
            sig = [sigdirs[index] for index, value in enumerate(move['signature']) if value]
            sigsurf = pygame.Surface((len(sig) * 36, 32))
            for inp in range(len(sig)):
                sigsurf.blit(sig[inp], (inp * 36, 0))
            charsiglist.append(sigsurf)
    charsigs.append(charsiglist)

blacklist = [None, None]
cnt = 0
cmdcnt = 0

bind = bound(0)
pbind = bind(10)
wbind = bind(gridwidth - 1)
hbind = bind(gridheight - 1)

particlesys = Particle()
p1 = Ruffian(3, 5, colors.RED, ['w', 'a', 's', 'd', 'space', 'left shift'])
p2 = Ruffian(7, 5, colors.BLUE, ['up', 'left', 'down', 'right', '/', 'right shift'], 'L')
players = (p1, p2)
projectiles = pygame.sprite.Group()
run = True
while run:
    clock.tick(framerate)
    for event in pygame.event.get():
        if event.type == pygame.QUIT:
            run = False
        if event.type == pygame.KEYDOWN:
            for player in players:
                player.update(key=pygame.key.name(event.key))

        if notstarted:
            if event.type == pygame.KEYDOWN:
                if notstarted in (4, 1):
                    if pygame.key.name(event.key) == 'up':
                        cnt -= 1
                        cmdcnt = 0
                    elif pygame.key.name(event.key) == 'down':
                        cnt += 1
                        cmdcnt = 0
                    if pygame.key.name(event.key) == 'right':
                        cmdcnt += 1
                    elif pygame.key.name(event.key) == 'left':
                        cmdcnt -= 1
                else:
                    if pygame.key.name(event.key) == 'w':
                        cnt -= 1
                        cmdcnt = 0
                    elif pygame.key.name(event.key) == 's':
                        cnt += 1
                        cmdcnt = 0
                    if pygame.key.name(event.key) == 'd':
                        cmdcnt += 1
                    elif pygame.key.name(event.key) == 'a':
                        cmdcnt -= 1
                if cnt < 0:
                    cnt += len(chars)
                elif cnt >= len(chars):
                    cnt -= len(chars)
                if cmdcnt < 0:
                    cmdcnt += len(charmoves[cnt])
                elif cmdcnt >= len(charmoves[cnt]):
                    cmdcnt -= len(charmoves[cnt])

                if pygame.key.name(event.key) == 'return':
                    if notstarted == 5:
                        p1.health, p2.health = 10, 10
                        p1.super, p2.super = 0, 0
                        p1.special, p2.special = p1.specstart, p2.specstart

                    if notstarted == 4:
                        blacklist[0] = chars[cnt]
                    elif notstarted == 3:
                        blacklist[1] = chars[cnt]
                    elif notstarted == 2:
                        if chars[cnt] == blacklist[0]:
                            continue
                        else:
                            p1 = chars[cnt](3, 5, colors.RED, ['w', 'a', 's', 'd', 'space', 'left shift'])
                    elif notstarted == 1:
                        if chars[cnt] == blacklist[1]:
                            continue
                        else:
                            p2 = chars[cnt](7, 5, colors.BLUE, ['up', 'left', 'down', 'right', '/', 'right shift'], 'L')
                    notstarted -= 1
                    cnt = 0
                    cmdcnt = 0
                    if not notstarted:
                        p1.health, p2.health = 10, 10
                        p1.super, p2.super = 0, 0
                        p1.special, p2.special = p1.specstart, p2.specstart
                        players = (p1, p2)
                        redrawgamewindow(full=True)
    if notstarted:
        win.fill((0, 0, 0))
        if notstarted == 5:
            if p1.health <= 0 and p2.health <= 0:
                win.blit(starttext[notstarted + 2], (5, 5))
            else:
                win.blit((starttext[notstarted] if p1.health else starttext[notstarted + 1]), (5, 5))
        else:
            win.blit(starttext[notstarted], (5, 5))
            win.blit(charpics[cnt][0], charpics[cnt][0].get_rect(center=(scwidth / 2, scheight / 3)))
            win.blit(charpics[cnt][cmdcnt], (scwidth * 1 / 6 - charoffsets[cnt][cmdcnt][0] * size,
                                             scheight * 2 / 3 - charoffsets[cnt][cmdcnt][1] * size))
            win.blit(charsigs[cnt][cmdcnt], charsigs[cnt][cmdcnt].get_rect(center=(scwidth * 1 / 2,
                                                                                   scheight * 3 / 4)))
            for offset, attr in enumerate(charmoves[cnt][cmdcnt]):
                win.blit(attr, (scwidth * 2 / 3, scheight * 2 / 3 + offset * 14))
            if (notstarted == 2 and chars[cnt] == blacklist[0]) or (notstarted == 1 and chars[cnt] == blacklist[1]):
                win.blit(starttext[-1], starttext[-1].get_rect(center=(scwidth / 2, scheight / 3 + size)))
            else:
                win.blit(chartext[cnt], chartext[cnt].get_rect(center=(scwidth / 2, scheight / 3 + size)))

        screen.fill((0, 0, 0))
        screen.blit(win, (0, 0))
        pygame.display.flip()
        continue

    counter += 1

    if counter >= turntime * framerate:
        counter = 0
        if not suddendeath:
            if turntime > turnmin:
                turntime *= turnmod
            else:
                turntime = turnmin
                suddendeath = True
        gameupdate()
    else:
        redrawgamewindow()

    if (p1.health <= 0 or p2.health <= 0) and \
            p1.move['name'] in ('idle', 'fall') and p2.move['name'] in ('idle', 'fall'):
        notstarted = 5
        counter = 0
        turntime = 1
        turns = 0
        suddendeath = False
        projectiles.empty()
pygame.quit()
