# Çoban: Shepherd Robotics'in Türkiye'ye Uyarlanmış Klonu

**Ödev:** Hacker News, Y Combinator ve YC RFS (2026 ve sonrası) incelenerek teknolojik "deprem" niteliğinde bir ürün belirlenmesi, klonlanması ve yerelleştirilmiş / yenilikçi bir versiyonunun geliştirilmesi.
**Seçilen ürün:** Shepherd Robotics (YC Fall 2026)
**Teslim:** Bu depo. Kod, testler, demo videoları ([docs/demo/](docs/demo/)) ve bu rapor.

---

## 1. Özet

Shepherd Robotics, yapay zekâ altyapısı (veri merkezleri) ve ileri üretim için beceri gerektiren fiziksel işleri yapan, **robot foundation model** ile yönetilen genel amaçlı robotlar geliştiriyor.

Bu projede iki şey yapıldı:

1. **Klon:** Shepherd'in temel döngüsünün çalışan bir kopyası. Kamera görüntüsü ve doğal dil komutu bir görme-dil modeline gidiyor, model eylem kararı veriyor, karar robot kola fiziksel hareket olarak iletiliyor.
2. **"Çoban":** Türk sanayisine uyarlanmış yenilikçi sürüm. Şunları içeriyor:
   - Türkçe komutla **kapalı döngü** çok adımlı görev yürütme ve kendi kendini doğrulama
   - Donanımsız demo için **dijital ikiz** (simülasyon)
   - Bursa ve İzmir'deki otomotiv tedarikçilerine yönelik **kablo demeti kitting ve kalite kontrol** senaryosu
   - **KVKK uyumlu** yüz anonimleştirme
   - Shepherd'in öğrenme yaklaşımının karşılığı olan **veri çarkı** (her görevin veri seti olarak kaydı)

---

## 2. Araştırma: neden bu ürün bir "deprem"?

### 2.1 YC Requests for Startups (Fall 2026)

YC'nin güncel RFS listesindeki [ycombinator.com/rfs](https://www.ycombinator.com/rfs) maddelerin birçoğu doğrudan fiziksel yapay zekâ ve robotik ile ilgili:

- **"New Operating Systems for the Physical World"** (Charlie Warren): "Robots actually deployed in the field" ve "what does safety look like when humans and robots work literally side-by-side?" ifadelerini içeriyor. Dikkat çekici bir nokta: Charlie Warren aynı zamanda **Shepherd Robotics'in YC partneri**.
- **"Compute at Sea"**: "data centers are running out of electricity and land". Veri merkezi inşasındaki darboğazı anlatıyor; Shepherd'in hedef pazarı da bu.
- **"Data for the Real World"**: robotlarla gerçek dünyadan veri toplanması.
- **"The Future of American Defense"**: "advanced manufacturing".

### 2.2 Y Combinator 2026 grupları

Fiziksel yapay zekâ 2026 gruplarının en büyük temalarından biri. Bir analize göre S26, F26 ve W27 gruplarında **32 robotik / fiziksel YZ şirketi** var; bu, YZ altyapı şirketlerinin sayısıyla aynı ([pinggy.io](https://pinggy.io/blog/what_yc_is_funding_in_2026/)). Aynı alandaki bazı örnekler ([YC listesi](https://www.ycombinator.com/companies/industry/manufacturing-and-robotics)):

| Şirket | Grup | Ne yapıyor |
|---|---|---|
| **Shepherd Robotics** | F26 | Veri merkezi ve elektronik üretimi için foundation model'li genel amaçlı robotlar |
| Lambda Robotics | F26 | Frontier YZ altyapısı için robotlar (en yakın rakip) |
| Deploy | F26 | Genel amaçlı robotlarla gerçek iş arasındaki katman |
| Proprio Robotics | S26 | Veri merkezi operasyon ve bakımı için fiziksel zekâ |
| Shiraz AI | S26 | Tek bir insan gösteriminden üretim görevi öğrenen robotlar |
| Tenet Industries | P26 | Elektronik üretim hizmetleri için YZ ile otomatikleştirilmiş fabrikalar |

### 2.3 Hacker News (2026)

Robot foundation model'leri 2026'da HN'nin en çok konuşulan konularından biri:

| Başlık | Tarih | Puan |
|---|---|---|
| [Gemini Robotics 2 brings whole body intelligence to robots](https://news.ycombinator.com/item?id=49111237) | 30.07.2026 | 620 (558 yorum) |
| [Xiaomi-Robotics-1](https://news.ycombinator.com/item?id=48974454) | 20.07.2026 | 528 |
| [Mistral's Robostral Navigate](https://news.ycombinator.com/item?id=48832212) | 08.07.2026 | 488 |
| [BMW Group to deploy humanoid robots in production in Germany](https://news.ycombinator.com/item?id=47253892) | 04.03.2026 | 225 |
| [Gemini Robotics-ER 1.6](https://news.ycombinator.com/item?id=47779094) | 15.04.2026 | 219 |
| [Qwen-Robot Suite](https://news.ycombinator.com/item?id=48554814) | 16.06.2026 | 213 |
| [Launch HN: Nori Robotics (YC S26)](https://news.ycombinator.com/item?id=49525153) | 01.09.2026 | 201 |

Shepherd Robotics'in kendisi henüz HN'de paylaşılmadı (Fall 2026 grubu yeni). Bu da şirketin çok erken aşamada olduğunu, yani bu ödevin çok güncel bir ürünü ele aldığını gösteriyor.

### 2.4 Neden "deprem"?

Klasik endüstriyel otomasyon her görev için ayrı ayrı programlanır ve görev değiştiğinde yeniden programlanması gerekir. Robot foundation model'leri ise doğal dil komutuyla **yeni görevlere genellenebiliyor**. Bu, otomasyonun ekonomisini değiştiriyor: küçük partili, sık değişen ve el becerisi isteyen işler ilk kez otomatikleştirilebilir hale geliyor. Google (Gemini Robotics 2), Physical Intelligence (π0.7), Xiaomi, Alibaba (Qwen-Robot) ve Mistral'in 2026'da aynı alana girmesi bu kırılmanın göstergesi.

---

## 3. Seçilen ürün: Shepherd Robotics

Kaynak: [YC şirket sayfası](https://www.ycombinator.com/companies/shepherd-robotics)

- **Ürün:** Yapay zekâ altyapısı ve ileri üretimde beceri gerektiren fiziksel işler için genel amaçlı robotlar. Hedef pazarlar: veri merkezi inşası ve operasyonu, elektrik ve elektronik üretimi, kablo demeti montajı.
- **Teknik yaklaşım:**
  - Robot foundation model'ler
  - Gerçek dünya ve simülasyon verisiyle eğitim
  - Sahadaki her robotun deneyimini pekiştirmeli öğrenme döngüsüne geri beslemesi
  - Modüler donanım
- **Ekip:** Feifei Duan (CEO; Waymo, Chef Robotics), David Fang (CTO; Dyna Robotics, Cruise), Kai Ru (Cruise, Rivian). 4 kişi, San Francisco.

---

## 4. Klon (85 puanlık kısım)

| Shepherd'in yaptığı | Bu projedeki karşılığı | Dosya |
|---|---|---|
| Doğal dil + görüntüden eylem üreten foundation model | Gemini, yapılandırılmış JSON şemasıyla AL/BIRAK kararı ve hedef nokta üretiyor | `vla_engine.py` |
| Kamera ile algılama | OpenCV ile kamera, gerçek çözünürlük tespiti | `vision_capture.py` |
| Algıdan fiziksel harekete geçiş | Kamera → robot kalibrasyonu (homografi), güvenli yaklaşma, tutma ve geri çekilme dizileri | `calibration.py`, `task_runner.py` |
| Robot donanımı ve kontrolü | Seri port JSON protokolü, her komutta `DONE` onayı, Arduino/STM32 firmware'i | `serial_controller.py`, `firmware/` |
| Simülasyonla eğitim ve test | Dijital ikiz (bkz. 5.2) | `simulator.py` |
| Sahadan öğrenme döngüsü | Episode veri seti kaydı (bkz. 5.4) | `episode_logger.py` |

---

## 5. Yerelleştirme ve yenilik: "Çoban" (100+ puanlık kısım)

### 5.1 Türkiye bağlamı: neden kablo demeti?

- **Kablo demeti sektörü:**
  - Türkiye otomotiv kablo demeti pazarı 2025'te yaklaşık **1,16 milyar USD**; 2034'te 1,56 milyar USD olması bekleniyor ([IMARC](https://www.imarcgroup.com/turkey-automotive-wiring-harness-market)).
  - Türkiye 2024'te 1,49 milyon araç üretti (aynı kaynak).
  - Yazaki'nin Gemlik ve Mudanya (Bursa) ile Kuzuluk'taki (Sakarya) tesislerinde 2016'da yaklaşık 6.600 kişi çalışıyordu ([olay.com.tr](https://www.olay.com.tr/yazaki-yeni-projelerle-kapasitesini-artiriyor-35464)).
  - Kablo demeti montajı ve kitting **emek yoğun**, ürün çeşitliliği yüksek ve sık değişen işlerdir. Klasik robotlarla otomatikleştirilmesi zordur; bu tam da foundation model'li robotların hedeflediği iş türü.
- **Düşük robot yoğunluğu:**
  - Dünya ortalaması 10.000 imalat çalışanı başına **162 robot** (IFR World Robotics 2025, [kaynak](https://www.industrial-production-worldwide.com/news/world-robotics-2025-report-reveals-south-korea-singapore-and-germany-have-highest-robot-density)).
  - Türkiye için **43** rakamı veriliyor ([Ekonomi Gazetesi, 24.08.2026](https://www.ekonomigazetesi.com/kobi/akilli-fabrikalar-robotik-otomasyonla-yeni-uretim-donemine-geciyor-86063)). Bu rakamın hangi IFR yılına ait olduğu belirtilmemiş.
  - Türkiye 2024'te 3.551 robot alarak dünyanın 14. büyük robot pazarı oldu ([Hürriyet Daily News](https://www.hurriyetdailynews.com/amp/turkiye-ranks-14th-globally-in-robotics-market-214152)).
  - Yani pazar büyüyor ama yoğunluk hâlâ düşük: KOBİ'ler için ucuz ve programlanması kolay robotik büyük bir fırsat.
- **Veri merkezleri:** 2026–2030 Yapay Zekâ Eylem Planı, 2030'a kadar en az **1 GW** veri merkezi kapasitesi ve en az 10 milyar USD özel yatırım hedefliyor ([Webtekno, 04.09.2026](https://www.webtekno.com/turkiye-veri-merkezi-kapasitesi-2030-hedefi-belirlendi-h223648.html)). Bu, Shepherd'in ABD'deki ikinci pazarının Türkiye'de de oluşacağını gösteriyor.
- **KVKK:**
  - 7499 sayılı Kanun ile KVKK'nın 9. maddesi (yurt dışına veri aktarımı) değişti ve 01.06.2024'te yürürlüğe girdi. Yönetmelik 10.07.2024 tarihli Resmî Gazete'de yayımlandı ([Erdem & Erdem](https://www.erdem-erdem.av.tr/bilgi-bankasi/kisisel-verilerin-korunmasi-kanunu-nda-neler-degisti)).
  - Fabrika kamerasında görünen işçi yüzleri kişisel veridir. Bu görüntülerin yurt dışındaki bir bulut modele gönderilmesi 9. madde kapsamına girer.
  - Bu nedenle sistem, görüntüler cihazdan çıkmadan önce yüzleri anonimleştiriyor (bkz. 5.5).

### 5.2 Yenilik 1: Dijital ikiz (simülasyon)

`simulator.py` sanal bir masa, tepeden bakan sanal bir kamera ve fiziği olan sanal bir robot kol içeriyor:

- tutma toleransı,
- nesnelerin gripper'la birlikte taşınması,
- üst üste bırakılan nesnelerin boş yere kayması,
- isteğe bağlı rastgele tutma hatası.

Sanal bileşenler gerçek kamera ve robotla **aynı arayüzü** kullanıyor. Bu yüzden Gemini, kalibrasyon, hareket dizileri ve doğrulama, donanım olmadan birebir aynı kodla çalışıyor. Shepherd de modellerini gerçek ve simülasyon verisinin karışımıyla eğitiyor; bu, aynı yaklaşımın küçük ölçekli bir karşılığı.

İki sahne var:
- `renkler`: renkli küp, silindir ve kutular (genel demo)
- `kablo`: **kablo demeti kitting hücresi**. Siyah ve beyaz konnektörler, sigortalar, bir KIT tepsisi, bir HURDA kutusu ve **çatlak bir konnektör** içeriyor. "Çatlak olan konnektörü hurda kutusuna at" gibi komutlarla **görsel kalite kontrol** de yapılabiliyor; bu Shepherd'in tanımında olmayan bir kullanım.

### 5.3 Yenilik 2: Kapalı döngü ve kendi kendini doğrulama

Basit bir klon tek görüntüye bakıp tek karar verir ("açık döngü"). Çoban ise VLA politikalarının çalışma biçimine yaklaşan bir yapıda:

1. Her adımda yeni görüntü alınır. Model görevi, geçmiş adımları ve gripper durumunu bilerek **sadece sıradaki adımı** seçer. Bu sayede "kırmızıların hepsini kutuya koy" gibi **çok adımlı** görevler yapılabilir.
2. Model, **önceki adımın gerçekten başarılı olup olmadığını** görüntüden kontrol eder. Örneğin nesne kaydıysa sistem durumu düzeltir ve yeniden dener. `MAX_RETRIES` kez üst üste başarısız olursa operatörü çağırır.
3. **Görme + dokunma sensör füzyonu:** Gripper'ın çene sensörü, kapanmadan sonra `DONE HELD` ya da `DONE EMPTY` bildirir. "Boş" cevabı geldiğinde adım modele sorulmadan başarısız sayılır. Bu özellik, gerçek Gemini testlerinde ortaya çıkan bir zayıflık üzerine eklendi (bkz. 6.2).
4. **Bitiş doğrulaması:** Model "bitti" dediğinde, ayrı bir kalite kontrol prompt'u son görüntüdeki nesneleri sayar. Eksik varsa "bitti" kararı reddedilir ve görev devam eder.
5. Model her adımda bir **ilerleme sayacı** tutar ("kit tepsisi: 1/2 siyah konnektör, 0/1 kırmızı sigorta"). Böylece fazla ya da yanlış nesne taşımaz.
6. Güvenlik kontrolleri:
   - düşük güvende hareket yok,
   - mantıksız kararların reddi (örneğin gripper doluyken AL),
   - firmware'de çalışma alanı sınırı,
   - kalibrasyon yoksa robotun hareket ettirilmemesi.

Demo: [docs/demo/gemini/4_tutma_hatasi_sensorle_kurtarma.mp4](docs/demo/gemini/4_tutma_hatasi_sensorle_kurtarma.mp4). %40 tutma hatası verilen simülasyonda küp iki kez kayıyor ve sensör iki seferi de yakalıyor. Model bir küp kutuya girdiğinde erken "bitti" diyor; bitiş doğrulaması "bir kırmızı küp hâlâ masada" diyerek bunu reddediyor ve görev gerçekten tamamlanıyor.

### 5.4 Yenilik 3: Veri çarkı

Her görev `episodes/` altında bir **episode** olarak kaydediliyor:
- modelin gördüğü kareler,
- her adımın kararı, gerekçesi ve güveni,
- robot koordinatları,
- doğrulama sonucu,
- simülasyonda altyazılı video.

Bu kayıtlar, ileride açık kaynak bir VLA modelini (örneğin π0 ya da LeRobot ile) **Türk fabrikalarının kendi görevlerine ince ayarlamak** için kullanılabilecek bir veri seti oluşturuyor. Bu, Shepherd'in "sahadaki her robot deneyimini öğrenme döngüsüne besler" yaklaşımının karşılığı.

### 5.5 Yenilik 4: KVKK uyumlu görüntü işleme

`privacy.py`, OpenCV'nin YuNet yüz algılayıcısıyla görüntüdeki yüzleri **Gemini'ye gönderilmeden ve diske kaydedilmeden önce** pikselleştiriyor (varsayılan olarak açık, `BLUR_FACES`). Gerçek bir fotoğrafta test edildi. Robotun işi için yüz bilgisine hiç gerek olmadığından bu, KVKK'nın veri minimizasyonu ilkesine de uygun.

### 5.6 Yenilik 5: Türkçe operatör deneyimi ve düşük maliyet

- **Türkçe arayüz:** Komutlar, model gerekçeleri, terminal arayüzü ve hata mesajları Türkçe. Operatörün İngilizce bilmesi gerekmiyor.
- **Düşük maliyetli donanım:** Firmware standart bir Arduino veya STM32 kartı ve bir servo gripper ile çalışıyor. Kol olarak yaklaşık 100–250 USD'lik açık kaynak SO-101 tipi kollar kullanılabilir ([kaynak](https://gvwire.com/2025/04/30/hugging-face-releases-affordable-3d-printed-robotic-arm/)).
- **Hazır komutlar:** Bir KOBİ, robot programcısı olmadan Türkçe komutla yeni bir kitting görevi tanımlayabiliyor.

---

## 6. Doğrulama

### 6.1 Otomatik testler

- **43 otomatik test** (`python -m unittest discover tests`). Kapsadıkları:
  - model cevabı ayrıştırma,
  - kalibrasyon matematiği,
  - seri protokol (DONE / ERR / zaman aşımı / gripper sensörü),
  - API hatalarında yeniden deneme ve yedek modele geçiş,
  - erken "bitti" kararının bitiş doğrulamasıyla yakalanması,
  - hareket dizileri,
  - simülasyon fiziği,
  - KVKK bulanıklaştırma,
  - **uçtan uca kapalı döngü:** simülasyonun gerçek durumunu okuyan bir "kâhin" politikayla görev tamamlama, tutma hatasından kurtulma ve tekrarlayan hatada vazgeçme.
- **Firmware:** Arduino API'sini taklit eden bir test düzeneğiyle (gerçek ArduinoJson kütüphanesi kullanılarak) derlendi ve 8 senaryoda çalıştırıldı. Senaryolar: geçerli hareket, çalışma alanı dışı hedef, eksik alan, gripper, gripper sensörü (HELD/EMPTY), bilinmeyen komut, bozuk JSON ve aşırı uzun satır. Bu test `LINE_MAX` adının bazı derleyicilerde sistem makrosuyla çakıştığını da ortaya çıkardı; düzeltildi.
- **API'siz demo:** `python main.py --sim --offline-demo` komutu kâhin politika ile tam akışı gösteriyor ([docs/demo/offline/](docs/demo/offline/)). Bu videolarda karar veren Gemini değil kâhin politikadır.

### 6.2 Gerçek Gemini ile testler

Tüm görevler simülasyonda gerçek Gemini API'siyle çalıştırıldı. Videolar ve modelin tüm kararlarını içeren episode kayıtları [docs/demo/gemini/](docs/demo/gemini/) klasöründe.

| # | Görev | Model | Sonuç |
|---|---|---|---|
| 1 | kırmızı küpleri sarı kutuya koy | gemini-3.8-flash | **DONE**, 5 adım, her adım doğrulandı |
| 2 | çatlak olan konnektörü hurda kutusuna at | gemini-3.6-flash (yedek) | **DONE**, çatlak parça sağlamlarından ayırt edildi |
| 3 | mor küpü beyaz tepsiye koy | gemini-3.6-flash (yedek) | **IMPOSSIBLE**, mor küp olmadığı fark edildi, robot hareket etmedi |
| 4 | kırmızı küpleri sarı kutuya koy (%40 tutma hatası) | gemini-3.5-flash-lite | **DONE**, 8 adım; 2 kayma sensörle, 1 erken "bitti" bitiş doğrulamasıyla yakalandı |
| 5 | iki siyah konnektörü ve kırmızı sigortayı kit tepsisine koy | gemini-3.5-flash-lite | **DONE**, 7 adım, doğru sayım |

İlk testte Gemini mavi küpün yerini **piksel düzeyinde doğru** buldu: tahmin (280, 220), gerçek konum (280, 220).

İlk tablodaki her sonuç, sadece modelin kendi beyanıyla değil, episode kaydının son karesi tek tek incelenerek doğrulandı.

**Testlerin ortaya çıkardığı sorunlar ve çözümleri.** Gerçek model testleri, kâhin politikayla görülemeyecek dört sorunu ortaya çıkardı:

1. **Fark edilmeyen kayma:** Küp sadece 1-2 cm kaydığında, tepeden bakan kamerada kapalı çenelerle üst üste göründüğü için Gemini tutmanın başarısız olduğunu anlayamadı ve "BIRAK" dedi. Gerçek robotlarda da görülen bu sorun **gripper sensörü füzyonuyla** çözüldü; sonrasında test 4 başarıyla tamamlandı.
2. **Yanlış sayım:** En küçük model (flash-lite) kitting görevinde beyaz bir konnektörü siyah sandı ve fazladan tepsiye koydu. Prompt'a zorunlu bir **ilerleme sayacı** ve "bitti demeden önce hedefi kontrol et" kuralı eklendi; sonrasında aynı model görevi hatasız tamamladı (test 5).
3. **Erken "bitti":** Tutma hatalı testin ilk denemesinde model, kayan küpü tekrar almak yerine zaten kutuda olan küpü alıp aynı kutuya geri bıraktı ve "bitti" dedi; ikinci küp masada kalmıştı. Bu hata, episode'un son karesi incelenirken fark edildi. Çözüm olarak model "bitti" dediğinde ayrı bir kalite kontrol prompt'uyla son görüntünün sayılması (**bitiş doğrulaması**) eklendi. Yeniden çekilen testte (test 4) model yine erken "bitti" dedi, ama doğrulama bunu yakaladı ve görev gerçekten tamamlandı.
4. **API kotası ve yoğunluk:** Testler sırasında Google sunucuları sık sık 503/504 döndü ve ücretsiz kotanın günlük sınırı (429) doldu. Buna karşı artan bekleme süreleriyle **yeniden deneme** ve ayrı kotaya sahip bir **yedek modele otomatik geçiş** eklendi. Hangi adımda hangi modelin cevap verdiği artık episode kaydına yazılıyor.

---

## 7. Sınırlamalar ve gelecek çalışmalar

- **Gerçek bir VLA değil.** Gemini bir görme-dil modeli; adım başına tek bir hedef nokta veriyor. Gerçek VLA modelleri saniyede birçok kez eklem açısı üretir. Bir sonraki adım, toplanan episode verisiyle açık kaynak bir VLA modelini ince ayarlamak.
- **2D varsayımı:** Nesnelerin düz bir masada olduğu varsayılıyor, derinlik kamerası yok.
- **Donanıma özel kısım:** Firmware'deki `moveTo()` fonksiyonu kullanılan kola göre doldurulmalı.
- **Doğrulanamayan veriler:** Türkiye kablo demeti sektörünün toplam istihdamı ve robot yoğunluğu rakamının (43) IFR yılı doğrulanamadı.
- **Olası geliştirmeler:**
  - gürültülü fabrika ortamı için Türkçe sesli komut,
  - veri yurt dışına çıkmasın diye yerel (on-premise) çalışan bir model,
  - birden fazla robot hücresini izleyen bir web paneli.

---

## 8. Kaynaklar

- Shepherd Robotics, YC: https://www.ycombinator.com/companies/shepherd-robotics
- YC Requests for Startups: https://www.ycombinator.com/rfs
- YC Manufacturing & Robotics şirketleri: https://www.ycombinator.com/companies/industry/manufacturing-and-robotics
- YC 2026 analizi: https://pinggy.io/blog/what_yc_is_funding_in_2026/
- HN: Gemini Robotics 2: https://news.ycombinator.com/item?id=49111237
- HN: Xiaomi-Robotics-1: https://news.ycombinator.com/item?id=48974454
- HN: Robostral Navigate: https://news.ycombinator.com/item?id=48832212
- HN: Gemini Robotics-ER 1.6: https://news.ycombinator.com/item?id=47779094
- HN: Qwen-Robot Suite: https://news.ycombinator.com/item?id=48554814
- HN: BMW humanoid robots: https://news.ycombinator.com/item?id=47253892
- HN: Launch HN: Nori Robotics: https://news.ycombinator.com/item?id=49525153
- Gemini Robotics 2: https://deepmind.google/blog/gemini-robotics-2-brings-whole-body-intelligence-to-robots/
- Physical Intelligence: https://www.pi.website/
- IMARC, Türkiye kablo demeti pazarı: https://www.imarcgroup.com/turkey-automotive-wiring-harness-market
- Yazaki Türkiye: https://www.olay.com.tr/yazaki-yeni-projelerle-kapasitesini-artiriyor-35464
- IFR World Robotics 2025: https://www.industrial-production-worldwide.com/news/world-robotics-2025-report-reveals-south-korea-singapore-and-germany-have-highest-robot-density
- Türkiye robot yoğunluğu: https://www.ekonomigazetesi.com/kobi/akilli-fabrikalar-robotik-otomasyonla-yeni-uretim-donemine-geciyor-86063
- Türkiye robot pazarı: https://www.hurriyetdailynews.com/amp/turkiye-ranks-14th-globally-in-robotics-market-214152
- Türkiye veri merkezi hedefi: https://www.webtekno.com/turkiye-veri-merkezi-kapasitesi-2030-hedefi-belirlendi-h223648.html
- KVKK m.9 değişikliği: https://www.erdem-erdem.av.tr/bilgi-bankasi/kisisel-verilerin-korunmasi-kanunu-nda-neler-degisti
- LeRobot SO-101: https://gvwire.com/2025/04/30/hugging-face-releases-affordable-3d-printed-robotic-arm/
- YuNet yüz algılama (MIT): https://github.com/opencv/opencv_zoo/tree/main/models/face_detection_yunet
