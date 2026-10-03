# ⚡ Aypitivi • TiviMate Kanal Klasörlü & Otomatik Temizlenen IPTV Listesi

Nuvio-Addons (WioSpor & Birdirbir) kataloglarındaki tüm spor ve TV kanallarını toplayıp, **çalışmayan ölü yayınları otomatik ayıklayarak** doğrudan **TiviMate, Smart TV ve IPTV oynatıcıları** için kanal bazında klasörlü sunan IPTV deposudur.

GitHub Actions sayesinde **her 6 saatte bir** otomatik olarak çalışmayan yayınlar elenir ve liste daima güncel kalır. **Bilgisayarınızı açık tutmanıza gerek yoktur.**

---

## 📺 TiviMate / Smart TV M3U Çalma Listesi Linki

TiviMate veya herhangi bir IPTV uygulamasına aşağıdaki linki eklemeniz yeterlidir:

```text
https://raw.githubusercontent.com/emrek92/aypitivi/main/playlist.m3u
```

### 📱 TiviMate Kurulum Adımları
1. **TiviMate** uygulamasını açın.
2. **Ayarlar (Settings)** ➔ **Çalma Listeleri (Playlists)** ➔ **Çalma Listesi Ekle (Add playlist)**.
3. **M3U Çalma Listesi** seçeneğini seçin.
4. Çalma listesi URL kutusuna yukarıdaki adresi yapıştırın:
   `https://raw.githubusercontent.com/emrek92/aypitivi/main/playlist.m3u`
5. Kaydedin. Kanallar ve tüm alternatif yayınlar anında yüklenecektir.

---

## 📁 Kanal Bazında Klasör Yapısı (TiviMate Görünümü)

Tüm yayınlar kanal bazında klasörlenmiştir. TiviMate sol menüsünde ilgili kanal klasörüne tıkladığınızda o kanalın tüm 4K, FHD ve alternatif yayınlarını görürsünüz:

* 📁 **beIN Sports 1** *(Spor20x 4K Yayın 1..10, FHD Yayın 11..20, 8kGold, Eagle...)*
* 📁 **beIN Sports 2** *(FHD Yayın 1..20, 8kGold, Eagle...)*
* 📁 **beIN Sports 3**
* 📁 **beIN Sports 4**
* 📁 **beIN Sports 5**
* 📁 **beIN Sports MAX 1 & MAX 2**
* 📁 **beIN Sports Haber**
* 📁 **S Sport 1 & S Sport 2 & Plus**
* 📁 **Tivibu Spor 1, 2, 3, 4**
* 📁 **Exxen Spor 1 .. 8**
* 📁 **Tabii Spor 1 .. 6**
* 📁 **Smart Spor 1 & 2**
* 📁 **Eurosport 1 & 2**
* 📁 **TRT Spor & A Spor & HT Spor**
* 📁 **Ulusal Kanallar** *(TRT 1, ATV, Kanal D, Show TV, Star TV, TV8, TV8.5, NOW, Sözcü TV...)*
* 📁 **Dünya Spor Kanalları** *(Sky Sports F1/Premier League, TNT Sports 1..4, DAZN, Canal+...)*

> **Toplam: 126 Kanal Klasörü ve 4.900+ Çalışan Canlı Yayın**

---

## 🤖 Otomatik Güncelleme (GitHub Actions)

Depoda bulunan `.github/workflows/playlist.yml` otomasyonu:
* **Her 6 saatte bir** Nuvio'dan en son güncel yayınları çeker.
* 35 paralel iş parçacığıyla her yayını canlı test eder; **HTTP 403, 404, 500, zaman aşımı ve ölü linkleri ayıklar**.
* Yalnızca çalışan yayınları `playlist.m3u` dosyasına işleyip repoya otomatik commit atar.
* Televizyonunuz listenin en güncel halini doğrudan GitHub'dan çeker.

---

## 💻 İsteğe Bağlı: Yerel Proxy Sunucusu (wio_proxy.py)

Bilgisayarınız üzerinden yerel ağda yayın yapmak veya tarayıcıdan izlemek isterseniz:
1. `start.bat` dosyasına çift tıklayın.
2. Web Kontrol Paneli: `http://localhost:8089`
3. Yerel Ağ M3U: `http://192.168.1.139:8089/streams.m3u`
