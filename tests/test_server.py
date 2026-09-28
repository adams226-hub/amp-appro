import sys, tempfile, unittest, json
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'server'))
import server as s
class WorkflowTests(unittest.TestCase):
 def setUp(self):
  self.tmp=tempfile.TemporaryDirectory();s.DB=str(Path(self.tmp.name)/'test.sqlite');s.init();self.c=s.connect()
  for role in s.ROLES:
   self.c.execute('INSERT INTO users VALUES(?,?,?,?,?,1)',(role,role,role+'@amp.test',role,s.hash_password('TestPassword123!')))
  self.c.execute('INSERT INTO units VALUES(?,?,?)',('u','Chantier test',100000));self.c.commit()
 def tearDown(self):self.c.close();self.tmp.cleanup()
 def call(self,role,path,b=None):
  user=self.c.execute('SELECT * FROM users WHERE id=?',(role,)).fetchone()
  try:
   self.c.execute('BEGIN IMMEDIATE');r=s.dispatch(self.c,user,'POST' if b is not None else 'GET',path,b or {});self.c.commit();return r
  except:self.c.rollback();raise
 def create(self):return self.call('DEMANDEUR','/requests',{'unit_id':'u','title':'Ciment','due':'2026-10-01','address':'Dépôt','lines':[{'designation':'Ciment','unit':'tonne','quantity':2}],'urgency':'NORMALE','kind':'FOURNITURE'})['id']
 def read(self,rid):return next(r for r in self.call('ACHATS','/state')['requests'] if r['id']==rid)
 def action(self,rid,role,action,**kwargs):return self.call(role,'/requests/'+rid+'/action',{'version':self.read(rid)['version'],'action':action,**kwargs})
 def price(self,rid,price=10000):return self.action(rid,'ACHATS','price',supplier='Fournisseur test',quote='DEV-001',payment='30 jours',prices=[{'price':price,'tax':18}])
 def test_full_flow_partial_and_oversupply(self):
  rid=self.create();self.price(rid);self.assertEqual(self.read(rid)['total_ttc'],23600)
  self.action(rid,'COMPTA','previsa',imputation='Matériaux');self.action(rid,'DG','approve');self.action(rid,'ACHATS','order',reason='Email de commande')
  self.action(rid,'DEMANDEUR','receive',reason='BL-001',quantities=[1]);self.assertEqual(self.read(rid)['status'],'PARTIELLE')
  with self.assertRaises(ValueError):self.action(rid,'DEMANDEUR','receive',reason='BL-002',quantities=[2])
  self.assertEqual(self.read(rid)['lines'][0]['received'],1)
  self.action(rid,'DEMANDEUR','receive',reason='BL-002',quantities=[1]);self.action(rid,'ACHATS','close');self.assertEqual(self.read(rid)['status'],'CLOTUREE')
  self.assertEqual(self.c.execute('SELECT COUNT(*) FROM decisions').fetchone()[0],3)
 def test_rbac_and_old_version(self):
  rid=self.create()
  with self.assertRaises(PermissionError):self.action(rid,'DG','approve')
  with self.assertRaises(PermissionError):self.action(rid,'ADMIN','price')
  self.price(rid)
  with self.assertRaises(ValueError):self.call('COMPTA','/requests/'+rid+'/action',{'version':1,'action':'previsa','imputation':'test'})
 def test_budget_double_reservation_and_return(self):
  a=self.create();b=self.create();self.price(a,30000);self.price(b,30000)
  self.action(a,'COMPTA','previsa',imputation='Matériaux')
  with self.assertRaises(ValueError):self.action(b,'COMPTA','previsa',imputation='Matériaux')
  self.action(a,'DG','return',reason='Revoir le devis');self.action(b,'COMPTA','previsa',imputation='Matériaux');self.assertEqual(self.read(a)['status'],'ATTENTE_ACHATS')
 def test_attachment_scope_and_lock(self):
  import base64
  rid=self.create();a=self.call('DEMANDEUR','/requests/'+rid+'/attachments',{'name':'devis.pdf','mime':'application/pdf','data':base64.b64encode(b'%PDF-1.4\n test').decode()})
  self.assertEqual(self.call('DG','/attachments/'+a['id'])['mime'],'application/pdf');self.price(rid)
  with self.assertRaises(PermissionError):self.call('DEMANDEUR','/requests/'+rid+'/attachments',{'name':'test'})
  self.c.execute('INSERT INTO users VALUES(?,?,?,?,?,1)',('other','Autre','other@amp.test','DEMANDEUR',s.hash_password('TestPassword123!')));self.c.commit()
  self.assertEqual(len(self.call('other','/state')['requests']),0)
  with self.assertRaises(PermissionError):self.call('other','/attachments/'+a['id'])
if __name__=='__main__':unittest.main(verbosity=2)
