import json, os, shutil, subprocess, sys, tempfile, unittest
from pathlib import Path
SOURCE=Path(__file__).resolve().parents[1]/'server/server.py'
class ConfigTests(unittest.TestCase):
 def config(self,envtext,overrides=None):
  with tempfile.TemporaryDirectory() as tmp:
   root=Path(tmp);(root/'server').mkdir();shutil.copy(SOURCE,root/'server/server.py');(root/'.env').write_text(envtext)
   env=dict(os.environ)
   for key in ['AMP_DB','AMP_HOST','AMP_PORT','PYTHON_DOTENV_DISABLED']:env.pop(key,None)
   env.update(overrides or {})
   code='import sys,json;sys.path.insert(0,sys.argv[1]);import server;print(json.dumps([server.DB,server.HOST,server.PORT]))'
   run=subprocess.run([sys.executable,'-c',code,str(root/'server')],env=env,cwd='/',text=True,capture_output=True)
   return run
 def test_dotenv_from_other_directory(self):
  r=self.config('AMP_DB=/tmp/amp-dotenv-test.sqlite3\nAMP_HOST=0.0.0.0\nAMP_PORT=8089\n');self.assertEqual(r.returncode,0,r.stderr);self.assertEqual(json.loads(r.stdout),['/tmp/amp-dotenv-test.sqlite3','0.0.0.0',8089])
 def test_environment_takes_precedence(self):
  r=self.config('AMP_DB=/from-file.sqlite3\n',{'AMP_DB':'/from-environment.sqlite3'});self.assertEqual(json.loads(r.stdout)[0],'/from-environment.sqlite3')
 def test_defaults_preserve_original_behavior(self):
  r=self.config('');self.assertEqual(json.loads(r.stdout),['amp-appro.sqlite3','127.0.0.1',8080])
 def test_empty_database_rejected(self):
  r=self.config('AMP_DB=\n');self.assertNotEqual(r.returncode,0);self.assertIn('AMP_DB',r.stderr)
 def test_invalid_port_rejected(self):
  r=self.config('AMP_PORT=70000\n');self.assertNotEqual(r.returncode,0);self.assertIn('AMP_PORT',r.stderr)
