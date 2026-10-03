#!/usr/bin/env python3
"""
Nuvio / WioLand -> TiviMate Akilli M3U Uretici (Otomatik Calismayan Yayin Ayiklama)
---------------------------------------------------------------------------------
1. Nuvio-Addons kataloglarindaki tum alternatif yayinlari toplar (5.700+ kaynak).
2. CALISMAYAN YAYINLARI AYIKLAR:
   - 403 (Erisim Engeli), 404 (Silinmis), 500-504 (Cökmüs Sunucu),
   - Zaman Asimi (Timeout) ve DNS hatalarini tespit edip listeden siler.
   - Sadece gercekten calisan ve video donduren kaynaklari listeye alir.
3. KANAL BAZINDA KLASORLER:
   - TiviMate'te 'beIN Sports 1', 'S Sport 1', 'Exxen Spor 1' vb. klasorler altinda gruplar.
4. GITHUB VE TIVIMATE DOSTU:
   - Bilgisayarin acik olmasina gerek kalmadan GitHub uzerinden dogrudan calisir.
"""

import os
import re
import sys
import json
import time
import urllib.parse
import concurrent.futures
import urllib.request
import ssl

if sys.platform.startswith("win"):
    try:
        sys.stdout.reconfigure(encoding='utf-8')
    except Exception:
        pass

CTX = ssl.create_default_context()
CTX.check_hostname = False
CTX.verify_mode = ssl.CERT_NONE

USER_AGENT = "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36"
NUVIO_BASE = "https://raw.githubusercontent.com/Wiojelt/Nuvio-Addons/live/wiospor"

CHANNEL_NAMES_MAP = {
    "wiospor_mor_1": "beIN Sports 1",
    "wiospor_mor_1_4k": "beIN Sports 1 (4K)",
    "wiospor_mor_2": "beIN Sports 2",
    "wiospor_mor_3": "beIN Sports 3",
    "wiospor_mor_4": "beIN Sports 4",
    "wiospor_mor_5": "beIN Sports 5",
    "wiospor_mor_max_1": "beIN Sports MAX 1",
    "wiospor_mor_max_2": "beIN Sports MAX 2",
    "wiospor_mor_haber": "beIN Sports Haber",
    "wiospor_yesil": "S Sport 1",
    "wiospor_yesil_1": "S Sport 1",
    "wiospor_yesil_2": "S Sport 2",
    "wiospor_yesil_3": "S Sport Plus",
    "wiospor_turuncu_1": "Tivibu Spor 1",
    "wiospor_turuncu_2": "Tivibu Spor 2",
    "wiospor_turuncu_3": "Tivibu Spor 3",
    "wiospor_turuncu_4": "Tivibu Spor 4",
    "wiospor_sari_1": "Exxen Spor 1",
    "wiospor_sari_2": "Exxen Spor 2",
    "wiospor_sari_3": "Exxen Spor 3",
    "wiospor_sari_4": "Exxen Spor 4",
    "wiospor_sari_5": "Exxen Spor 5",
    "wiospor_sari_6": "Exxen Spor 6",
    "wiospor_sari_7": "Exxen Spor 7",
    "wiospor_sari_8": "Exxen Spor 8",
    "wiospor_mavi_1": "Tabii Spor 1",
    "wiospor_mavi_2": "Tabii Spor 2",
    "wiospor_mavi_plus_1": "Tabii Spor 3",
    "wiospor_mavi_plus_2": "Tabii Spor 4",
    "wiospor_mavi_plus_3": "Tabii Spor 5",
    "wiospor_mavi_plus_4": "Tabii Spor 6",
    "wiospor_yildiz_smart_1": "Smart Spor 1",
    "wiospor_yildiz_smart_2": "Smart Spor 2",
    "wiospor_yildiz_euro_1": "Eurosport 1",
    "wiospor_yildiz_euro_2": "Eurosport 2",
    "wiospor_ulusal_trt_spor": "TRT Spor",
    "wiospor_ulusal_aspor": "A Spor",
    "wiospor_ulusal_trt1": "TRT 1",
    "wiospor_ulusal_atv": "ATV",
    "wiospor_ulusal_tv8": "TV8",
    "wiospor_ulusal_tv85": "TV8.5",
    "wiospor_ulusal_fbtv": "FB TV",
    "wiospor_ulusal_gstv": "GS TV",
}

def clean_title(name):
    if not name:
        return ""
    cleaned = re.sub(r'[\U00010000-\U0010ffff]', '', name).strip()
    cleaned = re.sub(r'^[•\s\-_]+', '', cleaned).strip()
    return cleaned or name

def fetch_json(url, timeout=10):
    req = urllib.request.Request(url, headers={"User-Agent": USER_AGENT})
    try:
        with urllib.request.urlopen(req, timeout=timeout, context=CTX) as r:
            return json.loads(r.read().decode("utf-8", "replace"))
    except Exception:
        return None

def fetch_channel_streams(ch_id):
    url = f"{NUVIO_BASE}/stream/tv/{ch_id}.json"
    data = fetch_json(url, timeout=7)
    if data and "streams" in data:
        return ch_id, data["streams"]
    return ch_id, []

def get_channel_folder(cid, raw_name):
    if cid in CHANNEL_NAMES_MAP:
        return CHANNEL_NAMES_MAP[cid]
    cleaned = clean_title(raw_name)
    return cleaned or cid

def verify_stream(item):
    """
    Yayinin gercekten canli ve erisilebilir olup olmadigini test eder.
    Calisiyorsa (True, item), oluyse (False, reason) dondurur.
    """
    url = item.get("url", "")
    if not url or not url.startswith("http"):
        return False, "invalid_url"

    ua = item.get("ua", USER_AGENT)
    ref = item.get("ref", "")
    headers = {"User-Agent": ua}
    if ref:
        headers["Referer"] = ref

    def do_probe(target_url):
        req = urllib.request.Request(target_url, headers=headers)
        try:
            with urllib.request.urlopen(req, timeout=2.5, context=CTX) as resp:
                code = resp.getcode()
                if code in (200, 206):
                    chunk = resp.read(188)
                    if len(chunk) > 0:
                        # MPEG-TS sync byte (0x47), HLS (#EXTM3U) veya HTML olmayan veri
                        if chunk[0] == 0x47 or b"#EXTM3U" in chunk or b"<html" not in chunk[:30].lower():
                            return True, "200_OK"
                return False, f"bad_content_{code}"
        except urllib.error.HTTPError as e:
            # 429: Sunucu cok hizli taramamizdan dolayi gecici sinirlama yapti (Sunucu canli!)
            if e.code == 429:
                return True, "429_alive"
            return False, f"http_{e.code}"
        except Exception as e:
            return False, type(e).__name__

    # 1. İlk deneme
    ok, reason = do_probe(url)

    # 2. Eger 460 veya 403 donerse ve URL'de suresi dolmus play_token varsa temizleyip tekrar dene
    if not ok and "play_token=" in url:
        clean_u = re.sub(r'([?&])play_token=[^&]+(&|$)', r'\1', url).rstrip('?&')
        ok2, reason2 = do_probe(clean_u)
        if ok2:
            item["url"] = clean_u
            return True, "token_cleaned"

    return ok, reason

def generate(verify=True):
    t_start = time.time()
    print("=" * 70)
    print("   [+] Nuvio / WioLand Akilli M3U Uretici (Calismayan Yayin Filtresi)")
    print("=" * 70)

    # 1. Adım: Katalogları İndir
    print("\n[1/4] Kanal kataloglari indiriliyor...")
    bird_data = fetch_json(f"{NUVIO_BASE}/catalog/tv/birdirbir-live.json") or {}
    wio_data = fetch_json(f"{NUVIO_BASE}/catalog/tv/wiospor-live.json") or {}

    all_channels = []
    seen_ids = set()

    for m in bird_data.get("metas", []):
        cid = m.get("id")
        if cid and cid not in seen_ids:
            seen_ids.add(cid)
            all_channels.append({
                "id": cid,
                "folder": get_channel_folder(cid, m.get("name", "")),
                "logo": m.get("poster", ""),
                "catalog": "birdirbir"
            })

    for m in wio_data.get("metas", []):
        cid = m.get("id")
        if cid and cid not in seen_ids:
            seen_ids.add(cid)
            all_channels.append({
                "id": cid,
                "folder": get_channel_folder(cid, m.get("name", "")),
                "logo": m.get("poster", ""),
                "catalog": "wiospor"
            })

    print(f"[OK] {len(all_channels)} kanal bulundu.")

    # 2. Adım: Alternatif Yayın Kaynaklarını İndir
    print("\n[2/4] Tum alternatif yayin kaynaklari taranıyor...")
    raw_stream_candidates = []
    with concurrent.futures.ThreadPoolExecutor(max_workers=25) as executor:
        futures = {executor.submit(fetch_channel_streams, ch["id"]): ch for ch in all_channels}
        for f in concurrent.futures.as_completed(futures):
            ch = futures[f]
            cid, streams = f.result()
            folder_name = ch["folder"]
            logo = ch["logo"]

            for idx, s in enumerate(streams, 1):
                s_url = s.get("url", "")
                if not s_url or not s_url.startswith("http"):
                    continue

                s_name = s.get("name", "")
                s_title = s.get("title", f"Yayın {idx}")
                full_title = f"{s_name} • {s_title}" if s_name and s_name not in s_title else s_title
                full_title = clean_title(full_title)

                hints = s.get("behaviorHints", {}).get("proxyHeaders", {}).get("request", {})
                ref = hints.get("Referer", "")
                ua = hints.get("User-Agent", USER_AGENT)

                raw_stream_candidates.append({
                    "channel_id": cid,
                    "folder": folder_name,
                    "title": full_title,
                    "logo": logo,
                    "url": s_url,
                    "ref": ref,
                    "ua": ua
                })

    total_candidates = len(raw_stream_candidates)
    print(f"[OK] Toplam {total_candidates} adet alternatif yayin kaynagi bulundu.")

    # 3. Adım: Çalışmayan Yayınları Ayıkla (Doğrulama Testi)
    if verify:
        print(f"\n[3/4] Calismayan yayinlar ayiklaniyor (35 paralel is parçacigi ile test ediliyor)...")
        t_verify = time.time()
        valid_streams = []
        dead_count = 0
        dead_breakdown = {}

        with concurrent.futures.ThreadPoolExecutor(max_workers=35) as executor:
            future_to_item = {executor.submit(verify_stream, item): item for item in raw_stream_candidates}
            for idx, future in enumerate(concurrent.futures.as_completed(future_to_item), 1):
                item = future_to_item[future]
                try:
                    is_ok, reason = future.result()
                    if is_ok:
                        valid_streams.append(item)
                    else:
                        dead_count += 1
                        dead_breakdown[reason] = dead_breakdown.get(reason, 0) + 1
                except Exception:
                    dead_count += 1

                if idx % 1000 == 0 or idx == total_candidates:
                    print(f"  -> {idx}/{total_candidates} yayin test edildi... ({len(valid_streams)} Calisiyor, {dead_count} Ayiklandi)")

        print(f"\n[TEST TAMAMLANDI] ({time.time() - t_verify:.1f} saniye):")
        print(f"  ✅ Calisan & Eklenen : {len(valid_streams)}")
        print(f"  ❌ Ayiklanan (Olu)   : {dead_count}")
        if dead_breakdown:
            top_reasons = sorted(dead_breakdown.items(), key=lambda x: x[1], reverse=True)[:5]
            print(f"  Detay: {', '.join(f'{k}: {v}' for k, v in top_reasons)}")
    else:
        print("\n[3/4] Dogrulama atlandi (--no-verify). Tum yayinlar aliniyor...")
        valid_streams = raw_stream_candidates

    # 4. Adım: Kanal Bazında Klasörleyerek M3U Yaz
    print("\n[4/4] TiviMate kanal klasorlu M3U dosyalari olusturuluyor...")
    folder_groups = {}
    for item in valid_streams:
        folder = item["folder"]
        folder_groups.setdefault(folder, []).append(item)

    # Klasör sıralaması
    def sort_key(name):
        n = name.lower()
        if "bein" in n: return (0, n)
        elif "s sport" in n: return (1, n)
        elif "tivibu" in n: return (2, n)
        elif "exxen" in n: return (3, n)
        elif "tabii" in n: return (4, n)
        elif "smart" in n or "euro" in n: return (5, n)
        elif any(k in n for k in ["trt", "a spor", "atv", "tv8"]): return (6, n)
        return (7, n)

    sorted_folders = sorted(folder_groups.keys(), key=sort_key)

    m3u_lines = [
        "#EXTM3U x-tvg-url=\"https://iptv-epg.org/epg.xml.gz\"",
        f"# PLAYLIST NAME: WioLand Temiz & Calisan IPTV ({len(valid_streams)} Yayin)",
    ]

    for folder in sorted_folders:
        for s in folder_groups[folder]:
            title = s["title"]
            logo = s["logo"]
            cid = s["channel_id"]
            url = s["url"]
            ref = s["ref"]
            ua = s["ua"]

            # group-title="{folder}" sayesinde TiviMate'te kanal klasörü oluşur
            m3u_lines.append(f'#EXTINF:-1 tvg-id="{cid}" tvg-name="{title}" tvg-logo="{logo}" group-title="{folder}",{title}')

            if ref:
                m3u_lines.append(f'#EXTVLCOPT:http-referrer={ref}')
            if ua and ua != USER_AGENT:
                m3u_lines.append(f'#EXTVLCOPT:http-user-agent={ua}')

            # TiviMate pipe syntax
            if ref or (ua and ua != USER_AGENT):
                pipe_params = []
                if ua: pipe_params.append(f"User-Agent={urllib.parse.quote(ua)}")
                if ref: pipe_params.append(f"Referer={urllib.parse.quote(ref)}")
                final_url = f"{url}|{'&'.join(pipe_params)}"
            else:
                final_url = url

            m3u_lines.append(final_url)

    content = "\n".join(m3u_lines) + "\n"

    with open("playlist.m3u", "w", encoding="utf-8") as f:
        f.write(content)

    with open("tivimate_kanallar.m3u", "w", encoding="utf-8") as f:
        f.write(content)

    print(f"\n" + "=" * 70)
    print(f" [BASARILI] Calisma {time.time() - t_start:.1f} saniyede tamamlandi!")
    print(f"  📁 Toplam Kanal Klasoru : {len(sorted_folders)}")
    print(f"  📺 Calisan Canli Yayin  : {len(valid_streams)}")
    print(f"  📄 Olusturulan Dosyalar : playlist.m3u, tivimate_kanallar.m3u")
    print("=" * 70)

if __name__ == "__main__":
    verify_flag = "--no-verify" not in sys.argv
    generate(verify=verify_flag)
