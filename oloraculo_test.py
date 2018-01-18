import json
import re
import sys
import unittest
import minqlx_fake
import trueskill_fake

from unittest.mock import mock_open
from unittest.mock import patch

sys.modules['minqlx'] = minqlx_fake
sys.modules['trueskill'] = trueskill_fake
import oloraculo

# {type:{id:[mu,sigma,w,l,k,d],...},...}
RATINGS = {
  'ad': {
    12: [1, 0, 2, 1, 200, 100],
    34: [2, 0, 1, 4, 100, 900],
    56: [3, 0, 3, 2, 300, 200],
    78: [4, 0, 1, 8, 100, 900],
   },
}
RATINGS_JSON = json.dumps(RATINGS)

PLAYER_ID_MAP = {
  12: minqlx_fake.Player(12, 'john'),
  34: minqlx_fake.Player(34, 'paul'),
  56: minqlx_fake.Player(56, 'george'),
  78: minqlx_fake.Player(78, 'ringo'),
}

class TestOloraculo(unittest.TestCase):
  def setUp(self):
    minqlx_fake.reset()


  def assertSavedJson(self, expected, mocked_open):
    file_handle = mocked_open.return_value.__enter__.return_value
    first_write = file_handle.write.call_args_list[0]
    write_arguments = first_write[0]
    saved_json = write_arguments[0]
    self.assertEqual(expected, json.loads(saved_json))


  def setup_game_test_data(
      self, red_team_ids, blue_team_ids, red_score, blue_score):
    players_by_teams = {'red': [], 'blue': []}
    for player_id in red_team_ids:
      players_by_teams['red'].append(PLAYER_ID_MAP[player_id])
    for player_id in blue_team_ids:
      players_by_teams['blue'].append(PLAYER_ID_MAP[player_id])

    minqlx_fake.Plugin.set_player_list(
        [PLAYER_ID_MAP[pid] for pid in blue_team_ids + red_team_ids])
    minqlx_fake.Plugin.set_game(minqlx_fake.Game('ad', red_score, blue_score))
    minqlx_fake.Plugin.set_players_by_team(players_by_teams)

    # return the game data obj received by hook handlers.
    return {
      'TSCORE0': red_score,
      'TSCORE1': blue_score,
      'SCORE_LIMIT': 15,
      'CAPTURE_LIMIT': 8,
      'ABORTED': False,
    }


  @patch('builtins.open', mock_open(read_data=json.dumps({})))
  def test_registers_commands_and_hooks(self):
    olor = oloraculo.oloraculo()
    self.assertEqual([
        'oloraculo',
        'oloraculo_ratings'],
        sorted([cmd[0] for cmd in minqlx_fake.Plugin.registered_commands]))

    self.assertEqual([
        'game_end',
        'game_start',
        'player_loaded'],
        sorted([hook[0] for hook in minqlx_fake.Plugin.registered_hooks]))


  @patch('builtins.open', mock_open(read_data=json.dumps({})))
  def test_get_stats_copy(self):
    olor = oloraculo.oloraculo()
    stats = olor.get_stats()
    self.assertEqual(0, len(olor.get_stats().get_player_ids('ad')))
    self.assertEqual(0, len(stats.get_player_ids('ad')))
    stats.new_player('ad', 666)
    self.assertEqual(0, len(olor.get_stats().get_player_ids('ad')))
    self.assertEqual(1, len(stats.get_player_ids('ad')))


  @patch('builtins.open', mock_open(read_data=RATINGS_JSON))
  def test_loads_stats(self):
    olor = oloraculo.oloraculo()
    expected_stats = RATINGS['ad']
    stats = olor.get_stats()
    for player_id in stats.get_player_ids('ad'):
      self.assertTrue(player_id in expected_stats)
      expected_player = expected_stats[player_id]
      expected_rating = trueskill_fake.Rating(
          expected_player[0], expected_player[1])
      self.assertEqual(expected_rating, stats.get_rating('ad', player_id))
      self.assertEqual(
          [expected_player[2], expected_player[3]],
          stats.get_winloss('ad', player_id))
      self.assertEqual(
          [expected_player[4], expected_player[5]],
          stats.get_killdeath('ad', player_id))


  @patch('builtins.open', mock_open(read_data=RATINGS_JSON))
  def test_handles_game_end(self):
    olor = oloraculo.oloraculo()
    # red_team_ids, blue_team_ids, red_score, blue_score
    game_data = self.setup_game_test_data([56, 78], [12, 34], 7, 15)
    olor.handle_game_end(game_data)
    stats = olor.get_stats()
    # winloss
    self.assertEqual([3, 1], stats.get_winloss('ad', 12))
    self.assertEqual([2, 4], stats.get_winloss('ad', 34))
    self.assertEqual([3, 3], stats.get_winloss('ad', 56))
    self.assertEqual([1, 9], stats.get_winloss('ad', 78))
    # ratings
    self.assertEqual(trueskill_fake.Rating(2), stats.get_rating('ad', 12))
    self.assertEqual(trueskill_fake.Rating(3), stats.get_rating('ad', 34))
    self.assertEqual(trueskill_fake.Rating(2), stats.get_rating('ad', 56))
    self.assertEqual(trueskill_fake.Rating(3), stats.get_rating('ad', 78))


  @patch('builtins.open', new_callable=mock_open, read_data=RATINGS_JSON)
  def test_saves_stats(self, m):
    olor = oloraculo.oloraculo()
    # red_team_ids, blue_team_ids, red_score, blue_score
    game_data = self.setup_game_test_data([56, 78], [12, 34], 7, 15)
    olor.handle_game_end(game_data)
    expected_data = {
      'ad': {
        '12': [2, 0, 3, 1, 200, 100],
        '34': [3, 0, 2, 4, 100, 900],
        '56': [2, 0, 3, 3, 300, 200],
        '78': [3, 0, 1, 9, 100, 900],
       },
    }
    self.assertSavedJson(expected_data, m)


  @patch('builtins.open', mock_open(read_data=json.dumps({})))
  def test_handles_player_loaded(self):
    olor = oloraculo.oloraculo()
    self.assertEqual(set(), olor.get_stats().get_player_ids('ad'))
    player = minqlx_fake.Player(123456, 'sarge')
    olor.handle_player_loaded(player)
    self.assertEqual({123456}, olor.get_stats().get_player_ids('ad'))
    self.assertEqual([0, 0], olor.get_stats().get_winloss('ad', 123456))
    self.assertEqual([0, 0], olor.get_stats().get_killdeath('ad', 123456))


  @patch('builtins.open', mock_open(read_data=RATINGS_JSON))
  def test_oloraculo_ratings(self):
    olor = oloraculo.oloraculo()
    player_names = [PLAYER_ID_MAP[id].name for id in PLAYER_ID_MAP]

    # No players loaded yet:
    minqlx_fake.call_command(olor.cmd_oloraculo_ratings)
    for player_name in player_names:
      self.assertFalse(player_name in ''.join(minqlx_fake.Plugin.messages))

    minqlx_fake.Plugin.reset()

    # Players loaded.
    for player_id in PLAYER_ID_MAP:
      olor.handle_player_loaded(PLAYER_ID_MAP[player_id])
    minqlx_fake.call_command(olor.cmd_oloraculo_ratings)
    for player_name in player_names:
      self.assertTrue(player_name in ''.join(minqlx_fake.Plugin.messages))


  @patch('builtins.open', mock_open(read_data=json.dumps({})))
  def test_oloraculo_ratings_no_stats(self):
    olor = oloraculo.oloraculo()
    player_names = [PLAYER_ID_MAP[id].name for id in PLAYER_ID_MAP]

    # No players loaded yet:
    minqlx_fake.call_command(olor.cmd_oloraculo_ratings)
    for player_name in player_names:
      self.assertFalse(player_name in ''.join(minqlx_fake.Plugin.messages))

    minqlx_fake.Plugin.reset()

    # Players loaded.
    for player_id in PLAYER_ID_MAP:
      olor.handle_player_loaded(PLAYER_ID_MAP[player_id])
    minqlx_fake.call_command(olor.cmd_oloraculo_ratings)
    for player_name in player_names:
      self.assertTrue(player_name in ''.join(minqlx_fake.Plugin.messages))


if __name__ == '__main__':
    unittest.main()