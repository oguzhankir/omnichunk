# Toplu veri yükleme deneyimi

Toplu yüklemenin ilk adımı dosyanın önizlemesidir. Kullanıcı kolon eşlemesini onaylamadan hiçbir satır kalıcı iş verisine yazılmaz.

İçe aktarma önizlemesi örnek satırlar gösterir ve örnek sayısını belirtir. Önizlemenin temiz görünmesi bütün dosyanın hatasız olduğunu garanti etmez.

Tarih kolonundaki belirsiz değer için kullanıcıdan açık biçim seçimi istenir. Sistem gün ve ay yerini tahmin ederek müşteri verisini değiştirmez.

Zorunlu alanı eksik satır hata raporuna alınır ve satır numarası korunur. Hata metni tam müşteri kaydını paylaşılabilir bağlantıya taşımaz.

Kullanıcı geçerli satırlarla devam etmeyi seçerse atlanan hatalı satırların sayısı sonuç ekranında açıkça gösterilir.

Önizlemeden sonra eşleme değişirse daha önce verilen onay geçersiz olur. Yeni eşleme için güncel örneklerin yeniden incelenmesi gerekir.

Yükleme ekranından çıkmak arka plandaki işi otomatik iptal etmez. İş listesi ayrı iptal düğmesi ve güncel durum bilgisi sunar.

İptal isteği, henüz uygulanmamış satırların işlenmesini durdurur. Önceden kaydedilmiş satırların geri alınması ayrı düzeltme işlemi olarak açıklanır.

Tekrarlanan dosya yüklemesinde aynı işlem anahtarı mevcut işi gösterir. Kullanıcı yeni bir iş istediğinde bilinçli olarak yeni anahtar oluşturulur.

Sonuç dosyası, kaynak dosya özeti ve kullanılan eşleme sürümünü içerir. Böylece kullanıcı hangi yüklemenin hatalarını düzelttiğini doğrulayabilir.

