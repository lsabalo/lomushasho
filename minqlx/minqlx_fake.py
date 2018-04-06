import re


ANSI_COLOR_MAP = {
    '^0': '\u001b[30m',  # black
    '^1': '\u001b[31m',  # red
    '^2': '\u001b[32m',  # green
    '^3': '\u001b[33m',  # yellow
    '^4': '\u001b[34m',  # blue
    '^5': '\u001b[36m',  # cyan
    '^6': '\u001b[35m',  # magenta
    '^7': '\u001b[37m',  # white
}


class PlayerStats(object):
  def __init__(self, kills, deaths):
    self.kills = kills
    self.deaths = deaths


class Player(object):
  def __init__(self, steam_id, name, team=None, kills=0, deaths=0):
    self.steam_id = steam_id
    self.name = name
    self.clean_name = name
    self.team = team
    self.stats = PlayerStats(kills, deaths)

  def __repr__(self):
    return 'Player<%d:%s(%s)>' % (self.steam_id, self.name, self.team)


class Game(object):
  def __init__(self, type_short, red_score=0, blue_score=0, aborted=False):
    self.type_short = type_short
    self.red_score = red_score
    self.blue_score = blue_score
    self.aborted = aborted

  def __repr__(self):
    return 'game<%s:%d-%d%s>' % (
        self.type_short, self.red_score, self.blue_score,
        '(aborted)' if self.aborted else '')


class Plugin(object):
  registered_commands = []
  registered_hooks = []
  messages = []
  current_map_name = None
  current_factory = None
  game = Game('ad')
  players_by_team = {}

  def reset():
    Plugin.registered_commands = []
    Plugin.registered_hooks = []
    Plugin.messages = []
    Plugin.current_map_name = None
    Plugin.current_factory = None
    Plugin.game = Game('ad')
    Plugin.players_by_team = {}

  def set_game(game):
    Plugin.game = game

  def reset_log():
    Plugin.messages = []

  def set_players_by_team(players_by_team):
    for team in players_by_team:
      for player in players_by_team[team]:
        player.team = team
    Plugin.players_by_team = players_by_team

  # minqlx.Plugin API here:

  def teams(self):
    return self.players_by_team.copy()

  def players(self):
    return [player for team in self.players_by_team.values() for player in team]

  def msg(self, message):
    """
    ansi_message = message
    for quake_color, ansi_color in ANSI_COLOR_MAP.items():
      ansi_message = ansi_message.replace(quake_color, ansi_color)
    print(ansi_message + ANSI_COLOR_MAP['^7'])
    """
    clean_message = re.sub(r'\^[\d]', '', message)
    Plugin.messages.append(clean_message)

  def add_command(self, name, cmd, arg_count=0):
    Plugin.registered_commands.append([name, cmd, arg_count])

  def add_hook(self, event, handler, priority=None):
    Plugin.registered_hooks.append([event, handler, priority])

  def change_map(self, map_name, factory):
    Plugin.current_map_name = map_name
    Plugin.current_factory = factory


class Channel(object):
  message_log = ''

  def reset():
    Channel.message_log = ''

  # minqlx.Plugin API here:

  def reply(self, message):
    clean_message = re.sub(r'\^[\d]', '', message)
    Channel.message_log = '%s\n%s' % (Channel.message_log, clean_message)


def reset():
  Plugin.reset()
  Channel.reset()


def load_player(player):
  run_game_hooks('player_loaded', player)


def run_game_hooks(event, data):
  hooks = [h for h in Plugin.registered_hooks if h[0] == event]
  if not hooks:
    return
  for hook in hooks:
    handler = hook[1]
    handler(data)


def end_game():
  run_game_hooks('game_end', {
      'TSCORE0': Plugin.game.red_score,
      'TSCORE1': Plugin.game.blue_score,
      'SCORE_LIMIT': 15,
      'CAPTURE_LIMIT': 8,
      'ABORTED': Plugin.game.aborted,
  })


def start_game(
        player_id_map,
        red_team_ids,
        blue_team_ids,
        red_score,
        blue_score,
        aborted=False):
  setup_game_data(
      player_id_map,
      red_team_ids,
      blue_team_ids,
      red_score,
      blue_score,
      aborted)
  run_game_hooks('game_start', {
      'TSCORE0': Plugin.game.red_score,
      'TSCORE1': Plugin.game.blue_score,
      'SCORE_LIMIT': 15,
      'CAPTURE_LIMIT': 8,
      'ABORTED': Plugin.game.aborted,
  })


def run_game(
        player_id_map,
        red_team_ids,
        blue_team_ids,
        red_score,
        blue_score,
        aborted=False):
  start_game(
      player_id_map,
      red_team_ids,
      blue_team_ids,
      red_score,
      blue_score,
      aborted)
  end_game()


def setup_game_data(
        player_id_map,
        red_team_ids,
        blue_team_ids,
        red_score,
        blue_score,
        aborted=False):
    players_by_teams = {'red': [], 'blue': []}
    for player_id in red_team_ids:
      players_by_teams['red'].append(player_id_map[player_id])
    for player_id in blue_team_ids:
      players_by_teams['blue'].append(player_id_map[player_id])

    Plugin.set_game(Game('ad', red_score, blue_score, aborted))
    Plugin.set_players_by_team(players_by_teams)


def call_command(command_string):
  if not command_string.startswith('!'):
    return

  channel = Channel()
  parts = command_string[1:].split(' ')
  command_name = parts[0]
  arguments = [None] + parts[1:]

  commands = [c for c in Plugin.registered_commands if c[0] == command_name]
  for command in commands:
    fun = command[1]
    fun(None, arguments, channel)