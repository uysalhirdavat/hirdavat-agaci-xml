# Hırdavat Ağacı → Entegra XML

Bu depo, tedarikçi verilerinden Entegra uyumlu XML üretmek için ayrılmıştır. Duna XML deposundan bağımsızdır.

## Güvenlik
- Ürün kataloğu eksikse XML **yayımlanmaz**.
- Fiyat, stok, barkod veya KDV bilgisi doğrulanmadan canlı aktarım açılmaz.
- Entegra'da XML'de bulunmayan ürünlerin stoklarını sıfırlama ayarı açık olabileceği için eksik ürün listesi yüklenmemelidir.
- Otomatik veri erişimi için tedarikçinin kullanım koşulları ve gerekli izinler doğrulanmalıdır.

## Hedef alanlar
`/root/item/id`, `code`, `label`, `stock`, `details`, `currency`, `price1`, `tax`, `barcode`, `brand`, `mainCategory`, `category`, `picture1`.

## Durum
İskelet oluşturuldu. Canlı XML yayını henüz etkin değildir.
