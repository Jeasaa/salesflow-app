from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
from typing import Optional
import libsql_client
import hashlib
import jwt
from datetime import datetime, timedelta

TURSO_URL = "https://app-jeasaa.aws-eu-west-1.turso.io"
TURSO_TOKEN = "eyJhbGciOiJFZERTQSIsInR5cCI6IkpXVCJ9.eyJhIjoicnciLCJpYXQiOjE3NzMwNjM0ODksImlkIjoiMDE5Y2QyY2UtZmUwMS03YjYyLTk4MjEtN2M1NjcxNjBiMDBmIiwicmlkIjoiMmVlNTYwNTYtMmJkZC00NmMzLTllZmEtODY3Yjc1MGI5ZmMyIn0.W5_YArM9r3v7hd8fy65ZRf5ya2xrPhmmmref4NdCUmhR8j6XytZ2_g73yALIJC8C5h9n-1BzBkix9X3FQ_yOAA"
JWT_SECRET = "salesflow-secret-key-2025"
TECHNIQUES = ["FTID", "LIT", "RTS", "DNA", "EB"]

app = FastAPI(title="SalesFlow API")
app.add_middleware(CORSMiddleware, allow_origins=["*"], allow_credentials=True, allow_methods=["*"], allow_headers=["*"])

_client = libsql_client.create_client_sync(url=TURSO_URL, auth_token=TURSO_TOKEN)
def run(sql, params=None): return _client.execute(sql, params or [])
def query(sql, params=None):
    rs = _client.execute(sql, params or [])
    if not rs.columns: return []
    return [dict(zip(rs.columns, row)) for row in rs.rows]
def query_one(sql, params=None):
    rows = query(sql, params); return rows[0] if rows else None
def query_val(sql, params=None):
    rs = _client.execute(sql, params or []); return rs.rows[0][0] if rs.rows else None
def now(): return datetime.now().strftime("%Y-%m-%d %H:%M:%S")

def init_db():
    tables = [
        "CREATE TABLE IF NOT EXISTS users (id INTEGER PRIMARY KEY AUTOINCREMENT,username TEXT NOT NULL UNIQUE,password_hash TEXT NOT NULL,role TEXT DEFAULT 'admin',created_at TEXT)",
        "CREATE TABLE IF NOT EXISTS acheteurs (id INTEGER PRIMARY KEY AUTOINCREMENT,nom TEXT NOT NULL UNIQUE,parrain TEXT DEFAULT 'Aucun',commission_parrain REAL DEFAULT 0.0,identifiant_boutique TEXT DEFAULT '',mdp_boutique TEXT DEFAULT '',date_creation TEXT)",
        "CREATE TABLE IF NOT EXISTS commandes (id INTEGER PRIMARY KEY AUTOINCREMENT,date TEXT,acheteur_id INTEGER NOT NULL,boutique TEXT NOT NULL,montant_total REAL NOT NULL,commission_mode TEXT DEFAULT 'pct',commission_vendeur_pct REAL DEFAULT 0.0,commission_vendeur_eur REAL NOT NULL,commission_parrain_eur REAL DEFAULT 0.0,notes TEXT DEFAULT '',statut TEXT DEFAULT 'En cours',paiement TEXT DEFAULT 'Non payée',technique TEXT DEFAULT '',cout_total REAL DEFAULT 0.0)",
        "CREATE TABLE IF NOT EXISTS notes_acheteurs (id INTEGER PRIMARY KEY AUTOINCREMENT,acheteur_id INTEGER NOT NULL,contenu TEXT NOT NULL,date_creation TEXT,auteur TEXT DEFAULT 'admin')",
        "CREATE TABLE IF NOT EXISTS objectifs (id INTEGER PRIMARY KEY AUTOINCREMENT,mois TEXT NOT NULL UNIQUE,objectif_ca REAL DEFAULT 0.0,objectif_commandes INTEGER DEFAULT 0)",
        "CREATE TABLE IF NOT EXISTS demandes (id INTEGER PRIMARY KEY AUTOINCREMENT,date_soumission TEXT,nom_client TEXT NOT NULL,boutique TEXT NOT NULL,montant REAL NOT NULL,identifiant_boutique TEXT DEFAULT '',mdp_boutique TEXT DEFAULT '',notes_client TEXT DEFAULT '',statut TEXT DEFAULT 'En attente')",
        "CREATE TABLE IF NOT EXISTS couts_techniques (id INTEGER PRIMARY KEY AUTOINCREMENT,nom TEXT NOT NULL UNIQUE,prix REAL NOT NULL DEFAULT 0.0)",
        "CREATE TABLE IF NOT EXISTS parrain_transactions (id INTEGER PRIMARY KEY AUTOINCREMENT,parrain_nom TEXT NOT NULL,montant REAL NOT NULL,description TEXT DEFAULT '',date TEXT,type TEXT DEFAULT 'prime')",
        "CREATE TABLE IF NOT EXISTS settings (key TEXT PRIMARY KEY,value TEXT)",
        "CREATE TABLE IF NOT EXISTS couts_mensuels (id INTEGER PRIMARY KEY AUTOINCREMENT,nom TEXT NOT NULL,montant REAL NOT NULL,mois TEXT NOT NULL,date_ajout TEXT)",
        "CREATE TABLE IF NOT EXISTS comptes_catalogue (id INTEGER PRIMARY KEY AUTOINCREMENT,nom TEXT NOT NULL UNIQUE,prix_achat REAL NOT NULL DEFAULT 0,prix_revente REAL NOT NULL DEFAULT 0)",
        "CREATE TABLE IF NOT EXISTS commande_comptes (id INTEGER PRIMARY KEY AUTOINCREMENT,commande_id INTEGER NOT NULL,compte_nom TEXT NOT NULL,prix_achat REAL NOT NULL,prix_revente REAL NOT NULL,paiement TEXT DEFAULT 'Non payé')",
    ]
    for t in tables:
        try: run(t)
        except: pass
    try: run("ALTER TABLE commandes ADD COLUMN paiement TEXT DEFAULT 'Non payée'")
    except: pass
    try: run("ALTER TABLE acheteurs ADD COLUMN prenom TEXT DEFAULT ''")
    except: pass
    try: run("ALTER TABLE commandes ADD COLUMN identifiant_boutique TEXT DEFAULT ''")
    except: pass
    try: run("ALTER TABLE commandes ADD COLUMN mdp_boutique TEXT DEFAULT ''")
    except: pass
    if query_val("SELECT COUNT(*) FROM users") == 0:
        run("INSERT INTO users (username,password_hash,role,created_at) VALUES (?,?,?,?)",
            ["admin", hashlib.sha256("admin".encode()).hexdigest(), "admin", now()])
    # Default theme
    try: run("INSERT INTO settings (key,value) VALUES ('theme','dark')")
    except: pass
init_db()

# ━━━ AUTH ━━━
def hash_pw(pw): return hashlib.sha256(pw.encode()).hexdigest()
def create_token(u): return jwt.encode({"sub":u,"exp":datetime.utcnow()+timedelta(days=30)},JWT_SECRET,algorithm="HS256")

class LoginReq(BaseModel):
    username: str; password: str
@app.post("/api/login")
def login(req: LoginReq):
    user = query_one("SELECT * FROM users WHERE username=? AND password_hash=?",[req.username,hash_pw(req.password)])
    if not user: raise HTTPException(401,"Identifiants incorrects")
    return {"token":create_token(req.username),"username":req.username}

class ChangePwReq(BaseModel):
    old_password: str; new_password: str; username: str
@app.post("/api/change-password")
def change_password(req: ChangePwReq):
    user = query_one("SELECT * FROM users WHERE username=? AND password_hash=?",[req.username,hash_pw(req.old_password)])
    if not user: raise HTTPException(401,"Incorrect")
    run("UPDATE users SET password_hash=? WHERE username=?",[hash_pw(req.new_password),req.username])
    return {"ok":True}

# ━━━ SETTINGS ━━━
@app.get("/api/settings")
def get_settings():
    rows = query("SELECT * FROM settings")
    return {r['key']:r['value'] for r in rows}

class SettingReq(BaseModel):
    key: str; value: str
@app.post("/api/settings")
def set_setting(req: SettingReq):
    if query_val("SELECT key FROM settings WHERE key=?",[req.key]):
        run("UPDATE settings SET value=? WHERE key=?",[req.value,req.key])
    else: run("INSERT INTO settings (key,value) VALUES (?,?)",[req.key,req.value])
    return {"ok":True}

# ━━━ DASHBOARD ━━━
@app.get("/api/dashboard")
def dashboard():
    stats = query_one("""SELECT
        (SELECT COUNT(*) FROM acheteurs) as clients,
        (SELECT COUNT(*) FROM commandes) as commandes,
        (SELECT COUNT(*) FROM commandes WHERE statut='En cours') as nb_en_cours,
        (SELECT COALESCE(SUM(commission_vendeur_eur),0) FROM commandes WHERE statut='En cours') as comm_en_cours,
        (SELECT COALESCE(SUM(cout_total),0) FROM commandes WHERE statut='En cours') as couts_en_cours,
        (SELECT COALESCE(SUM(commission_vendeur_eur),0) FROM commandes WHERE statut='Validée' AND paiement='Non payée') as en_attente_paiement,
        (SELECT COALESCE(SUM(commission_vendeur_eur),0) FROM commandes WHERE paiement='Payée') as comm_payee,
        (SELECT COALESCE(SUM(cout_total),0) FROM commandes WHERE paiement='Payée') as couts_payes,
        (SELECT COALESCE(SUM(cout_total),0) FROM commandes WHERE statut='Fails') as couts_fails,
        (SELECT COUNT(*) FROM commandes WHERE statut='Fails') as nb_fails,
        (SELECT COUNT(*) FROM demandes WHERE statut='En attente') as pending
    """)
    benefice = float(stats['comm_payee']) - float(stats['couts_payes']) - float(stats['couts_fails'])
    comm_en_cours_net = float(stats['comm_en_cours']) - float(stats['couts_en_cours'])
    recent = query("SELECT c.id,c.date,a.nom as acheteur,c.boutique,c.montant_total,c.commission_vendeur_eur,c.technique,c.cout_total,c.statut,c.paiement FROM commandes c JOIN acheteurs a ON c.acheteur_id=a.id ORDER BY c.date DESC LIMIT 10")
    return {
        "clients":stats['clients'],"commandes":stats['commandes'],
        "nb_en_cours":int(stats['nb_en_cours']),
        "comm_en_cours":comm_en_cours_net,
        "en_attente_paiement":float(stats['en_attente_paiement']),
        "benefice":benefice,
        "couts_fails":float(stats['couts_fails']),
        "nb_fails":int(stats['nb_fails']),
        "pending":int(stats['pending']),"recent":recent
    }

# ━━━ COÛTS ━━━
@app.get("/api/couts")
def get_couts(): return query("SELECT * FROM couts_techniques ORDER BY nom")
class CoutReq(BaseModel):
    nom: str; prix: float
@app.post("/api/couts")
def set_cout(req: CoutReq):
    if query_val("SELECT id FROM couts_techniques WHERE nom=?",[req.nom]): run("UPDATE couts_techniques SET prix=? WHERE nom=?",[req.prix,req.nom])
    else: run("INSERT INTO couts_techniques (nom,prix) VALUES (?,?)",[req.nom,req.prix])
    return {"ok":True}
@app.delete("/api/couts/{nom}")
def del_cout(nom: str): run("DELETE FROM couts_techniques WHERE nom=?",[nom]); return {"ok":True}
def get_prix(nom):
    v = query_val("SELECT prix FROM couts_techniques WHERE nom=?",[nom]); return float(v) if v else 0.0
def calc_cout(tech):
    if not tech: return 0.0
    total = 0.0
    for part in tech.split(","):
        part = part.strip()
        if not part: continue
        if ':' in part:
            nom, qty = part.rsplit(':', 1)
            try: qty = int(qty)
            except: qty = 1
        else:
            nom, qty = part, 1
        total += get_prix(nom.strip()) * qty
    return total

# ━━━ CLIENTS ━━━
@app.get("/api/acheteurs")
def get_acheteurs(): return query("SELECT * FROM acheteurs ORDER BY nom")

@app.get("/api/acheteurs/{aid}")
def get_acheteur(aid: int):
    ach = query_one("SELECT * FROM acheteurs WHERE id=?",[aid])
    if not ach: raise HTTPException(404)
    cmds = query("SELECT c.id,c.date,c.boutique,c.montant_total,c.commission_vendeur_eur,c.commission_parrain_eur,c.technique,c.cout_total,c.statut,c.paiement,c.notes FROM commandes c WHERE c.acheteur_id=? ORDER BY c.date DESC",[aid])
    notes = query("SELECT * FROM notes_acheteurs WHERE acheteur_id=? ORDER BY date_creation DESC",[aid])
    filleuls_commissions = 0
    if ach['nom']:
        r = query_val("SELECT COALESCE(SUM(c.commission_parrain_eur),0) FROM commandes c JOIN acheteurs a ON c.acheteur_id=a.id WHERE a.parrain=?",[ach['nom']])
        filleuls_commissions = float(r) if r else 0
    return {"acheteur":ach,"commandes":cmds,"notes":notes,"filleuls_commissions":filleuls_commissions}

class AcheteurReq(BaseModel):
    nom: str; prenom: str = ""; parrain: str = "Aucun"; commission_parrain: float = 0.0
@app.post("/api/acheteurs")
def add_acheteur(req: AcheteurReq):
    try:
        run("INSERT INTO acheteurs (nom,prenom,parrain,commission_parrain,date_creation) VALUES (?,?,?,?,?)",
            [req.nom.strip(),req.prenom.strip(),req.parrain.strip() or "Aucun",req.commission_parrain,now()])
        return {"ok":True}
    except: raise HTTPException(400,"Ce nom existe déjà")
@app.put("/api/acheteurs/{aid}")
def mod_acheteur(aid: int, req: AcheteurReq):
    try:
        run("UPDATE acheteurs SET nom=?,prenom=?,parrain=?,commission_parrain=? WHERE id=?",
            [req.nom.strip(),req.prenom.strip(),req.parrain.strip() or "Aucun",req.commission_parrain,aid])
        return {"ok":True}
    except: raise HTTPException(400,"Ce nom existe déjà")
@app.delete("/api/acheteurs/{aid}")
def del_acheteur(aid: int):
    run("DELETE FROM commande_comptes WHERE commande_id IN (SELECT id FROM commandes WHERE acheteur_id=?)",[aid])
    run("DELETE FROM notes_acheteurs WHERE acheteur_id=?",[aid])
    run("DELETE FROM commandes WHERE acheteur_id=?",[aid])
    run("DELETE FROM acheteurs WHERE id=?",[aid])
    return {"ok":True}

# ━━━ NOTES ━━━
class NoteReq(BaseModel):
    contenu: str; auteur: str = "admin"
@app.post("/api/acheteurs/{aid}/notes")
def add_note(aid: int, req: NoteReq):
    run("INSERT INTO notes_acheteurs (acheteur_id,contenu,date_creation,auteur) VALUES (?,?,?,?)",[aid,req.contenu.strip(),now(),req.auteur])
    return {"ok":True}
@app.delete("/api/notes/{nid}")
def del_note(nid: int): run("DELETE FROM notes_acheteurs WHERE id=?",[nid]); return {"ok":True}

# ━━━ COMMANDES ━━━
def get_or_create_ach(nom):
    row = query_val("SELECT id FROM acheteurs WHERE nom=?",[nom.strip()])
    if row: return int(row)
    rs = run("INSERT INTO acheteurs (nom,date_creation) VALUES (?,?)",[nom.strip(),now()])
    return rs.last_insert_rowid

def calc_comm(mont, mode, pct, eur, parrain, cp):
    if mode == "pct": cv=mont*(pct/100); pf=pct
    else: cv=eur; pf=(eur/mont*100) if mont>0 else 0
    cpar = mont*(cp/100) if parrain != "Aucun" and cp > 0 else 0
    return cv, cpar, pf

@app.get("/api/commandes")
def get_commandes():
    return query("""SELECT c.id,c.date,a.nom as acheteur,a.prenom,c.boutique,c.montant_total,
        c.commission_mode,c.commission_vendeur_pct,c.commission_vendeur_eur,
        a.parrain,c.commission_parrain_eur,c.notes,c.statut,c.paiement,
        c.technique,c.cout_total,c.acheteur_id,c.identifiant_boutique,c.mdp_boutique
        FROM commandes c JOIN acheteurs a ON c.acheteur_id=a.id ORDER BY c.date DESC""")

class CommandeReq(BaseModel):
    acheteur_nom: str; boutique: str; montant_total: float
    commission_mode: str = "pct"; commission_pct: float = 0.0; commission_eur: float = 0.0
    notes: str = ""; statut: str = "En cours"; paiement: str = "Non payée"; technique: str = ""
    identifiant_boutique: str = ""; mdp_boutique: str = ""
@app.post("/api/commandes")
def add_commande(req: CommandeReq):
    aid = get_or_create_ach(req.acheteur_nom)
    ach = query_one("SELECT * FROM acheteurs WHERE id=?",[aid])
    cv,cp,pf = calc_comm(req.montant_total, req.commission_mode, req.commission_pct, req.commission_eur, ach['parrain'], ach['commission_parrain'])
    cout = calc_cout(req.technique)
    rs = run("""INSERT INTO commandes (date,acheteur_id,boutique,montant_total,commission_mode,commission_vendeur_pct,commission_vendeur_eur,commission_parrain_eur,notes,statut,paiement,technique,cout_total,identifiant_boutique,mdp_boutique) VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)""",
        [now(),aid,req.boutique.strip(),req.montant_total,req.commission_mode,pf,cv,cp,req.notes.strip(),req.statut,req.paiement,req.technique,cout,req.identifiant_boutique.strip(),req.mdp_boutique.strip()])
    return {"ok":True,"id":rs.last_insert_rowid,"commission":cv,"cout":cout}

class CommandeEditReq(BaseModel):
    boutique: str; montant_total: float
    commission_mode: str = "pct"; commission_pct: float = 0.0; commission_eur: float = 0.0
    notes: str = ""; statut: str = "En cours"; paiement: str = "Non payée"; technique: str = ""
    identifiant_boutique: str = ""; mdp_boutique: str = ""
@app.put("/api/commandes/{cid}")
def mod_commande(cid: int, req: CommandeEditReq):
    aid = query_val("SELECT acheteur_id FROM commandes WHERE id=?",[cid])
    if not aid: raise HTTPException(404)
    ach = query_one("SELECT * FROM acheteurs WHERE id=?",[int(aid)])
    cv,cp,pf = calc_comm(req.montant_total, req.commission_mode, req.commission_pct, req.commission_eur, ach['parrain'], ach['commission_parrain'])
    cout = calc_cout(req.technique)
    run("UPDATE commandes SET boutique=?,montant_total=?,commission_mode=?,commission_vendeur_pct=?,commission_vendeur_eur=?,commission_parrain_eur=?,notes=?,statut=?,paiement=?,technique=?,cout_total=?,identifiant_boutique=?,mdp_boutique=? WHERE id=?",
        [req.boutique.strip(),req.montant_total,req.commission_mode,pf,cv,cp,req.notes.strip(),req.statut,req.paiement,req.technique,cout,req.identifiant_boutique.strip(),req.mdp_boutique.strip(),cid])
    return {"ok":True}

@app.post("/api/commandes/{cid}/toggle-paiement")
def toggle_paiement(cid: int):
    current = query_val("SELECT paiement FROM commandes WHERE id=?",[cid])
    if current is None: raise HTTPException(404)
    new_val = "Payée" if current != "Payée" else "Non payée"
    run("UPDATE commandes SET paiement=? WHERE id=?",[new_val,cid])
    return {"ok":True,"paiement":new_val}

@app.get("/api/commandes/{cid}")
def get_commande_detail(cid: int):
    row = query_one("""SELECT c.id,c.date,a.nom as acheteur,a.prenom,c.boutique,c.montant_total,
        c.commission_mode,c.commission_vendeur_pct,c.commission_vendeur_eur,
        a.parrain,c.commission_parrain_eur,c.notes,c.statut,c.paiement,
        c.technique,c.cout_total,c.acheteur_id,
        c.identifiant_boutique,c.mdp_boutique,a.commission_parrain
        FROM commandes c JOIN acheteurs a ON c.acheteur_id=a.id WHERE c.id=?""", [cid])
    if not row: raise HTTPException(404)
    row['comptes'] = query("SELECT * FROM commande_comptes WHERE commande_id=? ORDER BY id", [cid])
    return row

@app.delete("/api/commandes/{cid}")
def del_commande(cid: int):
    run("DELETE FROM commande_comptes WHERE commande_id=?",[cid])
    run("DELETE FROM commandes WHERE id=?",[cid])
    return {"ok":True}

# ━━━ DEMANDES ━━━
class DemandeReq(BaseModel):
    nom_client: str; boutique: str; montant: float
    identifiant_boutique: str = ""; mdp_boutique: str = ""; notes_client: str = ""
@app.post("/api/demandes/submit")
def submit_demande(req: DemandeReq):
    run("INSERT INTO demandes (date_soumission,nom_client,boutique,montant,identifiant_boutique,mdp_boutique,notes_client,statut) VALUES (?,?,?,?,?,?,?,'En attente')",
        [now(),req.nom_client.strip(),req.boutique.strip(),req.montant,req.identifiant_boutique.strip(),req.mdp_boutique.strip(),req.notes_client.strip()])
    return {"ok":True}
@app.get("/api/demandes")
def get_demandes(statut: Optional[str] = None):
    if statut: return query("SELECT * FROM demandes WHERE statut=? ORDER BY date_soumission DESC",[statut])
    return query("SELECT * FROM demandes ORDER BY date_soumission DESC")

class ValiderReq(BaseModel):
    commission_mode: str = "pct"; commission_pct: float = 0.0; commission_eur: float = 0.0
    technique: str = ""; notes_admin: str = ""; client_id: Optional[int] = None
@app.post("/api/demandes/{did}/valider")
def valider_demande(did: int, req: ValiderReq):
    dem = query_one("SELECT * FROM demandes WHERE id=?",[did])
    if not dem: raise HTTPException(404)
    notes = f"{dem['notes_client']} | {req.notes_admin}".strip(" | ")
    if req.client_id:
        aid = req.client_id
    else:
        aid = get_or_create_ach(dem['nom_client'])
    ach = query_one("SELECT * FROM acheteurs WHERE id=?",[aid])
    cv,cp,pf = calc_comm(dem['montant'], req.commission_mode, req.commission_pct, req.commission_eur, ach['parrain'], ach['commission_parrain'])
    cout = calc_cout(req.technique)
    run("""INSERT INTO commandes (date,acheteur_id,boutique,montant_total,commission_mode,commission_vendeur_pct,commission_vendeur_eur,commission_parrain_eur,notes,statut,paiement,technique,cout_total,identifiant_boutique,mdp_boutique) VALUES (?,?,?,?,?,?,?,?,?,'Validée','Non payée',?,?,?,?)""",
        [now(),aid,dem['boutique'],dem['montant'],req.commission_mode,pf,cv,cp,notes,req.technique,cout,dem['identifiant_boutique'],dem['mdp_boutique']])
    run("UPDATE demandes SET statut='Validée' WHERE id=?",[did])
    return {"ok":True,"commission":cv,"cout":cout}

@app.post("/api/demandes/{did}/rejeter")
def rejeter_demande(did: int): run("UPDATE demandes SET statut='Rejetée' WHERE id=?",[did]); return {"ok":True}

# ━━━ PARRAINS ━━━
@app.get("/api/parrains")
def get_parrains():
    parrains = query("""SELECT a.parrain as parrain, COUNT(DISTINCT a.nom) as filleuls, COUNT(c.id) as commandes,
        COALESCE(SUM(c.montant_total),0) as ca, COALESCE(SUM(c.commission_parrain_eur),0) as comm_auto,
        COALESCE(SUM(CASE WHEN c.paiement='Payée' THEN c.commission_parrain_eur ELSE 0 END),0) as comm_auto_payee
        FROM commandes c JOIN acheteurs a ON c.acheteur_id=a.id WHERE a.parrain != 'Aucun'
        GROUP BY a.parrain ORDER BY comm_auto DESC""")
    # Ajouter les transactions manuelles
    for p in parrains:
        manual = query_val("SELECT COALESCE(SUM(montant),0) FROM parrain_transactions WHERE parrain_nom=?",[p['parrain']])
        p['transactions_manuelles'] = float(manual) if manual else 0
        p['total_du'] = p['comm_auto'] + p['transactions_manuelles']
    return parrains

@app.get("/api/parrains/{nom}/transactions")
def get_parrain_transactions(nom: str):
    auto = query("SELECT c.id,c.date,a.nom as client,c.boutique,c.montant_total,c.commission_parrain_eur as montant,'auto' as type FROM commandes c JOIN acheteurs a ON c.acheteur_id=a.id WHERE a.parrain=? ORDER BY c.date DESC",[nom])
    manual = query("SELECT id,date,description as client,'' as boutique,0 as montant_total,montant,'prime' as type FROM parrain_transactions WHERE parrain_nom=? ORDER BY date DESC",[nom])
    return {"auto":auto,"manual":manual}

class ParrainTransReq(BaseModel):
    parrain_nom: str; montant: float; description: str = ""
@app.post("/api/parrains/transaction")
def add_parrain_transaction(req: ParrainTransReq):
    run("INSERT INTO parrain_transactions (parrain_nom,montant,description,date,type) VALUES (?,?,?,?,'prime')",
        [req.parrain_nom.strip(),req.montant,req.description.strip(),now()])
    return {"ok":True}

@app.delete("/api/parrains/transaction/{tid}")
def del_parrain_transaction(tid: int):
    run("DELETE FROM parrain_transactions WHERE id=?",[tid])
    return {"ok":True}

# ━━━ FINANCES ━━━
@app.get("/api/finances")
def get_finances():
    boutiques = query("""SELECT c.boutique, COUNT(c.id) as commandes, COALESCE(SUM(c.montant_total),0) as ca,
        COALESCE(SUM(c.commission_vendeur_eur),0) as commission, COALESCE(SUM(c.cout_total),0) as couts
        FROM commandes c GROUP BY c.boutique ORDER BY commission DESC""")
    non_payees = query("""SELECT c.id,c.date,a.nom as acheteur,c.boutique,c.montant_total,c.commission_vendeur_eur,c.statut
        FROM commandes c JOIN acheteurs a ON c.acheteur_id=a.id WHERE c.statut='Validée' AND c.paiement='Non payée' ORDER BY c.date DESC""")
    return {"boutiques":boutiques,"non_payees":non_payees}

# ━━━ SEARCH ━━━
@app.get("/api/search")
def search(q: str):
    t = f"%{q}%"
    ach = query("SELECT 'acheteur' as type, id, nom as titre, '' as detail FROM acheteurs WHERE nom LIKE ?",[t])
    cmd = query("SELECT 'commande' as type, c.id, c.boutique as titre, a.nom as detail FROM commandes c JOIN acheteurs a ON c.acheteur_id=a.id WHERE c.boutique LIKE ? OR a.nom LIKE ?",[t,t])
    return ach + cmd

@app.get("/api/techniques")
def get_techniques():
    rows = query("SELECT nom FROM couts_techniques ORDER BY nom")
    return [r['nom'] for r in rows]
    
# ━━━ ANALYTICS ━━━
@app.get("/api/analytics/ca-trend")
def analytics_ca_trend():
    data = query("""
        SELECT 
            strftime('%Y-%m', c.date) as mois,
            COUNT(*) as commandes,
            COALESCE(SUM(c.montant_total), 0) as ca,
            COALESCE(SUM(c.commission_vendeur_eur), 0) as commissions,
            COALESCE(SUM(CASE WHEN c.paiement='Payée' THEN c.commission_vendeur_eur ELSE 0 END), 0) as comm_payee,
            COALESCE(SUM(CASE WHEN c.paiement='Payée' THEN c.cout_total ELSE 0 END), 0) as couts_payes
        FROM commandes c
        WHERE c.date IS NOT NULL
        GROUP BY strftime('%Y-%m', c.date)
        ORDER BY mois DESC
        LIMIT 12
    """)
    return sorted(data, key=lambda x: x['mois'])

@app.get("/api/analytics/top-clients")
def analytics_top_clients():
    clients = query("""
        SELECT a.nom, COUNT(c.id) as commandes, 
            COALESCE(SUM(c.montant_total), 0) as ca,
            COALESCE(SUM(c.commission_vendeur_eur), 0) as commission
        FROM commandes c
        JOIN acheteurs a ON c.acheteur_id = a.id
        GROUP BY a.nom
        ORDER BY ca DESC
        LIMIT 10
    """)
    parrains = query("""
        SELECT a.parrain as nom, COUNT(DISTINCT a.nom) as filleuls,
            COUNT(c.id) as commandes,
            COALESCE(SUM(c.montant_total), 0) as ca,
            COALESCE(SUM(c.commission_parrain_eur), 0) as commission
        FROM commandes c
        JOIN acheteurs a ON c.acheteur_id = a.id
        WHERE a.parrain != 'Aucun'
        GROUP BY a.parrain
        ORDER BY ca DESC
        LIMIT 10
    """)
    return {"clients": clients, "parrains": parrains}

@app.get("/api/analytics/statut")
def analytics_statut():
    return query("""
        SELECT c.statut, c.paiement, COUNT(*) as count,
            COALESCE(SUM(c.montant_total), 0) as ca,
            COALESCE(SUM(c.commission_vendeur_eur), 0) as commission
        FROM commandes c
        GROUP BY c.statut, c.paiement
    """)

@app.get("/api/analytics/commissions-evolution")
def analytics_commissions_evolution():
    data = query("""
        SELECT
            strftime('%Y-%m', date) as mois,
            COALESCE(SUM(CASE WHEN statut='En cours' THEN commission_vendeur_eur ELSE 0 END), 0) as comm_en_cours,
            COALESCE(SUM(CASE WHEN statut='Validée' THEN commission_vendeur_eur ELSE 0 END), 0) as comm_validee,
            COUNT(CASE WHEN statut='En cours' THEN 1 END) as nb_en_cours,
            COUNT(CASE WHEN statut='Validée' THEN 1 END) as nb_validee
        FROM commandes
        WHERE date IS NOT NULL
        GROUP BY strftime('%Y-%m', date)
        ORDER BY mois DESC
        LIMIT 12
    """)
    return sorted(data, key=lambda x: x['mois'])

@app.get("/api/analytics/boutiques")
def analytics_boutiques():
    data = query("""
        SELECT
            boutique,
            COUNT(*) as commandes,
            COALESCE(SUM(montant_total), 0) as ca,
            COALESCE(SUM(commission_vendeur_eur), 0) as commissions,
            COUNT(CASE WHEN statut='Validée' THEN 1 END) as validees,
            COUNT(CASE WHEN statut='En cours' THEN 1 END) as en_cours
        FROM commandes
        WHERE boutique IS NOT NULL AND boutique != ''
        GROUP BY boutique
        ORDER BY commandes DESC
    """)
    total = sum(d['commandes'] for d in data)
    for d in data:
        d['pct'] = round(d['commandes'] / total * 100, 1) if total > 0 else 0
    return data

# ━━━ COÛTS MENSUELS ━━━
@app.get("/api/couts-mensuels")
def get_couts_mensuels(mois: Optional[str] = None):
    if mois: return query("SELECT * FROM couts_mensuels WHERE mois=? ORDER BY nom",[mois])
    return query("SELECT * FROM couts_mensuels ORDER BY mois DESC, nom")
class CoutMensuelReq(BaseModel):
    nom: str; montant: float; mois: str
@app.post("/api/couts-mensuels")
def add_cout_mensuel(req: CoutMensuelReq):
    run("INSERT INTO couts_mensuels (nom,montant,mois,date_ajout) VALUES (?,?,?,?)",[req.nom.strip(),req.montant,req.mois,now()])
    return {"ok":True}
@app.delete("/api/couts-mensuels/{cid}")
def del_cout_mensuel(cid: int):
    run("DELETE FROM couts_mensuels WHERE id=?",[cid]); return {"ok":True}

# ━━━ COMPTES CATALOGUE ━━━
@app.get("/api/comptes-catalogue")
def get_comptes_catalogue():
    return query("SELECT * FROM comptes_catalogue ORDER BY nom")
class CompteCatalogueReq(BaseModel):
    nom: str; prix_achat: float; prix_revente: float
@app.post("/api/comptes-catalogue")
def add_compte_catalogue(req: CompteCatalogueReq):
    if query_val("SELECT id FROM comptes_catalogue WHERE nom=?",[req.nom.strip()]):
        run("UPDATE comptes_catalogue SET prix_achat=?,prix_revente=? WHERE nom=?",[req.prix_achat,req.prix_revente,req.nom.strip()])
    else:
        run("INSERT INTO comptes_catalogue (nom,prix_achat,prix_revente) VALUES (?,?,?)",[req.nom.strip(),req.prix_achat,req.prix_revente])
    return {"ok":True}
@app.delete("/api/comptes-catalogue/{nom}")
def del_compte_catalogue(nom: str):
    run("DELETE FROM comptes_catalogue WHERE nom=?",[nom]); return {"ok":True}

# ━━━ COMMANDE COMPTES ━━━
@app.get("/api/commandes/{cid}/comptes")
def get_commande_comptes(cid: int):
    return query("SELECT * FROM commande_comptes WHERE commande_id=? ORDER BY id",[cid])
@app.post("/api/commandes/{cid}/comptes")
def add_commande_compte(cid: int, req: CompteCatalogueReq):
    run("INSERT INTO commande_comptes (commande_id,compte_nom,prix_achat,prix_revente) VALUES (?,?,?,?)",[cid,req.nom.strip(),req.prix_achat,req.prix_revente])
    return {"ok":True}
@app.post("/api/commande-comptes/{ccid}/toggle-paiement")
def toggle_compte_paiement(ccid: int):
    current = query_val("SELECT paiement FROM commande_comptes WHERE id=?",[ccid])
    if current is None: raise HTTPException(404)
    new_val = "Payé" if current != "Payé" else "Non payé"
    run("UPDATE commande_comptes SET paiement=? WHERE id=?",[new_val,ccid])
    return {"ok":True,"paiement":new_val}
@app.delete("/api/commande-comptes/{ccid}")
def del_commande_compte(ccid: int):
    run("DELETE FROM commande_comptes WHERE id=?",[ccid]); return {"ok":True}

# ━━━ FINANCES MENSUEL ━━━
@app.get("/api/finances/mensuel")
def finances_mensuel():
    mois_data = query("""
        SELECT strftime('%Y-%m', c.date) as mois, COUNT(*) as nb_commandes,
            COALESCE(SUM(c.montant_total),0) as ca,
            COALESCE(SUM(c.commission_vendeur_eur),0) as commissions_total,
            COALESCE(SUM(CASE WHEN c.paiement='Payée' THEN c.commission_vendeur_eur ELSE 0 END),0) as commissions_payees,
            COALESCE(SUM(c.cout_total),0) as couts_techniques,
            COALESCE(SUM(CASE WHEN c.paiement='Payée' THEN c.cout_total ELSE 0 END),0) as couts_techniques_payes
        FROM commandes c WHERE c.date IS NOT NULL
        GROUP BY strftime('%Y-%m', c.date) ORDER BY mois DESC
    """)
    for m in mois_data:
        cm = query_val("SELECT COALESCE(SUM(montant),0) FROM couts_mensuels WHERE mois=?",[m['mois']])
        m['couts_mensuels'] = float(cm) if cm else 0
        comptes = query_one("""
            SELECT COALESCE(SUM(cc.prix_revente-cc.prix_achat),0) as benef_comptes,
                COALESCE(SUM(cc.prix_achat),0) as cout_comptes,
                COUNT(cc.id) as nb_comptes,
                COUNT(CASE WHEN cc.paiement='Payé' THEN 1 END) as nb_comptes_payes,
                COALESCE(SUM(CASE WHEN cc.paiement='Payé' THEN cc.prix_revente-cc.prix_achat ELSE 0 END),0) as benef_comptes_payes
            FROM commande_comptes cc JOIN commandes c ON cc.commande_id=c.id
            WHERE strftime('%Y-%m', c.date)=?
        """,[m['mois']])
        m['benef_comptes'] = float(comptes['benef_comptes']) if comptes else 0
        m['cout_comptes'] = float(comptes['cout_comptes']) if comptes else 0
        m['nb_comptes'] = int(comptes['nb_comptes']) if comptes else 0
        m['nb_comptes_payes'] = int(comptes['nb_comptes_payes']) if comptes else 0
        m['benef_comptes_payes'] = float(comptes['benef_comptes_payes']) if comptes else 0
        m['benefice_net'] = float(m['commissions_payees']) - float(m['couts_techniques_payes']) - m['couts_mensuels'] + m['benef_comptes_payes']
    return mois_data

# ━━━ RESET ━━━
@app.post("/api/reset")
def reset_all():
    for t in ["commande_comptes","commandes","acheteurs","notes_acheteurs","demandes","objectifs","parrain_transactions","couts_mensuels"]: run(f"DELETE FROM {t}")
    return {"ok":True}
