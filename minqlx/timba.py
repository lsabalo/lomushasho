import datetime
import copy
import itertools
import json
import minqlx
import os
import pprint
import re

HEADER_COLOR_STRING = '^2'
JSON_FILE_NAME = 'timba_credits.json'
ROOT_PATH = os.path.dirname(os.path.realpath(__file__))
JSON_FILE_PATH = os.path.join(ROOT_PATH, JSON_FILE_NAME)
STARTING_CREDITS = 5000


class timba(minqlx.Plugin):

  def __init__(self):
    self.betting_open = False
    # dict: {player_id: {'team': ('red'|'blue'), 'amount': amount}, ...}
    self.current_bets = {}
    # dict: {player_id: credits, ...}
    self.credits = {}
    # dict: {player_id: clean_name, ...}
    self.names_by_id = {}
    self.load_credits()

    self.add_command('timba', self.cmd_timba, 3)
    self.add_hook('game_countdown', self.handle_game_countdown)
    self.add_hook('game_start', self.handle_game_start)
    self.add_hook('game_end', self.handle_game_end)

  def print_log(self, msg):
    self.msg('%sTimba:^7 %s' % (HEADER_COLOR_STRING, msg))

  def print_error(self, msg):
    self.msg('%sTimba:^1 %s' % (HEADER_COLOR_STRING, msg))

  def print_header(self, message):
    self.msg('%s%s' % (HEADER_COLOR_STRING, '=' * 80))
    self.msg('%sTimba v0.00001:^7 %s' % (HEADER_COLOR_STRING, message))
    self.msg('%s%s' % (HEADER_COLOR_STRING, '-' * 80))

  def get_clean_name(self, name):
    return re.sub(r'([\W]*\]v\[[\W]*|^\W+|\W+$)', '', name).lower()

  def get_current_bets(self):
    return self.current_bets

  def get_credits(self):
    return self.credits

  def load_credits(self):
    try:
      credits = json.loads(open(JSON_FILE_PATH).read())
      for key, value in credits.items():
        self.credits[int(key)] = value

      self.print_log(
          'Loaded credits for %s players.' % len(self.credits.keys()))
    except Exception as e:
      self.print_error('Could not load credits (%s)' % e)

  def save_credits(self):
    open(JSON_FILE_PATH, 'w+').write(
        json.dumps(self.credits, sort_keys=True, indent=2))
    self.print_log('Credits saved.')

  def handle_game_countdown(self):
    self.print_log('Betting is now open - place your bets!')
    self.betting_open = True

  def print_bets(self, winners, losers):
    self.print_header('Bets for this game:')
    if self.current_bets:
      for player_id in winners + losers:
        # for player_id, bet in self.current_bets.items():
        bet = self.current_bets[player_id]
        amount = bet['amount'] if player_id in winners else -bet['amount']
        clean_name = self.get_clean_name(self.names_by_id[player_id])
        amount_color = '^2' if player_id in winners else '^1'
        msg_string = '^5%30s^7 : %s%5d^7 on %-4s' % (clean_name, amount_color,
                                                     amount, bet['team'])
        msg_string = msg_string.replace('red', '^1red^7')
        msg_string = msg_string.replace('blue', '^4blue^7')
        self.msg(msg_string)

  # Workaround for invalid (empty?) teams() data on start, see:
  # https://github.com/MinoMino/minqlx-plugins/blob/96ef6f4ff630128a6c404ef3f3ca20a60c9bca6c/ban.py#L940
  @minqlx.delay(1)
  def handle_game_start(self, data):
    self.print_log('Betting is now closed.')
    self.betting_open = False

  def handle_game_end(self, data):
    self.betting_open = False

    if data['ABORTED']:
      self.current_bets = {}
      self.print_log('No one wins: game was aborted.')
      return

    # dict: {player_id: {'team': ('red'|'blue'), 'amount': amount}, ...}
    winner = 'red' if self.game.red_score > self.game.blue_score else 'blue'

    for player_id, bet in self.current_bets.items():
      delta = bet['amount'] if bet['team'] == winner else -bet['amount']
      self.credits[player_id] = (self.credits.setdefault(
          player_id, STARTING_CREDITS)) + delta

    winner_ids = [
        player_id for player_id in self.current_bets.keys()
        if self.current_bets[player_id]['team'] == winner
    ]
    loser_ids = list(self.current_bets.keys() - winner_ids)
    self.print_bets(winner_ids, loser_ids)
    self.save_credits()
    self.current_bets = {}

  def cmd_timba(self, player, msg, channel):
    player_id = player.steam_id
    self.names_by_id[player_id] = self.get_clean_name(player.clean_name)
    current_credits = self.credits.setdefault(player_id, STARTING_CREDITS)

    if not self.betting_open:
      player.tell(
          'You can only bet during warmup. You have ^3%d^7 credits to bet.' %
          current_credits)
      return

    valid_teams = ['red', 'blue']

    if len(msg) == 1:
      player.tell('You have ^3%d^1 credits to bet.' % current_credits)
      return

    if len(msg) < 3 or msg[1] not in valid_teams or not msg[2].isdigit():
      player.tell('To bet: ^5!timba (red|blue) <amount>^7. ' +
                  'You have ^3%d^7 credits to bet.' % current_credits)
      return

    team = msg[1]
    amount = int(msg[2])

    if current_credits < amount:
      player.tell('^1You only have ^3%d^7 credits to bet.' % current_credits)
      return

    if amount == 0 and player_id in self.current_bets:
      self.current_bets.pop(player_id, None)
      player.tell('You removed your bet.')
      return

    # dict: {player_id: {'team': ('red'|'blue'), 'amount': amount}, ...}
    self.current_bets[player_id] = {
        'team': team,
        'amount': amount,
    }

    team = '^1red^7' if team == 'red' else '^4blue^7'
    player.tell(
        'You bet ^3%d^7 credits on team %s. You have ^3%d^7 credits left.' %
        (amount, team, current_credits - amount))
