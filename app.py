import os, sqlite3
from datetime import date, timedelta
from decimal import Decimal, ROUND_HALF_UP
from flask import Flask, request, jsonify, render_template_string

app=Flask(__name__)
DB=os.environ.get('DB_PATH', os.path.join(os.path.dirname(__file__),'delivery.db'))

def m(x): return float(Decimal(str(x or 0)).quantize(Decimal('0.01'), rounding=ROUND_HALF_UP))
def db():
    x=sqlite3.connect(DB); x.row_factory=sqlite3.Row; x.execute('PRAGMA foreign_keys=ON'); return x

def init():
    x=db(); x.executescript('''
    CREATE TABLE IF NOT EXISTS customers(id INTEGER PRIMARY KEY,name TEXT NOT NULL,address TEXT DEFAULT '',phone TEXT DEFAULT '',delivery_charge REAL NOT NULL DEFAULT 0,payment_cycle TEXT NOT NULL DEFAULT 'monthly',cycle_start TEXT NOT NULL,active INTEGER NOT NULL DEFAULT 1,created_at TEXT DEFAULT CURRENT_TIMESTAMP);
    CREATE TABLE IF NOT EXISTS papers(id INTEGER PRIMARY KEY,name TEXT UNIQUE NOT NULL,current_price REAL NOT NULL DEFAULT 0,active INTEGER NOT NULL DEFAULT 1);
    CREATE TABLE IF NOT EXISTS customer_papers(customer_id INTEGER,paper_id INTEGER,active INTEGER DEFAULT 1,PRIMARY KEY(customer_id,paper_id),FOREIGN KEY(customer_id) REFERENCES customers(id) ON DELETE CASCADE,FOREIGN KEY(paper_id) REFERENCES papers(id) ON DELETE CASCADE);
    CREATE TABLE IF NOT EXISTS deliveries(id INTEGER PRIMARY KEY,customer_id INTEGER NOT NULL,delivery_date TEXT NOT NULL,paper_total REAL NOT NULL,delivery_charge REAL NOT NULL,total REAL NOT NULL,created_at TEXT DEFAULT CURRENT_TIMESTAMP,UNIQUE(customer_id,delivery_date),FOREIGN KEY(customer_id) REFERENCES customers(id) ON DELETE CASCADE);
    CREATE TABLE IF NOT EXISTS delivery_items(id INTEGER PRIMARY KEY,delivery_id INTEGER,paper_id INTEGER,paper_name TEXT,unit_price REAL,FOREIGN KEY(delivery_id) REFERENCES deliveries(id) ON DELETE CASCADE);
    CREATE TABLE IF NOT EXISTS payments(id INTEGER PRIMARY KEY,customer_id INTEGER,payment_date TEXT NOT NULL,amount REAL NOT NULL,method TEXT NOT NULL,notes TEXT DEFAULT '',FOREIGN KEY(customer_id) REFERENCES customers(id) ON DELETE CASCADE);
    CREATE TABLE IF NOT EXISTS coupons(id INTEGER PRIMARY KEY,customer_id INTEGER,value REAL NOT NULL,remaining REAL NOT NULL,issued_date TEXT NOT NULL,expiry_date TEXT,active INTEGER DEFAULT 1,FOREIGN KEY(customer_id) REFERENCES customers(id) ON DELETE CASCADE);
    '''); x.commit(); x.close()

def balance(x,cid):
    d=x.execute('SELECT COALESCE(SUM(total),0) v FROM deliveries WHERE customer_id=?',(cid,)).fetchone()['v']
    p=x.execute('SELECT COALESCE(SUM(amount),0) v FROM payments WHERE customer_id=?',(cid,)).fetchone()['v']
    return m(d-p)
def cycle_days(c): return {'daily':1,'weekly':7,'2weekly':14,'monthly':30,'2monthly':60,'quarterly':90}.get(c,30)
def next_due(c):
    s=date.fromisoformat(c['cycle_start']); n=cycle_days(c['payment_cycle']); today=date.today()
    while s+timedelta(days=n)<=today:s+=timedelta(days=n)
    return s+timedelta(days=n)

@app.before_request
def boot(): init()

HTML='''<!doctype html><html><head><meta name="viewport" content="width=device-width,initial-scale=1"><title>Newspaper Delivery V5</title><style>
*{box-sizing:border-box}body{font-family:Arial,sans-serif;margin:0;background:#f3f5f7;color:#17202a}header{background:#17202a;color:#fff;padding:22px 4%;display:flex;justify-content:space-between;align-items:center;gap:20px}h1{margin:0 0 5px}header p{margin:0;color:#cbd5e1}button{padding:9px 12px;border:1px solid #cbd5e1;border-radius:7px;background:#fff;cursor:pointer}.primary{background:#0f766e;color:#fff;border:0}.hero{font-size:16px;padding:14px 18px}.stats{display:grid;grid-template-columns:repeat(4,1fr);gap:14px;padding:18px 4%}.card,.panel{background:#fff;border-radius:12px;padding:16px;box-shadow:0 2px 8px #0001}.stat b,.stat span{display:block}.stat span{font-size:25px;font-weight:bold;margin-top:8px}.grid{display:grid;grid-template-columns:2fr 1fr;gap:18px;padding:0 4% 30px}.toolbar{display:flex;gap:8px;margin-bottom:12px}table{width:100%;border-collapse:collapse}th,td{padding:9px;border-bottom:1px solid #e5e7eb;text-align:left;vertical-align:top}input,select{padding:9px;border:1px solid #cbd5e1;border-radius:7px}form{display:flex;flex-wrap:wrap;gap:8px;margin:8px 0 16px}form label{display:flex;flex-direction:column;gap:4px;min-width:170px}.modal{position:fixed;inset:0;background:#0008;display:flex;align-items:center;justify-content:center;padding:18px}.hidden{display:none}.box{background:#fff;border-radius:14px;max-width:950px;width:100%;max-height:92vh;overflow:auto;padding:22px;position:relative}.close{position:absolute;right:10px;top:8px;border:0;font-size:24px}.checks label{display:inline-block;margin:6px 12px 6px 0}.account{display:grid;grid-template-columns:repeat(3,1fr);gap:10px}.account .card strong{display:block;font-size:23px;margin-top:5px}.muted{color:#64748b}@media(max-width:850px){header{flex-direction:column;align-items:stretch}.grid{grid-template-columns:1fr}.stats{grid-template-columns:repeat(2,1fr)}}@media(max-width:520px){.stats{grid-template-columns:1fr}.account{grid-template-columns:1fr}}
</style></head><body>
<header><div><h1>Newspaper Delivery V5</h1><p>Deliveries • Payments • Customer ledger • Collections</p></div><button class="primary hero" onclick="goods()">Goods Received — All Customers</button></header>
<div class="stats"><div class="card stat"><b>Customers</b><span>{{customers|length}}</span></div><div class="card stat"><b>Delivered today</b><span>{{today_count}}</span></div><div class="card stat"><b>Today's charges</b><span>£{{'%.2f'|format(today_total)}}</span></div><div class="card stat"><b>Total outstanding</b><span>£{{'%.2f'|format(outstanding)}}</span></div></div>
<div class="grid"><section class="panel"><h2>Customers</h2><div class="toolbar"><button onclick="customerForm()">+ Add customer</button><button onclick="collections()">Collections / Due</button></div><table><tr><th>Customer</th><th>Papers</th><th>Cycle</th><th>Balance</th><th>Advance</th><th></th></tr>{% for c in customers %}<tr><td><b>{{c.name}}</b><br><small>{{c.phone}}</small></td><td>{{c.papers or '—'}}</td><td>{{c.cycle}}</td><td>£{{'%.2f'|format(c.balance)}}<br><small>Due {{c.next_due}}</small></td><td>£{{'%.2f'|format(c.advance)}}</td><td><button onclick="account({{c.id}})">Account</button> <button onclick="editCustomer({{c.id}})">Edit</button></td></tr>{% endfor %}</table></section>
<section class="panel"><h2>Papers & Prices</h2><form onsubmit="addPaper(event)"><input id="pn" placeholder="Paper name" required><input id="pp" type="number" min="0" step="0.01" placeholder="£ price" required><button>Add</button></form><table><tr><th>Paper</th><th>Price</th><th></th></tr>{% for p in papers %}<tr><td>{{p.name}}</td><td>£{{'%.2f'|format(p.current_price)}}</td><td><button onclick='price({{p.id}},{{p.name|tojson}},{{p.current_price}})'>Change</button></td></tr>{% endfor %}</table><p class="muted">Price changes affect future deliveries. Historical delivery items keep their charged price.</p></section></div>
<div id="modal" class="modal hidden"><div class="box"><button class="close" onclick="closeM()">×</button><div id="body"></div></div></div>
<script>
const papers={{papers|tojson}}; const today='{{today}}';
function closeM(){modal.classList.add('hidden')} function show(h){body.innerHTML=h;modal.classList.remove('hidden')}
function cycles(v='monthly'){return `<select id="cy"><option value="daily" ${v==='daily'?'selected':''}>Daily</option><option value="weekly" ${v==='weekly'?'selected':''}>Weekly</option><option value="2weekly" ${v==='2weekly'?'selected':''}>Every 2 weeks</option><option value="monthly" ${v==='monthly'?'selected':''}>Monthly</option><option value="2monthly" ${v==='2monthly'?'selected':''}>Every 2 months</option><option value="quarterly" ${v==='quarterly'?'selected':''}>Quarterly</option></select>`}
function checks(sel=[]){return papers.map(p=>`<label><input type="checkbox" name="p" value="${p.id}" ${sel.includes(p.id)?'checked':''}> ${p.name} (£${Number(p.current_price).toFixed(2)})</label>`).join('')}
function customerForm(c=null,sel=[]){show(`<h2>${c?'Edit':'Add'} customer</h2><form onsubmit="saveC(event,${c?c.id:'null'})"><label>Name<input id="cn" required value="${c?.name||''}"></label><label>Address<input id="ca" value="${c?.address||''}"></label><label>Phone<input id="cp" value="${c?.phone||''}"></label><label>Delivery charge<input id="cc" type="number" min="0" step="0.01" value="${c?.delivery_charge??0}"></label><label>Payment cycle${cycles(c?.payment_cycle||'monthly')}</label><label>Cycle start<input id="cs" type="date" value="${c?.cycle_start||today}"></label><div class="checks"><b>Papers</b><br>${checks(sel)}</div><button class="primary">${c?'Save changes':'Add customer'}</button></form>`)}
async function saveC(e,id){e.preventDefault();let d={name:cn.value,address:ca.value,phone:cp.value,delivery_charge:cc.value,payment_cycle:cy.value,cycle_start:cs.value,paper_ids:[...document.querySelectorAll('input[name=p]:checked')].map(x=>+x.value)};let r=await fetch(id?'/api/customers/'+id:'/api/customers',{method:id?'PUT':'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify(d)});if(r.ok)location.reload();else alert(await r.text())}
async function editCustomer(id){let x=await (await fetch('/api/customers/'+id)).json();customerForm(x.customer,x.papers.map(p=>p.id))}
async function account(id){let x=await (await fetch('/api/customers/'+id)).json(),c=x.customer;show(`<h2>${c.name} — Account</h2><div class="account"><div class="card"><b>Outstanding</b><strong>£${c.balance.toFixed(2)}</strong></div><div class="card"><b>Advance</b><strong>£${c.advance.toFixed(2)}</strong></div><div class="card"><b>Next due</b><strong>${c.next_due}</strong></div></div><h3>Record payment</h3><form onsubmit="pay(event,${id})"><input id="pa" type="number" min="0.01" step="0.01" placeholder="Amount" required><select id="pm"><option>cash</option><option>bank transfer</option><option>card</option><option>cheque</option><option>other</option></select><input id="pnote" placeholder="Notes"><button class="primary">Save payment</button></form><h3>Issue coupon</h3><form onsubmit="coupon(event,${id})"><input id="cv" type="number" min="0.01" step="0.01" placeholder="Coupon value" required><input id="ce" type="date"><button>Save coupon</button></form><h3>Ledger</h3><table><tr><th>Date</th><th>Type</th><th>Amount</th><th>Details</th></tr>${x.deliveries.map(d=>`<tr><td>${d.delivery_date}</td><td>Charge</td><td>£${d.total.toFixed(2)}</td><td>Paper £${d.paper_total.toFixed(2)} + delivery £${d.delivery_charge.toFixed(2)}</td></tr>`).join('')}${x.payments.map(p=>`<tr><td>${p.payment_date}</td><td>Payment</td><td>-£${p.amount.toFixed(2)}</td><td>${p.method} ${p.notes||''}</td></tr>`).join('')}</table>`)}
async function pay(e,id){e.preventDefault();let r=await fetch('/api/payments',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({customer_id:id,amount:pa.value,method:pm.value,notes:pnote.value})});if(r.ok)account(id);else alert(await r.text())}
async function coupon(e,id){e.preventDefault();let r=await fetch('/api/coupons',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({customer_id:id,value:cv.value,expiry_date:ce.value||null})});if(r.ok)account(id);else alert(await r.text())}
async function goods(){if(!confirm('Process Goods Received for ALL customers today? Already processed customers will be skipped.'))return;let x=await (await fetch('/api/goods',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({date:today})})).json();alert(`Processed ${x.processed}; skipped ${x.skipped}; charges £${x.total.toFixed(2)}`);location.reload()}
async function addPaper(e){e.preventDefault();let r=await fetch('/api/papers',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({name:pn.value,price:pp.value})});if(r.ok)location.reload();else alert(await r.text())}
async function price(id,n,p){let v=prompt('New price for '+n,p);if(v===null)return;let r=await fetch('/api/papers/'+id,{method:'PUT',headers:{'Content-Type':'application/json'},body:JSON.stringify({name:n,price:v})});if(r.ok)location.reload();else alert(await r.text())}
async function collections(){let x=await (await fetch('/api/collections')).json();show('<h2>Collections / Due</h2><table><tr><th>Customer</th><th>Cycle</th><th>Next due</th><th>Due</th><th>Advance</th></tr>'+x.map(c=>`<tr><td><a href="#" onclick="account(${c.id});return false">${c.name}</a></td><td>${c.cycle}</td><td>${c.next_due}</td><td>£${c.due.toFixed(2)}</td><td>£${c.advance.toFixed(2)}</td></tr>`).join('')+'</table>')}
</script></body></html>'''

@app.route('/')
def home():
    x=db(); cs=x.execute("SELECT c.*,GROUP_CONCAT(p.name,', ') papers FROM customers c LEFT JOIN customer_papers cp ON cp.customer_id=c.id AND cp.active=1 LEFT JOIN papers p ON p.id=cp.paper_id WHERE c.active=1 GROUP BY c.id ORDER BY c.name").fetchall(); ps=x.execute('SELECT * FROM papers WHERE active=1 ORDER BY name').fetchall(); td=date.today().isoformat(); tc=x.execute('SELECT COUNT(*) n FROM deliveries WHERE delivery_date=?',(td,)).fetchone()['n']; tt=x.execute('SELECT COALESCE(SUM(total),0) n FROM deliveries WHERE delivery_date=?',(td,)).fetchone()['n']; out=0
    rows=[]
    for c in cs:
        b=balance(x,c['id']); out+=max(0,b); rows.append(dict(c,balance=max(0,b),advance=max(0,-b),next_due=next_due(c).isoformat(),cycle={'daily':'Daily','weekly':'Weekly','2weekly':'Every 2 weeks','monthly':'Monthly','2monthly':'Every 2 months','quarterly':'Quarterly'}.get(c['payment_cycle'],c['payment_cycle'])))
    x.close(); return render_template_string(HTML,customers=rows,papers=[dict(p) for p in ps],today=td,today_count=tc,today_total=m(tt),outstanding=m(out))

@app.post('/api/customers')
def addc():
    d=request.json; x=db(); cur=x.execute('INSERT INTO customers(name,address,phone,delivery_charge,payment_cycle,cycle_start) VALUES(?,?,?,?,?,?)',(d['name'],d.get('address',''),d.get('phone',''),m(d.get('delivery_charge',0)),d.get('payment_cycle','monthly'),d.get('cycle_start',date.today().isoformat()))); cid=cur.lastrowid
    for p in d.get('paper_ids',[]): x.execute('INSERT OR IGNORE INTO customer_papers(customer_id,paper_id) VALUES(?,?)',(cid,p))
    x.commit();x.close();return jsonify(ok=True,id=cid)
@app.get('/api/customers/<int:cid>')
def getc(cid):
    x=db(); c=x.execute('SELECT * FROM customers WHERE id=?',(cid,)).fetchone();
    if not c:return jsonify(error='Not found'),404
    r={'customer':dict(c),'papers':[dict(a) for a in x.execute('SELECT p.* FROM customer_papers cp JOIN papers p ON p.id=cp.paper_id WHERE cp.customer_id=? AND cp.active=1',(cid,)).fetchall()],'deliveries':[dict(a) for a in x.execute('SELECT * FROM deliveries WHERE customer_id=? ORDER BY delivery_date DESC,id DESC',(cid,)).fetchall()],'payments':[dict(a) for a in x.execute('SELECT * FROM payments WHERE customer_id=? ORDER BY payment_date DESC,id DESC',(cid,)).fetchall()]}; b=balance(x,cid); r['customer'].update(balance=max(0,b),advance=max(0,-b),next_due=next_due(c).isoformat());x.close();return jsonify(r)
@app.put('/api/customers/<int:cid>')
def editc(cid):
    d=request.json;x=db();x.execute('UPDATE customers SET name=?,address=?,phone=?,delivery_charge=?,payment_cycle=?,cycle_start=? WHERE id=?',(d['name'],d.get('address',''),d.get('phone',''),m(d.get('delivery_charge',0)),d.get('payment_cycle','monthly'),d.get('cycle_start',date.today().isoformat()),cid));x.execute('DELETE FROM customer_papers WHERE customer_id=?',(cid,));
    for p in d.get('paper_ids',[]):x.execute('INSERT OR IGNORE INTO customer_papers(customer_id,paper_id) VALUES(?,?)',(cid,p))
    x.commit();x.close();return jsonify(ok=True)
@app.post('/api/papers')
def addp():
    d=request.json;x=db();x.execute('INSERT INTO papers(name,current_price) VALUES(?,?)',(d['name'],m(d['price'])));x.commit();x.close();return jsonify(ok=True)
@app.put('/api/papers/<int:pid>')
def editp(pid):
    d=request.json;x=db();x.execute('UPDATE papers SET name=?,current_price=? WHERE id=?',(d['name'],m(d['price']),pid));x.commit();x.close();return jsonify(ok=True)
@app.post('/api/goods')
def goods():
    d=request.json.get('date',date.today().isoformat());x=db();processed=skipped=total=0
    try:
        x.execute('BEGIN')
        for c in x.execute('SELECT * FROM customers WHERE active=1').fetchall():
            if x.execute('SELECT 1 FROM deliveries WHERE customer_id=? AND delivery_date=?',(c['id'],d)).fetchone():skipped+=1;continue
            items=x.execute('SELECT p.* FROM customer_papers cp JOIN papers p ON p.id=cp.paper_id WHERE cp.customer_id=? AND cp.active=1 AND p.active=1',(c['id'],)).fetchall()
            if not items:skipped+=1;continue
            pt=m(sum(i['current_price'] for i in items)); dc=m(c['delivery_charge']); gt=m(pt+dc); cur=x.execute('INSERT INTO deliveries(customer_id,delivery_date,paper_total,delivery_charge,total) VALUES(?,?,?,?,?)',(c['id'],d,pt,dc,gt));did=cur.lastrowid
            for i in items:x.execute('INSERT INTO delivery_items(delivery_id,paper_id,paper_name,unit_price) VALUES(?,?,?,?)',(did,i['id'],i['name'],m(i['current_price'])))
            processed+=1;total+=gt
        x.commit()
    except: x.rollback();raise
    x.close();return jsonify(ok=True,processed=processed,skipped=skipped,total=m(total))
@app.post('/api/payments')
def pay():
    d=request.json; amt=m(d['amount']);
    if amt<=0:return jsonify(error='Amount must be positive'),400
    x=db();x.execute('INSERT INTO payments(customer_id,payment_date,amount,method,notes) VALUES(?,?,?,?,?)',(int(d['customer_id']),d.get('payment_date',date.today().isoformat()),amt,d.get('method','cash'),d.get('notes','')));x.commit();b=balance(x,int(d['customer_id']));x.close();return jsonify(ok=True,balance=max(0,b),advance=max(0,-b))
@app.post('/api/coupons')
def coupon():
    d=request.json;v=m(d['value']);x=db();x.execute('INSERT INTO coupons(customer_id,value,remaining,issued_date,expiry_date) VALUES(?,?,?,?,?)',(d['customer_id'],v,v,date.today().isoformat(),d.get('expiry_date')));x.commit();x.close();return jsonify(ok=True)
@app.get('/api/collections')
def coll():
    x=db();r=[]
    for c in x.execute('SELECT * FROM customers WHERE active=1 ORDER BY name').fetchall():
        b=balance(x,c['id']);r.append({'id':c['id'],'name':c['name'],'cycle':c['payment_cycle'],'next_due':next_due(c).isoformat(),'due':max(0,b),'advance':max(0,-b)})
    x.close();return jsonify(r)
@app.get('/health')
def health():return 'ok',200

if __name__=='__main__':init();app.run(host='0.0.0.0',port=int(os.environ.get('PORT',5000)))
