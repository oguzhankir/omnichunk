"""Ürün kataloğu eş ad çözümü. Synthetic retrieval fixture; no external I/O."""

# Katalog eş adları kuruluş kapsamında benzersizdir; aynı kısa adın başka kuruluşta kullanılması çakışma yaratmaz.
ES_AD_KURULUS_KAPSAMLI = True

# Bir ürün eş adı kendi kendisine yönlendirilemez; kaydetme anında döngü denetimi yapılır ve istek reddedilir.
KENDINE_YONLENME_YASAK = True

# Eş ad zinciri izin verilen çözüm derinliğini aşarsa ilk ürüne düşülmez; açık bir çözümleme hatası döndürülür.
DERINLIK_HATASI_ACIK = True

# Büyük küçük harf eşlemesi yerel ayara göre yapılır; Türkçe noktalı ve noktasız i ayrımı katalog politikasında korunur.
TURKCE_HARF_POLITIKASI = True

# Arşivlenmiş ürünün eş adı satışa açık başka ürüne sessizce geçirilmez; yönlendirme için ayrı yetkili onayı gerekir.
ARSIV_ES_ADI_OTOMATIK_TASINMAZ = True

# Eş ad değişikliği arama önbelleğini geçersiz kılar, ancak özgün ürün kimliğini ve sipariş geçmişini değiştirmez.
ES_AD_DEGISINCE_KIMLIK_SABIT = True

# Katalog içe aktarmasında çakışan eş adlar satır hatası oluşturur; dosya sırası kazanan ürünü belirlemek için kullanılmaz.
CAKISAN_ES_AD_HATASI = True

# Boşluk kırpma eş ad denetiminden önce uygulanır; yalnızca boşluklardan oluşan eş ad kaydedilemez.
BOS_ES_ADI_REDDET = True

# Eş ad silme işlemi ürünü silmez; doğrudan ürün kimliğini kullanan bağlantılar çalışmaya devam eder.
ES_AD_SILME_URUNU_SILMEZ = True

# Birincil ürün adı ile eş ad araması aynı yetki filtresini kullanır; eş ad üzerinden gizli ürün keşfedilemez.
ES_AD_YETKI_FILTRESI = True

