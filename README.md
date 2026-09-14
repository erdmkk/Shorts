# Puzzly Shorts Generator V8.1

Puzzly for Kids için konuşmasız ve dil bağımsız videoları bilgisayarınızda üretir. Quick Math, Missing Number, Puzzle Fit, Find the Exit, Memory Challenge, Flash Count ve zorluk seçimi gerektirmeyen tek oyunluk Lucky Pick aktiftir. Line Follow kodu korunur ancak deneysel olduğu için üretim menülerinde kapalıdır. Karışık mod yalnızca aktif türleri kullanır; ücretli API veya elle düzenleme gerekmez.

V7 ile Easy/Medium/Hard arka planları sırasıyla açık mint, gök mavisi ve lavanta-pembe olarak standartlaştırılmıştır. Quick Math farklı bilinmeyen konumları; Missing Number toplama, çıkarma ve uygun zorluklarda çarpma dizilerini kullanır. Puzzle Fit Hard dört seçenek ve 5 saniye düşünme süresi sunar. Sesler yerel olarak 48 kHz üretilir ve kesilme tıklarını önleyen kısa geçişlerle güvenli biçimde karıştırılır.

## Gereksinimler ve ilk kurulum

Windows 10/11 ve Python 3.11+ gerekir. İlk kullanımda internet bağlantısıyla `setup.bat` dosyasına çift tıklayın. Bu işlem yalnızca açık kaynak Python paketlerini yerel `.venv` klasörüne kurar.

## Çalıştırma ve üretim

`run.bat` dosyasına çift tıklayın. Tarayıcıda tür, Easy/Medium/Hard zorluk, Quick Math işlemi, challenge sayısı, video adedi ve Draft/Final kalitesini seçin. İsterseniz tekrarlanabilir bir seed girin; ardından `1 Video Üret` veya `Toplu Video Üret` düğmesine basın.

Auto: Quick Math, Missing Number ve Puzzle Fit için 5 tur; Find the Exit ve Line Follow için 4 tur kullanır. Bu türlerde 3, 4 veya 5 tur da seçebilirsiniz. Memory Challenge ise her zaman tek bir 5 şekilli renk panosu gösterir: 3 saniye ezberleme, dört adet 3 saniyelik hafıza sorusu ve beklemeden açılan son şekil. Memory seçiliyken challenge sayısı otomatik gizlenir. Easy/Medium/Hard zorluğu şekil sayısını değil renk benzerliğini değiştirir. Süre otomatik hesaplanır. Draft hızlı kontrol; Final ise daha yavaş, 2× örneklemeli 1080×1920 / 30 FPS kaliteli çıktı içindir.

Line Follow zorluğu Easy/Medium/Hard için sırasıyla 3/4/5 yol ve 2/6/12 kontrollü köprü kesişimi kullanır. Köprü üst çizgileri boşluksuz biçimde ana yola yeniden bağlanır. Hard modunda hedef ve tüm yan yollar alt yarıda da etkileşmeye devam eder; uzun, kolay dikey inişler sınırlandırılır. Final çıktıda eğriler ayrıca 4× çözünürlükte çizilip yumuşatılır.

Videolar tarihli `output` klasörüne kaydedilir. Her MP4 ile aynı ada sahip 1080×1920 JPG kapak ve rapor amaçlı metadata CSV dosyaları oluşturulur. Yeni ad biçimi `PZ_0024_memory_challenge_hard.mp4` şeklindedir.

Üretilen dosyaları `output/` içinden güvenle silebilirsiniz; metadata CSV dosyaları da silinebilir. Bunları silmek tekrar önleme belleğini veya sonraki `PZ_` numarasını sıfırlamaz.

`data/generation_history.sqlite` dosyasını silmeyin. Bu yerel veritabanı üretilmiş bulmacaların parmak izlerini ve sıra numarası geçmişini tutar. Bu dosyayı silmek hem tekrar önleme belleğini hem de sıra geçmişini kasıtlı olarak sıfırlar. Eski `data/history.json` geçiş sırasında yedeklenir ve geriye dönük güvenlik için korunur.

## Logo

Şeffaf PNG logonuzu `assets/branding/logo.png` adıyla yerleştirin. Sonraki videolar logoyu otomatik kullanır.

## Yaygın sorunlar

- Python bulunamadı: Python 3.11+ kurup PATH seçeneğini etkinleştirin.
- Kurulum hatası: Bağlantıyı kontrol edip `setup.bat` dosyasını yeniden çalıştırın.
- Video üretilemiyor: Disk alanını ve `logs/puzzly.log` dosyasını kontrol edin.
- Uygulama açılmıyor: Önce `setup.bat`, sonra `run.bat` çalıştırın.
