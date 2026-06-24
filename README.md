# Monitoring warunkow ruchu na al. Wojska Polskiego w Szczecinie

Male repozytorium badawcze w Pythonie do cyklicznego pobierania danych o warunkach ruchu z TomTom Traffic API, zapisywania pomiarow w SQLite i generowania raportow dobowych w Markdown oraz HTML.

Projekt nie korzysta ze scrapingu Google Maps, automatycznych zrzutow ekranu Google Maps ani zapisywania kafelkow mapowych. Dane pomiarowe pochodza z endpointu TomTom Traffic API Flow Segment Data. Repo zawiera tez opcjonalny tor badawczy oparty o TomTom Routing API, ktory mierzy czas przejazdu zdefiniowanych odcinkow.

## Cel projektu

Projekt monitoruje wybrane punkty pomiarowe na al. Wojska Polskiego w Szczecinie. Dla kazdego punktu pobiera biezaca predkosc, predkosc swobodna, biezacy czas przejazdu, swobodny czas przejazdu, wiarygodnosc danych i informacje o zamknieciu drogi. Na tej podstawie oblicza wskazniki opoznienia i przeciazenia ruchu.

Projekt odpytuje tylko wybrane punkty z `config/points.yaml` oraz, opcjonalnie, trasy z `config/routes.yaml`. Nie pobiera wszystkich drog w Szczecinie, nie pobiera kafelkow, nie odpytuje incydentow i nie korzysta z Google Maps. Z odpowiedzi TomTom do kolumn analitycznych trafia wybrany zestaw pol potrzebnych do badania, ale pelna odpowiedz API jest zachowana w `raw_json` oraz w plikach `data/raw/` albo `data/raw_routes/`.

## Klucz TomTom API

1. Zaloz konto w portalu TomTom Developer: <https://developer.tomtom.com/>.
2. Utworz aplikacje i wlacz dostep do Traffic API.
3. Jesli chcesz testowac czasy przejazdu tras, wlacz dla tego samego klucza takze Routing API.
4. Skopiuj klucz API.
5. Ustaw zmienna srodowiskowa:

```bash
export TOMTOM_API_KEY="twoj_klucz"
```

W systemie Windows PowerShell:

```powershell
$env:TOMTOM_API_KEY="twoj_klucz"
```

Lokalnie mozna tez utworzyc plik `.env` na podstawie `.env.example`.

## Konfiguracja punktow pomiarowych

Punkty sa zdefiniowane w `config/points.yaml`. Kazdy punkt zawiera:

- `id`
- `name`
- `latitude`
- `longitude`
- `direction`
- `location_description`
- `corridor_order`
- opcjonalne `traffic_role` i `connection_name` dla wlotow, wylotow i punktow wezlowych

Wspolrzedne nalezy traktowac jako punkty orientacyjne dla endpointu Flow Segment Data. Przed dluzszym monitoringiem warto zweryfikowac, czy TomTom przypisuje je do oczekiwanych segmentow ulicznych.

## Konfiguracja tras odcinkowych

Trasy sa zdefiniowane w `config/routes.yaml`. Ten plik sluzy do pomiaru czasu przejazdu calym odcinkiem, np. `Plac Zwyciestwa -> Plac Szarych Szeregow`, zamiast oceny pojedynczego punktu.

Na serwerze punkty sa domyslnie mierzone co 15 minut. Trasy mozna wlaczyc
ustawieniem `routing.enabled: true`; wtedy sa mierzone raz na godzine, zgodnie
z `routing.measurement_interval_minutes: 60`. Przy 24 punktach i 2 trasach
daje to 2352 zapytania na typowa dobe.

Niezaleznie od Routing API projekt domyslnie estymuje czasy obu kierunkow AWP
z juz pobranych predkosci Flow (`route_estimation.enabled: true`). Punkty
korytarzowe sa wskazane przez `point_ids` w `config/routes.yaml`. Dlugosc
reprezentowana przez punkt wynika z polow odleglosci do punktow sasiednich,
a czas odcinka jest suma `dlugosc / predkosc`. Ta metoda nie zuzywa dodatkowych
requestow API.

Kazda trasa zawiera:

- `id`
- `name`
- `direction`
- `corridor_order`
- `point_ids` - uporzadkowane punkty Flow uzywane do estymacji
- `coordinates` - punkt startowy, opcjonalne punkty posrednie i punkt koncowy

Bezposredni tryb Routing API jest domyslnie wylaczony w
`config/settings.yaml`, bo wymaga dodatkowego uprawnienia produktu i kazda
trasa zuzywa dodatkowy request. Przy 24 punktach Flow co 15 minut dzienny plan
wynosi 2304 requesty. Dwie trasy raz na godzine dodalyby 48 requestow, czyli
laczenie 2352.

Jednorazowy test tras:

```bash
python scripts/fetch_routes.py --force
```

Windows:

```powershell
.\.venv\Scripts\python.exe scripts\fetch_routes.py --force
```

Jesli TomTom zwroci blad autoryzacji, sprawdz w MyTomTom, czy klucz ma wlaczony produkt Routing API.

## Uruchomienie lokalne

Utworz srodowisko i zainstaluj zaleznosci:

```bash
python -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
```

Windows PowerShell:

```powershell
python -m venv .venv
.\.venv\Scripts\Activate.ps1
pip install -r requirements.txt
```

Pobranie jednego zestawu pomiarow:

```bash
python scripts/fetch_traffic.py
```

Wygenerowanie raportu dla dnia biezacego:

```bash
python scripts/make_daily_report.py
```

Wygenerowanie raportu dla wybranej daty:

```bash
python scripts/make_daily_report.py --date 2026-06-22
```

Eksport danych do CSV:

```bash
python scripts/export_csv.py --date 2026-06-22
```

Testy:

```bash
python -m pytest
```

## GitHub Actions

Workflow `hourly.yml` dziala jako watchdog co 5 minut wedlug harmonogramu `*/5 * * * *`, ale zapisuje dane do 15-minutowych slotow pomiarowych. Jesli slot, np. `06:30`, jest juz kompletny dla wszystkich punktow, kolejne uruchomienie nie odpytuje TomTom API i nie zuzywa limitu.

Przy 24 punktach pomiarowych i kompletnych slotach co 15 minut plan wynosi okolo 2304 zapytan dziennie, czyli ponizej limitu referencyjnego 2500 zapytan dziennie.

GitHub Actions moze uruchomic zaplanowany cykl z opoznieniem kilku minut, a sporadycznie moze pominac zaplanowany cykl. To jest wystarczajace do prototypu i obserwacji trendow, ale nie jest zegarem laboratoryjnym. Dlatego baza zapisuje dwa rodzaje czasu:

- `measurement_slot_local` / `scheduled_slot_local` - planowany slot badawczy, np. `06:30`;
- `timestamp_local` / `started_at_local` - faktyczny czas pobrania, np. `06:38`.

Do analiz godzinowych i raportow uzywany jest slot badawczy. Faktyczny czas zostaje w bazie jako informacja kontrolna. Jesli GitHub Actions nie uruchomi zadania przez dluzszy czas, brakujace sloty sa widoczne w pulpicie jako `Braki slotow`; takich luk nie nalezy ukrywac w analizie.

Po kazdym cyklu workflow generuje statyczny pulpit `reports/dashboard/index.html` oraz plik maszynowy `reports/dashboard/status.json`. Pulpit pokazuje liczbe requestow dzisiaj, zapas limitu, status ostatniego cyklu, ostatnie pomiary dla punktow i ostatnie uruchomienia skryptu.

Lokalny podglad pulpitu w przegladarce:

Najwygodniejsza lokalna appka kontrolna:

```text
control_panel.cmd
```

Otwiera panel pod adresem:

```text
http://127.0.0.1:8010/
```

W panelu mozna odswiezyc dane z GitHuba, otworzyc pulpit HTML, mape punktow, status JSON, raporty i GitHub Actions. Odswiezenie z GitHuba nie zuzywa limitu TomTom API.

Wersja konsolowa w PowerShellu:

```text
traffic_console.cmd
```

Najprosciej uruchom plik:

```text
start_dashboard.cmd
```

Ten plik najpierw pobiera najnowszy stan dashboardu i bazy z GitHuba, a potem uruchamia lokalny panel.

Jesli panel juz dziala i chcesz tylko odswiezyc stan badania na zadanie, uruchom:

```text
refresh_dashboard.cmd
```

Po odswiezeniu danych przeladuj karte z pulpitem w przegladarce.

Albo z PowerShella:

```powershell
.\.venv\Scripts\python.exe scripts\serve_dashboard.py --sync
```

Adres domyslny:

```text
http://127.0.0.1:8000/dashboard/
```

Mapa punktow bedzie wtedy dostepna pod:

```text
http://127.0.0.1:8000/maps/awp_points.html
```

Ten lokalny panel korzysta z danych, ktore sa aktualnie pobrane do folderu `reports`. Panel online z adresem WWW wymaga GitHub Pages albo innego hostingu statycznego.

Workflow `daily_report.yml` generuje raport dobowy raz dziennie i rowniez obsluguje `workflow_dispatch`. Dla uruchomienia recznego mozna podac date raportu w formacie `YYYY-MM-DD`; puste pole oznacza poprzedni dzien wzgledem strefy Europe/Warsaw.

W repozytorium GitHub dodaj sekret:

```text
TOMTOM_API_KEY
```

Oba workflow maja uprawnienie `contents: write`, aby commitowac zebrane dane i wygenerowane raporty do repozytorium. Dla wiekszego projektu badawczego lepszym miejscem na dane moze byc zewnetrzny storage albo baza poza repozytorium. Pushowanie pliku SQLite i wielu JSON-ow do Gita co 15 minut jest rozwiazaniem prototypowym, podatnym na konflikty i rozrost historii repozytorium.

## Kontrola pracy 24/7

Monitoring jest zaprojektowany tak, aby dzialal przez GitHub Actions nawet wtedy, gdy komputer lokalny jest wylaczony.

Docelowy tryb badawczy dla pracy 24/7 to jednak serwer VPS, bo GitHub Actions nie jest precyzyjnym zegarem pomiarowym. Gotowa instrukcja wdrozenia serwerowego jest w `deploy/SERVER.md`. GitHub moze wtedy zostac miejscem na kod, a serwer przejmuje pobieranie danych, baze SQLite, dashboard i backupy.

Serwer VPS moze takze wysylac raz dziennie raport email z zalacznikami Markdown, HTML i CSV. Funkcja jest opcjonalna, wymaga danych SMTP w pliku `.env` na serwerze i jest opisana w `deploy/SERVER.md`.

Serwer moze dodatkowo wysylac lokalne kopie bazy SQLite na Google Drive przez `rclone`. To opcjonalny backup poza VPS, opisany w `deploy/SERVER.md`.

Najwazniejsze ustawienia sa w `config/settings.yaml`:

```yaml
monitoring:
  enabled: true
  daily_request_soft_limit: 2400
```

Zatrzymanie monitoringu bez usuwania workflow:

```yaml
monitoring:
  enabled: false
```

Wznowienie:

```yaml
monitoring:
  enabled: true
```

Limit `daily_request_soft_limit` jest bezpiecznikiem. Jesli kolejny cykl mialby przekroczyc limit miekki, skrypt pominie pobieranie i zapisze status `skipped_limit` w tabeli `fetch_runs`.

Reczne zatrzymanie pojedynczego uruchomienia:

```text
GitHub -> Actions -> Traffic fetch every 15 minutes -> Cancel workflow
```

Reczne uruchomienie:

```text
GitHub -> Actions -> Traffic fetch every 15 minutes -> Run workflow
```

Do kontroli zuzycia API uzywaj jednoczesnie:

- `reports/dashboard/index.html`
- TomTom Developer Portal -> Analytics

## Struktura danych

Glowna tabela `measurements` w SQLite zawiera:

- `id`
- `timestamp_utc`
- `timestamp_local`
- `measurement_slot_utc`
- `measurement_slot_local`
- `point_id`
- `point_name`
- `direction`
- `latitude`
- `longitude`
- `current_speed`
- `free_flow_speed`
- `current_travel_time`
- `free_flow_travel_time`
- `confidence`
- `road_closure`
- `congestion_index`
- `delay_ratio`
- `delay_seconds`
- `raw_json`

Tabela `points` przechowuje konfiguracje punktow pomiarowych.

Tabela `routes` przechowuje konfiguracje tras odcinkowych.

Tabela `route_measurements` przechowuje pomiary z TomTom Routing API:

- `timestamp_utc`
- `timestamp_local`
- `measurement_slot_utc`
- `measurement_slot_local`
- `route_id`
- `route_name`
- `direction`
- `length_meters`
- `travel_time_seconds`
- `no_traffic_travel_time_seconds`
- `historic_traffic_travel_time_seconds`
- `live_traffic_travel_time_seconds`
- `traffic_delay_seconds`
- `average_speed_kmh`
- `free_flow_average_speed_kmh`
- `congestion_index`
- `delay_ratio`
- `delay_seconds`
- `raw_json`

Estymacje z punktow Flow nie sa trwale duplikowane w SQLite. Sa obliczane
odtwarzalnie podczas generowania dashboardu i raportu dobowego na podstawie
tabeli `measurements`.

Tabela `fetch_runs` przechowuje log cykli pobierania, w tym planowany slot (`scheduled_slot_local`), faktyczny start (`started_at_local`), liczbe requestow, liczbe sukcesow i bledow.

## Wskazniki

Projekt oblicza:

```text
congestion_index = current_speed / free_flow_speed
delay_ratio = current_travel_time / free_flow_travel_time
delay_seconds = current_travel_time - free_flow_travel_time
```

Interpretacja obejmuje kategorie:

- ruch plynny
- lekkie spowolnienie
- wyrazne spowolnienie
- silne przeciazenie
- brak danych lub niska wiarygodnosc

Progi interpretacyjne sa w `config/settings.yaml`.

Dla tras odcinkowych znaczenie jest analogiczne, ale liczone na czasie przejazdu calej trasy:

```text
delay_ratio = travel_time_seconds / no_traffic_travel_time_seconds
delay_seconds = traffic_delay_seconds
congestion_index = no_traffic_travel_time_seconds / travel_time_seconds
```

Estymacja odcinkowa laczy wiele punktow Flow w jeden wskaznik uzytkowego
opoznienia dla calego badanego fragmentu ulicy.

## Ograniczenia metodologiczne

Projekt nie mierzy bezposrednio natezenia ruchu w pojazdach na godzine. Projekt mierzy warunki ruchu, predkosc biezaca, predkosc swobodna, czas przejazdu, opoznienie oraz wskazniki przeciazenia. Sa to wskazniki zastepcze, ktore moga byc uzyte do analizy zmiennosci warunkow ruchu na odcinku ulicznym.

Dane z Flow Segment Data sa zalezne od dostepnosci i wiarygodnosci danych TomTom dla danego miejsca i momentu. Punkt pomiarowy jest przekazywany jako wspolrzedna, a API zwraca dane dla dopasowanego segmentu drogowego. Z tego powodu interpretacja wynikow powinna uwzgledniac mozliwe przesuniecie segmentu, zmiany organizacji ruchu, remonty, zdarzenia incydentalne oraz rozna jakosc danych w poszczegolnych porach dnia.

Estymowany czas przejazdu calego odcinka jest wskaznikiem pochodnym z predkosci
w punktach. Nie jest nawigacyjnym czasem przejazdu i moze nie obejmowac calego
oczekiwania na sygnalizacji lub rondach, jezeli nie zostalo ono odzwierciedlone
w predkosci segmentu Flow. Odleglosci sa przyblizane na podstawie wspolrzednych
punktow, a nie pelnej geometrii osi jezdni.

Role `corridor_inflow`, `corridor_outflow`, `side_inflow` i `side_outflow`
opisuja topologie punktu, a nie zmierzone natezenie. Flow Segment Data pozwala
obserwowac predkosc i pogorszenie warunkow na wlocie lub wylocie, ale nie
pozwala wiarygodnie wyliczyc liczby pojazdow wjezdzajacych i wyjezdzajacych.
Do bilansu doplywow i odplywow w pojazdach na godzine potrzebne bylyby petle
indukcyjne, kamery z detekcja, radary lub inne liczniki ruchu.

Jesli w godzinach szczytu punkty Flow nadal pokazuja stale `congestion_index = 1.0` i `delay_ratio = 1.0`, nie nalezy tego automatycznie traktowac jako dowodu braku korkow. Moze to oznaczac, ze Flow Segment Data ma za mala czulosc dla tych krotkich odcinkow. W takim przypadku bardziej wiarygodna dla badania bedzie analiza czasow przejazdu tras z Routing API albo uzupelnienie zrodla danych.
