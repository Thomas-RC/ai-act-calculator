// AlpineJS root component — cały state aplikacji.
// Komunikuje się z backendem przez nginx proxy na /api/*.

function app() {
  return {
    step: 'form',            // 'form' | 'loading' | 'result' | 'error'
    ankieta: pustaAnkieta(),
    wynik: null,
    error: '',
    pdfLoading: false,
    meta: [],                // proweniencja korpusu pobierana na starcie

    // Listy opcji dla UI
    praktykiZakazaneLista: [
      { v: 'manipulacja_podprogowa',      t: 'Manipulacja podprogowa',             d: 'Techniki niebędące przedmiotem świadomości — Art. 5 ust. 1 lit. a.' },
      { v: 'exploitation_wrazliwosci',    t: 'Wykorzystanie wrażliwości osób',     d: 'Ze względu na wiek, niepełnosprawność, sytuację — lit. b.' },
      { v: 'social_scoring',              t: 'Social scoring przez władzę publiczną', d: 'Ocena zachowań społecznych — lit. c.' },
      { v: 'predykcja_przestepczosci',    t: 'Predykcja popełnienia przestępstwa', d: 'Na bazie cech osobowych — lit. d.' },
      { v: 'scraping_twarzy',             t: 'Scraping twarzy z internetu/CCTV',   d: 'Rozbudowa bazy rozpoznawania twarzy — lit. e.' },
      { v: 'rozpoznawanie_emocji',        t: 'Rozpoznawanie emocji w pracy/edukacji', d: 'Lit. f.' },
      { v: 'kategoryzacja_biometryczna',  t: 'Kategoryzacja biometryczna (chronione cechy)', d: 'Rasa, poglądy polityczne, religia — lit. g.' },
      { v: 'biometria_realtime_publiczna', t: 'Biometria czasu rzeczywistego w przestrzeniach publicznych', d: 'Lit. h.' },
    ],

    sektoryLista: [
      { v: 'inne', t: '— żaden z poniższych —' },
      { v: 'biometria',                t: '1. Biometria (zdalna identyfikacja, kategoryzacja, rozpoznawanie emocji)' },
      { v: 'infrastruktura',           t: '2. Infrastruktura krytyczna (energetyka, transport, ruch drogowy)' },
      { v: 'edukacja',                 t: '3. Edukacja i szkolenia zawodowe' },
      { v: 'zatrudnienie',             t: '4. Zatrudnienie, zarządzanie pracownikami, samozatrudnienie' },
      { v: 'uslugi_publiczne',         t: '5. Usługi publiczne (świadczenia socjalne, kredyt, zdrowie, ubezpieczenia)' },
      { v: 'sciganie',                 t: '6. Ściganie przestępstw' },
      { v: 'migracja',                 t: '7. Migracja, azyl, kontrola graniczna' },
      { v: 'wymiar_sprawiedliwosci',   t: '8. Wymiar sprawiedliwości i procesy demokratyczne' },
    ],

    daneLista: [
      { v: 'ogolne',        t: 'Ogólne' },
      { v: 'biometryczne',  t: 'Biometryczne' },
      { v: 'zdrowotne',     t: 'Zdrowotne' },
      { v: 'behawioralne',  t: 'Behawioralne' },
      { v: 'lokalizacyjne', t: 'Lokalizacyjne' },
    ],

    // --- computed ---

    get kategoriaBg() {
      if (!this.wynik) return '';
      return {
        'NIEDOPUSZCZALNY': 'bg-gradient-to-r from-rose-600 to-rose-700',
        'WYSOKIE':         'bg-gradient-to-r from-orange-500 to-orange-600',
        'OGRANICZONE':     'bg-gradient-to-r from-amber-400 to-amber-500',
        'MINIMALNE':       'bg-gradient-to-r from-emerald-500 to-emerald-600',
      }[this.wynik.kategoria] || 'bg-slate-600';
    },

    get kategoriaIcon() {
      if (!this.wynik) return 'help-circle';
      return {
        'NIEDOPUSZCZALNY': 'ban',
        'WYSOKIE':         'alert-triangle',
        'OGRANICZONE':     'info',
        'MINIMALNE':       'check-circle-2',
      }[this.wynik.kategoria] || 'help-circle';
    },

    // --- lifecycle ---

    async init() {
      try {
        const r = await fetch('/api/meta');
        if (r.ok) this.meta = await r.json();
      } catch (e) { /* silent */ }
      this._renderIcons();
      // Re-render ikon przy każdej zmianie kroku (Alpine nie wywołuje lucide.createIcons() sam)
      this.$watch('step', () => queueMicrotask(() => this._renderIcons()));
      this.$watch('wynik', () => queueMicrotask(() => this._renderIcons()));
    },

    _renderIcons() {
      if (window.lucide) window.lucide.createIcons();
    },

    // --- akcje ---

    resetForm() {
      this.ankieta = pustaAnkieta();
      this.wynik = null;
      this.error = '';
      this.step = 'form';
    },

    async klasyfikuj() {
      this.error = '';
      this.step = 'loading';
      // Jeśli nie zaznaczono żadnej zakazanej praktyki, dodaj "zadne" żeby API dostało niepustą listę
      const payload = { ...this.ankieta };
      if (!payload.praktyki_zakazane.length) {
        payload.praktyki_zakazane = ['zadne'];
      }
      if (!payload.dane_wejsciowe.length) {
        payload.dane_wejsciowe = ['ogolne'];
      }
      try {
        const r = await fetch('/api/classify', {
          method: 'POST',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify(payload),
        });
        if (!r.ok) {
          const errBody = await r.json().catch(() => ({}));
          throw new Error(errBody.detail || `Błąd HTTP ${r.status}`);
        }
        this.wynik = await r.json();
        this.step = 'result';
      } catch (e) {
        this.error = e.message || String(e);
        this.step = 'error';
      }
    },

    async pobierzPDF() {
      this.pdfLoading = true;
      try {
        // Wysyłamy i wynik klasyfikacji, i oryginalną ankietę — żeby PDF mógł pokazać opis systemu
        const payload = {
          odpowiedz: this.wynik,
          ankieta: { ...this.ankieta,
            praktyki_zakazane: this.ankieta.praktyki_zakazane.length ? this.ankieta.praktyki_zakazane : ['zadne'],
            dane_wejsciowe: this.ankieta.dane_wejsciowe.length ? this.ankieta.dane_wejsciowe : ['ogolne'],
          },
        };
        const r = await fetch('/api/report', {
          method: 'POST',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify(payload),
        });
        if (!r.ok) throw new Error(`Błąd HTTP ${r.status}`);
        const blob = await r.blob();
        const url = URL.createObjectURL(blob);
        const a = document.createElement('a');
        a.href = url;
        a.download = `ai_act_raport_${new Date().toISOString().slice(0,10)}.pdf`;
        document.body.appendChild(a);
        a.click();
        a.remove();
        URL.revokeObjectURL(url);
      } catch (e) {
        alert('Nie udało się pobrać PDF-a: ' + (e.message || e));
      } finally {
        this.pdfLoading = false;
      }
    },
  };
}

function pustaAnkieta() {
  return {
    opis: '',
    cel_systemu: '',
    praktyki_zakazane: [],
    sektor: 'inne',
    uzytkownik_koncowy: '',
    dane_wejsciowe: [],
    autonomia: 'doradczy',
    zal_I_produkt: false,
    art_50_generacja_lub_interakcja: false,
    rola: 'dostawca',
  };
}
