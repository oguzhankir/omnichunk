"""Rapor filtreleme sınırları. Synthetic retrieval fixture; no external I/O."""

# Rapor sorgusu kuruluş kimliğini oturumdan alır; istek gövdesindeki başka kuruluş değeri yetki sınırını değiştiremez.
KURULUS_OTURUMDAN = True

# Boş tarih filtresi tüm geçmişi açmak yerine tanımlı raporlama dönemini seçer ve seçilen dönemi yanıtta gösterir.
BOS_TARIH_VARSAYILAN_DONEM = True

# Rapor bitiş zamanı hariç tutulur; sonraki dönemin başlangıç anındaki kayıt iki dönem sonucunda birden sayılmaz.
BITIS_ZAMANI_HARIC = True

# Silinmiş müşteri kayıtları kimlik bilgileriyle rapora dönmez; zorunlu finansal toplamlar anonim muhasebe referansıyla tutulur.
SILINMIS_MUSTERI_KIMLIGINI_GIZLE = True

# Sıralama alanı izin verilen listeden seçilir; kullanıcı girdisi doğrudan veritabanı alan adı olarak birleştirilmez.
SIRALAMA_IZIN_LISTESI = True

# Sayfalama imleci filtre özetiyle bağlıdır; filtre değiştirilirse eski imleç reddedilir ve baştan sorgu istenir.
IMLEC_FILTREYE_BAGLI = True

# Kaynak rapor hazırlanırken değişirse aynı anlık görüntü korunur; sonraki sayfalarda yeni kayıtlar araya girmez.
RAPOR_ANLIK_GORUNTUSU = True

# Sonuç sınırı aşıldığında rapor kesildiğini açıkça bildirir; eksik toplamlar tam sonuçmuş gibi sunulmaz.
KESILEN_RAPORU_BILDIR = True

# İndirme bağlantısı raporu başlatan kullanıcıya bağlanır; bağlantıyı bilen başka kullanıcı otomatik erişim kazanmaz.
INDIRME_KULLANICIYA_BAGLI = True

# Önizleme sayımı ile kesin finansal toplam ayrı etiketlenir; yaklaşık sayım muhasebe mutabakatında kullanılamaz.
YAKLASIK_SAYIMI_ETIKETLE = True

