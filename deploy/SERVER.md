# Wdrozenie na serwerze VPS

Ten tryb jest docelowy dla badania 24/7. GitHub zostaje miejscem na kod, ale serwer wykonuje pomiary, zapisuje baze i wystawia pulpit.

## Jaki serwer wybrac

Minimalnie wystarczy:

- Linux Ubuntu 24.04 LTS albo 22.04 LTS
- 1 vCPU
- 1-2 GB RAM
- 20 GB dysku
- staly publiczny adres IP

Rozsadnie wybrac 2 GB RAM, bo wykresy `matplotlib` i raporty HTML sa wtedy mniej kaprysne.

Polskie lub wygodne dla uzytkownika z Polski opcje:

- OVHcloud Polska - panel i rozliczenia po polsku/PLN, sensowny wybor na pierwszy VPS.
- nazwa.pl VPS - polski dostawca, zwykle prostszy panel, ale warto sprawdzic, czy dostajesz pelny dostep root/SSH.
- home.pl VPS - podobnie: wygodne rozliczenia, przed zakupem sprawdz pelny dostep SSH i mozliwosc instalacji Dockera.

Do tego projektu nie potrzebujesz serwera dedykowanego ani uslug zarzadzanych. Wystarczy zwykly VPS z Ubuntu.

## Bardzo wazne: GitHub i serwer jednoczesnie

Nie wylaczamy teraz GitHub Actions. Ale gdy uruchomisz serwer 24/7 i zostawisz GitHuba jako aktywnego zbieracza, zuzycie TomTom API sie podwoi.

Przy 24 punktach:

```text
GitHub: 24 x 96 = 2304 requesty/dobe
Serwer: 24 x 96 = 2304 requesty/dobe
Razem: 4608 requestow/dobe
```

To przekroczy darmowy limit. Dlatego plan migracji jest taki:

1. GitHub zostaje wlaczony podczas przygotowania serwera.
2. Na serwerze robisz test `--once`.
3. Potem robisz test 1-2 slotow.
4. Dopiero po potwierdzeniu, ze serwer dziala, wybierasz jedno aktywne zrodlo pobierania danych.

## Wariant A: Docker Compose

To najprostszy wariant na nowym VPS.

Na serwerze:

```bash
sudo apt update
sudo apt install -y git docker.io docker-compose-plugin
sudo systemctl enable --now docker
```

Pobierz repo:

```bash
sudo mkdir -p /opt
cd /opt
sudo git clone https://github.com/JaRu77/awp-traffic-monitor.git
sudo chown -R $USER:$USER /opt/awp-traffic-monitor
cd /opt/awp-traffic-monitor
```

Utworz plik `.env`:

```bash
nano .env
```

Wpisz:

```text
TOMTOM_API_KEY=tu_wklej_swoj_klucz
```

Start:

```bash
docker compose up -d --build
```

Logi schedulera:

```bash
docker compose logs -f scheduler
```

Logi dashboardu:

```bash
docker compose logs -f dashboard
```

Adres pulpitu:

```text
http://ADRES_IP_SERWERA:8000/dashboard/
```

Mapa:

```text
http://ADRES_IP_SERWERA:8000/maps/awp_points.html
```

Zatrzymanie:

```bash
docker compose down
```

Jednorazowy backup bazy:

```bash
docker compose run --rm scheduler python scripts/backup_sqlite.py --keep 7
```

## Wariant B: systemd bez Dockera

Ten wariant jest bardziej klasyczny i bardzo stabilny.

Instalacja pakietow:

```bash
sudo apt update
sudo apt install -y git python3 python3-venv python3-pip
```

Uzytkownik systemowy:

```bash
sudo useradd --system --create-home --shell /bin/bash awp
```

Repo:

```bash
sudo mkdir -p /opt
cd /opt
sudo git clone https://github.com/JaRu77/awp-traffic-monitor.git
sudo chown -R awp:awp /opt/awp-traffic-monitor
cd /opt/awp-traffic-monitor
```

Srodowisko Python:

```bash
sudo -u awp python3 -m venv .venv
sudo -u awp .venv/bin/python -m pip install --upgrade pip
sudo -u awp .venv/bin/python -m pip install -r requirements.txt
```

Plik `.env`:

```bash
sudo -u awp nano /opt/awp-traffic-monitor/.env
```

Zawartosc:

```text
TOMTOM_API_KEY=tu_wklej_swoj_klucz
```

Test bez petli:

```bash
sudo -u awp /opt/awp-traffic-monitor/.venv/bin/python /opt/awp-traffic-monitor/scripts/server_scheduler.py --once --skip-routes
```

Uwaga: ten test pobiera dane z TomTom i zuzywa requesty.

Instalacja uslug:

```bash
sudo cp /opt/awp-traffic-monitor/deploy/systemd/*.service /etc/systemd/system/
sudo cp /opt/awp-traffic-monitor/deploy/systemd/*.timer /etc/systemd/system/
sudo systemctl daemon-reload
sudo systemctl enable --now awp-traffic-dashboard.service
sudo systemctl enable --now awp-traffic-scheduler.service
sudo systemctl enable --now awp-traffic-backup.timer
```

Status:

```bash
systemctl status awp-traffic-scheduler.service
systemctl status awp-traffic-dashboard.service
systemctl list-timers | grep awp
```

Logi:

```bash
journalctl -u awp-traffic-scheduler.service -f
journalctl -u awp-traffic-dashboard.service -f
```

Restart po zmianach:

```bash
sudo systemctl restart awp-traffic-scheduler.service
sudo systemctl restart awp-traffic-dashboard.service
```

## Routing API na serwerze

Domyslnie `routing.enabled` jest `false`, bo dodatkowe trasy moga wyczerpac limit TomTom.

Jednorazowy test tras:

```bash
python scripts/fetch_routes.py --force
```

Pelne wlaczenie tras:

```yaml
routing:
  enabled: true
```

Przy 24 punktach Flow i 2 trasach co 15 minut plan dzienny to okolo 2496 requestow. To jest bardzo blisko 2500, a przy limicie miekkim `2400` system bedzie blokowal koncowke dnia. Lepsza konfiguracja badawcza to np. mniej punktow Flow plus trasy odcinkowe.

## Raport email raz dziennie

Serwer moze wysylac dobowy raport mailem. Funkcja jest opcjonalna i domyslnie wylaczona.

Do pliku `/opt/awp-traffic-monitor/.env` dopisz dane SMTP:

```text
EMAIL_ENABLED=true
SMTP_HOST=smtp.example.com
SMTP_PORT=587
SMTP_USERNAME=login_smtp
SMTP_PASSWORD=haslo_smtp_lub_haslo_aplikacji
SMTP_USE_TLS=true
SMTP_USE_SSL=false
EMAIL_FROM=awp-monitor@example.com
EMAIL_TO=adres_docelowy@example.com
```

Uwagi:

- Gmail zwykle wymaga hasla aplikacji, a nie zwyklego hasla do konta.
- `EMAIL_TO` moze zawierac kilka adresow oddzielonych przecinkami.
- Sekrety SMTP trzymamy tylko w `.env` na serwerze, nigdy w repozytorium.

Test reczny:

```bash
cd /opt/awp-traffic-monitor
.venv/bin/python scripts/send_daily_email.py --date YYYY-MM-DD --force
```

Instalacja uslugi email przez systemd:

```bash
sudo cp /opt/awp-traffic-monitor/deploy/systemd/awp-traffic-email.service /etc/systemd/system/
sudo cp /opt/awp-traffic-monitor/deploy/systemd/awp-traffic-email.timer /etc/systemd/system/
sudo sed -i 's/User=awp/User=ubuntu/g; s/Group=awp/Group=ubuntu/g' /etc/systemd/system/awp-traffic-email.service
sudo systemctl daemon-reload
sudo systemctl enable --now awp-traffic-email.timer
systemctl list-timers --no-pager | grep awp
```

Logi wysylki:

```bash
journalctl -u awp-traffic-email.service --no-pager -n 80
```

## Backup zdalny do Google Drive

Najprostszy wariant zdalnej kopii to `rclone`. Serwer robi zwykly lokalny backup SQLite, a potem wysyla pliki `awp_traffic_*.sqlite` do katalogu na Google Drive.

Instalacja rclone na VPS:

```bash
sudo apt update
sudo apt install -y rclone
```

Konfiguracja Google Drive:

```bash
rclone config
```

W kreatorze wybierz:

```text
n
name> gdrive
Storage> drive
client_id> [Enter]
client_secret> [Enter]
scope> drive.file
service_account_file> [Enter]
Edit advanced config? n
Use auto config? n
```

Rclone pokaze dlugi link. Skopiuj go do przegladarki na swoim komputerze, zaloguj sie do Google, zatwierdz dostep i wklej kod albo token z powrotem do terminala VPS. Przy pytaniu o shared drive zwykle wybierz `n`, a na koncu `y`, zeby zapisac konfiguracje.

Test polaczenia:

```bash
rclone lsd gdrive:
rclone mkdir gdrive:AWP-Traffic-Backups/backups
```

Do pliku `/opt/awp-traffic-monitor/.env` dopisz:

```text
REMOTE_BACKUP_ENABLED=true
RCLONE_REMOTE_PATH=gdrive:AWP-Traffic-Backups/backups
REMOTE_BACKUP_KEEP_DAYS=120
```

Test reczny:

```bash
cd /opt/awp-traffic-monitor
.venv/bin/python scripts/remote_backup.py --force
```

Instalacja automatycznego backupu zdalnego:

```bash
sudo cp /opt/awp-traffic-monitor/deploy/systemd/awp-traffic-remote-backup.service /etc/systemd/system/
sudo cp /opt/awp-traffic-monitor/deploy/systemd/awp-traffic-remote-backup.timer /etc/systemd/system/
sudo sed -i 's/User=awp/User=ubuntu/g; s/Group=awp/Group=ubuntu/g' /etc/systemd/system/awp-traffic-remote-backup.service
sudo systemctl daemon-reload
sudo systemctl enable --now awp-traffic-remote-backup.timer
systemctl list-timers --no-pager | grep awp
```

Logi backupu zdalnego:

```bash
journalctl -u awp-traffic-remote-backup.service --no-pager -n 80
```

Uwaga: zdalny backup nie zastepuje lokalnego backupu. To druga kopia poza VPS, przydatna na wypadek awarii dysku, usuniecia serwera albo pomylki administracyjnej.

## Bezpieczenstwo

Na start najprosciej otworzyc port 8000 tylko dla swojego IP albo przez zapore serwera. Publiczny pulpit bez hasla nie powinien wisiec stale w internecie.

Minimalna zapora:

```bash
sudo ufw allow OpenSSH
sudo ufw allow 8000/tcp
sudo ufw enable
```

Docelowo lepszy jest Nginx z haslem lub VPN, ale to mozna zrobic po uruchomieniu pierwszego stabilnego pomiaru.
