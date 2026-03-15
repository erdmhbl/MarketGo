from flask import Flask, request, jsonify, render_template_string
import pandas as pd
import io, os, requests, time

app = Flask(__name__)

SHEET_ID = "1qNwL82ctBVHhGv3vtrFT1mjHN1KeN9Dt2OkI8Vg5XLM"
_cache = {"df": None, "zaman": 0}
CACHE_SURE = 300

TR_MAP = {
    'u': 'ü', 'ü': 'u', 'c': 'ç', 'ç': 'c',
    'i': 'ı', 'ı': 'i', 'o': 'ö', 'ö': 'o',
    's': 'ş', 'ş': 's',
}

def tr_varyantlar(kelime):
    sonuclar = {kelime}
    for k, v in TR_MAP.items():
        yeni = set()
        for s in sonuclar:
            yeni.add(s.replace(k, v))
        sonuclar |= yeni
    return sonuclar

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
    tum = []
    try:
        sheets = sheet_listesi_al()
        if not sheets:
            for i in range(5):
                url = f"https://docs.google.com/spreadsheets/d/{SHEET_ID}/export?format=csv&gid={i}"
                try:
                    r = requests.get(url, timeout=10)
                    if r.status_code == 200 and len(r.content) > 100:
                        df = pd.read_csv(io.StringIO(r.text))
                        df['Market'] = f"Sayfa{i+1}"
                        tum.append(df)
                except:
                    break
        else:
            for sheet_name, gid in sheets.items():
                url = f"https://docs.google.com/spreadsheets/d/{SHEET_ID}/export?format=csv&gid={gid}"
                try:
                    r = requests.get(url, timeout=10)
                    if r.status_code == 200:
                        df = pd.read_csv(io.StringIO(r.text))
                        df['Market'] = sheet_name
                        tum.append(df)
                        print(f"✅ {sheet_name}: {len(df)} satır")
                except Exception as e:
                    print(f"❌ {sheet_name}: {e}")

        if tum:
            return pd.concat(tum, ignore_index=True)
    except Exception as e:
        print(f"Sheets hatası: {e}")

    if os.path.exists("market_fisi_urunler_2.xlsx"):
        print("⚠️ Yedek Excel kullanılıyor")
        tum2 = []
        xl = pd.ExcelFile("market_fisi_urunler_2.xlsx")
        for sheet in xl.sheet_names:
            df = pd.read_excel("market_fisi_urunler_2.xlsx", sheet_name=sheet)
            df['Market'] = sheet
            tum2.append(df)
        return pd.concat(tum2, ignore_index=True)
    return None

def veri_al():
    simdi = time.time()
    if _cache["df"] is None or (simdi - _cache["zaman"]) > CACHE_SURE:
        df = google_sheets_yukle()
        if df is not None:
            _cache["df"] = df
            _cache["zaman"] = simdi
    return _cache["df"]

HTML = """<!DOCTYPE html>
<html lang="tr">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<title>Market Go — Birim Fiyat Sorgulama</title>
<link rel="icon" href="/static/favicon.ico">
<style>
  * { box-sizing: border-box; margin: 0; padding: 0; }
  body { background: #0f3460; font-family: 'Segoe UI', sans-serif; min-height: 100vh; }
  .header { background: #16213e; padding: 16px 24px; display: flex; align-items: center; gap: 16px; box-shadow: 0 2px 12px #0005; }
  .header img { width: 58px; height: 58px; border-radius: 50%; object-fit: cover; }
  .header-text h1 { color: #e94560; font-size: 1.7rem; font-weight: 800; }
  .header-text h2 { color: #FF6600; font-size: 1.7rem; font-weight: 800; }
  .search-box { padding: 24px 20px 10px; max-width: 900px; margin: 0 auto; }
  .search-row { display: flex; gap: 10px; flex-wrap: wrap; }
  .search-row input { flex: 1; min-width: 200px; padding: 12px 18px; font-size: 1.05rem; border-radius: 10px; border: none; background: #1a1a2e; color: #fff; outline: 2px solid transparent; transition: outline 0.2s; }
  .search-row input:focus { outline: 2px solid #e94560; }
  .search-row input::placeholder { color: #666; }
  .btn-temizle { padding: 12px 22px; background: #533483; color: white; border: none; border-radius: 10px; font-size: 1rem; font-weight: 700; cursor: pointer; }
  .btn-temizle:hover { background: #3d2568; }
  .btn-yenile { padding: 12px 18px; background: #16213e; color: #2ecc71; border: 1px solid #2ecc71; border-radius: 10px; font-size: 1rem; font-weight: 700; cursor: pointer; }
  .btn-yenile:hover { background: #2ecc71; color: #16213e; }
  .bulunan { color: #2ecc71; font-size: 0.95rem; padding: 8px 4px; font-weight: 600; min-height: 28px; }
  .tablo-wrap { max-width: 900px; margin: 0 auto; padding: 0 20px 30px; }
  table { width: 100%; border-collapse: collapse; background: #16213e; border-radius: 12px; overflow: hidden; }
  thead tr { background: #e94560; }
  thead th { padding: 12px 14px; color: white; font-size: 0.95rem; text-align: left; }
  tbody tr { border-bottom: 1px solid #0f3460; transition: background 0.15s; }
  tbody tr:hover { background: #1f2f52; }
  tbody td { padding: 11px 14px; color: #eaeaea; font-size: 0.93rem; }
  .fiyat { color: #2ecc71; font-weight: 700; font-size: 1rem; white-space: nowrap; }
  .market-badge { background: #533483; color: white; padding: 2px 10px; border-radius: 20px; font-size: 0.78rem; font-weight: 600; }
  .bos { text-align: center; padding: 40px; color: #666; font-size: 1rem; }
  .bilgi { text-align: center; color: #a8a8b3; font-size: 0.8rem; padding: 10px; }
  @media (max-width: 600px) {
    .header-text h1, .header-text h2 { font-size: 1.2rem; }
    thead th:nth-child(4), tbody td:nth-child(4) { display: none; }
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
<div class="search-box">
  <div class="search-row">
    <input type="text" id="giris" placeholder="Ürün adı veya barkod girin..." autofocus>
    <button class="btn-yenile" onclick="yenile()" title="Veriyi güncelle">🔄</button>
    <button class="btn-temizle" onclick="temizle()">🗑 Temizle</button>
  </div>
  <div class="bulunan" id="bulunan"></div>
</div>
<div class="tablo-wrap">
  <table>
    <thead><tr><th>Ürün Adı</th><th>Birim Fiyat</th><th>Market</th><th>Barkod</th></tr></thead>
    <tbody id="sonuclar"><tr><td colspan="4" class="bos">⏳ Yükleniyor...</td></tr></tbody>
  </table>
  <div class="bilgi" id="bilgi"></div>
</div>
<script>
const giris = document.getElementById('giris');
const tbody = document.getElementById('sonuclar');
const bulunan = document.getElementById('bulunan');
const bilgi = document.getElementById('bilgi');

fetch('/durum').then(r=>r.json()).then(d=>{
  bilgi.textContent = d.toplam ? `📦 Toplam ${d.toplam} ürün  •  Son güncelleme: ${d.zaman}` : '';
  tbody.innerHTML = '<tr><td colspan="4" class="bos">Ürün adı veya barkod girerek arama yapın...</td></tr>';
});

let timer;
giris.addEventListener('input', () => { clearTimeout(timer); timer = setTimeout(ara, 200); });

async function ara() {
  const q = giris.value.trim();
  if (!q) {
    tbody.innerHTML = '<tr><td colspan="4" class="bos">Ürün adı veya barkod girerek arama yapın...</td></tr>';
    bulunan.textContent = ''; return;
  }
  const data = await fetch('/ara?q=' + encodeURIComponent(q)).then(r=>r.json());
  if (data.length === 0) {
    tbody.innerHTML = '<tr><td colspan="4" class="bos">❌ Sonuç bulunamadı.</td></tr>';
    bulunan.textContent = '0 ürün bulundu'; bulunan.style.color = '#e74c3c';
  } else {
    bulunan.textContent = data.length + ' ürün bulundu'; bulunan.style.color = '#2ecc71';
    tbody.innerHTML = data.map(r=>`<tr><td>${r.urun}</td><td class="fiyat">💰 ${r.fiyat} ₺</td><td><span class="market-badge">${r.market}</span></td><td style="color:#888;font-size:0.82rem">${r.barkod}</td></tr>`).join('');
  }
}

function temizle() {
  giris.value = '';
  tbody.innerHTML = '<tr><td colspan="4" class="bos">Ürün adı veya barkod girerek arama yapın...</td></tr>';
  bulunan.textContent = ''; giris.focus();
}

async function yenile() {
  bilgi.textContent = '🔄 Güncelleniyor...';
  await fetch('/yenile');
  const d = await fetch('/durum').then(r=>r.json());
  bilgi.textContent = d.toplam ? `📦 Toplam ${d.toplam} ürün  •  Son güncelleme: ${d.zaman}` : '';
  if (giris.value.trim()) ara();
}
</script>
</body>
</html>"""

@app.route('/')
def index():
    veri_al()
    return render_template_string(HTML)

@app.route('/ara')
def ara():
    q = request.args.get('q', '').strip().lower()
    df = veri_al()
    if not q or df is None:
        return jsonify([])
    varyantlar = tr_varyantlar(q)
    
    # Sütun adlarını esnek bul
    cols = df.columns.tolist()
    urun_col  = next((c for c in cols if 'r' in c.lower() and 'n' in c.lower() and 'ad' in c.lower()), cols[1] if len(cols)>1 else cols[0])
    fiyat_col = next((c for c in cols if 'fiyat' in c.lower() or 'price' in c.lower()), cols[2] if len(cols)>2 else cols[0])
    barkod_col= next((c for c in cols if 'barkod' in c.lower() or 'barcode' in c.lower()), cols[0])
    
    maske = pd.Series([False] * len(df))
    for v in varyantlar:
        maske |= df[urun_col].astype(str).str.lower().str.contains(v, na=False)
        maske |= df[barkod_col].astype(str).str.lower().str.contains(v, na=False)
    
    return jsonify([
        {
            'urun': str(r[urun_col]),
            'fiyat': f"{float(str(r[fiyat_col]).replace(',','.')):.2f}",
            'market': str(r.get('Market', r.get('market', '-'))),
            'barkod': str(r[barkod_col])
        }
        for _, r in df[maske].iterrows()
    ])

@app.route('/yenile')
def yenile():
    _cache["zaman"] = 0
    veri_al()
    return jsonify({"ok": True})

@app.route('/durum')
def durum():
    df = veri_al()
    if df is None:
        return jsonify({"toplam": 0, "zaman": "-"})
    from datetime import datetime
    zaman = datetime.fromtimestamp(_cache["zaman"]).strftime("%H:%M:%S") if _cache["zaman"] else "-"
    return jsonify({"toplam": len(df), "zaman": zaman})


@app.route('/debug')
def debug():
    df = veri_al()
    if df is None:
        return jsonify({'hata': 'veri yok'})
    return jsonify({'kolonlar': df.columns.tolist(), 'ilk_satir': df.iloc[0].to_dict() if len(df)>0 else {}, 'toplam': len(df)})
if __name__ == '__main__':
    port = int(os.environ.get('PORT', 5000))
    app.run(host='0.0.0.0', port=port)
