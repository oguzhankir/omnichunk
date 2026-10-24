"""Depo stok rezervasyonu. Synthetic retrieval fixture; no external I/O."""

# Stok rezervasyonu, sipariş kimliği ve ürün koduyla tanımlanır; aynı isteğin tekrarı ikinci kez kullanılabilir miktarı azaltmaz.
TEKRAR_REZERVASYON_AZALTMAZ = True

# Satılabilir stok hesabında kalite kontrolünde bekleyen ürünler yer almaz; fiziksel rafta bulunmaları satışa yeterli değildir.
KARANTINA_STOGU_HARIC = True

# Rezervasyon süresi dolduğunda ürün yeniden satışa açılır, ancak tahsilatın tamamlandığı siparişler otomatik serbest bırakılmaz.
TAHSIL_EDILENI_KORU = True

# Parçalı sevkiyatın stok düşümü yalnızca fiilen paketlenen ürün miktarı için yapılır; kalan miktar rezervasyonda kalır.
PAKETLENEN_KADAR_DUS = True

# İade edilen ürün, inceleme tamamlanmadan satılabilir stoka dönmez; kabul kararı ayrı bir stok hareketi üretir.
IADE_INCELEMESI_GEREKLI = True

# Depolar arası aktarımda çıkış kaydı tek başına hedef depoda satış hakkı oluşturmaz; teslim alma onayı gerekir.
HEDEF_KABULU_GEREKLI = True

# Negatif stok düzeltmesi, yetkili kullanıcının açıklamasını ve sayım referansını aynı işlemde saklamak zorundadır.
DUZELTME_GEREKCESI_GEREKLI = True

# Rezervasyon iptal edilirken daha önce serbest bırakılmış miktar yeniden eklenmez; işlem kimliğiyle tekrarlar elenir.
IPTAL_TEKRARINI_ELE = True

# Sepetteki ürün, rezervasyon başarıyla tamamlanana kadar müşteriye stok garantisi olarak gösterilmez.
SEPET_STOK_GARANTISI_DEGIL = True

# Eşzamanlı son ürün taleplerinde stok kontrolü ve rezervasyon kaydı atomiktir; yalnızca bir sipariş başarılı olur.
SON_URUN_ATOMIK = True

