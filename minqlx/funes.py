import datetime
import copy
import itertools
import json
import minqlx
import os
import re

HEADER_COLOR_STRING = '^2'
JSON_FILE_NAME = 'funes_history.json'
ROOT_PATH = os.path.dirname(os.path.realpath(__file__))
JSON_FILE_PATH = os.path.join(ROOT_PATH, JSON_FILE_NAME)


class funes(minqlx.Plugin):

  def __init__(self):
    # Dict: {'red':[id, ...], 'blue':[id, ...]}
    self.current_teams = {}
    # List: [['yyyy-ww', 'gt', [r_ids], [b_ids], r_score, b_score], ...]
    self.history = None
    self.load_history()
    self.add_command('funes', self.cmd_funes, 2)
    self.add_hook('game_start', self.handle_game_start)
    self.add_hook('game_end', self.handle_game_end)

  def print_log(self, msg):
    self.msg('%sFunes:^7 %s' % (HEADER_COLOR_STRING, msg))

  def print_error(self, msg):
    self.msg('%sFunes:^1 %s' % (HEADER_COLOR_STRING, msg))

  def get_clean_name(self, name):
    return re.sub(r'([\W]*\]v\[[\W]*|^\W+|\W+$)', '', name).lower()

  def get_week_key(self):
    iso = datetime.date.today().isocalendar()
    return '-'.join([str(iso[0]), '%02d' % iso[1]])

  def print_header(self, message):
    self.msg('%s%s' % (HEADER_COLOR_STRING, '=' * 80))
    self.msg('%sFunes v1.0:^7 %s' % (HEADER_COLOR_STRING, message))
    self.msg('%s%s' % (HEADER_COLOR_STRING, '-' * 80))

  def load_history(self):
    try:
      self.history = json.loads(open(JSON_FILE_PATH).read())
      self.print_log('Loaded %s history events.' % len(self.history))
    except Exception as e:
      self.print_error('Could not load history (%s)' % e)
      self.history = []

  def save_history(self):
    open(JSON_FILE_PATH, 'w+').write(
        json.dumps(self.history, sort_keys=True, indent=2))
    self.print_log('History saved.')

  def get_history(self):
    return copy.deepcopy(self.history)

  def get_teams_history(self, game_type, teams, aggregate=False):
    relevant_matches = []
    week_key = self.get_week_key()
    team_0_ids = sorted(teams[0])
    team_1_ids = sorted(teams[1])

    history = [0, 0]
    for match in self.history:
      if not aggregate and match[0] != week_key:
        # don't need this date
        continue

      if match[1] != game_type:
        # wrong game type
        continue

      if not (team_0_ids in match and team_1_ids in match):
        # wrong teams
        continue

      team_0_score = match[match.index(team_0_ids) + 2]
      team_1_score = match[match.index(team_1_ids) + 2]
      if team_0_score > team_1_score:
        history[0] += 1
      elif team_0_score < team_1_score:
        history[1] += 1

    return history

  def get_first_week(self):
    if len(self.history) > 0:
      return self.history[0][0].replace('-', 'w')
    else:
      return 'never'

  # Workaround for invalid (empty?) teams() data on start, see:
  # https://github.com/MinoMino/minqlx-plugins/blob/96ef6f4ff630128a6c404ef3f3ca20a60c9bca6c/ban.py#L940
  @minqlx.delay(1)
  def handle_game_start(self, data):
    self.load_history()

    teams = self.teams()
    self.current_teams = copy.deepcopy(teams)
    red_team = teams['red']
    blue_team = teams['blue']
    if len(red_team) == 0 or len(blue_team) == 0:
      self.print_log('Teams are empty on game start.')
      return

    game_type = self.game.type_short
    red_ids = [p.steam_id for p in red_team]
    blue_ids = [p.steam_id for p in blue_team]

    history = self.get_teams_history(game_type, [red_ids, blue_ids])
    aggregate = self.get_teams_history(
        game_type, [red_ids, blue_ids], aggregate=True)

    red_names = ', '.join(
        sorted([self.get_clean_name(p.clean_name) for p in red_team]))
    blue_names = ', '.join(
        sorted([self.get_clean_name(p.clean_name) for p in blue_team]))

    self.print_header('teams history (%s)' % game_type)
    self.msg('  ^1%s^7 ^3%d^7 v ^3%d^7 ^4%s^7' % (red_names, history[0],
                                                  history[1], blue_names))

    format_str = '^3%%%dd^7 v ^3%%d^7 (since %s)' % (len(red_names) + 4,
                                                     self.get_first_week())
    self.msg(format_str % (aggregate[0], aggregate[1]))

  def handle_game_end(self, data):
    teams = copy.deepcopy(self.current_teams)
    self.current_teams = {}

    if data['ABORTED']:
      self.print_log('Not updating history: game was aborted.')
      return

    game_type = self.game.type_short
    max_score = max(data['TSCORE0'], data['TSCORE1'])
    if game_type == 'ctf':
      limit = data['CAPTURE_LIMIT']
    elif game_type == 'ad':
      limit = data['SCORE_LIMIT']
    else:
      limit = data['FRAG_LIMIT']

    if max_score < limit:
      self.print_log('Not updating history: no team won.')
      return

    red_team = teams['red']
    blue_team = teams['blue']
    if len(red_team) == 0 or len(blue_team) == 0:
      self.print_log('Not updating history: one or more empty teams.')
      return

    datum = [
        self.get_week_key(), game_type,
        sorted([p.steam_id for p in red_team]),
        sorted([p.steam_id for p in blue_team]), self.game.red_score,
        self.game.blue_score
    ]

    self.history.append(datum)
    self.print_log('History updated.')
    self.save_history()

  def cmd_funes(self, player, msg, channel):
    game_type = self.game.type_short
    players_present = [
        p.steam_id for p in self.players() if p.team in ['red', 'blue']
    ]
    names_by_id = dict(
        zip(players_present, [
            self.get_clean_name(p.clean_name)
            for p in self.players()
            if p.team in ['red', 'blue']
        ]))

    if len(players_present) < 2:
      self.print_log('No history for less than 2 players.')
      return

    players_present.sort()
    players_per_team = int(len(players_present) / 2)
    teams = list(itertools.combinations(players_present, players_per_team))

    seen_matches = set()
    day_line_data = []
    aggregated_line_data = []

    for team_a in teams:
      for team_b in teams:
        match_key = repr(sorted((sorted(team_a), sorted(team_b))))
        if list(set(team_a) & set(team_b)) or match_key in seen_matches:
          continue

        seen_matches.add(match_key)
        names_a = ', '.join([names_by_id[i] for i in team_a])
        names_b = ', '.join([names_by_id[i] for i in team_b])
        history = self.get_teams_history(game_type, (team_a, team_b))
        aggregate = self.get_teams_history(
            game_type, (team_a, team_b), aggregate=True)
        if history != [0, 0]:
          day_line_data.append((names_a, history[0], history[1], names_b))
        if aggregate != [0, 0]:
          aggregated_line_data.append((names_a, aggregate[0], aggregate[1],
                                       names_b))

    def line_sorter(line):
      return -(line[1] + line[2])

    day_line_data.sort(key=line_sorter)
    aggregated_line_data.sort(key=line_sorter)

    self.print_header('Teams history (%s)' % game_type)
    if len(day_line_data) > 0:
      self.msg('Today:')
      for data in day_line_data:
        self.msg('^3%30s  ^2%d  ^7v  ^2%d  ^3%s' % data)
    else:
      self.msg('Today: no history with these players.')

    self.msg('%s%s' % (HEADER_COLOR_STRING, '-' * 80))
    since_str = 'Since %s:' % (self.get_first_week())
    if len(aggregated_line_data) > 0:
      self.msg(since_str)
      for data in aggregated_line_data:
        self.msg('^3%30s  ^2%d  ^7v  ^2%d  ^3%s' % data)
    else:
      self.msg('%s no history with these players.' % since_str)
