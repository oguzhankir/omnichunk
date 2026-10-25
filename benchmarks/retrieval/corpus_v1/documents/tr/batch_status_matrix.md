# Gece toplu işlem durumları

| Scope | Rule | Condition |
| --- | --- | --- |
| Hazır | Bütün kaynak dilimleri doğrulanmıştır | Hazır durumu henüz müşteri raporunun yayımlandığı anlamına gelmez. |
| Çalışıyor | İşçi sahipliği ve ilerleme noktası kaydedilir | Yönetim ekranı son başarılı adımı gösterir, tahmini tamamlanmayı kesin süre gibi sunmaz. |
| Beklemede | Dış bağımlılık için tekrar zamanı belirlenmiştir | Yeni işçi açmak bağımlılığın bekleme kuralını atlatamaz. |
| Kısmi | Bazı dilimler sonuç üretmiş ve hatalar ayrılmıştır | Tüm veri tamamlanmış gibi tek başarı işareti gösterilmez. |
| Doğrulamada | Üretilen toplamlar kaynakla karşılaştırılır | Hesaplama bitmesi yayın onayının otomatik verildiği anlamına gelmez. |
| Yayımlandı | Doğrulanmış sonuç kuşağı etkinleştirilmiştir | Önceki kuşak geri dönüş penceresi bitene kadar korunur. |
| İptal isteği | Henüz başlanmamış dilimler durdurulur | Tamamlanmış dış yazmaların telafisi ayrı kayıtlarda izlenir. |
| Hatalı | Hata sınıfı ve tekrar edilebilirlik bilgisi kaydedilir | Girdi bozukluğunda sınırsız otomatik tekrar yapılmaz. |
| Arşiv | Sonuç kuşağı salt okunur denetim için tutulur | Arşive alınmış iş yeni kaynak değişikliklerini kendiliğinden işlemez. |
| Geri alındı | Önceki doğrulanmış sonuç kuşağı yeniden etkinleşir | Başarısız aday kuşağın tanı bilgileri inceleme için saklanır. |
