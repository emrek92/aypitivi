#!/usr/bin/env python3
"""
WioLand / TurkSpor / Nuvio-Addons Tam M3U & IPTV Proxy Sunucusu
--------------------------------------------------------------
Nuvio-Addons WioSpor ve Birdirbir kataloglarındaki 163+ kanal ve 5,700+ alternatif yayını
(Spor20x, 8kGold, Eagle, Aslan, PatronHD, JestYayın vb.)
çözer, proxy'ler ve TiviMate, VLC, Kodi, Smart TV ve Web için tam uyumlu M3U listeleri sunar.
"""

import os
import re
import sys
import time
import json
import socket
import urllib.parse
import threading
import concurrent.futures
from http.server import ThreadingHTTPServer, BaseHTTPRequestHandler
import requests
import urllib3

urllib3.disable_warnings()

if sys.platform.startswith("win"):
    try:
        sys.stdout.reconfigure(encoding='utf-8')
    except Exception:
        pass

PORT = 8089
HOST = "0.0.0.0"

USER_AGENT = "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36"

NUVIO_BASE = "https://raw.githubusercontent.com/Wiojelt/Nuvio-Addons/live/wiospor"
CACHE_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), ".cache")
os.makedirs(CACHE_DIR, exist_ok=True)
CACHE_FILE = os.path.join(CACHE_DIR, "catalog_streams_cache.json")

def get_local_ip():
    try:
        s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        s.connect(("8.8.8.8", 80))
        ip = s.getsockname()[0]
        s.close()
        return ip
    except Exception:
        return "127.0.0.1"

LOCAL_IP = get_local_ip()

def clean_title(name):
    if not name:
        return ""
    # Emojileri temizle
    cleaned = re.sub(r'[\U00010000-\U0010ffff]', '', name).strip()
    cleaned = re.sub(r'^[•\s\-_]+', '', cleaned).strip()
    return cleaned or name

class CatalogManager:
    """Nuvio-Addons kanallarını ve 5,700+ alternatif yayınını yöneten sınıf."""
    def __init__(self):
        self.channels = []          # 163 kanal listesi
        self.channel_streams = {}   # ch_id -> list of stream dicts
        self.all_expanded_streams = [] # Her alternatif yayın ayrı bir kanal olarak (~5,700 adet)
        self.last_sync = 0
        self.is_syncing = False
        self.lock = threading.Lock()

    def get_group(self, ch_id, ch_name):
        name_lower = ch_name.lower()
        if ch_id.startswith("wiospor_mor_") or "bein" in name_lower:
            return "beIN Sports"
        elif ch_id.startswith("wiospor_yesil") or "s sport" in name_lower:
            return "S Sport"
        elif ch_id.startswith("wiospor_turuncu_") or "tivibu" in name_lower:
            return "Tivibu Spor"
        elif ch_id.startswith("wiospor_sari_") or "exxen" in name_lower:
            return "Exxen Spor"
        elif ch_id.startswith("wiospor_mavi_") or "tabii" in name_lower:
            return "Tabii Spor"
        elif ch_id.startswith("wiospor_yildiz_") or "smart" in name_lower or "euro" in name_lower:
            return "Smart & Eurosport"
        elif any(k in name_lower for k in ["trt", "atv", "a spor", "ht spor", "fb tv", "gs tv", "tv8", "show", "kanal d", "star", "now", "beyaz"]):
            return "Ulusal & Kulüp Kanalları"
        elif ch_id.startswith("wiospor_world_") or any(k in name_lower for k in ["sky", "tnt", "espn", "dazn", "canal+", "polsat", "ziggo"]):
            return "Dünya Spor Kanalları"
        elif ch_id.startswith("birdirbir_"):
            return "Birdirbir IPTV"
        return "Diğer Kanallar"

    def fetch_stream_data(self, ch):
        cid = ch["id"]
        url = f"{NUVIO_BASE}/stream/tv/{cid}.json"
        try:
            r = requests.get(url, headers={"User-Agent": USER_AGENT}, timeout=6)
            if r.status_code == 200:
                streams = r.json().get("streams", [])
                return cid, streams
        except Exception:
            pass
        return cid, []

    def sync(self, force=False):
        with self.lock:
            now = time.time()
            if not force and self.channels and (now - self.last_sync < 7200):
                return

            # Önce disk önbelleğini kontrol et
            if not force and os.path.exists(CACHE_FILE):
                try:
                    with open(CACHE_FILE, "r", encoding="utf-8") as f:
                        cached_data = json.load(f)
                    if now - cached_data.get("time", 0) < 7200:
                        self.channels = cached_data.get("channels", [])
                        self.channel_streams = cached_data.get("channel_streams", {})
                        self.all_expanded_streams = cached_data.get("all_expanded_streams", [])
                        self.last_sync = cached_data.get("time", now)
                        print(f"[CATALOG] Önbellekten yüklendi: {len(self.channels)} kanal, {len(self.all_expanded_streams)} alternatif yayın.")
                        return
                except Exception as e:
                    print(f"[CATALOG] Önbellek okuma uyarısı: {e}")

            print("[CATALOG] Nuvio-Addons katalogları indiriliyor...")
            catalogs = [
                ("birdirbir", f"{NUVIO_BASE}/catalog/tv/birdirbir-live.json"),
                ("wiospor", f"{NUVIO_BASE}/catalog/tv/wiospor-live.json"),
            ]

            loaded_channels = []
            seen_ids = set()

            for prefix, cat_url in catalogs:
                try:
                    r = requests.get(cat_url, headers={"User-Agent": USER_AGENT}, timeout=10)
                    if r.status_code == 200:
                        metas = r.json().get("metas", [])
                        for m in metas:
                            cid = m.get("id")
                            if cid in seen_ids:
                                continue
                            seen_ids.add(cid)

                            raw_name = m.get("name", "")
                            cleaned = clean_title(raw_name)
                            group = self.get_group(cid, cleaned)
                            poster = m.get("poster") or ""
                            desc = m.get("description") or ""

                            loaded_channels.append({
                                "id": cid,
                                "raw_name": raw_name,
                                "name": cleaned,
                                "group": group,
                                "logo": poster,
                                "desc": desc,
                                "catalog": prefix
                            })
                except Exception as e:
                    print(f"[CATALOG] {prefix} yükleme hatası: {e}")

            if not loaded_channels:
                print("[CATALOG] Katalog yüklenemedi!")
                return

            self.channels = loaded_channels
            print(f"[CATALOG] {len(self.channels)} kanal tespit edildi. Alternatif yayınlar taranıyor...")

            # Tüm kanalların stream.json verilerini paralel indir
            streams_map = {}
            expanded = []

            with concurrent.futures.ThreadPoolExecutor(max_workers=25) as executor:
                futures = {executor.submit(self.fetch_stream_data, ch): ch for ch in self.channels}
                for future in concurrent.futures.as_completed(futures):
                    ch = futures[future]
                    try:
                        cid, streams = future.result()
                        streams_map[cid] = streams

                        ch_name = ch["name"]
                        ch_group = ch["group"]
                        ch_logo = ch["logo"]

                        for idx, s in enumerate(streams, 1):
                            s_name = s.get("name", "Bilinmeyen Sağlayıcı")
                            s_title = s.get("title", f"Yayın {idx}")
                            s_url = s.get("url", "")
                            if not s_url or not s_url.startswith("http"):
                                continue

                            # Sağlayıcı adını ayrıştır (Spor20x, 8kGold, Eagle, Aslan vb.)
                            provider = "Diğer"
                            if "Spor20x" in s_name or "Spor20x" in s_title:
                                provider = "Spor20x"
                            elif "8kGold" in s_name or "8kGold" in s_title:
                                provider = "8kGold"
                            elif "Eagle" in s_name or "Eagle" in s_title:
                                provider = "Eagle"
                            elif "WorldSport" in s_name:
                                provider = "WorldSport"
                            elif "Aslan" in s_name:
                                provider = "Aslan"
                            elif "PatronHD" in s_name:
                                provider = "PatronHD"
                            elif "VİONTV" in s_name:
                                provider = "VİONTV"
                            elif "JestYayın" in s_name:
                                provider = "JestYayın"
                            elif "Atom" in s_name:
                                provider = "Atom Spor"

                            # Çözünürlük etiketi (4K, 1080p, 720p)
                            quality = ""
                            if "4K" in s_title or "2160p" in s_title:
                                quality = "4K"
                            elif "FHD" in s_title or "1080p" in s_title:
                                quality = "1080p"
                            elif "HD" in s_title or "720p" in s_title:
                                quality = "720p"
                            elif "SD" in s_title:
                                quality = "SD"

                            # Tam başlık (Nuvio arayüzündeki gibi)
                            full_title = f"{s_name} • {s_title}" if s_name not in s_title else s_title
                            full_title = clean_title(full_title)

                            expanded.append({
                                "id": f"{cid}_{idx}",
                                "channel_id": cid,
                                "channel_name": ch_name,
                                "title": full_title,
                                "raw_title": s_title,
                                "provider": provider,
                                "quality": quality,
                                "group": ch_group,
                                "logo": ch_logo,
                                "url": s_url,
                                "behaviorHints": s.get("behaviorHints", {})
                            })
                    except Exception as e:
                        pass

            self.channel_streams = streams_map
            self.all_expanded_streams = expanded
            self.last_sync = now

            print(f"[CATALOG] Senkronizasyon tamamlandı! Toplam {len(self.channels)} kanal ve {len(self.all_expanded_streams)} alternatif yayın hazır.")

            # Önbelleğe kaydet
            try:
                with open(CACHE_FILE, "w", encoding="utf-8") as f:
                    json.dump({
                        "time": now,
                        "channels": self.channels,
                        "channel_streams": self.channel_streams,
                        "all_expanded_streams": self.all_expanded_streams
                    }, f, ensure_ascii=False)
            except Exception as e:
                print(f"[CATALOG] Önbellek yazma uyarısı: {e}")

CATALOG = CatalogManager()

class StreamResolver:
    """Tekil kanal modu için hızlı ve çalışan yayını çözen motor."""
    def __init__(self):
        self.session = requests.Session()
        self.session.headers.update({"User-Agent": USER_AGENT})
        self.cache = {}

    def get_stream(self, ch_id):
        now = time.time()
        cached = self.cache.get(ch_id)
        if cached and cached["expires"] > now:
            return cached["url"], cached["headers"]

        streams = CATALOG.channel_streams.get(ch_id, [])
        if not streams:
            # Alternatif katalogdan bul
            return None, {}

        # 8kGold, Eagle veya Spor20x öncelikli dene
        for s in streams:
            s_url = s.get("url", "")
            if not s_url:
                continue
            req_headers = {"User-Agent": USER_AGENT}
            hints = s.get("behaviorHints", {}).get("proxyHeaders", {}).get("request", {})
            req_headers.update(hints)

            # URL temizle
            test_url = s_url
            if "play_token=" in test_url:
                test_url = re.sub(r'([?&])play_token=[^&]+(&|$)', r'\1', test_url).rstrip('?&')

            self.cache[ch_id] = {
                "url": test_url,
                "headers": req_headers,
                "expires": now + 600
            }
            return test_url, req_headers

        return None, {}

RESOLVER = StreamResolver()

class ProxyHandler(BaseHTTPRequestHandler):
    def send_cors_headers(self):
        self.send_header("Access-Control-Allow-Origin", "*")
        self.send_header("Access-Control-Allow-Methods", "GET, HEAD, OPTIONS")
        self.send_header("Access-Control-Allow-Headers", "*")

    def do_OPTIONS(self):
        self.send_response(200)
        self.send_cors_headers()
        self.end_headers()

    def do_GET(self):
        try:
            parsed = urllib.parse.urlparse(self.path)
            path = parsed.path
            query = urllib.parse.parse_qs(parsed.query)

            host_header = self.headers.get("Host", f"{LOCAL_IP}:{PORT}")
            base_server = f"http://{host_header}"

            if path in ("", "/", "/index.html"):
                self.serve_dashboard(base_server)
            elif path in ("/playlist.m3u", "/streams.m3u", "/tivimate.m3u"):
                # Kullanıcının tam istediği: Nuvio'daki TÜM alternatif yayınların açık listesi!
                self.serve_expanded_playlist(base_server, group_by="category")
            elif path == "/streams_by_channel.m3u":
                # Kanal bazında klasörlü (beIN 1, beIN 2 vb.)
                self.serve_expanded_playlist(base_server, group_by="channel")
            elif path == "/streams_by_provider.m3u":
                # Sağlayıcı bazında klasörlü (Spor20x, 8kGold, Eagle vb.)
                self.serve_expanded_playlist(base_server, group_by="provider")
            elif path in ("/channels.m3u", "/tekil.m3u"):
                # Klasik tekil 163 kanal listesi
                self.serve_single_channels_playlist(base_server)
            elif path == "/stream":
                url = query.get("url", [None])[0]
                ref = query.get("ref", [""])[0]
                ua = query.get("ua", [USER_AGENT])[0]
                if url:
                    self.serve_stream_proxy(url, ref, ua, base_server)
                else:
                    self.send_error(400, "Missing url parameter")
            elif path.startswith("/live/"):
                ch_id = path[len("/live/"):].replace(".m3u8", "")
                self.serve_single_channel_live(ch_id, base_server)
            elif path == "/ts":
                url = query.get("url", [None])[0]
                ref = query.get("ref", [""])[0]
                ua = query.get("ua", [USER_AGENT])[0]
                if url:
                    self.serve_ts_segment(url, ref, ua)
                else:
                    self.send_error(400, "Missing url parameter")
            elif path == "/api/channel_streams":
                cid = query.get("id", [""])[0]
                self.serve_api_channel_streams(cid, base_server)
            elif path == "/api/refresh":
                CATALOG.sync(force=True)
                self.send_response(200)
                self.send_header("Content-Type", "application/json; charset=utf-8")
                self.send_cors_headers()
                self.end_headers()
                self.wfile.write(b'{"status": "ok", "message": "Catalog refreshed"}')
            else:
                self.send_error(404, "Not Found")
        except Exception as e:
            try:
                self.send_error(500, f"Proxy Hatasi: {e}")
            except Exception:
                pass

    def serve_expanded_playlist(self, base_server, group_by="category"):
        """Tüm alternatif yayınları (Spor20x 4K, 8kGold, Eagle vb.) içeren M3U listesi."""
        items = CATALOG.all_expanded_streams
        lines = [
            "#EXTM3U x-tvg-url=\"https://iptv-epg.org/epg.xml.gz\"",
            f"# PLAYLIST NAME: WioLand IPTV ({len(items)} Alternatif Yayin)",
        ]

        for item in items:
            raw_url = item["url"]
            ref = item.get("behaviorHints", {}).get("proxyHeaders", {}).get("request", {}).get("Referer", "")
            ua = item.get("behaviorHints", {}).get("proxyHeaders", {}).get("request", {}).get("User-Agent", USER_AGENT)

            safe_url = urllib.parse.quote(raw_url, safe="")
            safe_ref = urllib.parse.quote(ref, safe="")
            safe_ua = urllib.parse.quote(ua, safe="")

            stream_proxy_url = f"{base_server}/stream?url={safe_url}&ref={safe_ref}&ua={safe_ua}"

            if group_by == "channel":
                group_title = item["channel_name"]
                display_name = f"{item['title']}"
            elif group_by == "provider":
                group_title = item["provider"]
                display_name = f"{item['channel_name']} • {item['title']}"
            else:
                group_title = item["group"]
                display_name = f"{item['channel_name']} • {item['title']}"

            logo = item.get("logo", "")
            lines.append(f'#EXTINF:-1 tvg-id="{item["channel_id"]}" tvg-name="{display_name}" tvg-logo="{logo}" group-title="{group_title}",{display_name}')
            lines.append(stream_proxy_url)

        content = "\n".join(lines) + "\n"
        self.send_response(200)
        self.send_header("Content-Type", "application/vnd.apple.mpegurl; charset=utf-8")
        self.send_header("Content-Disposition", f"inline; filename=\"wio_{group_by}_streams.m3u\"")
        self.send_cors_headers()
        self.end_headers()
        self.wfile.write(content.encode("utf-8"))

    def serve_single_channels_playlist(self, base_server):
        """Kompakt 163 kanal M3U listesi."""
        lines = ["#EXTM3U x-tvg-url=\"https://iptv-epg.org/epg.xml.gz\""]
        for ch in CATALOG.channels:
            stream_url = f"{base_server}/live/{ch['id']}.m3u8"
            lines.append(f'#EXTINF:-1 tvg-id="{ch["id"]}" tvg-name="{ch["name"]}" tvg-logo="{ch["logo"]}" group-title="{ch["group"]}",{ch["name"]}')
            lines.append(stream_url)

        content = "\n".join(lines) + "\n"
        self.send_response(200)
        self.send_header("Content-Type", "application/vnd.apple.mpegurl; charset=utf-8")
        self.send_header("Content-Disposition", "inline; filename=\"wio_channels.m3u\"")
        self.send_cors_headers()
        self.end_headers()
        self.wfile.write(content.encode("utf-8"))

    def serve_single_channel_live(self, ch_id, base_server):
        url, req_headers = RESOLVER.get_stream(ch_id)
        if not url:
            self.send_error(503, f"Yayin su an cozulemedi: {ch_id}")
            return
        ref = req_headers.get("Referer", "")
        ua = req_headers.get("User-Agent", USER_AGENT)
        self.serve_stream_proxy(url, ref, ua, base_server)

    def serve_stream_proxy(self, target_url, referer, ua, base_server):
        """
        Evrensel Stream Yönlendirici:
        - MPEG-TS akışları (Spor20x, 8kGold, Eagle) kesintisiz aktarır (video/mp2t).
        - Süresi dolmuş play_token parametresini tespit edip otomatik temizler.
        - HLS (.m3u8) çalma listelerini ayrıştırıp segmentleri /ts proxy'sine yönlendirir.
        """
        fetch_headers = {
            "User-Agent": ua or USER_AGENT,
            "Accept": "*/*",
            "Connection": "keep-alive"
        }
        if referer:
            fetch_headers["Referer"] = referer

        # İlk istek
        try:
            r = requests.get(target_url, headers=fetch_headers, stream=True, timeout=7)
        except Exception as e:
            self.send_error(502, f"Akisa baglanilamadi: {e}")
            return

        # play_token süresi dolmuşsa (460 veya 403), token'ı kaldırıp tekrar dene
        if r.status_code in (460, 403) and "play_token=" in target_url:
            clean_url = re.sub(r'([?&])play_token=[^&]+(&|$)', r'\1', target_url).rstrip('?&')
            try:
                r_retry = requests.get(clean_url, headers=fetch_headers, stream=True, timeout=7)
                if r_retry.status_code in (200, 206):
                    r = r_retry
                    target_url = clean_url
            except Exception:
                pass

        if r.status_code not in (200, 206):
            self.send_error(r.status_code, f"Kaynak sunucu yanit vermedi: {r.status_code}")
            return

        content_type = r.headers.get("Content-Type", "").lower()

        # Durum 1: HLS M3U8 Çalma Listesi
        is_m3u8 = "mpegurl" in content_type or target_url.endswith(".m3u8")
        if not is_m3u8:
            # İlk 256 baytı kokla
            try:
                peek = r.raw.peek(256)
                if peek.startswith(b"#EXTM3U"):
                    is_m3u8 = True
            except Exception:
                pass

        if is_m3u8:
            try:
                m3u8_text = r.text
                base_url = target_url.rsplit("/", 1)[0] + "/"

                rewritten_lines = []
                for line in m3u8_text.splitlines():
                    line_str = line.strip()
                    if not line_str:
                        continue
                    if line_str.startswith("#"):
                        rewritten_lines.append(line_str)
                    else:
                        if line_str.startswith("http://") or line_str.startswith("https://"):
                            full_seg_url = line_str
                        else:
                            full_seg_url = urllib.parse.urljoin(base_url, line_str)

                        safe_u = urllib.parse.quote(full_seg_url, safe="")
                        safe_r = urllib.parse.quote(referer, safe="")
                        safe_a = urllib.parse.quote(ua, safe="")
                        proxy_line = f"{base_server}/ts?url={safe_u}&ref={safe_r}&ua={safe_a}"
                        rewritten_lines.append(proxy_line)

                output = "\n".join(rewritten_lines) + "\n"
                self.send_response(200)
                self.send_header("Content-Type", "application/vnd.apple.mpegurl")
                self.send_cors_headers()
                self.end_headers()
                self.wfile.write(output.encode("utf-8"))
                return
            except Exception as e:
                self.send_error(500, f"HLS Parse Hatasi: {e}")
                return

        # Durum 2: MPEG-TS veya Doğrudan Video Akışı (Spor20x, 8kGold, Eagle)
        self.send_response(200)
        self.send_header("Content-Type", "video/mp2t")
        self.send_header("Accept-Ranges", "bytes")
        self.send_cors_headers()
        self.end_headers()

        try:
            for chunk in r.iter_content(chunk_size=65536):
                if chunk:
                    self.wfile.write(chunk)
        except (BrokenPipeError, ConnectionResetError):
            pass
        except Exception:
            pass

    def serve_ts_segment(self, target_url, referer, ua):
        fetch_headers = {
            "User-Agent": ua or USER_AGENT,
            "Accept": "*/*"
        }
        if referer:
            fetch_headers["Referer"] = referer

        if "Range" in self.headers:
            fetch_headers["Range"] = self.headers["Range"]

        try:
            with requests.get(target_url, headers=fetch_headers, stream=True, timeout=8) as r:
                self.send_response(r.status_code)
                self.send_header("Content-Type", "video/mp2t")
                if "Content-Length" in r.headers:
                    self.send_header("Content-Length", r.headers["Content-Length"])
                if "Content-Range" in r.headers:
                    self.send_header("Content-Range", r.headers["Content-Range"])
                self.send_cors_headers()
                self.end_headers()

                for chunk in r.iter_content(chunk_size=65536):
                    if chunk:
                        self.wfile.write(chunk)
        except Exception:
            pass

    def serve_api_channel_streams(self, ch_id, base_server):
        streams = CATALOG.channel_streams.get(ch_id, [])
        result = []
        for idx, s in enumerate(streams, 1):
            raw_url = s.get("url", "")
            if not raw_url:
                continue
            ref = s.get("behaviorHints", {}).get("proxyHeaders", {}).get("request", {}).get("Referer", "")
            ua = s.get("behaviorHints", {}).get("proxyHeaders", {}).get("request", {}).get("User-Agent", USER_AGENT)

            safe_url = urllib.parse.quote(raw_url, safe="")
            safe_ref = urllib.parse.quote(ref, safe="")
            safe_ua = urllib.parse.quote(ua, safe="")
            proxy_url = f"{base_server}/stream?url={safe_url}&ref={safe_ref}&ua={safe_ua}"

            result.append({
                "index": idx,
                "name": s.get("name", ""),
                "title": s.get("title", f"Yayın {idx}"),
                "proxy_url": proxy_url,
                "raw_url": raw_url
            })

        out = json.dumps(result, ensure_ascii=False)
        self.send_response(200)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_cors_headers()
        self.end_headers()
        self.wfile.write(out.encode("utf-8"))

    def serve_dashboard(self, base_server):
        channels = CATALOG.channels
        total_streams = len(CATALOG.all_expanded_streams)
        groups = sorted(list(set(c["group"] for c in channels)))

        html = f"""<!DOCTYPE html>
<html lang="tr">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>WioLand • Tam IPTV & Alternatif Yayın Hub</title>
    <link rel="stylesheet" href="https://cdn.jsdelivr.net/npm/bootstrap@5.3.3/dist/css/bootstrap.min.css">
    <script src="https://cdn.jsdelivr.net/npm/hls.js@latest"></script>
    <style>
        body {{ background-color: #0b0f19; color: #e1e7ed; font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, sans-serif; }}
        .navbar {{ background: #111827; border-bottom: 1px solid #1f2937; }}
        .card {{ background: #111827; border: 1px solid #1f2937; border-radius: 12px; }}
        .card-ch {{ transition: transform 0.15s, border-color 0.15s; }}
        .card-ch:hover {{ border-color: #3b82f6; transform: translateY(-2px); }}
        .btn-brand {{ background: #2563eb; border: none; color: #fff; font-weight: 600; }}
        .btn-brand:hover {{ background: #1d4ed8; color: #fff; }}
        .ch-logo {{ width: 48px; height: 48px; object-fit: contain; border-radius: 8px; background: #0b0f19; padding: 4px; }}
        .badge-group {{ background: #1f2937; color: #60a5fa; border: 1px solid #374151; font-weight: 500; font-size: 0.75rem; }}
        .badge-count {{ background: #064e3b; color: #34d399; font-weight: 600; font-size: 0.75rem; }}
        .url-box {{ background: #070b12; border: 1px solid #1f2937; border-radius: 8px; padding: 10px 14px; font-family: monospace; font-size: 0.92rem; color: #34d399; word-break: break-all; }}
        .filter-btn {{ border-radius: 20px; font-size: 0.85rem; font-weight: 500; }}
        #videoPlayer {{ width: 100%; border-radius: 10px; background: #000; max-height: 480px; }}
        .search-box {{ background: #111827; border: 1px solid #374151; color: #fff; border-radius: 10px; }}
        .search-box:focus {{ background: #111827; border-color: #3b82f6; color: #fff; box-shadow: none; }}
        .modal-content {{ background-color: #111827; border: 1px solid #374151; color: #fff; border-radius: 14px; }}
        .modal-header {{ border-bottom: 1px solid #1f2937; }}
        .modal-footer {{ border-top: 1px solid #1f2937; }}
        .stream-row {{ background: #1f2937; border-radius: 8px; padding: 10px 14px; margin-bottom: 8px; display: flex; align-items: center; justify-content: space-between; }}
        .stream-row:hover {{ background: #374151; }}
        .badge-provider {{ font-size: 0.75rem; font-weight: bold; background: #2563eb; color: #fff; }}
        .badge-res {{ font-size: 0.75rem; background: #059669; color: #fff; }}
    </style>
</head>
<body>
    <nav class="navbar navbar-dark py-3">
        <div class="container d-flex justify-content-between align-items-center">
            <span class="navbar-brand mb-0 h1 d-flex align-items-center gap-2">
                <span style="font-size: 1.6rem;">⚡</span>
                <strong>WioLand IPTV Hub</strong>
                <span class="badge bg-success ms-2">{len(channels)} Kanal</span>
                <span class="badge bg-primary ms-1">{total_streams} Canlı Yayın</span>
            </span>
            <div class="d-flex align-items-center gap-3">
                <button class="btn btn-sm btn-outline-secondary" onclick="refreshCatalog()">🔄 Kataloğu Yenile</button>
                <span class="text-secondary small d-none d-md-inline">IP: {LOCAL_IP}:{PORT}</span>
            </div>
        </div>
    </nav>

    <div class="container my-4">
        <!-- TiviMate Playlist Kutuları -->
        <div class="p-4 mb-4 card shadow-sm">
            <div class="d-flex align-items-center justify-content-between mb-2">
                <h5 class="fw-bold text-white mb-0">📺 TiviMate & Smart TV M3U Çalma Listeleri</h5>
                <span class="badge bg-warning text-dark fw-bold">Nuvio Alternatif Yayınları Aktif</span>
            </div>
            <p class="text-secondary small mb-3">TiviMate, VLC, Smart TV veya IPTV oynatıcınıza eklemek için aşağıdaki linklerden birini seçin:</p>
            
            <!-- Ana Alternatif Yayın Linki (Resimdeki Nuvio listesi) -->
            <div class="card p-3 mb-3" style="background: #0d1527; border-color: #2563eb;">
                <div class="d-flex justify-content-between align-items-center mb-1">
                    <strong class="text-info">⭐ Tüm Alternatif Yayınlar Listesi (Spor20x 4K, 8kGold, Eagle, Aslan vb. ~{total_streams} Yayın)</strong>
                    <span class="badge bg-info text-dark">Önerilen (Resimdeki Gibi)</span>
                </div>
                <p class="text-secondary small mb-2">Her kanalın altındaki tüm 4K, FHD, HD yayınları (Yayın 1, Yayın 2, Yayın 4, 8kGold vb.) ayrı ayrı TiviMate'te listeler.</p>
                <div class="row g-2 align-items-center">
                    <div class="col-md-9">
                        <div class="url-box">{base_server}/streams.m3u</div>
                    </div>
                    <div class="col-md-3">
                        <button class="btn btn-brand w-100" onclick="copyUrl('{base_server}/streams.m3u')">📋 Bu Listeyi Kopyala</button>
                    </div>
                </div>
            </div>

            <!-- Diğer Formatlar -->
            <div class="row g-2">
                <div class="col-md-4">
                    <div class="card p-2 h-100">
                        <div class="small fw-bold text-white mb-1">📁 Kanal Bazında Klasörlü</div>
                        <div class="text-secondary small mb-2" style="font-size:0.78rem;">beIN 1, beIN 2 klasörleri içinde tüm yayınlar</div>
                        <button class="btn btn-sm btn-outline-info w-100 mt-auto" onclick="copyUrl('{base_server}/streams_by_channel.m3u')">📋 Kopyala (/streams_by_channel.m3u)</button>
                    </div>
                </div>
                <div class="col-md-4">
                    <div class="card p-2 h-100">
                        <div class="small fw-bold text-white mb-1">🏷️ Sağlayıcı Bazında Klasörlü</div>
                        <div class="text-secondary small mb-2" style="font-size:0.78rem;">Spor20x, 8kGold, Eagle klasörleri</div>
                        <button class="btn btn-sm btn-outline-warning w-100 mt-auto" onclick="copyUrl('{base_server}/streams_by_provider.m3u')">📋 Kopyala (/streams_by_provider.m3u)</button>
                    </div>
                </div>
                <div class="col-md-4">
                    <div class="card p-2 h-100">
                        <div class="small fw-bold text-white mb-1">⚡ Tekil Kanallar (163 Kanal)</div>
                        <div class="text-secondary small mb-2" style="font-size:0.78rem;">Kanal başına tek link (Otomatik çözücü)</div>
                        <button class="btn btn-sm btn-outline-success w-100 mt-auto" onclick="copyUrl('{base_server}/channels.m3u')">📋 Kopyala (/channels.m3u)</button>
                    </div>
                </div>
            </div>
        </div>

        <!-- Video Oynatıcı Alanı -->
        <div id="playerSection" class="p-3 mb-4 card shadow-sm d-none">
            <div class="d-flex justify-content-between align-items-center mb-2">
                <h6 id="playerTitle" class="fw-bold text-white mb-0">Canlı Yayın</h6>
                <button class="btn btn-sm btn-outline-secondary" onclick="closePlayer()">✕ Kapat</button>
            </div>
            <video id="videoPlayer" controls autoplay muted playsinline></video>
        </div>

        <!-- Filtreleme & Arama -->
        <div class="row g-2 mb-3 align-items-center">
            <div class="col-md-5">
                <input type="text" id="searchInput" class="form-control search-box" placeholder="🔍 Kanal ara (beIN, S Sport, Exxen, Tivibu)..." onkeyup="filterChannels()">
            </div>
            <div class="col-md-7 d-flex flex-wrap gap-1">
                <button class="btn btn-sm btn-primary filter-btn active" onclick="setGroupFilter('all', this)">Hepsi ({len(channels)})</button>
"""
        for g in groups:
            g_safe = urllib.parse.quote(g)
            g_count = sum(1 for c in channels if c["group"] == g)
            html += f"""<button class="btn btn-sm btn-outline-secondary filter-btn" onclick="setGroupFilter('{g_safe}', this)">{g} ({g_count})</button>\n"""

        html += f"""
            </div>
        </div>

        <!-- Kanal Grid -->
        <div class="row row-cols-1 row-cols-md-2 row-cols-lg-3 g-3" id="channelGrid">
"""
        for ch in channels:
            cid = ch["id"]
            c_streams = CATALOG.channel_streams.get(cid, [])
            stream_count = len(c_streams)
            count_badge = f"{stream_count} Yayın Seçeneği" if stream_count > 0 else "Canlı"

            html += f"""
            <div class="col ch-item" data-name="{ch['name'].lower()}" data-group="{urllib.parse.quote(ch['group'])}">
                <div class="card card-ch p-3 h-100 d-flex flex-row align-items-center justify-content-between">
                    <div class="d-flex align-items-center gap-3 overflow-hidden">
                        <img src="{ch['logo']}" class="ch-logo flex-shrink-0" onerror="this.src='https://via.placeholder.com/48?text=TV'">
                        <div class="overflow-hidden">
                            <div class="fw-bold text-white text-truncate mb-1" title="{ch['name']}" style="font-size: 0.95rem;">{ch['name']}</div>
                            <div class="d-flex gap-1 flex-wrap">
                                <span class="badge badge-group text-truncate">{ch['group']}</span>
                                <span class="badge badge-count">{count_badge}</span>
                            </div>
                        </div>
                    </div>
                    <button class="btn btn-sm btn-brand flex-shrink-0 ms-2" onclick="openStreamModal('{cid}', '{ch['name']}')">
                        📺 Yayınlar ({stream_count})
                    </button>
                </div>
            </div>
"""

        html += f"""
        </div>
    </div>

    <!-- Alternatif Yayınlar Modalı (Nuvio Ekranı Gibi) -->
    <div class="modal fade" id="streamModal" tabindex="-1" aria-hidden="true">
        <div class="modal-dialog modal-dialog-centered modal-lg modal-dialog-scrollable">
            <div class="modal-content">
                <div class="modal-header">
                    <div>
                        <h5 class="modal-title fw-bold" id="modalChannelName">Kanal Adı</h5>
                        <div class="small text-secondary" id="modalStreamCount">0 alternatif yayın bulundu</div>
                    </div>
                    <button type="button" class="btn-close btn-close-white" data-bs-dismiss="modal" aria-label="Close"></button>
                </div>
                <div class="modal-body" id="modalStreamList">
                    <div class="text-center py-4 text-secondary">Yayınlar yükleniyor...</div>
                </div>
                <div class="modal-footer">
                    <button type="button" class="btn btn-sm btn-secondary" data-bs-dismiss="modal">Kapat</button>
                </div>
            </div>
        </div>
    </div>

    <script src="https://cdn.jsdelivr.net/npm/bootstrap@5.3.3/dist/js/bootstrap.bundle.min.js"></script>
    <script>
        function copyUrl(url) {{
            navigator.clipboard.writeText(url).then(() => {{
                alert('M3U Adresi Kopyalandı:\\n' + url + '\\n\\nBu adresi TiviMate çalma listesi (M3U) olarak ekleyin.');
            }});
        }}

        function refreshCatalog() {{
            fetch('/api/refresh').then(r => r.json()).then(d => {{
                alert('Katalog güncellendi! Sayfa yenileniyor...');
                location.reload();
            }});
        }}

        let currentGroup = 'all';

        function setGroupFilter(group, btn) {{
            currentGroup = group;
            document.querySelectorAll('.filter-btn').forEach(b => {{
                b.classList.remove('btn-primary', 'active');
                b.classList.add('btn-outline-secondary');
            }});
            btn.classList.remove('btn-outline-secondary');
            btn.classList.add('btn-primary', 'active');
            filterChannels();
        }}

        function filterChannels() {{
            const query = document.getElementById('searchInput').value.toLowerCase().trim();
            const items = document.querySelectorAll('.ch-item');

            items.forEach(el => {{
                const name = el.getAttribute('data-name');
                const group = el.getAttribute('data-group');
                const matchesQuery = !query || name.includes(query);
                const matchesGroup = currentGroup === 'all' || group === currentGroup;

                if (matchesQuery && matchesGroup) {{
                    el.classList.remove('d-none');
                }} else {{
                    el.classList.add('d-none');
                }}
            }});
        }}

        const streamModalObj = new bootstrap.Modal(document.getElementById('streamModal'));

        function openStreamModal(cid, name) {{
            document.getElementById('modalChannelName').innerText = name;
            document.getElementById('modalStreamList').innerHTML = '<div class=\"text-center py-4 text-secondary\">Yayınlar listeleniyor...</div>';
            streamModalObj.show();

            fetch('/api/channel_streams?id=' + cid)
                .then(r => r.json())
                .then(streams => {{
                    document.getElementById('modalStreamCount').innerText = streams.length + ' alternatif yayın kaynağı (Resimdeki Nuvio listesi)';
                    if (!streams || streams.length === 0) {{
                        document.getElementById('modalStreamList').innerHTML = '<div class=\"text-center py-4 text-warning\">Bu kanal için alternatif yayın bulunamadı.</div>';
                        return;
                    }}

                    let html = '';
                    streams.forEach(s => {{
                        const title = s.title || ('Yayın ' + s.index);
                        const prov = s.name || 'Bilinmeyen';
                        const safeUrl = encodeURIComponent(s.proxy_url);

                        let resBadge = '';
                        if (title.includes('4K') || title.includes('2160p')) resBadge = '<span class=\"badge bg-danger\">4K UHD</span>';
                        else if (title.includes('FHD') || title.includes('1080p')) resBadge = '<span class=\"badge bg-primary\">1080p FHD</span>';
                        else if (title.includes('HD') || title.includes('720p')) resBadge = '<span class=\"badge bg-success\">720p HD</span>';

                        html += `
                        <div class=\"stream-row\">
                            <div class=\"d-flex align-items-center gap-2 overflow-hidden\">
                                <span class=\"badge badge-provider flex-shrink-0\">${{prov}}</span>
                                ${{resBadge}}
                                <div class=\"fw-bold text-white text-truncate\" style=\"font-size:0.9rem;\">${{title}}</div>
                            </div>
                            <div class=\"d-flex gap-2 flex-shrink-0 ms-2\">
                                <button class=\"btn btn-sm btn-outline-info\" onclick=\"navigator.clipboard.writeText('${{s.proxy_url}}'); alert('Yayın linki kopyalandı!');\">📋 Link</button>
                                <button class=\"btn btn-sm btn-success\" onclick=\"streamModalObj.hide(); playChannel('${{s.proxy_url}}', '${{name}} - ${{title}}');\">▶ Oynat</button>
                            </div>
                        </div>`;
                    }});
                    document.getElementById('modalStreamList').innerHTML = html;
                }})
                .catch(err => {{
                    document.getElementById('modalStreamList').innerHTML = '<div class=\"text-center py-4 text-danger\">Hata: ' + err + '</div>';
                }});
        }}

        let currentHls = null;
        function playChannel(url, name) {{
            const section = document.getElementById('playerSection');
            const title = document.getElementById('playerTitle');
            const video = document.getElementById('videoPlayer');
            section.classList.remove('d-none');
            title.innerText = 'Canlı Yayın: ' + name;

            if (currentHls) {{
                currentHls.destroy();
                currentHls = null;
            }}

            if (url.includes('.m3u8') && Hls.isSupported()) {{
                const hls = new Hls();
                hls.loadSource(url);
                hls.attachMedia(video);
                hls.on(Hls.Events.MANIFEST_PARSED, function() {{
                    video.play();
                }});
                currentHls = hls;
            }} else {{
                video.src = url;
                video.play().catch(e => console.log('Autoplay error:', e));
            }}
            window.scrollTo({{ top: 0, behavior: 'smooth' }});
        }}

        function closePlayer() {{
            const section = document.getElementById('playerSection');
            const video = document.getElementById('videoPlayer');
            if (currentHls) {{
                currentHls.destroy();
                currentHls = null;
            }}
            video.pause();
            section.classList.add('d-none');
        }}
    </script>
</body>
</html>"""
        self.send_response(200)
        self.send_header("Content-Type", "text/html; charset=utf-8")
        self.send_cors_headers()
        self.end_headers()
        self.wfile.write(html.encode("utf-8"))

def write_local_playlists():
    try:
        base_server = f"http://{LOCAL_IP}:{PORT}"
        # 1. streams.m3u (Tam alternatifli liste - Nuvio ekranındaki gibi)
        items = CATALOG.all_expanded_streams
        lines = [
            "#EXTM3U x-tvg-url=\"https://iptv-epg.org/epg.xml.gz\"",
            f"# PLAYLIST: WioLand IPTV ({len(items)} Alternatif Yayin)",
        ]
        for item in items:
            raw_url = item["url"]
            ref = item.get("behaviorHints", {}).get("proxyHeaders", {}).get("request", {}).get("Referer", "")
            ua = item.get("behaviorHints", {}).get("proxyHeaders", {}).get("request", {}).get("User-Agent", USER_AGENT)
            safe_url = urllib.parse.quote(raw_url, safe="")
            safe_ref = urllib.parse.quote(ref, safe="")
            safe_ua = urllib.parse.quote(ua, safe="")
            stream_proxy_url = f"{base_server}/stream?url={safe_url}&ref={safe_ref}&ua={safe_ua}"

            display_name = f"{item['channel_name']} • {item['title']}"
            logo = item.get("logo", "")
            lines.append(f'#EXTINF:-1 tvg-id="{item["channel_id"]}" tvg-name="{display_name}" tvg-logo="{logo}" group-title="{item["group"]}",{display_name}')
            lines.append(stream_proxy_url)

        with open("streams.m3u", "w", encoding="utf-8") as f:
            f.write("\n".join(lines) + "\n")

        # 2. playlist.m3u dosyasını da bu tam listeyle senkronize et
        with open("playlist.m3u", "w", encoding="utf-8") as f:
            f.write("\n".join(lines) + "\n")

        print(f"[OK] 'streams.m3u' ve 'playlist.m3u' ({len(items)} alternatif yayın) yerel dizine yazıldı.")
    except Exception as e:
        print(f"[UYARI] Yerel dosya yazma hatası: {e}")

def main():
    print("=" * 68)
    print("   [+] WioLand / Nuvio-Addons Tam IPTV & M3U Proxy Sunucusu v2.0")
    print("=" * 68)

    # Başlangıçta tüm katalogları ve 5,700+ yayını senkronize et
    CATALOG.sync(force=False)
    write_local_playlists()

    print("\n" + "=" * 68)
    print(f" 🌐 Web Kontrol Paneli    : http://localhost:{PORT}")
    print(f" 🌐 Ağ Kontrol Paneli    : http://{LOCAL_IP}:{PORT}")
    print("=" * 68)
    print(" 📺 TiviMate / Smart TV M3U Linkleri:")
    print(f"  ⭐ TÜM YAYINLAR (Resimdeki Gibi) : http://{LOCAL_IP}:{PORT}/streams.m3u")
    print(f"  📁 Kanal Bazında Klasörlü        : http://{LOCAL_IP}:{PORT}/streams_by_channel.m3u")
    print(f"  🏷️  Sağlayıcı Bazında Klasörlü     : http://{LOCAL_IP}:{PORT}/streams_by_provider.m3u")
    print(f"  ⚡ Tekil 163 Kanal (Otomatik)    : http://{LOCAL_IP}:{PORT}/channels.m3u")
    print("=" * 68)
    print("Sunucu aktif. TiviMate oynatıcınıza 'streams.m3u' linkini ekleyin.")
    print("Durdurmak için Ctrl+C tuşlarına basın.\n")

    ThreadingHTTPServer.allow_reuse_address = True
    server = ThreadingHTTPServer((HOST, PORT), ProxyHandler)
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        print("\nSunucu kapatıldı.")

if __name__ == "__main__":
    main()
