"""Encrypts everything with numbers in docs/ so the public GitHub Pages site is unreadable without the password.

Before 2026-10-17 the password only hid the page: data.js was served in clear text and the unlock value
was the SHA-256 written in index.html. Now:

- the key is PBKDF2-SHA256 (600k iterations, salt kept in data/public_lock.json) of PUBLIC_DASHBOARD_PASSWORD
  from .env (falls back to DASHBOARD_PASSWORD);
- data.js and student_profile_data.js become data.enc / student_profile_data.enc (AES-256-GCM, JSON {iv, ct});
- every other .html in docs (weekly and L24 decks, archives) is replaced by a small lock page that decrypts
  the original in the browser; every .pdf becomes <name>.pdf.html the same way and links are rewritten;
- the browser keeps the derived key (not the password) in localStorage, so one login opens the dashboard
  and the decks on the same device. Changing the password changes the salt and logs every device out.
"""
from __future__ import annotations

import base64
import hashlib
import json
import os
import re
import secrets
from pathlib import Path

from cryptography.hazmat.primitives import hashes
from cryptography.hazmat.primitives.ciphers.aead import AESGCM
from cryptography.hazmat.primitives.kdf.pbkdf2 import PBKDF2HMAC

ROOT = Path(__file__).resolve().parent.parent
LOCK_FILE = ROOT / "data" / "public_lock.json"
ITERATIONS = 600_000
STORAGE_KEY = "presubs_dash_key_v2"


class EncryptionConfigError(RuntimeError):
    pass


def _b64(data: bytes) -> str:
    return base64.b64encode(data).decode("ascii")


def read_password() -> str:
    values: dict[str, str] = {}
    env_file = ROOT / ".env"
    if env_file.exists():
        for line in env_file.read_text(encoding="utf-8").splitlines():
            if "=" in line and not line.lstrip().startswith("#"):
                key, value = line.split("=", 1)
                values[key.strip()] = value.strip().strip('"').strip("'")
    password = (
        os.getenv("PUBLIC_DASHBOARD_PASSWORD")
        or values.get("PUBLIC_DASHBOARD_PASSWORD")
        or os.getenv("DASHBOARD_PASSWORD")
        or values.get("DASHBOARD_PASSWORD")
        or ""
    )
    if len(password) < 10:
        raise EncryptionConfigError(
            "PUBLIC_DASHBOARD_PASSWORD missing or shorter than 10 characters in .env. "
            "The public site is not generated without it."
        )
    return password


def load_key(password: str) -> tuple[bytes, bytes]:
    """Returns (key, salt). The salt is reused while the password stays the same, so devices stay logged in."""
    fingerprint = hashlib.sha256(("presubs-lock:" + password).encode("utf-8")).hexdigest()
    lock = {}
    if LOCK_FILE.exists():
        lock = json.loads(LOCK_FILE.read_text(encoding="utf-8"))
    if lock.get("fingerprint") != fingerprint or lock.get("iterations") != ITERATIONS:
        lock = {"salt": _b64(secrets.token_bytes(16)), "iterations": ITERATIONS, "fingerprint": fingerprint}
        LOCK_FILE.write_text(json.dumps(lock, indent=2), encoding="utf-8")
    salt = base64.b64decode(lock["salt"])
    kdf = PBKDF2HMAC(algorithm=hashes.SHA256(), length=32, salt=salt, iterations=ITERATIONS)
    return kdf.derive(password.encode("utf-8")), salt


def encrypt(key: bytes, data: bytes) -> dict[str, str]:
    iv = secrets.token_bytes(12)
    return {"iv": _b64(iv), "ct": _b64(AESGCM(key).encrypt(iv, data, None))}


# Shared browser code: derive key, keep it, decrypt. Used by the dashboard gate and by every lock page.
BROWSER_CRYPTO = """
var LOCK={salt:"__SALT__",iter:__ITER__,store:"__STORE__"};
function b64(s){var b=atob(s),u=new Uint8Array(b.length);for(var i=0;i<b.length;i++)u[i]=b.charCodeAt(i);return u}
function deriveKey(pw){return crypto.subtle.importKey("raw",new TextEncoder().encode(pw),"PBKDF2",false,["deriveKey"]).then(function(base){
  return crypto.subtle.deriveKey({name:"PBKDF2",salt:b64(LOCK.salt),iterations:LOCK.iter,hash:"SHA-256"},base,{name:"AES-GCM",length:256},true,["decrypt"])})}
function storedKey(){var raw=null;try{raw=JSON.parse(localStorage.getItem(LOCK.store)||"null")}catch(e){}
  if(!raw||raw.salt!==LOCK.salt)return Promise.resolve(null);
  return crypto.subtle.importKey("raw",b64(raw.k),{name:"AES-GCM"},true,["decrypt"])}
function keepKey(key){return crypto.subtle.exportKey("raw",key).then(function(r){var s="",u=new Uint8Array(r);for(var i=0;i<u.length;i++)s+=String.fromCharCode(u[i]);
  try{localStorage.setItem(LOCK.store,JSON.stringify({salt:LOCK.salt,k:btoa(s)}));localStorage.removeItem("presubs_dash_unlock_v1")}catch(e){}})}
function decrypt(key,box){return crypto.subtle.decrypt({name:"AES-GCM",iv:b64(box.iv)},key,b64(box.ct))}
"""

LOCK_FORM = """<div id="dashLockOverlay" style="position:fixed;inset:0;z-index:99999;background:#0c0f1c;display:flex;align-items:center;justify-content:center;font-family:Inter,system-ui,sans-serif">
  <form id="dashLockForm" style="background:#161c30;border:1px solid #2a3350;border-radius:14px;padding:32px 28px;width:min(340px,90vw);box-shadow:0 20px 60px rgba(0,0,0,.4)">
    <div style="font-size:15px;font-weight:800;color:#f5f6fb;margin-bottom:6px">PreSubs Dashboard</div>
    <div style="font-size:13px;color:#b4bbd1;margin-bottom:16px">Digite a senha para acessar.</div>
    <label for="dashLockInput" style="position:absolute;left:-9999px">Senha</label>
    <input id="dashLockInput" type="password" placeholder="Senha" autocomplete="current-password" autofocus style="width:100%;box-sizing:border-box;padding:10px 12px;border-radius:8px;border:1px solid #2a3350;background:#0c0f1c;color:#f5f6fb;font-size:16px;margin-bottom:12px" />
    <button id="dashLockBtn" type="submit" style="width:100%;padding:11px 12px;border-radius:8px;border:none;background:#6a5cff;color:#fff;font-weight:700;font-size:14px;cursor:pointer">Entrar</button>
    <div id="dashLockError" role="alert" style="display:none;margin-top:10px;font-size:13px;color:#ff8a8a">Senha incorreta.</div>
  </form>
</div>"""

# Lock flow shared by the dashboard and the lock pages. onKey(key) must return a promise that rejects on a wrong key.
LOCK_FLOW = """
function runLock(onKey){
  var form=document.getElementById("dashLockForm"),input=document.getElementById("dashLockInput"),
      err=document.getElementById("dashLockError"),btn=document.getElementById("dashLockBtn");
  function open(key,remember){return onKey(key).then(function(){if(remember)keepKey(key);var o=document.getElementById("dashLockOverlay");if(o)o.remove()})}
  form.addEventListener("submit",function(ev){ev.preventDefault();btn.disabled=true;btn.textContent="Abrindo...";err.style.display="none";
    deriveKey(input.value).then(function(key){return open(key,true)}).catch(function(){err.style.display="block";input.value="";input.focus()})
      .then(function(){btn.disabled=false;btn.textContent="Entrar"})});
  storedKey().then(function(key){if(key)return open(key,false)}).catch(function(){try{localStorage.removeItem(LOCK.store)}catch(e){}})
}
"""


def browser_crypto(salt: bytes) -> str:
    return (BROWSER_CRYPTO.replace("__SALT__", _b64(salt)).replace("__ITER__", str(ITERATIONS))
            .replace("__STORE__", STORAGE_KEY)) + LOCK_FLOW


def dashboard_gate(salt: bytes, scripts_before: list[str], script_after: str) -> str:
    """Script for index.html: decrypts the .enc files, runs them in order, then loads dashboard.js."""
    files = json.dumps(scripts_before)
    return f"""<script>
(function(){{
{browser_crypto(salt)}
var FILES={files};
function runScript(text){{return new Promise(function(ok,fail){{var s=document.createElement("script");
  s.src=URL.createObjectURL(new Blob([text],{{type:"text/javascript"}}));s.onload=ok;s.onerror=fail;document.body.appendChild(s)}})}}
var started=false;
runLock(function(key){{
  return Promise.all(FILES.map(function(f){{return fetch(f,{{cache:"no-cache"}}).then(function(r){{return r.json()}})}}))
    .then(function(boxes){{return Promise.all(boxes.map(function(b){{return decrypt(key,b)}}))}})
    .then(function(plain){{if(started)return;started=true;var dec=new TextDecoder();
      return plain.reduce(function(p,buf){{return p.then(function(){{return runScript(dec.decode(buf))}})}},Promise.resolve())
        .then(function(){{var s=document.createElement("script");s.src="{script_after}";document.body.appendChild(s)}})}});
}});
}})();
</script>"""


def lock_page(salt: bytes, box: dict[str, str], kind: str, title: str) -> str:
    """Standalone page that decrypts an HTML deck (kind=html) or a PDF (kind=pdf)."""
    show = (
        'var html=new TextDecoder().decode(buf);document.open();document.write(html);document.close();'
        if kind == "html" else
        'var url=URL.createObjectURL(new Blob([buf],{type:"application/pdf"}));'
        'document.body.innerHTML=\'<iframe title="PDF" src="\'+url+\'" style="position:fixed;inset:0;width:100%;height:100%;border:0"></iframe>\';'
    )
    return f"""<!doctype html>
<html lang="pt-BR"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">
<meta name="robots" content="noindex,nofollow"><title>{title}</title>
<style>html,body{{margin:0;background:#0c0f1c}}</style></head>
<body>
{LOCK_FORM}
<script>
(function(){{
{browser_crypto(salt)}
var BOX={json.dumps(box)};
runLock(function(key){{return decrypt(key,BOX).then(function(buf){{{show}}})}});
}})();
</script>
</body></html>
"""


PDF_HREF = re.compile(r'href="([^"]+?\.pdf)"', re.IGNORECASE)


def encrypt_docs(docs_dir: Path, plain_scripts: dict[str, str]) -> dict[str, int]:
    """plain_scripts: {"data.enc": js_text, ...} written encrypted. Then locks every deck/archive page and PDF."""
    key, salt = load_key(read_password())
    for name, text in plain_scripts.items():
        (docs_dir / name).write_text(json.dumps(encrypt(key, text.encode("utf-8"))), encoding="utf-8")

    pages = pdfs = 0
    for pdf in sorted(docs_dir.rglob("*.pdf")):
        box = encrypt(key, pdf.read_bytes())
        pdf.with_name(pdf.name + ".html").write_text(lock_page(salt, box, "pdf", pdf.stem), encoding="utf-8")
        pdf.unlink()
        pdfs += 1
    for page in sorted(docs_dir.rglob("*.html")):
        if page.parent == docs_dir and page.name == "index.html":
            continue
        if page.name.endswith(".pdf.html"):
            continue
        html = page.read_text(encoding="utf-8")
        html = PDF_HREF.sub(lambda m: f'href="{m.group(1)}.html"', html)
        title = re.search(r"<title>(.*?)</title>", html, re.IGNORECASE | re.DOTALL)
        page.write_text(lock_page(salt, encrypt(key, html.encode("utf-8")), "html",
                                  (title.group(1).strip() if title else "PreSubs")), encoding="utf-8")
        pages += 1
    return {"salt": salt, "pages": pages, "pdfs": pdfs}


def gate_salt() -> bytes:
    return load_key(read_password())[1]
