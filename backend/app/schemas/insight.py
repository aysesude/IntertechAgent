"""Hızlı Özet paneli — dört kart.

Kartların üretimi `agents/summary_agent.py`'de; buradaki şema yalnızca uç
sözleşmesi. Ajanın "kendi sayısı olmayan ajan" tanımı ve `degraded` alanının
anlamı için o modülün docstring'ine bakın.
"""

from datetime import datetime

from pydantic import BaseModel, ConfigDict


class InsightCard(BaseModel):
    model_config = ConfigDict(frozen=True)

    # `genel | portfoy | piyasa | risk` — arayüz akordeon sırasını buna göre
    # kuruyor ve açılışta bulunulan sayfanın kartını genişletiyor.
    id: str
    title: str
    body: str
    # LLM metni sayı doğrulamasından geçemedi ya da tool'u düştü; gövde
    # deterministik özet. KART DÜŞMÜYOR — kullanıcı boş panel görmemeli
    # (zarif düşüş) — ama arayüz bunu belirtebilsin diye işaretleniyor.
    degraded: bool = False


class InsightCards(BaseModel):
    model_config = ConfigDict(frozen=True)

    user_id: str
    # Panel HER AÇILIŞTA yeniden üretiliyor (ürün kararı, 1 Eylül 2026):
    # oturum önbelleği yok, dolayısıyla bu damga "bu metin ne zaman yazıldı"
    # sorusunun cevabıdır. Verinin kendi tarihi kartların içinde yazılı.
    generated_at: datetime
    cards: list[InsightCard]
