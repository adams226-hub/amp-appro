#!/usr/bin/env python3
"""AMP Appro pilot API. Standard Python 3.11+, SQLite. Bind behind an HTTPS reverse proxy."""
import argparse, base64, datetime, hashlib, hmac, json, os, secrets, sqlite3, time
from decimal import Decimal, InvalidOperation, ROUND_HALF_UP
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

from dotenv import load_dotenv

# Explicit root path: loading does not depend on the shell's working directory.
# Existing process/Docker variables take priority over .env.
PROJECT_DIR = Path(__file__).resolve().parent.parent
load_dotenv(PROJECT_DIR / '.env', override=False)
DB = os.environ.get('AMP_DB', 'amp-appro.sqlite3')
HOST = os.environ.get('AMP_HOST', '127.0.0.1')
PORT = int(os.environ.get('AMP_PORT', '8080'))
if not DB.strip():
 raise ValueError('AMP_DB ne doit pas être vide.')
if not 1 <= PORT <= 65535:
 raise ValueError('AMP_PORT doit être compris entre 1 et 65535.')
ROLES = ['DEMANDEUR','ACHATS','COMPTA','DG','ADMIN']
LABELS = {'ATTENTE_ACHATS':'En attente Achats','ATTENTE_COMPTA':'En validation Compta','ATTENTE_DG':'En attente DG','VALIDEE':'Validée','COMMANDEE':'Commandée','PARTIELLE':'Réception partielle','LIVREE':'Livrée','CLOTUREE':'Clôturée','REJETEE':'Rejetée'}
def now(): return datetime.datetime.now(datetime.timezone.utc).isoformat()
def connect():
 c=sqlite3.connect(DB, timeout=15);c.row_factory=sqlite3.Row;c.execute('PRAGMA foreign_keys=ON');return c

def init():
 with connect() as c:
  c.executescript('''
  PRAGMA journal_mode=WAL;
  CREATE TABLE IF NOT EXISTS users(id TEXT PRIMARY KEY,name TEXT NOT NULL,email TEXT UNIQUE NOT NULL,role TEXT NOT NULL,password TEXT NOT NULL,active INTEGER NOT NULL DEFAULT 1);
  CREATE TABLE IF NOT EXISTS sessions(token_hash TEXT PRIMARY KEY,user_id TEXT NOT NULL REFERENCES users(id),expires REAL NOT NULL);
  CREATE TABLE IF NOT EXISTS units(id TEXT PRIMARY KEY,name TEXT NOT NULL UNIQUE,budget INTEGER NOT NULL CHECK(budget>=0));
  CREATE TABLE IF NOT EXISTS requests(id TEXT PRIMARY KEY,owner TEXT NOT NULL REFERENCES users(id),unit_id TEXT NOT NULL REFERENCES units(id),status TEXT NOT NULL,version INTEGER NOT NULL,amount INTEGER NOT NULL DEFAULT 0,document TEXT NOT NULL);
  CREATE TABLE IF NOT EXISTS attachments(id TEXT PRIMARY KEY,request_id TEXT NOT NULL REFERENCES requests(id),name TEXT NOT NULL,mime TEXT NOT NULL,data BLOB NOT NULL,hash TEXT NOT NULL);
  CREATE TABLE IF NOT EXISTS events(id INTEGER PRIMARY KEY,request_id TEXT,actor TEXT NOT NULL,event TEXT NOT NULL,at TEXT NOT NULL);
  CREATE TABLE IF NOT EXISTS decisions(id TEXT PRIMARY KEY,request_id TEXT NOT NULL REFERENCES requests(id),version INTEGER NOT NULL,actor TEXT NOT NULL,action TEXT NOT NULL,snapshot TEXT NOT NULL,hash TEXT NOT NULL,at TEXT NOT NULL,UNIQUE(request_id,version));
  CREATE TABLE IF NOT EXISTS idempotency(user_id TEXT NOT NULL,key TEXT NOT NULL,payload_hash TEXT NOT NULL,response TEXT NOT NULL,PRIMARY KEY(user_id,key));
  CREATE TABLE IF NOT EXISTS login_attempts(email TEXT PRIMARY KEY,failures INTEGER NOT NULL,last REAL NOT NULL);
  ''')
def hash_password(password):
 salt=secrets.token_hex(16)
 return salt+':'+hashlib.pbkdf2_hmac('sha256',password.encode(),salt.encode(),300000).hex()
def verify_password(password,stored):
 salt,expected=stored.split(':');return hmac.compare_digest(expected,hashlib.pbkdf2_hmac('sha256',password.encode(),salt.encode(),300000).hex())
def text(v, maxlen=2000):
 if not isinstance(v,str) or not v.strip() or len(v)>maxlen: raise ValueError('Champ obligatoire manquant ou trop long.')
 return v.strip()
def number(v, minimum=0, maximum=10**12):
 try: d=Decimal(str(v))
 except InvalidOperation: raise ValueError('Valeur numérique invalide.')
 if not d.is_finite() or d<minimum or d>maximum: raise ValueError('Valeur numérique hors limites.')
 return d
def money(d): return int(d.quantize(Decimal('1'),rounding=ROUND_HALF_UP))
def audit(c,user,rid,event): c.execute('INSERT INTO events(request_id,actor,event,at) VALUES(?,?,?,?)',(rid,user['id'],event,now()))
def authorized(user,r): return user['role']!='DEMANDEUR' or r['owner']==user['id']
def store(c,d):
 c.execute('UPDATE requests SET status=?,version=?,amount=?,document=? WHERE id=?',(d['status'],d['version'],d.get('total_ht',0),json.dumps(d,ensure_ascii=False),d['id']))
def spent(c,unit,exclude=''):
 return c.execute("SELECT COALESCE(SUM(amount),0) FROM requests WHERE unit_id=? AND id!=? AND status IN ('ATTENTE_DG','VALIDEE','COMMANDEE','PARTIELLE','LIVREE','CLOTUREE')",(unit,exclude)).fetchone()[0]

def dispatch(c,user,method,path,b):
 role=user['role']
 if method=='GET' and path=='/state':
  reqs=[json.loads(r['document']) for r in c.execute('SELECT * FROM requests ORDER BY rowid DESC') if authorized(user,r)]
  for d in reqs:
   d['attachments']=[dict(x) for x in c.execute('SELECT id,name,mime,hash FROM attachments WHERE request_id=?',(d['id'],))]
  units=[dict(x) for x in c.execute('SELECT * FROM units ORDER BY name')]
  for u in units:
   u['committed']=spent(c,u['id'])
   if role=='DEMANDEUR': u.pop('budget');u.pop('committed')
  return {'user':{k:user[k] for k in ['id','name','email','role']},'requests':reqs,'units':units,'users':[dict(x) for x in c.execute('SELECT id,name,email,role FROM users')] if role=='ADMIN' else []}
 if method=='POST' and path=='/units':
  if role!='ADMIN': raise PermissionError('Administration uniquement.')
  uid=secrets.token_hex(12);c.execute('INSERT INTO units VALUES(?,?,?)',(uid,text(b.get('name'),120),money(number(b.get('budget')))));audit(c,user,None,'Création chantier/service');return {'id':uid}
 if method=='POST' and path=='/users':
  if role!='ADMIN': raise PermissionError('Administration uniquement.')
  if b.get('role') not in ROLES: raise ValueError('Rôle invalide.')
  pwd=text(b.get('password'),200)
  if len(pwd)<12: raise ValueError('Mot de passe : 12 caractères minimum.')
  email=text(b.get('email'),200).lower()
  if '@' not in email: raise ValueError('Adresse email invalide.')
  uid=secrets.token_hex(12);c.execute('INSERT INTO users VALUES(?,?,?,?,?,1)',(uid,text(b.get('name'),120),email,b['role'],hash_password(pwd)));audit(c,user,None,'Création utilisateur');return {'id':uid}
 if method=='POST' and path=='/requests':
  if role!='DEMANDEUR': raise PermissionError('Création réservée aux demandeurs.')
  unit=c.execute('SELECT * FROM units WHERE id=?',(b.get('unit_id'),)).fetchone()
  if not unit: raise ValueError('Sélectionnez un chantier/service.')
  lines=b.get('lines',[])
  if not isinstance(lines,list) or not 1<=len(lines)<=100: raise ValueError('Ajoutez de 1 à 100 lignes.')
  clean=[]
  for l in lines: clean.append({'designation':text(l.get('designation'),300),'unit':text(l.get('unit'),30),'quantity':float(number(l.get('quantity'),Decimal('.001'),10**8)),'price':0,'tax':0,'received':0})
  due=text(b.get('due'),10);datetime.date.fromisoformat(due)
  urgency=b.get('urgency','NORMALE')
  if urgency not in ['NORMALE','URGENTE','CRITIQUE']: raise ValueError('Urgence invalide.')
  reason=text(b.get('reason'),500) if urgency!='NORMALE' else str(b.get('reason',''))[:500]
  rid=secrets.token_hex(12);ref='DA-'+str(datetime.date.today().year)+'-'+rid[:6].upper()
  d={'id':rid,'reference':ref,'owner':user['id'],'owner_name':user['name'],'unit_id':unit['id'],'unit_name':unit['name'],'title':text(b.get('title'),200),'due':due,'urgency':urgency,'reason':reason,'address':text(b.get('address'),500),'kind':b.get('kind','FOURNITURE'),'lines':clean,'status':'ATTENTE_ACHATS','version':1,'created':now(),'total_ht':0,'total_tax':0,'total_ttc':0,'history':[{'at':now(),'actor':user['name'],'action':'Demande soumise'}]}
  if d['kind'] not in ['FOURNITURE','SERVICE']: raise ValueError('Type de demande invalide.')
  c.execute('INSERT INTO requests VALUES(?,?,?,?,?,?,?)',(rid,user['id'],unit['id'],d['status'],1,0,json.dumps(d,ensure_ascii=False)));audit(c,user,rid,'Demande soumise');return {'id':rid}
 parts=path.strip('/').split('/')
 if len(parts)>=2 and parts[0]=='requests':
  r=c.execute('SELECT * FROM requests WHERE id=?',(parts[1],)).fetchone()
  if not r or not authorized(user,r): raise PermissionError('Dossier inaccessible.')
  d=json.loads(r['document'])
  if method=='POST' and len(parts)==3 and parts[2]=='attachments':
   if d['status']!='ATTENTE_ACHATS' or (role!='ACHATS' and not(role=='DEMANDEUR' and user['id']==d['owner'])): raise PermissionError('Ajout de pièces uniquement avant contrôle comptable.')
   raw=base64.b64decode(b.get('data',''),validate=True)
   if len(raw)>5*1024*1024 or not raw: raise ValueError('Pièce limitée à 5 Mo.')
   mime=b.get('mime');valid=(mime=='application/pdf' and raw.startswith(b'%PDF-')) or (mime=='image/png' and raw.startswith(b'\x89PNG\r\n\x1a\n')) or (mime=='image/jpeg' and raw.startswith(b'\xff\xd8\xff'))
   if not valid: raise ValueError('Formats acceptés : PDF, JPEG, PNG valides.')
   if c.execute('SELECT COUNT(*) FROM attachments WHERE request_id=?',(d['id'],)).fetchone()[0]>=10: raise ValueError('10 pièces maximum par dossier.')
   aid=secrets.token_hex(12);c.execute('INSERT INTO attachments VALUES(?,?,?,?,?,?)',(aid,d['id'],text(b.get('name'),150),mime,raw,hashlib.sha256(raw).hexdigest()))
   d['version']+=1;d['history'].append({'at':now(),'actor':user['name'],'action':'Pièce ajoutée : '+b['name']});store(c,d);audit(c,user,d['id'],'Pièce ajoutée');return {'id':aid}
  if method=='POST' and len(parts)==3 and parts[2]=='action':
   if b.get('version')!=d['version']: raise ValueError('Dossier modifié. Actualisez avant de recommencer.')
   action=b.get('action');status=d['status'];event='';reason=str(b.get('reason','')).strip()
   expected={'price':('ACHATS',['ATTENTE_ACHATS']),'previsa':('COMPTA',['ATTENTE_COMPTA']),'approve':('DG',['ATTENTE_DG']),'order':('ACHATS',['VALIDEE']),'close':('ACHATS',['LIVREE'])}
   if action in expected:
    rr,ss=expected[action]
    if role!=rr or status not in ss: raise PermissionError('Action non autorisée à cette étape.')
   elif action in ['reject','return']:
    rr={'ATTENTE_ACHATS':'ACHATS','ATTENTE_COMPTA':'COMPTA','ATTENTE_DG':'DG'}.get(status)
    if role!=rr: raise PermissionError('Action non autorisée.')
    reason=text(b.get('reason'),1000)
   elif action=='receive':
    if not(role=='ACHATS' or (role=='DEMANDEUR' and d['owner']==user['id'])) or status not in ['COMMANDEE','PARTIELLE']: raise PermissionError('Réception non autorisée.')
   else: raise ValueError('Action inconnue.')
   if action=='price':
    prices=b.get('prices',[])
    if len(prices)!=len(d['lines']): raise ValueError('Chiffrage incomplet.')
    d['supplier']=text(b.get('supplier'),200);d['quote']=text(b.get('quote'),200);d['payment']=text(b.get('payment'),500)
    ht=tax=0
    for l,p in zip(d['lines'],prices):
     price=number(p.get('price'));rate=number(p.get('tax'),0,100);lineht=money(Decimal(str(l['quantity']))*price);linetax=money(Decimal(lineht)*rate/100)
     l.update(price=float(price),tax=float(rate),ht=lineht,tax_amount=linetax);ht+=lineht;tax+=linetax
    d.update(total_ht=ht,total_tax=tax,total_ttc=ht+tax,status='ATTENTE_COMPTA');event='Dossier chiffré et transmis à la comptabilité'
   elif action=='previsa':
    if user['id']==d['owner']: raise PermissionError('Auto-visa interdit.')
    u=c.execute('SELECT * FROM units WHERE id=?',(d['unit_id'],)).fetchone()
    if spent(c,u['id'],d['id'])+d['total_ht']>u['budget']: raise ValueError('Budget insuffisant sur ce chantier/service.')
    d['imputation']=text(b.get('imputation'),200);d['previsa_actor']=user['id'];d['status']='ATTENTE_DG';event='Pré-visa comptable ; budget réservé'
   elif action=='approve':
    if user['id'] in [d['owner'],d.get('previsa_actor')]: raise PermissionError('Séparation des validations requise.')
    d['status']='VALIDEE';d['approved_at']=now();d['approved_by']=user['name'];event='Approbation DG horodatée'
   elif action=='order':
    d['sent_reference']=text(b.get('reason'),500);d['status']='COMMANDEE';event='Commande transmise au fournisseur : '+d['sent_reference']
   elif action=='receive':
    reference=text(b.get('reason'),500);qs=b.get('quantities',[])
    if len(qs)!=len(d['lines']): raise ValueError('Réception incomplète.')
    total=0
    for l,q in zip(d['lines'],qs):
     qty=number(q,0,Decimal(str(l['quantity']))-Decimal(str(l['received'])));l['received']=float(Decimal(str(l['received']))+qty);total+=qty
    if total<=0: raise ValueError('Indiquez une quantité reçue supérieure à zéro.')
    d['status']='LIVREE' if all(l['received']>=l['quantity'] for l in d['lines']) else 'PARTIELLE';event='Réception enregistrée — BL/PV : '+reference
   elif action=='close': d['status']='CLOTUREE';event='Dossier clôturé'
   elif action=='reject':d['status']='REJETEE';event='Rejet : '+reason
   elif action=='return':
    if status=='ATTENTE_ACHATS':raise ValueError('Rejetez avec motif pour demander une nouvelle soumission.')
    d['status']='ATTENTE_ACHATS';d.pop('previsa_actor',None);event='Retour aux Achats : '+reason
   snapshot_data=dict(d)
   snapshot_data['attachments']=[dict(x) for x in c.execute('SELECT id,name,mime,hash FROM attachments WHERE request_id=? ORDER BY id',(d['id'],))]
   snapshot=json.dumps(snapshot_data,ensure_ascii=False,sort_keys=True)
   if action in ['price','previsa','approve','reject','return']:
    c.execute('INSERT INTO decisions VALUES(?,?,?,?,?,?,?,?)',(secrets.token_hex(12),d['id'],d['version'],user['id'],action,snapshot,hashlib.sha256(snapshot.encode()).hexdigest(),now()))
   d['version']+=1;d['history'].append({'at':now(),'actor':user['name'],'action':event});store(c,d);audit(c,user,d['id'],event);return {'id':d['id']}
 if method=='GET' and len(parts)==2 and parts[0]=='attachments':
  a=c.execute('SELECT a.*,r.owner FROM attachments a JOIN requests r ON r.id=a.request_id WHERE a.id=?',(parts[1],)).fetchone()
  if not a or not authorized(user,a):raise PermissionError('Pièce inaccessible.')
  return {'name':a['name'],'mime':a['mime'],'data':base64.b64encode(a['data']).decode()}
 raise ValueError('Opération inconnue.')

class Handler(BaseHTTPRequestHandler):
 def log_message(self,*args): pass
 def reply(self,status,obj):
  data=json.dumps(obj,ensure_ascii=False).encode();self.send_response(status)
  self.send_header('Content-Type','application/json; charset=utf-8');self.send_header('Content-Length',str(len(data)))
  self.send_header('Access-Control-Allow-Origin','https://app.amp.local');self.send_header('Vary','Origin');self.send_header('Cache-Control','no-store');self.end_headers();self.wfile.write(data)
 def do_OPTIONS(self):
  self.send_response(204);self.send_header('Access-Control-Allow-Origin','https://app.amp.local');self.send_header('Access-Control-Allow-Headers','Content-Type, Authorization, Idempotency-Key');self.send_header('Access-Control-Allow-Methods','GET, POST, OPTIONS');self.end_headers()
 def do_GET(self):self.handle_api('GET')
 def do_POST(self):self.handle_api('POST')
 def handle_api(self,method):
  c=connect()
  try:
   size=int(self.headers.get('Content-Length',0))
   if size<0 or size>8*1024*1024:raise ValueError('Requête trop volumineuse.')
   b=json.loads(self.rfile.read(size)) if size else {}
   if not isinstance(b,dict):raise ValueError('Objet JSON requis.')
   path=self.path.split('?')[0];c.execute('BEGIN IMMEDIATE')
   if path=='/health' and method=='GET':
    c.execute('SELECT 1');c.rollback();return self.reply(200,{'status':'ok'})
   if path=='/login' and method=='POST':
    email=text(b.get('email'),200).lower();pwd=text(b.get('password'),200)
    attempt=c.execute('SELECT * FROM login_attempts WHERE email=?',(email,)).fetchone()
    if attempt and attempt['failures']>=5 and time.time()-attempt['last']<900:raise PermissionError('Trop de tentatives. Réessayez dans 15 minutes.')
    u=c.execute('SELECT * FROM users WHERE email=? AND active=1',(email,)).fetchone()
    if not u or not verify_password(pwd,u['password']):
     count=attempt['failures']+1 if attempt and time.time()-attempt['last']<900 else 1
     c.execute('INSERT OR REPLACE INTO login_attempts VALUES(?,?,?)',(email,count,time.time()));c.commit();raise PermissionError('Identifiants invalides.')
    c.execute('DELETE FROM login_attempts WHERE email=?',(email,));token=secrets.token_urlsafe(32)
    c.execute('DELETE FROM sessions WHERE expires<?',(time.time(),));c.execute('INSERT INTO sessions VALUES(?,?,?)',(hashlib.sha256(token.encode()).hexdigest(),u['id'],time.time()+8*3600));c.commit();return self.reply(200,{'token':token})
   token=self.headers.get('Authorization','').removeprefix('Bearer ')
   u=c.execute('SELECT u.* FROM sessions s JOIN users u ON u.id=s.user_id WHERE s.token_hash=? AND s.expires>? AND u.active=1',(hashlib.sha256(token.encode()).hexdigest(),time.time())).fetchone()
   if not u:raise PermissionError('Session expirée ou connexion requise.')
   if path=='/logout':c.execute('DELETE FROM sessions WHERE token_hash=?',(hashlib.sha256(token.encode()).hexdigest(),));c.commit();return self.reply(200,{'ok':True})
   key=self.headers.get('Idempotency-Key','');digest=hashlib.sha256((path+json.dumps(b,sort_keys=True)).encode()).hexdigest()
   if method=='POST':
    if not key or len(key)>100:raise ValueError('Clé de transaction requise.')
    old=c.execute('SELECT * FROM idempotency WHERE user_id=? AND key=?',(u['id'],key)).fetchone()
    if old:
     if old['payload_hash']!=digest:raise ValueError('Clé de transaction déjà utilisée.')
     c.rollback();return self.reply(200,json.loads(old['response']))
   result=dispatch(c,u,method,path,b)
   if method=='POST':c.execute('INSERT INTO idempotency VALUES(?,?,?,?)',(u['id'],key,digest,json.dumps(result)))
   c.commit();self.reply(200,result)
  except PermissionError as e:c.rollback();self.reply(403,{'error':str(e)})
  except (ValueError,TypeError,KeyError,sqlite3.IntegrityError) as e:c.rollback();self.reply(400,{'error':str(e) if not isinstance(e,sqlite3.IntegrityError) else 'Donnée déjà existante ou incohérente.'})
  except Exception:
   c.rollback();self.reply(500,{'error':'Erreur serveur. Consultez le journal technique.'});import traceback;traceback.print_exc()
  finally:c.close()

if __name__=='__main__':
 p=argparse.ArgumentParser();p.add_argument('--init-admin',action='store_true');p.add_argument('--host',default=HOST);p.add_argument('--port',type=int,default=PORT);args=p.parse_args();init()
 if args.init_admin:
  import getpass
  email=input('Email administrateur : ').strip().lower();name=input('Nom : ').strip();pwd=getpass.getpass('Mot de passe (12 caractères minimum) : ')
  if len(pwd)<12:raise SystemExit('Mot de passe trop court.')
  with connect() as c:c.execute('INSERT INTO users VALUES(?,?,?,?,?,1)',(secrets.token_hex(12),name,email,'ADMIN',hash_password(pwd)))
  print('Administrateur créé.')
 else:
  print('AMP Appro API : '+args.host+':'+str(args.port)+' — placer derrière HTTPS',flush=True);ThreadingHTTPServer((args.host,args.port),Handler).serve_forever()
