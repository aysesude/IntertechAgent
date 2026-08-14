"""
Finansal Asistan - Stage 5 (Qwen 2.5 7B & Nezaket/Teşekkür Eşleşme Düzeltmesi)

Geliştirmeler:
1. Nezaket / Teşekkür Eşleşme Düzeltmesi ('sağol' -> 'sahol' Sabancı Yanılsaması Çözüldü):
   'sağol', 'saol', 'teşekkürler', 'eyvallah' gibi nezaket kelimeleri EXCLUDED_WORDS listesine 
   eklendi. Artık 'sağol' kelimesi Sabancı Holding (SAHOL) ticker'ı ile çakışmaz ve sıcak 
   bir "Rica ederim! Başka bir finansal konuda yardımcı olabilir miyim?" yanıtı döner.
2. Çince / Asya Karakter Sızıntı Engelleyicisi (CJK Sanitizer & Strict Prompting):
   'olur' gibi tekil onaylarda Çince karaktere düşülmesi engellendi.
3. Tekil Para Birimi Algılama Düzeltmesi (Dolar Kuru / Euro Kuru / Sterlin Kuru):
   'dolar kuru' sorulduğunda SADECE Dolar, 'euro kuru' sorulduğunda SADECE Euro getirilir.
4. Qwen 2.5 7B Entegrasyonu (ollama_model: "qwen2.5:7b"):
   Aksansız Türkçe anlatım, sıfır yabancı dil sızıntısı.
5. Mantıksal Bölüm Sıralayıcısı:
   Önce Piyasa Varlıkları, ardından Şirket Bilançoları.
"""

import json
import os
import re
import difflib
import asyncio
from typing import List, Dict, Tuple, Optional
from langchain_core.documents import Document
from langchain_text_splitters import RecursiveCharacterTextSplitter
from langchain_huggingface import HuggingFaceEmbeddings
from langchain_community.vectorstores import Chroma
from langchain_community.retrievers import BM25Retriever
from langchain_ollama import ChatOllama
from langchain_core.messages import SystemMessage, HumanMessage

try:
    from symspellpy import SymSpell, Verbosity
    HAS_SYMSPELL = True
except ImportError:
    HAS_SYMSPELL = False


MARKET_ASSET_NAMES = {"Dolar", "Euro", "İngiliz Sterlini", "Gram Altın", "Devlet Tahvili", "Yatırım Fonları"}


class ResponseSanitizer:
    """LLM çıktılarındaki etiket, konuşma artığı, başlık ve tüm yabancı kelime sızıntılarını temizleyen evrensel filtre."""
    
    ENGLISH_LEAK_MAP = {
        r'\bfazi\b': 'faizi',
        r'\bdatos[ıa-z]*\b': 'verileri',
        r'\bsuccessful\b': 'başarılı',
        r'\binformaci[óo]n\b': 'bilgi',
        r'\bwill be added to the fleet\b': 'filoya katılacaktır',
        r'\badded to the fleet\b': 'filoya katılacaktır',
        r'\bnew aircraft\b': 'yeni uçak',
        r'\baircraft\b': 'uçak',
        r'\bfleet\b': 'filo',
        r'\bunavailable[\'a-z]*\b': 'mevcut değildir',
        r'\bcentral bank[ıa-z]*\b': 'merkez bankası',
        r'\binflation rates[ıa-z]*\b': 'enflasyon oranları',
        r'\binflation rates?\b': 'enflasyon oranları',
        r'\binterest rates?\b': 'faiz oranları',
        r'\bverschiedene\b': 'çeşitli',
        r'\bgovernment bondlar\b': 'devlet tahvilleri',
        r'\bgovernment bonds?\b': 'devlet tahvili',
        r'\binvestors\b': 'yatırımcılar',
        r'\binvestor\b': 'yatırımcı',
        r'\benstrüman\'tir\.?\b': 'enstrümandır.',
        r'\benstrüman\'tir\b': 'enstrümandır',
        r'\binstruments?\b': 'enstrüman',
        r'\bmeaningi\b': 'anlamı',
        r'\bmeaning\b': 'anlamı',
        r'\busedilmektedir\b': 'kullanılmaktadır',
        r'\bused\b': 'kullanılan',
        r'\bwidespread\b': 'yaygın',
        r'\bintroduction\b': 'kullanıma',
        r'\busageya\b': 'kullanıma',
        r'\bsignificant\b': 'önemli',
        r'\bOptimist\b': 'İyimser',
        r'\boptimist\b': 'iyimser',
        r'\bportfolio\b': 'portföy',
        r'\bportfolyo\b': 'portföy',
        r'\bincrease[\'a-z]*\b': 'artışı',
        r'\bzusammen\b': 'birlikte',
        r'\bposition[\'a-z]*\b': 'konumunu',
        r'\bpositionu\b': 'konumunu',
        r'\bposition\b': 'konum',
        r'\brecord\b': 'rekor',
        r'\busagea\b': 'kullanıma',
        r'\bbeingeldir\b': 'bilgisidir',
        r'\bbeing\b': 'olması',
        r'\binformation[a-z]*\b': 'bilgi',
        r'\bfiyat\'in[i]?\b': 'fiyatını',
        r'\bfiyat\'i[n]?\b': 'fiyatını',
        r'\bcustomers[\'a-z]*\b': 'müşteriler',
        r'\bcustomer\b': 'müşteri',
        r'\bperformance[\'a-z]*\b': 'performans',
        r'\brecently\b': 'son zamanlarda',
        r'\bincome[\'a-z]*\b': 'gelir',
        r'\bsalesi\b': 'satışı',
        r'\bsales\b': 'satışlar',
        r'\bsale\b': 'satış',
        r'\brange\b': 'aralık',
        r'\bmarketinde\b': 'piyasasında',
        r'\bmarketin\b': 'piyasanın',
        r'\bmarket\b': 'piyasa',
        r'\b profit\b': ' kâr',
        r'\b growth\b': ' büyüme',
        r'\brevenue\b': 'hasılat',
        r'\bof bir\b': 'bir',
        r'\bcurrent price\b': 'güncel fiyat',
        r'\bglobal events\b': 'küresel gelişmeler',
        r'\bbritish pound[\'a-z]*\b': 'İngiliz Sterlini',
        r'\bgiá\b': 'fiyat',
        r'\bmovements[a-z]*\b': 'hareketleri',
        r'\brates\b': 'oranlar',
        r'\bdetails?\b': 'detaylar',
        r'\bdata\b': 'veri',
        r'\bdeep learning\b': 'derin öğrenme',
        r'\bother\b': 'diğer',
        r'\bcontinue olarak\b': 'sürekli olarak',
        r'\bcontinue\b': 'sürekli',
        r'\bçip çiplerine\b': 'çiplerine',
        r'\bçip çipleri\b': 'çipleri'
    }

    @classmethod
    def sanitize_english_leakage(cls, text: str) -> str:
        if not text:
            return text
        cleaned = text
        # Çince / Asya karakterlerini tamamen temizle
        cleaned = re.sub(r'[\u4e00-\u9fff\u3040-\u30ff\uff00-\uffef\u2e80-\u2eff\u1100-\u11ff]+', '', cleaned)
        for pattern, repl in cls.ENGLISH_LEAK_MAP.items():
            cleaned = re.sub(pattern, repl, cleaned, flags=re.IGNORECASE)
        return cleaned

    @classmethod
    def sanitize_company_hallucinations(cls, text: str, is_equity_company: bool = False) -> str:
        """Şirket bilançolarına sızan uydurma döviz kuru, faiz, alakasız TÜİK verileri ve prompt artıklarını temizler."""
        if not text or not is_equity_company:
            return text
            
        lines = text.split('\n')
        clean_lines = []
        for line in lines:
            if re.search(r'^\s*[-*]?\s*(Döviz Kuru|Kur|Faiz)\s*:\s*(1\s*USD|ASLA|değişken|%|\$)', line, re.I):
                continue
            if "ASLA PAYLAŞTIRILMADI" in line or "yani %" in line:
                continue
            if "TÜİK" in line or "dış ticaret endeksi" in line or "İhracat birim değer" in line:
                continue
            clean_lines.append(line)
            
        return "\n".join(clean_lines).strip()

    @classmethod
    def sanitize(cls, text: str, is_equity_company: bool = False) -> str:
        if not text:
            return text
            
        cleaned = text.strip()
        cleaned = re.sub(r'^\s*Soru\s*:.*?\n', '', cleaned, flags=re.IGNORECASE | re.MULTILINE)
        
        prefixes = [
            r'^\s*Cevap\s*:\s*',
            r'^\s*Yanıt\s*:\s*',
            r'^\s*Çıktı\s*:\s*',
            r'^\s*Metne göre\s*,\s*',
            r'^\s*Veriye göre\s*,\s*',
            r'^\s*BAĞLAM içinde\s*:\s*',
            r'^\s*BAĞLAM metnine göre\s*,\s*',
            r'^\s*Senin bu veriye dayalı olarak.*?:?\s*',
            r'^\s*Bu bilgiye göre\s*,?\s*',
            r'^\s*Verilen bilgilere göre\s*,?\s*',
            r'^\s*Metne dayalı olarak\s*,?\s*',
            r'^\s*Şifreli bilgi\s*:\s*',
            r'^\s*Açıklama\s*:\s*',
            r'^\s*Sonuç\s*:\s*'
        ]
        
        for pattern in prefixes:
            cleaned = re.sub(pattern, '', cleaned, flags=re.IGNORECASE | re.MULTILINE)
            
        cleaned = re.sub(r'^[\s,\.:]+', '', cleaned)
        cleaned = cls.sanitize_english_leakage(cleaned)
        cleaned = cls.sanitize_company_hallucinations(cleaned, is_equity_company=is_equity_company)
        return cleaned.strip()


class AutoSpellCorrector:
    """Aşama 2+: SymSpell tabanlı otomatik imla düzeltici motoru."""
    
    def __init__(self):
        self.is_ready = False
        if HAS_SYMSPELL:
            try:
                self.sym_spell = SymSpell(max_dictionary_edit_distance=2, prefix_length=7)
                terms = [
                    "merhaba", "selam", "günaydın", "akşamlar", "günler", "nasılsın",
                    "garanti", "bankası", "çeyrek", "kâr", "zarar", "bilanço",
                    "üçüncü", "dördüncü", "birinci", "ikinci", "hava", "yolları",
                    "aselsan", "ereğli", "demir", "çelik", "hisse", "borsa",
                    "dolar", "euro", "sterlin", "altın", "tahvil", "bono", "fon",
                    "net", "operasyonel", "marj", "fiyat", "haberleri",
                    "paylaş", "anlat", "göster", "ver", "söyle", "getir", "yaz",
                    "tamam", "olur", "tabi", "tabii", "lütfen", "detay", "yolla"
                ]
                for t in terms:
                    self.sym_spell.create_dictionary_entry(t, 1000)
                self.is_ready = True
            except Exception:
                self.is_ready = False

    def correct(self, text: str) -> str:
        if not self.is_ready or not text:
            return text
        words = text.split()
        corrected = []
        for word in words:
            clean_w = re.sub(r'[^\w\s]', '', word)
            if len(clean_w) <= 2 or clean_w.isdigit():
                corrected.append(word)
                continue
            suggestions = self.sym_spell.lookup(clean_w, Verbosity.TOP, max_edit_distance=2)
            if suggestions:
                corrected.append(suggestions[0].term)
            else:
                corrected.append(word)
        return " ".join(corrected)


class QueryOptimizer:
    """Esnek İmla Düzeltme ve Dinamik Selamlaşma Motoru."""

    CANONICAL_GREETINGS = ["merhaba", "selam", "günaydın", "iyi günler", "iyi akşamlar", "naber", "nasılsın", "slm", "mrb"]
    REJECTION_WORDS = ["hayır", "istemem", "kalsın", "yok", "istemiyorum", "gerek yok"]
    PRONOUN_PATTERNS = ["o haberi", "haberi ver", "haberi getir", "detayı ver", "detayı anlat", "haberi göster", "detayları ver", "ver", "verin", "göster", "anlat", "getir", "söyle", "yaz", "oku", "paylaş", "tabi"]
    AVAILABILITY_PATTERNS = ["haber var mı", "bilgi var mı", "gelişme var mı", "duyuru var mı", "haberi var mı"]
    AVAILABILITY_REGEX = re.compile(r'\b(bilgi|haber|gelişme|duyuru)\b.*?\b(v\s*a\s*r|v[a-z]*)\s*(m[ıiuü]|armı|armi)\b', re.IGNORECASE)
    ACTION_VERBS = ["paylaş", "ver", "göster", "anlat", "yolla", "getir", "söyle", "oku", "yaz", "detaylandır", "aktar"]
    CONFIRMATION_WORDS = {
        "evet", "tamam", "olur", "tabi", "tabii", "lütfen", "yolla", "göster",
        "anlat", "ver", "verin", "paylaş", "detay", "detaylandır", "getir", "söyle", "oku"
    }
    THANK_WORDS = ["sağol", "sağolun", "saol", "teşekkürler", "teşekkür", "teşekkür ederim", "eyvallah", "rica ederim"]

    def __init__(self):
        self.spell_corrector = AutoSpellCorrector()

    @classmethod
    def is_thanks(cls, query: str) -> bool:
        q = query.lower().strip()
        words = set(re.findall(r'\b\w+\b', q))
        return bool(words.intersection(set(cls.THANK_WORDS)))

    @classmethod
    def is_greeting_word(cls, word: str) -> bool:
        if not word or len(word) < 3:
            return False
        clean_w = word.strip().lower()
        if clean_w in cls.CANONICAL_GREETINGS:
            return True
        matches = difflib.get_close_matches(clean_w, cls.CANONICAL_GREETINGS, n=1, cutoff=0.70)
        return bool(matches)

    @classmethod
    def is_direct_action_request(cls, query: str) -> bool:
        q = query.lower().strip()
        return any(re.search(r'\b' + verb + r'[a-zçğıöşü]*\b', q) for verb in cls.ACTION_VERBS)

    @classmethod
    def is_confirmation(cls, query: str) -> bool:
        words = set(re.findall(r'\b\w+\b', query.lower()))
        return bool(words.intersection(cls.CONFIRMATION_WORDS)) or cls.is_direct_action_request(query)

    def is_gibberish(self, query: str) -> bool:
        q = query.strip().lower()
        if len(q) < 3:
            return True
        if re.search(r'(.{2,4})\1{2,}', q):
            return True
        vowels = set("aeıioöuü")
        words = q.split()
        for w in words:
            if len(w) > 4 and not any(char in vowels for char in w):
                return True
        return False

    def is_greeting(self, query: str, detected_company: Optional[str] = None) -> bool:
        if detected_company:
            return False

        clean_q = self.spell_corrector.correct(query.strip().lower())
        words = clean_q.split()
        for w in words:
            if self.is_greeting_word(w):
                return True
        return False

    @classmethod
    def is_rejection(cls, query: str) -> bool:
        q = query.lower().strip()
        return any(r in q for r in cls.REJECTION_WORDS)

    @classmethod
    def is_pronoun_followup(cls, query: str) -> bool:
        q = query.lower().strip()
        return any(p in q or q == p for p in cls.PRONOUN_PATTERNS)

    @classmethod
    def is_availability_query(cls, query: str) -> bool:
        q = query.lower().strip()
        if any(p in q for p in cls.AVAILABILITY_PATTERNS):
            return True
        return bool(cls.AVAILABILITY_REGEX.search(q))

    @classmethod
    def is_company_only_query(cls, query: str, detected_company: Optional[str]) -> bool:
        if not detected_company:
            return False
        if cls.is_direct_action_request(query):
            return False
        words = query.lower().split()
        action_kws = ["kar", "kâr", "bilanço", "çeyrek", "cyrk", "fiyat", "temettü", "hisse", "kaç", "ne kadar", "neka", "sonuç", "açıkladı", "kuru", "faizi"]
        return len(words) <= 3 and not any(kw in query.lower() for kw in action_kws)

    def clean_query(self, query: str) -> str:
        rewritten = query.strip()

        term_replacements = {
            r'\btümşirket[a-zçğıöşü]*\b': 'büyük şirketler',
            r'\bbüyükşirket[a-zçğıöşü]*\b': 'büyük şirketler',
            r'\bbbono\b': 'bono',
            r'\bbilano[çc]olar[ıa]*\b': 'bilançolar',
            r'\bbilancolar[ıa]*\b': 'bilançolar',
            r'\bthavil\b': 'tahvil',
            r'\bfoviz\b': 'döviz',
            r'\bdoviz\b': 'döviz',
            r'\beruo\b': 'euro',
            r'\beuroo\b': 'euro',
            r'\bdlr\b': 'dolar',
            r'\bgrnat\b': 'garanti',
            r'\bgranti\b': 'garanti',
            r'\bbnksı\b': 'bankası',
            r'\bbnksi\b': 'bankası',
            r'\bneka\s*dar\b': 'ne kadar',
            r'\bucnc\b': 'üçüncü',
            r'\bcyrk\b': 'çeyrek',
            r'\bcyrktei\b': 'çeyrekteki',
            r'\bcyrkte\b': 'çeyrekte',
            r'\bceyrek\b': 'çeyrek',
            r'\bv\s*armı\b': 'var mı',
            r'\bv\s*armi\b': 'var mı',
            r'\bvarmı\b': 'var mı',
            r'\bvarmi\b': 'var mı',
            r'\bvrmı\b': 'var mı',
            r'\bvrmi\b': 'var mı'
        }
        for pattern, repl in term_replacements.items():
            rewritten = re.sub(pattern, repl, rewritten, flags=re.IGNORECASE)

        quarter_regex_4 = r'\b(son|dördüncü|dorduncu|dordunc|drnc|4)\s*\.?\s*(e\.)?\s*[cç][eyrk]*[a-zçğıöşü]*\b'
        quarter_regex_3 = r'\b(üçüncü|ucuncu|ucunc|ucnc|3)\s*\.?\s*[cç][eyrk]*[a-zçğıöşü]*\b'
        quarter_regex_2 = r'\b(ikinci|ikinc|iknc|2)\s*\.?\s*(e\.)?\s*[cç][eyrk]*[a-zçğıöşü]*\b'
        quarter_regex_1 = r'\b(ilk|birinci|birinc|birnc|brnc|1)\s*\.?\s*(e\.)?\s*[cç][eyrk]*[a-zçğıöşü]*\b'

        rewritten = re.sub(quarter_regex_4, '4. çeyrek (son çeyrek)', rewritten, flags=re.IGNORECASE)
        rewritten = re.sub(quarter_regex_3, '3. çeyrek', rewritten, flags=re.IGNORECASE)
        rewritten = re.sub(quarter_regex_2, '2. çeyrek', rewritten, flags=re.IGNORECASE)
        rewritten = re.sub(quarter_regex_1, '1. çeyrek', rewritten, flags=re.IGNORECASE)

        return rewritten

    @classmethod
    def extract_quarter(cls, text: str) -> Optional[str]:
        if re.search(r'\b(4\.?\s*çeyrek|son\s+çeyrek|dördüncü\s+çeyrek)\b', text, re.I):
            return "4"
        if re.search(r'\b(3\.?\s*çeyrek|üçüncü\s+çeyrek)\b', text, re.I):
            return "3"
        if re.search(r'\b(2\.?\s*çeyrek|ikinci\s+çeyrek)\b', text, re.I):
            return "2"
        if re.search(r'\b(1\.?\s*çeyrek|ilk\s+çeyrek|birinci\s+çeyrek)\b', text, re.I):
            return "1"
        return None


class FinancialMappingManager:
    """
    Aşama 5: Qwen 2.5 7B Destekli Çoklu Varlık ve İmla Dayanıklı Algılama Motoru.
    """
    EXCLUDED_WORDS = {
        "selam", "merhaba", "günaydın", "iyi", "günler", "akşamlar", "naber", "nasılsın", "slm", "mrb",
        "evet", "hayır", "olur", "ver", "tamam", "paylaş", "tabi", "tabii", "lütfen", "detay", "yolla",
        "anlat", "göster", "getir", "söyle", "yaz", "oku", "hakkında", "bilgi", "haber",
        "çeyrek", "çeyrekte", "çeyrekteki", "çyrektei", "çeyreği", "kar", "kâr", "zarar", "bilanço",
        "bilançosu", "bilanoçoları", "durumu", "nedir", "sonuç", "sonucu", "fiyatı", "kuru", "faizi", "son",
        "tarih", "tarihi", "tarihçe", "geçmiş", "güncel", "hepsi", "tümü", "oranı", "oranları", "ve", "veya",
        "sağol", "sağolun", "saol", "teşekkürler", "teşekkür", "eyvallah", "rica"
    }

    def __init__(self, config_path: str = "./data/company_mappings.json"):
        self.config_path = config_path
        self.mapping: Dict[str, Dict[str, str]] = {}
        self.load_mappings()
        self.optimizer = QueryOptimizer()

    def load_mappings(self):
        if os.path.exists(self.config_path):
            with open(self.config_path, 'r', encoding='utf-8') as f:
                self.mapping = json.load(f)
        else:
            self.mapping = {}
        
        self.all_keys = list(self.mapping.keys())
        sorted_keys = sorted([k for k in self.mapping.keys() if len(k) >= 2], key=len, reverse=True)
        pattern_str = r'\b(' + '|'.join(re.escape(k) for k in sorted_keys) + r')[a-zçğıöşü]*\b'
        self.company_regex = re.compile(pattern_str, re.IGNORECASE)

    def detect_companies(self, query: str) -> List[str]:
        q_cleaned = self.optimizer.clean_query(query)
        q_lower = q_cleaned.lower()

        # 0. KÜÇÜK ŞİRKETLER (SMALL-CAP) UYARI KONTROLÜ
        if any(w in q_lower for w in ["küçük şirket", "küçük şirketler", "küçük ölçekli", "yan tahta", "small cap", "small-cap"]):
            return ["KUCUK_SIRKET_UYARI"]

        all_detected = []

        # 1. Bireysel Varlık / Şirket Eşleşmeleri (Exact / Regex Match)
        raw_matches = []
        for match in self.company_regex.finditer(q_lower):
            matched_key = match.group(1).lower()
            comp_name = self.mapping.get(matched_key, {}).get("name")
            if comp_name:
                raw_matches.append((match.start(), match.end(), comp_name, matched_key))

        for m in raw_matches:
            if m[2] not in all_detected:
                all_detected.append(m[2])

        # 2. Esnek Kategori Bazlı Eşleşmeler (Döviz, Tahvil/Bono, Şirket Bilançoları)
        doviz_specific = [c for c in ["Dolar", "Euro", "İngiliz Sterlini"] if c in all_detected]
        has_general_doviz_keyword = bool(re.search(r'\b(d[öo]viz|foviz)\b', q_lower))

        if has_general_doviz_keyword or not doviz_specific:
            if has_general_doviz_keyword or re.search(r'\b(kurlar|kurları)\b', q_lower):
                for d in ["Dolar", "Euro", "İngiliz Sterlini"]:
                    if d not in all_detected:
                        all_detected.append(d)

        if re.search(r'\b(altın|altınlar|gram altın)\b', q_lower):
            if "Gram Altın" not in all_detected:
                all_detected.append("Gram Altın")
        if re.search(r'\b(tahvil|thavil|bono|bonolar|bbono)\b', q_lower):
            if "Devlet Tahvili" not in all_detected:
                all_detected.append("Devlet Tahvili")
        if re.search(r'\b(fon|fonlar|yatırım fonları)\b', q_lower):
            if "Yatırım Fonları" not in all_detected:
                all_detected.append("Yatırım Fonları")
        if re.search(r'\b(büyük şirket|tüm şirket|şirket|şriket|bilan[çc]o|bilano[çc]o)\b', q_lower):
            for s in ["Garanti BBVA", "Türk Hava Yolları", "Apple", "Nvidia"]:
                if s not in all_detected:
                    all_detected.append(s)

        # 3. Kelime Bazlı Yüksek Hassasiyetli Fuzzy Match (Sadece muaf tutulmayan kelimeler için)
        words = q_lower.split()
        for word in words:
            w_clean = re.sub(r'[^\w\s]', '', word)
            if w_clean in self.EXCLUDED_WORDS or QueryOptimizer.is_greeting_word(w_clean):
                continue
            if len(w_clean) >= 4:
                cutoff = 0.80 if len(w_clean) <= 5 else 0.85
                matches = difflib.get_close_matches(w_clean, self.all_keys, n=1, cutoff=cutoff)
                if matches:
                    matched_key = matches[0]
                    comp_name = self.mapping.get(matched_key, {}).get("name")
                    if comp_name and comp_name not in all_detected:
                        all_detected.append(comp_name)

        unique_detected = []
        for item in all_detected:
            if item not in unique_detected:
                unique_detected.append(item)

        return unique_detected

    def detect_company(self, query: str) -> Optional[str]:
        comps = self.detect_companies(query)
        return comps[0] if comps else None


class FinancialRAGAssistant:
    """
    Production-ready Qwen 2.5 7B Destekli Smart Hibrit RAG Finansal Asistan.
    """
    def __init__(
        self,
        persist_directory: str = "./chroma_db",
        ollama_model: str = "qwen2.5:7b",
        embedding_model_name: str = "sentence-transformers/paraphrase-multilingual-MiniLM-L12-v2",
        mapping_config_path: str = "./data/company_mappings.json"
    ):
        self.persist_directory = persist_directory
        self.mapping_manager = FinancialMappingManager(config_path=mapping_config_path)
        self.optimizer = QueryOptimizer()
        self.text_splitter = RecursiveCharacterTextSplitter(chunk_size=500, chunk_overlap=50)

        # 1. Embedding Modeli
        self.embeddings = HuggingFaceEmbeddings(
            model_name=embedding_model_name,
            model_kwargs={'device': 'cpu'}
        )

        # 2. Kalıcı Chroma Vector Database
        self.vectorstore = Chroma(
            collection_name="live_financial_docs",
            embedding_function=self.embeddings,
            persist_directory=self.persist_directory
        )

        # 3. BM25 İndeksi
        self.all_chunks: List[Document] = []
        self.bm25_retriever: Optional[BM25Retriever] = None
        self._load_existing_chunks_for_bm25()

        # 4. LLM (Ollama - Qwen 2.5 7B)
        self.llm = ChatOllama(model=ollama_model, temperature=0.0)

        # 5. Session State
        self.sessions: Dict[str, Dict] = {}

    def _load_existing_chunks_for_bm25(self):
        existing_data = self.vectorstore.get()
        if existing_data and existing_data.get("documents"):
            documents = []
            for text, meta in zip(existing_data["documents"], existing_data["metadatas"]):
                documents.append(Document(page_content=text, metadata=meta or {}))
            self.all_chunks = documents
            self._update_bm25()

    def _update_bm25(self):
        if self.all_chunks:
            self.bm25_retriever = BM25Retriever.from_documents(self.all_chunks)
            self.bm25_retriever.k = 3

    def ingest_live_data(self, raw_documents: List[Document]):
        chunks = self.text_splitter.split_documents(raw_documents)
        if not chunks:
            return

        existing_contents = {doc.page_content for doc in self.all_chunks}
        new_chunks = [c for c in chunks if c.page_content not in existing_contents]

        if not new_chunks:
            return

        self.vectorstore.add_documents(new_chunks)
        self.all_chunks.extend(new_chunks)
        self._update_bm25()
        print(f"-> [Canlı Veri İçe Aktarıldı]: {len(new_chunks)} yeni parça veritabanına işlendi.")

    def _get_session(self, session_id: str) -> Dict:
        if session_id not in self.sessions:
            self.sessions[session_id] = {
                "pending_offer": False,
                "pending_company": "",
                "pending_content": "",
                "last_company": ""
            }
        return self.sessions[session_id]

    async def classify_intent_async(self, query: str, detected_company: Optional[str] = None) -> str:
        if detected_company:
            return "FINANS"

        financial_keywords = ["hisse", "kar", "kâr", "bilanço", "borsa", "çeyrek", "fiyat", "temettü", "thyao", "garan", "haber", "altın", "dolar", "euro", "sterlin", "tahvil", "bono", "fon", "detay"]
        if any(kw in query.lower() for kw in financial_keywords):
            return "FINANS"

        system_prompt = "Sen bir finansal niyet sınıflandırıcısısın. SADECE 'FINANS' veya 'KAPSAM_DISI' döndür."
        messages = [SystemMessage(content=system_prompt), HumanMessage(content=query)]
        try:
            res = await self.llm.ainvoke(messages)
            return "FINANS" if "FINANS" in res.content.strip().upper() else "KAPSAM_DISI"
        except Exception:
            return "FINANS"

    def _retrieve_docs_for_company(self, company: str, query: str) -> List[Document]:
        filter_dict = {"company": company}
        search_q = f"{company} finansal sonuçları kurları ve haberleri"
        
        v_results = self.vectorstore.similarity_search(search_q, k=3, filter=filter_dict)
        matched_chunks = [d for d in self.all_chunks if d.metadata.get("company", "").lower() == company.lower()]
        
        combined = list({d.page_content: d for d in (v_results + matched_chunks)}.values())
        return combined[:3]

    async def chat_async(self, query: str, session_id: str = "default") -> str:
        state = self._get_session(session_id)
        user_input_lower = query.lower().strip()

        detected_companies = self.mapping_manager.detect_companies(query)

        # -------------------------------------------------------------
        # KÜÇÜK ŞİRKETLER (SMALL-CAP) ŞEFFAF UYARI KONTROLÜ
        # -------------------------------------------------------------
        if detected_companies == ["KUCUK_SIRKET_UYARI"]:
            return "Veritabanımız şu anda BİST 30, BİST 100 ve küresel dev (large-cap / mega-cap) şirketlerin verilerini barındırmaktadır. Küçük ölçekli (small-cap) şirket verileri henüz entegre edilmemiştir. Dilerseniz BİST ve küresel büyük şirketler hakkında bilgi verebilirim."

        detected_company = detected_companies[0] if detected_companies else None

        # -------------------------------------------------------------
        # ÇOKLU VARLIK / BİRLEŞİK KATEGORİ SORGULAMA MOTORU
        # -------------------------------------------------------------
        if len(detected_companies) > 1:
            clean_q = self.optimizer.clean_query(query)
            
            # MANTIKSAL KATEGORİ SIRALAMASI: Önce tüm Piyasa Varlıkları, ardından tüm Şirket Bilançoları
            market_assets_detected = [c for c in detected_companies if c in MARKET_ASSET_NAMES]
            equity_companies_detected = [c for c in detected_companies if c not in MARKET_ASSET_NAMES]
            ordered_companies = market_assets_detected + equity_companies_detected
            
            sections = []
            for comp in ordered_companies:
                comp_docs = self._retrieve_docs_for_company(comp, query)
                
                if not comp_docs:
                    sections.append(f"### {comp}:\nVeritabanımızda {comp} ile ilgili doğrulanmış bir bilgi bulunmamaktadır.")
                    continue
                
                comp_context = "\n".join([d.page_content for d in comp_docs])
                is_market_asset = comp in MARKET_ASSET_NAMES
                
                if is_market_asset:
                    sys_msg = f"""Sen Türkçe konuşan resmi bir finans analizörüsün.
GÖREV:
SADECE {comp} piyasa varlığına ait güncel Alış/Satış kurlarını veya faiz oranlarını net 1 cümle ile bildir.
- Tarihçe, geçmiş veya genel tanım ASLA ANLATMA.
- Şirket bilançoları veya döviz kuru tahminleri uydurma.
- SADECE SAF TÜRKÇE KELİMELER VE TÜRKÇE ALFABE KULLAN. Çince veya İngilizce kelimeler/karakterler ASLA KULLANMA."""
                else:
                    sys_msg = f"""Sen Türkçe konuşan resmi bir finans analizörüsün.
GÖREV:
SADECE {comp} şirketinin son çeyrek bilanço verilerini (net kâr, gelir, aktif büyüklüğü vb.) net 1-2 madde ile açıkla.
- SADECE {comp} şirketinin bankacılık/finans sonuçlarını ver. TÜİK dış ticaret endeksi gibi alakasız makro verileri SAKIN EKLEME.
- SAKIN DÖVİZ KURU (1 USD = X TRY gibi) VEYA FAİZ ORANI UYDURMA, ASLA EKLEME.
- SAKIN 'ASLA PAYLAŞTIRILMADI' gibi prompt etiketleri veya İngilizce/İspanyolca/Çince kelimeler/karakterler KULLANMA.
- SADECE SAF TÜRKÇE KELİMELER VE TÜRKÇE ALFABE KULLAN. Yabancı kelimeler veya Çince karakterler ASLA KULLANMA."""

                user_msg = f"VERİ:\n{comp_context}\n\nSORU:\n{comp} için finansal verileri ver."
                
                res_obj = await self.llm.ainvoke([SystemMessage(content=sys_msg), HumanMessage(content=user_msg)])
                clean_ans = ResponseSanitizer.sanitize(res_obj.content, is_equity_company=not is_market_asset)
                if not clean_ans:
                    clean_ans = comp_context
                sections.append(f"### {comp}:\n{clean_ans}")
                
            return "\n\n".join(sections)

        # 2. DİYALOG TAKİBİ (Tekil Onay / 'olur' Akışı)
        if state["pending_offer"]:
            if self.optimizer.is_rejection(user_input_lower):
                state["pending_offer"] = False
                state["pending_company"] = ""
                state["last_company"] = ""
                return "Anlaşıldı, başka bir finansal konuda yardımcı olabilir miyim?"
            elif QueryOptimizer.is_confirmation(user_input_lower):
                content = state["pending_content"]
                company = state["pending_company"]
                state["pending_offer"] = False
                state["pending_company"] = ""
                state["last_company"] = company
                
                is_market_asset = company in MARKET_ASSET_NAMES
                sys_msg = f"""Sen Türkçe konuşan resmi bir finans analizörüsün.
GÖREV:
SADECE {company} varlığına ait bilgileri net 1-2 madde veya cümle ile açıkla.
- SADECE SAF TÜRKÇE KELİMELER VE TÜRKÇE ALFABE KULLAN.
- Çince, İngilizce, İspanyolca veya Almanca kelimeler/karakterler ASLA KULLANMA.
- Sakın Çince yanıt verme veya Çince karakter üretme.
- Giriş etiketleri (Soru:, Cevap:, Evet haber var) KULLANMA."""
                
                messages = [
                    SystemMessage(content=sys_msg),
                    HumanMessage(content=f"VERİ:\n{content}\n\nSORU:\n{company} finansal detaylarını Türkçe açıkla.")
                ]
                res = await self.llm.ainvoke(messages)
                return ResponseSanitizer.sanitize(res.content, is_equity_company=not is_market_asset)
            else:
                state["pending_offer"] = False
                state["pending_company"] = ""

        # 3. KONTROL: TEŞEKKÜR / SAĞOL VEYA ŞİRKETSİZ / VARLIKSIZ SORULAR
        if not detected_company:
            if QueryOptimizer.is_thanks(query):
                return "Rica ederim! Başka bir finansal konuda yardımcı olabilir miyim?"

            if self.optimizer.is_pronoun_followup(query):
                state["last_company"] = ""
                return "Hangi şirketin, döviz kurunun veya finansal varlığın haberini öğrenmek istiyorsunuz? (Örn: 'Dolar kuru', 'THY haberlerini ver', 'Euro ne kadar')"
            
            if any(w in user_input_lower for w in ["çeyrek", "cyrk", "kar", "kâr", "bilanço", "temettü", "hisse"]):
                state["last_company"] = ""
                return "Hangi şirketin finansal verisini öğrenmek istiyorsunuz? Lütfen şirket adını belirtin. (Örn: 'Garanti son çeyrek kârı ne kadar?' veya 'THY 3. çeyrek')"

        if detected_company:
            state["last_company"] = detected_company

        # 4. SELAMLAŞMA KONTROLÜ
        if self.optimizer.is_greeting(query, detected_company=detected_company):
            return "Merhaba! Ben Finansal Asistan. Borsa, döviz kurları (Dolar, Euro, Sterlin), altın, tahvil/bono ve şirket bilançoları hakkında nasıl yardımcı olabilirim?"

        # 5. ANLAMSIZ METİN FİLTRESİ
        if not detected_company and self.optimizer.is_gibberish(query):
            return "Anlayamadığım veya rastgele bir metin girdiniz. Lütfen finansal bir konu, döviz veya şirket sorunuz. (Örn: 'Dolar kuru ne kadar?' veya 'Garanti 3. çeyrek kârı')"

        # 6. Niyet Kontrolü
        intent = await self.classify_intent_async(query, detected_company=detected_company)
        if intent == "KAPSAM_DISI":
            return "Ben bir finansal analiz asistanıyım. Sadece borsa, döviz kurları, altın, tahvil/bono ve ekonomi konularında yardımcı olabilirim."

        clean_query = self.optimizer.clean_query(query)
        final_docs = self._retrieve_docs_for_company(detected_company, clean_query) if detected_company else []

        if not final_docs:
            return f"Sorunuza karşılık veritabanımızda {detected_company or ''} ile ilgili doğrulanmış bir bilgi bulunmamaktadır."

        context = "\n\n".join([doc.page_content for doc in final_docs])

        # 7. Sorunun Tipi ve Çeyrek Dönem Doğrulaması
        req_quarter = QueryOptimizer.extract_quarter(clean_query)
        ctx_quarter = QueryOptimizer.extract_quarter(context)

        if req_quarter and ctx_quarter and req_quarter != ctx_quarter:
            state["pending_offer"] = True
            state["pending_company"] = detected_company or ""
            state["pending_content"] = context
            return "Aradığınız döneme ait bilgi bulunmamaktadır. Dilerseniz elimizdeki mevcut dönem bilgisini paylaşabilirim."

        is_avail = QueryOptimizer.is_availability_query(query)
        is_company_only = QueryOptimizer.is_company_only_query(query, detected_company)
        is_direct_action = QueryOptimizer.is_direct_action_request(query)

        if (is_avail or is_company_only) and not is_direct_action:
            state["pending_offer"] = True
            state["pending_company"] = detected_company or ""
            state["pending_content"] = context
            return f"Evet, {detected_company or 'ilgili varlık'} ile ilgili güncel bilgi bulunmaktadır. Dilerseniz detayları paylaşabilirim."

        is_market_asset = detected_company in MARKET_ASSET_NAMES if detected_company else False
        if is_direct_action:
            system_instruction = f"""Sen Türkçe konuşan resmi bir finans analizörüsün.
GÖREV:
Kullanıcı {detected_company or 'varlık'} hakkındaki detayları paylaşmanı istedi. SADECE VERİ metnindeki bilgileri kullanarak net 1-2 cümle ile bilgileri açıkla.
- SADECE SAF TÜRKÇE KELİMELER VE TÜRKÇE ALFABE KULLAN. Yabancı kelimeler veya Çince karakterler ASLA KULLANMA.
- Sakın 'Evet haber var', 'Senin verine göre' veya 'Şifreli bilgi' DEME.
"""
        else:
            system_instruction = f"""Sen Türkçe konuşan resmi bir finans analizörüsün.
GÖREV:
Sorulan soruyu VERİ metnindeki bilgilere göre SADECE {detected_company or 'varlık'} için net 1 cümle ile yanıtla. 
- SADECE SAF TÜRKÇE KELİMELER VE TÜRKÇE ALFABE KULLAN. Yabancı kelimeler veya Çince karakterler ASLA KULLANMA.
- Giriş etiketleri (Soru:, Cevap:, Evet haber var, Bu bilgiye göre) KULLANMA.
"""

        messages = [
            SystemMessage(content=system_instruction),
            HumanMessage(content=f"VERİ:\n{context}\n\nSORU:\n{clean_query}")
        ]

        response_obj = await self.llm.ainvoke(messages)
        clean_response = ResponseSanitizer.sanitize(response_obj.content, is_equity_company=not is_market_asset)

        if not clean_response:
            clean_response = context

        if "dilerseniz" in clean_response.lower() or "mevcut dönem" in clean_response.lower():
            state["pending_offer"] = True
            state["pending_company"] = detected_company or ""
            state["pending_content"] = context

        return clean_response


# ==========================================
# İNTERAKTİF TEST
# ==========================================
async def main():
    assistant = FinancialRAGAssistant(persist_directory="./chroma_db")

    print("--- Finansal Asistan Stage 5 (Sağol / Sahol Excluded Words Active) Başlatıldı (Çıkış için 'q') ---")
    session_id = "test_user_saagol"

    while True:
        user_query = input("\nSoru: ")
        if user_query.lower() in ['q', 'exit', 'cikis']:
            break

        bot_response = await assistant.chat_async(user_query, session_id=session_id)
        print(f"Bot: {bot_response}")

if __name__ == "__main__":
    asyncio.run(main())