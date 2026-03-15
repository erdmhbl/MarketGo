from flask import Flask, request, jsonify, render_template_string
import pandas as pd
import io, os, requests, time, json

app = Flask(__name__)

SHEET_ID = "1qNwL82ctBVHhGv3vtrFT1mjHN1KeN9Dt2OkI8Vg5XLM"
ALIS_GID  = "574689991"
_cache = {"df": None, "gecmis": None, "zaman": 0, "gecmis_zaman": 0}
CACHE_SURE = 300

# ── Google Sheets yazma istemcisi ──────────────────────────────
def get_gspread_client():
    import gspread
    from google.oauth2.service_account import Credentials
    creds_json = os.environ.get("GOOGLE_CREDENTIALS", "")
    if creds_json:
        info = json.loads(creds_json)
        scopes = ["https://spreadsheets.google.com/feeds", "https://www.googleapis.com/auth/drive"]
        creds = Credentials.from_service_account_info(info, scopes=scopes)
        return gspread.authorize(creds)
    if os.path.exists("credentials.json"):
        scopes = ["https://spreadsheets.google.com/feeds", "https://www.googleapis.com/auth/drive"]
        creds = Credentials.from_service_account_file("credentials.json", scopes=scopes)
        return gspread.authorize(creds)
    return None

def eksik_sayfasi_al():
    """EKSİK LİSTE sayfasını döner, yoksa oluşturur."""
    try:
        gc = get_gspread_client()
        if not gc:
            return None
        sh = gc.open_by_key(SHEET_ID)
        try:
            ws = sh.worksheet("EKSİK LİSTE")
        except:
            ws = sh.add_worksheet(title="EKSİK LİSTE", rows=500, cols=5)
            ws.append_row(["Ürün Adı", "Alış Fiyatı", "Market", "Eklenme Tarihi", "Durum"])
        return ws
    except Exception as e:
        print(f"Eksik liste sayfa hatası: {e}")
        return None

# ── Türkçe araç fonksiyonları ──────────────────────────────────
def tr_normalize(metin):
    metin = str(metin).replace('İ', 'i').replace('I', 'i').lower()
    for a, b in [('ı','i'),('ç','c'),('ğ','g'),('ö','o'),('ş','s'),('ü','u')]:
        metin = metin.replace(a, b)
    return metin

def tr_aramayi_hazirla(seri, kelime):
    kelime_norm = tr_normalize(kelime)
    return seri.astype(str).apply(tr_normalize).str.contains(kelime_norm, na=False, regex=False)

# ── Veri yükleme ───────────────────────────────────────────────
def sheet_listesi_al():
    import re
    url = f"https://docs.google.com/spreadsheets/d/{SHEET_ID}/edit"
    try:
        r = requests.get(url, timeout=10)
        matches = re.findall(r'"name":"([^"]+)","index":\d+,"sheetId":(\d+)', r.text)
        return {name: gid for name, gid in matches}
    except:
        return {}

def google_sheets_yukle():
    try:
        url = f"https://docs.google.com/spreadsheets/d/{SHEET_ID}/export?format=csv&gid={ALIS_GID}"
        r = requests.get(url, timeout=10)
        if r.status_code == 200 and len(r.content) > 50:
            df = pd.read_csv(io.StringIO(r.content.decode('utf-8')))
            df = df.dropna(how='all')
            df.columns = [c.strip() for c in df.columns]
            print(f"✅ Alış Fiyatları yüklendi: {len(df)} kayıt")
            return df
    except Exception as e:
        print(f"Sheets hatası: {e}")
    if os.path.exists("market_fisi_urunler_2.xlsx"):
        xl = pd.ExcelFile("market_fisi_urunler_2.xlsx")
        for sheet in xl.sheet_names:
            if 'alis' in tr_normalize(sheet) and 'fiyat' in tr_normalize(sheet):
                df = pd.read_excel("market_fisi_urunler_2.xlsx", sheet_name=sheet)
                return df.dropna(how='all')
    return None

def gecmis_yukle():
    try:
        url = f"https://docs.google.com/spreadsheets/d/{SHEET_ID}/export?format=csv&gid={ALIS_GID}"
        r = requests.get(url, timeout=10)
        if r.status_code == 200 and len(r.content) > 50:
            df = pd.read_csv(io.StringIO(r.content.decode('utf-8')))
            return df.dropna(how='all')
    except Exception as e:
        print(f"Geçmiş yükleme hatası: {e}")
    return pd.DataFrame()

def veri_al():
    simdi = time.time()
    if _cache["df"] is None or (simdi - _cache["zaman"]) > CACHE_SURE:
        df = google_sheets_yukle()
        if df is not None:
            _cache["df"] = df
            _cache["zaman"] = simdi
    return _cache["df"]

def gecmis_al():
    simdi = time.time()
    if _cache["gecmis"] is None or (simdi - _cache["gecmis_zaman"]) > CACHE_SURE:
        _cache["gecmis"] = gecmis_yukle()
        _cache["gecmis_zaman"] = simdi
    return _cache["gecmis"]

# ── HTML ───────────────────────────────────────────────────────
HTML = """<!DOCTYPE html>
<html lang="tr">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<title>Market Go — Birim Fiyat Sorgulama</title>
<link rel="icon" href="/static/favicon.ico">
<script src="https://cdnjs.cloudflare.com/ajax/libs/Chart.js/4.4.0/chart.umd.min.js"></script>
<style>
  * { box-sizing: border-box; margin: 0; padding: 0; }
  body { background: #0f3460; font-family: 'Segoe UI', sans-serif; min-height: 100vh; }
  .header { background: #16213e; padding: 16px 24px; display: flex; align-items: center; gap: 16px; box-shadow: 0 2px 12px #0005; }
  .header img { width: 58px; height: 58px; border-radius: 50%; object-fit: cover; }
  .header-text h1 { color: #e94560; font-size: 1.7rem; font-weight: 800; }
  .header-text h2 { color: #FF6600; font-size: 1.7rem; font-weight: 800; }
  .tabs { display: flex; background: #16213e; padding: 0 24px; border-bottom: 2px solid #0f3460; overflow-x: auto; }
  .tab { padding: 14px 22px; cursor: pointer; color: #a8a8b3; font-weight: 700; font-size: 1rem; border-bottom: 3px solid transparent; margin-bottom: -2px; transition: all 0.2s; white-space: nowrap; }
  .tab:hover { color: #eaeaea; }
  .tab.active { color: #e94560; border-bottom-color: #e94560; }
  .sayfa { display: none; padding: 24px 20px; max-width: 960px; margin: 0 auto; }
  .sayfa.active { display: block; }
  .search-row { display: flex; gap: 10px; flex-wrap: wrap; margin-bottom: 10px; }
  .search-row input { flex: 1; min-width: 200px; padding: 12px 18px; font-size: 1.05rem; border-radius: 10px; border: none; background: #1a1a2e; color: #fff; outline: 2px solid transparent; transition: outline 0.2s; }
  .search-row input:focus { outline: 2px solid #e94560; }
  .search-row input::placeholder { color: #666; }
  .btn { padding: 12px 22px; border: none; border-radius: 10px; font-size: 1rem; font-weight: 700; cursor: pointer; transition: all 0.2s; }
  .btn-red    { background: #e94560; color: white; } .btn-red:hover    { background: #c0392b; }
  .btn-purple { background: #533483; color: white; } .btn-purple:hover { background: #3d2568; }
  .btn-green  { background: #27ae60; color: white; } .btn-green:hover  { background: #1e8449; }
  .btn-orange { background: #e67e22; color: white; } .btn-orange:hover { background: #ca6f1e; }
  .btn-wa     { background: #25D366; color: white; } .btn-wa:hover     { background: #1da851; }
  .btn-outline { background: #16213e; color: #2ecc71; border: 1px solid #2ecc71; } .btn-outline:hover { background: #2ecc71; color: #16213e; }
  .btn-sm { padding: 6px 14px; font-size: 0.82rem; border-radius: 8px; }
  .bulunan { color: #2ecc71; font-size: 0.95rem; padding: 6px 4px; font-weight: 600; min-height: 26px; }
  table { width: 100%; border-collapse: collapse; background: #16213e; border-radius: 12px; overflow: hidden; margin-bottom: 20px; }
  thead tr { background: #e94560; }
  thead th { padding: 12px 14px; color: white; font-size: 0.95rem; text-align: left; }
  tbody tr { border-bottom: 1px solid #0f3460; transition: background 0.15s; }
  tbody tr:hover { background: #1f2f52; }
  tbody td { padding: 11px 14px; color: #eaeaea; font-size: 0.93rem; }
  .fiyat { color: #2ecc71; font-weight: 700; font-size: 1rem; white-space: nowrap; }
  .market-badge { background: #533483; color: white; padding: 2px 10px; border-radius: 20px; font-size: 0.78rem; font-weight: 600; }
  .zam-badge { padding: 3px 10px; border-radius: 20px; font-size: 0.82rem; font-weight: 700; }
  .zam-up   { background: #e74c3c33; color: #e74c3c; }
  .zam-down { background: #2ecc7133; color: #2ecc71; }
  .bos { text-align: center; padding: 40px; color: #666; font-size: 1rem; }
  .bilgi { text-align: center; color: #a8a8b3; font-size: 0.8rem; padding: 10px; }
  .filtre-row { display: flex; gap: 10px; flex-wrap: wrap; margin-bottom: 16px; align-items: center; }
  .filtre-row input[type=date], .filtre-row input[type=text] { padding: 10px 14px; border-radius: 10px; border: none; background: #1a1a2e; color: #fff; font-size: 0.95rem; flex: 1; min-width: 140px; }
  .card-row { display: grid; grid-template-columns: repeat(auto-fit, minmax(180px, 1fr)); gap: 14px; margin-bottom: 20px; }
  .card { background: #16213e; border-radius: 12px; padding: 18px; text-align: center; }
  .card .sayi { font-size: 1.8rem; font-weight: 800; color: #e94560; }
  .card .etiket { color: #a8a8b3; font-size: 0.85rem; margin-top: 4px; }
  .bolum { background: #16213e; border-radius: 12px; padding: 20px; margin-bottom: 20px; }
  .bolum h3 { color: #eaeaea; margin-bottom: 14px; font-size: 1rem; }
  /* Eksik Liste */
  .ekle-btn { background: #e67e22; color: white; border: none; border-radius: 8px; padding: 5px 12px; font-size: 0.82rem; font-weight: 700; cursor: pointer; transition: all 0.2s; white-space: nowrap; }
  .ekle-btn:hover { background: #ca6f1e; }
  .ekle-btn.eklendi { background: #27ae60; }
  .eksik-actions { display: flex; gap: 10px; flex-wrap: wrap; margin-bottom: 16px; }
  .durum-badge { padding: 2px 10px; border-radius: 20px; font-size: 0.78rem; font-weight: 600; background: #e94560; color: white; cursor: pointer; }
  .durum-badge.alindi { background: #27ae60; }
  .sil-btn { background: transparent; border: none; color: #e74c3c; cursor: pointer; font-size: 1rem; padding: 2px 6px; }
  .sil-btn:hover { color: #fff; }
  .toast { position: fixed; bottom: 24px; left: 50%; transform: translateX(-50%); background: #27ae60; color: white; padding: 12px 28px; border-radius: 12px; font-weight: 700; font-size: 1rem; z-index: 999; opacity: 0; transition: opacity 0.3s; pointer-events: none; }
  .toast.show { opacity: 1; }
  @media print {
    .header, .tabs, .eksik-actions, .sil-btn, .durum-badge { display: none !important; }
    body { background: white; }
    table { color: black; }
    thead tr { background: #333 !important; }
  }
  @media (max-width: 600px) {
    .header-text h1, .header-text h2 { font-size: 1.2rem; }
    .tab { padding: 12px 12px; font-size: 0.8rem; }
  }
</style>
</head>
<body>
<div class="header">
  <img src="/static/logo.png" alt="Market Go Logo">
  <div class="header-text">
    <h1>Market Go</h1>
    <h2>Birim Fiyat Sorgulama</h2>
  </div>
</div>
<div class="tabs">
  <div class="tab active"  onclick="sekmeAc('arama')">🔍 Fiyat Sorgula</div>
  <div class="tab"         onclick="sekmeAc('gecmis')">📈 Alış Geçmişi</div>
  <div class="tab"         onclick="sekmeAc('eksik')">🛒 Eksik Liste <span id="eksik-badge" style="background:#e94560;color:white;border-radius:20px;padding:1px 8px;font-size:0.75rem;margin-left:4px;display:none">0</span></div>
</div>

<!-- ── ARAMA ── -->
<div class="sayfa active" id="sayfa-arama">
  <div class="search-row">
    <input type="text" id="giris" placeholder="Ürün adı veya barkod girin..." autofocus>
    <button class="btn btn-outline" onclick="yenile()">🔄</button>
    <button class="btn btn-purple" onclick="temizle()">🗑 Temizle</button>
  </div>
  <div class="bulunan" id="bulunan"></div>
  <table>
    <thead><tr><th>Tarih</th><th>Ürün Adı</th><th>Alış Fiyatı</th><th>Market</th><th>🛒</th></tr></thead>
    <tbody id="sonuclar"><tr><td colspan="5" class="bos">Ürün adı veya barkod girerek arama yapın...</td></tr></tbody>
  </table>
  <div class="bilgi" id="bilgi"></div>
</div>

<!-- ── GEÇMİŞ ── -->
<div class="sayfa" id="sayfa-gecmis">
  <div class="filtre-row">
    <input type="date" id="tarih-bas" title="Başlangıç">
    <input type="date" id="tarih-bit" title="Bitiş">
    <input type="text" id="urun-filtre" placeholder="Ürün adı filtrele...">
    <button class="btn btn-red"    onclick="gecmisYukle()">🔍 Filtrele</button>
    <button class="btn btn-purple" onclick="filtreTemizle()">🗑</button>
    <button class="btn btn-green"  onclick="gecmisYenile()">🔄 Yenile</button>
  </div>
  <div class="card-row" id="ozet-kartlar"></div>
  <div class="bolum">
    <h3>🔥 En Çok Fiyat Değişen Ürünler</h3>
    <div id="zam-listesi"><div class="bos">Yükleniyor...</div></div>
  </div>
  <div class="bolum" id="grafik-wrap" style="display:none">
    <h3 id="grafik-baslik">📊 Fiyat Geçmişi</h3>
    <canvas id="fiyatGrafik" height="100"></canvas>
  </div>
  <table>
    <thead><tr><th>Tarih</th><th>Ürün Adı</th><th>Alış Fiyatı</th><th>Market</th></tr></thead>
    <tbody id="gecmis-tablo"><tr><td colspan="4" class="bos">⏳ Yükleniyor...</td></tr></tbody>
  </table>
</div>

<!-- ── EKSİK LİSTE ── -->
<div class="sayfa" id="sayfa-eksik">
  <div class="eksik-actions">
    <button class="btn btn-wa"     onclick="whatsappGonder()">📱 WhatsApp'a Gönder</button>
    <button class="btn btn-purple" onclick="yazdir()">🖨️ Yazdır / PDF</button>
    <button class="btn btn-green"  onclick="eksikYenile()">🔄 Yenile</button>
    <button class="btn btn-red"    onclick="tumunuSil()">🗑 Tümünü Sil</button>
  </div>
  <div class="card-row" id="eksik-ozet"></div>
  <table id="eksik-tablo-wrap">
    <thead><tr><th>Ürün Adı</th><th>Fiyat</th><th>Market</th><th>Durum</th><th></th></tr></thead>
    <tbody id="eksik-tablo"><tr><td colspan="5" class="bos">⏳ Yükleniyor...</td></tr></tbody>
  </table>
</div>

<div class="toast" id="toast"></div>

<script>
// ── Sekme yönetimi ──
function sekmeAc(id) {
  const tablar = ['arama','gecmis','eksik'];
  document.querySelectorAll('.tab').forEach((t,i) => t.classList.toggle('active', tablar[i]===id));
  document.querySelectorAll('.sayfa').forEach(s => s.classList.remove('active'));
  document.getElementById('sayfa-'+id).classList.add('active');
  if (id==='gecmis') gecmisYukle();
  if (id==='eksik')  eksikYenile();
}

function toast(msg, renk='#27ae60') {
  const t = document.getElementById('toast');
  t.textContent = msg; t.style.background = renk;
  t.classList.add('show');
  setTimeout(() => t.classList.remove('show'), 2500);
}

// ── ARAMA ──
const giris  = document.getElementById('giris');
const tbody  = document.getElementById('sonuclar');
const bulunan = document.getElementById('bulunan');
const bilgi   = document.getElementById('bilgi');

tbody.innerHTML = '<tr><td colspan="5" class="bos">Ürün adı veya barkod girerek arama yapın...</td></tr>';
fetch('/durum').then(r=>r.json()).then(d=>{
  bilgi.textContent = d.toplam ? `📦 Toplam ${d.toplam} ürün  •  Son güncelleme: ${d.zaman}` : '';
}).catch(()=>{});

let timer;
giris.addEventListener('input',()=>{ clearTimeout(timer); timer=setTimeout(ara,200); });

async function ara() {
  const q = giris.value.trim();
  if (!q) {
    tbody.innerHTML='<tr><td colspan="5" class="bos">Ürün adı veya barkod girerek arama yapın...</td></tr>';
    bulunan.textContent=''; return;
  }
  const data = await fetch('/ara?q='+encodeURIComponent(q)).then(r=>r.json());
  if (!data.length) {
    tbody.innerHTML='<tr><td colspan="5" class="bos">❌ Sonuç bulunamadı.</td></tr>';
    bulunan.textContent='0 ürün bulundu'; bulunan.style.color='#e74c3c';
  } else {
    bulunan.textContent=data.length+' ürün bulundu'; bulunan.style.color='#2ecc71';
    tbody.innerHTML=data.map(r=>{
      const urunJs = r.urun.replace(/\\/g,'\\\\').replace(/'/g,"\\'");
      return `<tr>
        <td style="color:#a8a8b3;font-size:0.85rem">${r.tarih}</td>
        <td style="cursor:pointer" onclick="urunGecmis('${urunJs}')">${r.urun}</td>
        <td class="fiyat">💰 ${r.fiyat} ₺</td>
        <td><span class="market-badge">${r.market}</span></td>
        <td><button class="ekle-btn" onclick="eksikEkle(this,'${urunJs}','${r.fiyat}','${r.market}')">+ Eksik</button></td>
      </tr>`;}).join('');
  }
}

function temizle() {
  giris.value='';
  tbody.innerHTML='<tr><td colspan="5" class="bos">Ürün adı veya barkod girerek arama yapın...</td></tr>';
  bulunan.textContent=''; giris.focus();
}

async function yenile() {
  bilgi.textContent='🔄 Güncelleniyor...';
  await fetch('/yenile');
  const d = await fetch('/durum').then(r=>r.json());
  bilgi.textContent = d.toplam ? `📦 Toplam ${d.toplam} ürün  •  Son güncelleme: ${d.zaman}` : '';
  if (giris.value.trim()) ara();
}

function urunGecmis(urunAdi) {
  sekmeAc('gecmis');
  document.getElementById('urun-filtre').value=urunAdi;
  gecmisYukle();
}

// ── EKSİK LİSTE ──
async function eksikEkle(btn, urun, fiyat, market) {
  btn.disabled = true; btn.textContent = '⏳';
  const res = await fetch('/eksik-ekle', {
    method: 'POST',
    headers: {'Content-Type':'application/json'},
    body: JSON.stringify({urun, fiyat, market})
  }).then(r=>r.json());
  if (res.ok) {
    btn.textContent = '✅ Eklendi'; btn.classList.add('eklendi');
    eksikBadgeGuncelle();
    toast('✅ ' + urun + ' eksik listeye eklendi!');
  } else {
    btn.textContent = '❌'; btn.disabled = false;
    toast('Hata: ' + (res.hata||'bilinmiyor'), '#e74c3c');
  }
}

async function eksikYenile() {
  document.getElementById('eksik-tablo').innerHTML = '<tr><td colspan="5" class="bos">⏳ Yükleniyor...</td></tr>';
  const data = await fetch('/eksik-liste').then(r=>r.json());
  const bekleyen = data.filter(d=>d.durum!=='Alındı').length;
  document.getElementById('eksik-ozet').innerHTML=`
    <div class="card"><div class="sayi">${data.length}</div><div class="etiket">Toplam Ürün</div></div>
    <div class="card"><div class="sayi" style="color:#e94560">${bekleyen}</div><div class="etiket">Bekleyen</div></div>
    <div class="card"><div class="sayi" style="color:#27ae60">${data.length-bekleyen}</div><div class="etiket">Alındı</div></div>`;
  if (!data.length) {
    document.getElementById('eksik-tablo').innerHTML = '<tr><td colspan="5" class="bos">📭 Eksik liste boş.</td></tr>';
    return;
  }
  document.getElementById('eksik-tablo').innerHTML = data.map((r,i)=>`
    <tr id="eksik-row-${i}">
      <td>${r.urun}</td>
      <td class="fiyat">💰 ${parseFloat(r.fiyat||0).toFixed(2)} ₺</td>
      <td><span class="market-badge">${r.market}</span></td>
      <td><span class="durum-badge ${r.durum==='Alındı'?'alindi':''}" onclick="durumDegistir(${i},'${r.urun.replace(/'/g,"\\'")}','${r.durum}')">${r.durum==='Alındı'?'✅ Alındı':'⏳ Bekliyor'}</span></td>
      <td><button class="sil-btn" onclick="eksikSil(${i},'${r.urun.replace(/'/g,"\\'")}')">🗑</button></td>
    </tr>`).join('');
  eksikBadgeGuncelle(bekleyen);
}

async function eksikBadgeGuncelle(sayi) {
  if (sayi === undefined) {
    const data = await fetch('/eksik-liste').then(r=>r.json());
    sayi = data.filter(d=>d.durum!=='Alındı').length;
  }
  const b = document.getElementById('eksik-badge');
  b.textContent = sayi; b.style.display = sayi > 0 ? 'inline' : 'none';
}

async function durumDegistir(idx, urun, mevcutDurum) {
  const yeniDurum = mevcutDurum === 'Alındı' ? 'Bekliyor' : 'Alındı';
  await fetch('/eksik-durum', {
    method: 'POST',
    headers: {'Content-Type':'application/json'},
    body: JSON.stringify({urun, durum: yeniDurum})
  });
  eksikYenile();
}

async function eksikSil(idx, urun) {
  if (!confirm(urun + ' listeden silinsin mi?')) return;
  await fetch('/eksik-sil', {
    method: 'POST',
    headers: {'Content-Type':'application/json'},
    body: JSON.stringify({urun})
  });
  eksikYenile();
  toast('🗑 ' + urun + ' silindi', '#e74c3c');
}

async function tumunuSil() {
  if (!confirm('Tüm eksik liste silinsin mi?')) return;
  await fetch('/eksik-temizle', {method:'POST'});
  eksikYenile();
  toast('🗑 Liste temizlendi', '#e74c3c');
}

async function whatsappGonder() {
  const data = await fetch('/eksik-liste').then(r=>r.json());
  if (!data.length) { toast('Liste boş!', '#e74c3c'); return; }
  let metin = '🛒 *EKSİK ÜRÜN LİSTESİ*\n\n';
  data.forEach((r,i) => {
    const durum = r.durum==='Alındı' ? '✅' : '⬜';
    metin += `${durum} ${i+1}. ${r.urun} — ${parseFloat(r.fiyat||0).toFixed(2)} ₺ (${r.market})\n`;
  });
  metin += `\n📅 ${new Date().toLocaleDateString('tr-TR')}`;
  window.open('https://wa.me/?text=' + encodeURIComponent(metin), '_blank');
}

function yazdir() {
  window.print();
}

// ── GEÇMİŞ ──
let grafik = null;

async function gecmisYukle() {
  const bas  = document.getElementById('tarih-bas').value;
  const bit  = document.getElementById('tarih-bit').value;
  const urun = document.getElementById('urun-filtre').value;
  let url='/gecmis?';
  if(bas)  url+='bas='+bas+'&';
  if(bit)  url+='bit='+bit+'&';
  if(urun) url+='urun='+encodeURIComponent(urun)+'&';
  const data = await fetch(url).then(r=>r.json());
  const harcama = data.reduce((s,d)=>s+parseFloat(d.fiyat||0),0);
  document.getElementById('ozet-kartlar').innerHTML=`
    <div class="card"><div class="sayi">${data.length}</div><div class="etiket">Toplam Kayıt</div></div>
    <div class="card"><div class="sayi">${[...new Set(data.map(d=>d.urun))].length}</div><div class="etiket">Farklı Ürün</div></div>
    <div class="card"><div class="sayi" style="color:#FF6600">${harcama.toFixed(2)} ₺</div><div class="etiket">Toplam Alış</div></div>`;
  document.getElementById('gecmis-tablo').innerHTML = !data.length
    ? '<tr><td colspan="4" class="bos">📭 Kayıt bulunamadı.</td></tr>'
    : data.map(r=>`<tr onclick="tekUrunGrafik('${r.urun.replace(/'/g,"\\'")}')">
        <td style="color:#a8a8b3">${r.tarih}</td><td>${r.urun}</td>
        <td class="fiyat">💰 ${parseFloat(r.fiyat).toFixed(2)} ₺</td>
        <td><span class="market-badge">${r.market}</span></td></tr>`).join('');
  const zamData = await fetch('/zamlanlar').then(r=>r.json());
  document.getElementById('zam-listesi').innerHTML = !zamData.length
    ? '<div class="bos" style="padding:16px">Karşılaştırmak için aynı ürünün farklı tarihlerdeki fiyatını girin.</div>'
    : `<table><thead><tr><th>Ürün</th><th>İlk Fiyat</th><th>Son Fiyat</th><th>Değişim</th></tr></thead><tbody>
        ${zamData.map(z=>{
          const y=((z.son-z.ilk)/z.ilk*100).toFixed(1);
          const c=z.son>z.ilk?'zam-up':'zam-down';
          const i=z.son>z.ilk?'▲':'▼';
          return `<tr><td>${z.urun}</td><td>${z.ilk.toFixed(2)} ₺</td><td>${z.son.toFixed(2)} ₺</td><td><span class="zam-badge ${c}">${i} %${Math.abs(y)}</span></td></tr>`;
        }).join('')}</tbody></table>`;
  if(urun && data.length) tekUrunGrafik(urun);
}

function tekUrunGrafik(urunAdi) {
  fetch('/gecmis?urun='+encodeURIComponent(urunAdi)).then(r=>r.json()).then(data=>{
    if(!data.length) return;
    const wrap=document.getElementById('grafik-wrap');
    wrap.style.display='block';
    document.getElementById('grafik-baslik').textContent='📊 '+urunAdi+' — Fiyat Geçmişi';
    if(grafik) grafik.destroy();
    grafik=new Chart(document.getElementById('fiyatGrafik'),{
      type:'line',
      data:{labels:data.map(d=>d.tarih),datasets:[{label:'Alış Fiyatı (₺)',data:data.map(d=>parseFloat(d.fiyat)),
        borderColor:'#e94560',backgroundColor:'#e9456022',borderWidth:2,pointBackgroundColor:'#e94560',
        pointRadius:5,tension:0.3,fill:true}]},
      options:{responsive:true,plugins:{legend:{labels:{color:'#eaeaea'}}},
        scales:{x:{ticks:{color:'#a8a8b3'},grid:{color:'#ffffff11'}},
                y:{ticks:{color:'#a8a8b3',callback:v=>v+' ₺'},grid:{color:'#ffffff11'}}}}
    });
    wrap.scrollIntoView({behavior:'smooth'});
  });
}

function filtreTemizle() {
  document.getElementById('tarih-bas').value='';
  document.getElementById('tarih-bit').value='';
  document.getElementById('urun-filtre').value='';
  document.getElementById('grafik-wrap').style.display='none';
  gecmisYukle();
}

async function gecmisYenile() {
  await fetch('/yenile-gecmis');
  gecmisYukle();
}

// Sayfa açılışında eksik badge güncelle
eksikBadgeGuncelle();
</script>
</body>
</html>"""

# ── ROUTES ────────────────────────────────────────────────────
@app.route('/')
def index():
    veri_al()
    return render_template_string(HTML)

@app.route('/ara')
def ara():
    q = request.args.get('q', '').strip().lower()
    df = veri_al()
    if not q or df is None: return jsonify([])
    cols = df.columns.tolist()
    tarih_col  = next((c for c in cols if 'tarih' in tr_normalize(c)), cols[0])
    urun_col   = next((c for c in cols if 'urun' in tr_normalize(c) or 'adi' in tr_normalize(c)), cols[1] if len(cols)>1 else cols[0])
    barkod_col = next((c for c in cols if 'barkod' in tr_normalize(c)), cols[2] if len(cols)>2 else cols[0])
    fiyat_col  = next((c for c in cols if 'fiyat' in tr_normalize(c)), cols[3] if len(cols)>3 else cols[2])
    market_col = next((c for c in cols if 'market' in tr_normalize(c)), cols[4] if len(cols)>4 else cols[-1])
    maske = tr_aramayi_hazirla(df[urun_col], q) | tr_aramayi_hazirla(df[barkod_col], q)
    return jsonify([{
        'urun':   str(r[urun_col]),
        'fiyat':  f"{float(str(r[fiyat_col]).replace(',', '.')):.2f}",
        'market': str(r[market_col]) if market_col else '-',
        'barkod': str(r[barkod_col]),
        'tarih':  str(r[tarih_col]) if tarih_col else '-'
    } for _, r in df[maske].iterrows()])

@app.route('/gecmis')
def gecmis():
    df = gecmis_al()
    if df is None or df.empty: return jsonify([])
    cols = df.columns.tolist()
    tarih_col  = next((c for c in cols if 'tarih' in c.lower()), cols[0])
    urun_col   = next((c for c in cols if 'ürün' in c.lower() or 'urun' in c.lower() or 'ad' in c.lower()), cols[1] if len(cols)>1 else cols[0])
    fiyat_col  = next((c for c in cols if 'fiyat' in c.lower()), cols[3] if len(cols)>3 else cols[2])
    market_col = next((c for c in cols if 'market' in c.lower()), cols[-1])
    bas  = request.args.get('bas','')
    bit  = request.args.get('bit','')
    urun = request.args.get('urun','').strip().lower()
    sonuc = df.copy()
    if urun:
        sonuc = sonuc[tr_aramayi_hazirla(sonuc[urun_col], urun)]
    if bas:
        try: sonuc = sonuc[pd.to_datetime(sonuc[tarih_col], dayfirst=True, errors='coerce') >= pd.to_datetime(bas)]
        except: pass
    if bit:
        try: sonuc = sonuc[pd.to_datetime(sonuc[tarih_col], dayfirst=True, errors='coerce') <= pd.to_datetime(bit)]
        except: pass
    sonuc = sonuc.sort_values(tarih_col, ascending=True)
    return jsonify([{
        'tarih':  str(r[tarih_col]),
        'urun':   str(r[urun_col]),
        'fiyat':  str(r[fiyat_col]).replace(',','.'),
        'market': str(r[market_col])
    } for _, r in sonuc.iterrows()])

@app.route('/zamlanlar')
def zamlanlar():
    df = gecmis_al()
    if df is None or df.empty: return jsonify([])
    cols = df.columns.tolist()
    tarih_col = next((c for c in cols if 'tarih' in c.lower()), cols[0])
    urun_col  = next((c for c in cols if 'ürün' in c.lower() or 'urun' in c.lower() or 'ad' in c.lower()), cols[1] if len(cols)>1 else cols[0])
    fiyat_col = next((c for c in cols if 'fiyat' in c.lower()), cols[3] if len(cols)>3 else cols[2])
    sonuc = []
    for urun, grup in df.groupby(urun_col):
        grup = grup.sort_values(tarih_col)
        if len(grup) < 2: continue
        ilk = float(str(grup.iloc[0][fiyat_col]).replace(',','.'))
        son = float(str(grup.iloc[-1][fiyat_col]).replace(',','.'))
        fark = ((son-ilk)/ilk*100) if ilk>0 else 0
        sonuc.append({'urun':str(urun),'ilk':ilk,'son':son,'fark':fark})
    sonuc.sort(key=lambda x: abs(x['fark']), reverse=True)
    return jsonify(sonuc[:15])

# ── EKSİK LİSTE ROUTES ────────────────────────────────────────
@app.route('/eksik-ekle', methods=['POST'])
def eksik_ekle():
    from datetime import datetime
    data = request.json
    urun   = data.get('urun','')
    fiyat  = data.get('fiyat','')
    market = data.get('market','')
    try:
        ws = eksik_sayfasi_al()
        if not ws:
            return jsonify({'ok': False, 'hata': 'Sheets bağlantısı kurulamadı'})
        tarih = datetime.now().strftime('%d.%m.%Y %H:%M')
        ws.append_row([urun, fiyat, market, tarih, 'Bekliyor'])
        return jsonify({'ok': True})
    except Exception as e:
        return jsonify({'ok': False, 'hata': str(e)})

@app.route('/eksik-liste')
def eksik_liste():
    try:
        ws = eksik_sayfasi_al()
        if not ws: return jsonify([])
        rows = ws.get_all_records()
        return jsonify([{
            'urun':   str(r.get('Ürün Adı','')),
            'fiyat':  str(r.get('Alış Fiyatı','')),
            'market': str(r.get('Market','')),
            'tarih':  str(r.get('Eklenme Tarihi','')),
            'durum':  str(r.get('Durum','Bekliyor'))
        } for r in rows if r.get('Ürün Adı')])
    except Exception as e:
        print(f"Eksik liste okuma hatası: {e}")
        return jsonify([])

@app.route('/eksik-durum', methods=['POST'])
def eksik_durum():
    data = request.json
    urun      = data.get('urun','')
    yeni_durum = data.get('durum','Bekliyor')
    try:
        ws = eksik_sayfasi_al()
        if not ws: return jsonify({'ok': False})
        kayitlar = ws.get_all_values()
        for i, row in enumerate(kayitlar[1:], start=2):
            if row and row[0] == urun:
                ws.update_cell(i, 5, yeni_durum)
                break
        return jsonify({'ok': True})
    except Exception as e:
        return jsonify({'ok': False, 'hata': str(e)})

@app.route('/eksik-sil', methods=['POST'])
def eksik_sil():
    data = request.json
    urun = data.get('urun','')
    try:
        ws = eksik_sayfasi_al()
        if not ws: return jsonify({'ok': False})
        kayitlar = ws.get_all_values()
        for i, row in enumerate(kayitlar[1:], start=2):
            if row and row[0] == urun:
                ws.delete_rows(i)
                break
        return jsonify({'ok': True})
    except Exception as e:
        return jsonify({'ok': False, 'hata': str(e)})

@app.route('/eksik-temizle', methods=['POST'])
def eksik_temizle():
    try:
        ws = eksik_sayfasi_al()
        if not ws: return jsonify({'ok': False})
        ws.clear()
        ws.append_row(["Ürün Adı", "Alış Fiyatı", "Market", "Eklenme Tarihi", "Durum"])
        return jsonify({'ok': True})
    except Exception as e:
        return jsonify({'ok': False, 'hata': str(e)})

# ── DİĞER ROUTES ──────────────────────────────────────────────
@app.route('/yenile')
def yenile():
    _cache["zaman"] = 0
    veri_al()
    return jsonify({"ok": True})

@app.route('/yenile-gecmis')
def yenile_gecmis():
    _cache["gecmis_zaman"] = 0
    gecmis_al()
    return jsonify({"ok": True})

@app.route('/durum')
def durum():
    df = veri_al()
    if df is None: return jsonify({"toplam": 0, "zaman": "-"})
    from datetime import datetime
    zaman = datetime.fromtimestamp(_cache["zaman"]).strftime("%H:%M:%S") if _cache["zaman"] else "-"
    return jsonify({"toplam": len(df), "zaman": zaman})

@app.route('/debug')
def debug():
    df = veri_al()
    g  = gecmis_al()
    return jsonify({
        'kolonlar':       df.columns.tolist() if df is not None else [],
        'gecmis_kolonlar': g.columns.tolist() if g is not None and not g.empty else [],
        'toplam':         len(df) if df is not None else 0,
        'gecmis_toplam':  len(g)  if g  is not None else 0
    })

@app.route('/gecmis-debug')
def gecmis_debug():
    try:
        sheets = sheet_listesi_al()
        return jsonify({'sheets': list(sheets.keys()), 'sheet_ids': sheets})
    except Exception as e:
        return jsonify({'hata': str(e)})

if __name__ == '__main__':
    port = int(os.environ.get('PORT', 5000))
    app.run(host='0.0.0.0', port=port)
