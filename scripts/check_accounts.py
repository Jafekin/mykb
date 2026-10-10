"""Integration check using temporary accounts; does not modify source documents."""
import http.cookiejar,json,secrets,urllib.request,urllib.error,os
from pathlib import Path
BASE=os.environ.get('SITE_URL','http://127.0.0.1:4173')
def client():return urllib.request.build_opener(urllib.request.ProxyHandler({}),urllib.request.HTTPCookieProcessor(http.cookiejar.CookieJar()))
def call(opener,path,body=None,method=None):
 request=urllib.request.Request(BASE+path,data=None if body is None else json.dumps(body).encode(),headers={} if body is None else {'Content-Type':'application/json'},method=method)
 try:
  with opener.open(request,timeout=20) as response:return response.status,json.loads(response.read()) if method!='HEAD' else None
 except urllib.error.HTTPError as error:return error.code,json.loads(error.read()) if method!='HEAD' else None
admin=client();guest=client();anon=client()
password=(Path(__file__).resolve().parent.parent/'private/admin-initial-password.txt').read_text().split('初始密码：')[1].splitlines()[0]
assert call(anon,'/data/index.json')[0]==401
assert call(anon,'/api/state')[0]==401
assert call(anon,'/data/index.json',method='HEAD')[0]==401
assert call(admin,'/api/auth/login',{'username':'admin','password':password})[0]==200
index=call(admin,'/data/index.json')[1];allowed=next(item for item in index['items'] if item['section']=='notes');key=allowed['section']+'::'+allowed['category'];hidden=next(item for item in index['items'] if item['section']+'::'+item['category']!=key)
username='check_'+secrets.token_hex(4);pw=secrets.token_urlsafe(16)
assert call(admin,'/api/admin/users',{'action':'create','username':username,'password':pw,'permissions':{'visible':[key]}})[0]==200
user=next(user for user in call(admin,'/api/admin/users')[1]['users'] if user['username']==username)
try:
 assert call(guest,'/api/auth/login',{'username':username,'password':pw})[0]==200
 filtered=call(guest,'/data/index.json')[1]
 assert filtered['items'] and all(item['section']+'::'+item['category']==key for item in filtered['items'])
 for path in ['/data/articles/'+hidden['id']+'.json','/api/articles/'+hidden['id'],'/data/%61rticles/'+hidden['id']+'.json']:
  assert call(guest,path)[0]==403,path
 assert call(guest,'/api/admin/users')[0]==403
 assert call(guest,'/api/index/rebuild',{})[0]==403
 assert call(guest,'/api/articles/'+allowed['id'],{'body':'must not write'})[0]==403
 assert call(guest,'/api/articles/'+allowed['id']+'/delete',{})[0]==403
 assert call(guest,'/api/articles',{'section':'notes','category':allowed['category'],'title':'must not create','body':'x'})[0]==403
 assert call(guest,'/api/state',{'key':'saved','value':{allowed['id']:True}})[0]==200
 other=client();assert call(other,'/api/auth/login',{'username':username,'password':pw})[0]==200
 assert call(other,'/api/state')[1]['saved'][allowed['id']] is True
 assert call(admin,'/api/state')[1].get('saved',{}).get(allowed['id']) is not True
 assert call(guest,'/api/admin/users',{'action':'delete','id':1})[0]==403
 assert call(guest,'/api/state',{'key':'saved','value':{},'user_id':1})[0]==200
 assert call(admin,'/api/admin/users',{'action':'delete','id':user['id']})[0]==200
 assert call(other,'/data/index.json')[0]==401
 print('PASS: login required, category filtering, direct file and HEAD protection, edit/create/delete/admin denial, private persistent favorites, session revocation')
finally:
 call(admin,'/api/admin/users',{'action':'delete','id':user['id']})
