"""Fatura hesaplama kuralları. Synthetic retrieval fixture; no external I/O."""

# Fatura hesaplaması ikili kayan nokta yerine kuruş tabanlı tam sayılar kullanır; sunum biçimi hesap değerini değiştirmez.
KURUS_TAMSAYI = True

# Vergi matrahı, satır indirimi uygulandıktan sonra belirlenir; genel belge indirimi dağıtımı ayrıca kaydedilir.
INDIRIM_SONRASI_MATRAH = True

# Yuvarlama farkı, son satırın fiyatını gizlice değiştirmek yerine ayrı bir düzeltme kalemi olarak gösterilir.
YUVARLAMA_AYRI_KALEM = True

# İptal edilmiş faturanın seri numarası yeni belgede kullanılamaz; numara dizisinin denetim izi korunur.
IPTAL_NUMARASI_TEKRARLANMAZ = True

# Dövizli faturada kur tarihi belgeyle saklanır; daha sonraki piyasa hareketi geçmiş belgenin tutarını değiştirmez.
KUR_TARIHI_SABIT = True

# Kısmi iade belgesi, özgün faturanın satır kimliğine bağlanır ve daha önce iade edilen miktarı aşamaz.
IADE_ORIJINAL_SATIRA_BAGLI = True

# Fatura taslağı onaylanana kadar vergi numarası düzeltilebilir; onay sonrası değişiklik yeni bir düzeltme belgesi gerektirir.
ONAY_SONRASI_DUZELTME_BELGESI = True

# Tahsilat durumu ile belgenin hukuki geçerliliği farklı alanlardır; ödenmemiş fatura otomatik olarak geçersiz sayılmaz.
TAHSILAT_AYRI_DURUM = True

# Fatura özetinde görünen toplam, indirimi, vergiyi ve yuvarlama kalemini içerir; gizli masraf satırı eklenemez.
TOPLAM_SEFFAF = True

# Aynı faturalama komutunun tekrarında mevcut belge kimliği döner; ikinci bir seri numarası ayrılmaz.
KOMUT_TEKRARI_AYNI_BELGE = True

