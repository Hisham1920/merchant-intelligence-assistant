"""A real process restart must retain context and suppression state."""

import os
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest


ROOT = Path(__file__).resolve().parents[1]
SETUP = """
import json
from pathlib import Path
from fastapi.testclient import TestClient
from app import app

data = Path('dataset')
category = json.loads((data/'categories'/'dentists.json').read_text())
merchant = json.loads((data/'merchants_seed.json').read_text())['merchants'][0]
trigger = json.loads((data/'triggers_seed.json').read_text())['triggers'][0]
client = TestClient(app)
for scope, key, item in [('category','slug',category), ('merchant','merchant_id',merchant), ('trigger','id',trigger)]:
    response = client.post('/v1/context', json={'scope': scope, 'context_id': item[key], 'version': 1, 'payload': item})
    assert response.status_code == 200, response.text
response = client.post('/v1/tick', json={'now':'2026-04-26T10:00:00Z','available_triggers':[trigger['id']]})
assert len(response.json()['actions']) == 1, response.text
"""

CHECK = """
import json
from pathlib import Path
from fastapi.testclient import TestClient
from app import app

client = TestClient(app)
assert client.get('/v1/healthz').json()['contexts_loaded'] == {'category': 1, 'merchant': 1, 'customer': 0, 'trigger': 1}
trigger = json.loads((Path('dataset')/'triggers_seed.json').read_text())['triggers'][0]
response = client.post('/v1/tick', json={'now':'2026-04-26T10:05:00Z','available_triggers':[trigger['id']]})
assert response.status_code == 200 and response.json()['actions'] == [], response.text
"""


class RestartTest(unittest.TestCase):
    def test_context_and_sent_history_survive_restart(self):
        with tempfile.TemporaryDirectory() as temporary:
            environment = {**os.environ, 'VERA_DB': str(Path(temporary) / 'state.sqlite3')}
            environment.pop('DATABASE_URL', None)
            environment.pop('OPENAI_API_KEY', None)
            for script in (SETUP, CHECK):
                result = subprocess.run([sys.executable, '-c', script], cwd=ROOT,
                                        env=environment, capture_output=True, text=True, timeout=20)
                self.assertEqual(result.returncode, 0, result.stderr)
